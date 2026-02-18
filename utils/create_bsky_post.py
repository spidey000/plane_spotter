#!/usr/bin/env python3

"""
Script demonstrating how to create posts using the Bluesky API, covering most of the features and embed options.

To run this Python script, you need the 'requests' and 'bs4' (BeautifulSoup) packages installed.
"""

import re
import os
import sys
import json
import argparse
import time
from typing import Dict, List
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from monitoring.api_usage import record_api_event


def _tracked_request(method: str, url: str, **kwargs):
    endpoint = f"{method.upper()} {urlparse(url).path or '/'}"
    started = time.perf_counter()
    try:
        response = requests.request(method=method.upper(), url=url, **kwargs)
        duration_ms = (time.perf_counter() - started) * 1000.0
        record_api_event(
            provider="bluesky",
            endpoint=endpoint,
            method=method.upper(),
            status_code=response.status_code,
            success=200 <= response.status_code < 300,
            duration_ms=duration_ms,
            estimated_cost_usd=0.0,
        )
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        record_api_event(
            provider="bluesky",
            endpoint=endpoint,
            method=method.upper(),
            status_code=None,
            success=False,
            duration_ms=duration_ms,
            estimated_cost_usd=0.0,
            error=str(exc),
        )
        raise


def _tracked_get(url: str, **kwargs):
    return _tracked_request("GET", url, **kwargs)


def _tracked_post(url: str, **kwargs):
    return _tracked_request("POST", url, **kwargs)


def bsky_login_session(pds_url: str, handle: str, password: str) -> Dict:
    resp = _tracked_post(
        pds_url + "/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
    )
    resp.raise_for_status()
    return resp.json()


def parse_mentions(text: str) -> List[Dict]:
    spans = []
    # regex based on: https://atproto.com/specs/handle#handle-identifier-syntax
    mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(mention_regex, text_bytes):
        spans.append(
            {
                "start": m.start(1),
                "end": m.end(1),
                "handle": m.group(1)[1:].decode("UTF-8"),
            }
        )
    return spans


def test_parse_mentions():
    assert parse_mentions("prefix @handle.example.com @handle.com suffix") == [
        {"start": 7, "end": 26, "handle": "handle.example.com"},
        {"start": 27, "end": 38, "handle": "handle.com"},
    ]
    assert parse_mentions("handle.example.com") == []
    assert parse_mentions("@bare") == []
    assert parse_mentions("💩💩💩 @handle.example.com") == [
        {"start": 13, "end": 32, "handle": "handle.example.com"}
    ]
    assert parse_mentions("email@example.com") == []
    assert parse_mentions("cc:@example.com") == [
        {"start": 3, "end": 15, "handle": "example.com"}
    ]


def parse_urls(text: str) -> List[Dict]:
    spans = []
    # partial/naive URL regex based on: https://stackoverflow.com/a/3809435
    # tweaked to disallow some training punctuation
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(url_regex, text_bytes):
        spans.append(
            {
                "start": m.start(1),
                "end": m.end(1),
                "url": m.group(1).decode("UTF-8"),
            }
        )
    return spans


def test_parse_urls():
    assert parse_urls(
        "prefix https://example.com/index.html http://bsky.app suffix"
    ) == [
        {"start": 7, "end": 37, "url": "https://example.com/index.html"},
        {"start": 38, "end": 53, "url": "http://bsky.app"},
    ]
    assert parse_urls("example.com") == []
    assert parse_urls("💩💩💩 http://bsky.app") == [
        {"start": 13, "end": 28, "url": "http://bsky.app"}
    ]
    assert parse_urls("runonhttp://blah.comcontinuesafter") == []
    assert parse_urls("ref [https://bsky.app]") == [
        {"start": 5, "end": 21, "url": "https://bsky.app"}
    ]
    # note: a better regex would not mangle these:
    assert parse_urls("ref (https://bsky.app/)") == [
        {"start": 5, "end": 22, "url": "https://bsky.app/"}
    ]
    assert parse_urls("ends https://bsky.app. what else?") == [
        {"start": 5, "end": 21, "url": "https://bsky.app"}
    ]


def parse_facets(pds_url: str, text: str) -> List[Dict]:
    """
    parses post text and returns a list of app.bsky.richtext.facet objects for any mentions (@handle.example.com) or URLs (https://example.com)

    indexing must work with UTF-8 encoded bytestring offsets, not regular unicode string offsets, to match Bluesky API expectations
    """
    facets = []
    for m in parse_mentions(text):
        resp = _tracked_get(
            pds_url + "/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": m["handle"]},
        )
        # if handle couldn't be resolved, just skip it! will be text in the post
        if resp.status_code == 400:
            continue
        did = resp.json()["did"]
        facets.append(
            {
                "index": {
                    "byteStart": m["start"],
                    "byteEnd": m["end"],
                },
                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
            }
        )
    for u in parse_urls(text):
        facets.append(
            {
                "index": {
                    "byteStart": u["start"],
                    "byteEnd": u["end"],
                },
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        # NOTE: URI ("I") not URL ("L")
                        "uri": u["url"],
                    }
                ],
            }
        )
    return facets


def parse_uri(uri: str) -> Dict:
    if uri.startswith("at://"):
        repo, collection, rkey = uri.split("/")[2:5]
        return {"repo": repo, "collection": collection, "rkey": rkey}
    elif uri.startswith("https://bsky.app/"):
        repo, collection, rkey = uri.split("/")[4:7]
        if collection == "post":
            collection = "app.bsky.feed.post"
        elif collection == "lists":
            collection = "app.bsky.graph.list"
        elif collection == "feed":
            collection = "app.bsky.feed.generator"
        return {"repo": repo, "collection": collection, "rkey": rkey}
    else:
        raise Exception("unhandled URI format: " + uri)


def get_reply_refs(pds_url: str, parent_uri: str) -> Dict:
    uri_parts = parse_uri(parent_uri)
    resp = _tracked_get(
        pds_url + "/xrpc/com.atproto.repo.getRecord",
        params=uri_parts,
    )
    resp.raise_for_status()
    parent = resp.json()
    root = parent
    parent_reply = parent["value"].get("reply")
    if parent_reply is not None:
        root_uri = parent_reply["root"]["uri"]
        root_repo, root_collection, root_rkey = root_uri.split("/")[2:5]
        resp = _tracked_get(
            pds_url + "/xrpc/com.atproto.repo.getRecord",
            params={
                "repo": root_repo,
                "collection": root_collection,
                "rkey": root_rkey,
            },
        )
        resp.raise_for_status()
        root = resp.json()

    return {
        "root": {
            "uri": root["uri"],
            "cid": root["cid"],
        },
        "parent": {
            "uri": parent["uri"],
            "cid": parent["cid"],
        },
    }


def upload_file(pds_url, access_token, filename, img_bytes) -> Dict:
    suffix = filename.split(".")[-1].lower()
    mimetype = "application/octet-stream"
    if suffix in ["png"]:
        mimetype = "image/png"
    elif suffix in ["jpeg", "jpg"]:
        mimetype = "image/jpeg"
    elif suffix in ["webp"]:
        mimetype = "image/webp"

    # WARNING: a non-naive implementation would strip EXIF metadata from JPEG files here by default
    resp = _tracked_post(
        pds_url + "/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Content-Type": mimetype,
            "Authorization": "Bearer " + access_token,
        },
        data=img_bytes,
    )
    resp.raise_for_status()
    return resp.json()["blob"]


def upload_images(
    pds_url: str, access_token: str, image_paths: List[str], alt_text: str
) -> Dict:
    images = []
    for ip in image_paths:
        with open(ip, "rb") as f:
            img_bytes = f.read()
        # this size limit specified in the app.bsky.embed.images lexicon
        if len(img_bytes) > 1000000:
            raise Exception(
                f"image file size too large. 1000000 bytes maximum, got: {len(img_bytes)}"
            )
        blob = upload_file(pds_url, access_token, ip, img_bytes)
        images.append({"alt": alt_text or "", "image": blob})
    return {
        "$type": "app.bsky.embed.images",
        "images": images,
    }


def fetch_embed_url_card(pds_url: str, access_token: str, url: str) -> Dict:
    # the required fields for an embed card
    card = {
        "uri": url,
        "title": "",
        "description": "",
    }

    # fetch the HTML
    resp = _tracked_get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title_tag = soup.find("meta", property="og:title")
    if title_tag:
        card["title"] = title_tag["content"]

    description_tag = soup.find("meta", property="og:description")
    if description_tag:
        card["description"] = description_tag["content"]

    image_tag = soup.find("meta", property="og:image")
    if image_tag:
        img_url = image_tag["content"]
        if "://" not in img_url:
            img_url = url + img_url
        resp = _tracked_get(img_url)
        resp.raise_for_status()
        card["thumb"] = upload_file(pds_url, access_token, img_url, resp.content)

    return {
        "$type": "app.bsky.embed.external",
        "external": card,
    }


def get_embed_ref(pds_url: str, ref_uri: str) -> Dict:
    uri_parts = parse_uri(ref_uri)
    resp = _tracked_get(
        pds_url + "/xrpc/com.atproto.repo.getRecord",
        params=uri_parts,
    )
    #print(resp.json())
    resp.raise_for_status()
    record = resp.json()

    return {
        "$type": "app.bsky.embed.record",
        "record": {
            "uri": record["uri"],
            "cid": record["cid"],
        },
    }


def create_post(args):
    session = bsky_login_session(args.pds_url, args.handle, args.password)

    # trailing "Z" is preferred over "+00:00"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # these are the required fields which every post must include
    post = {
        "$type": "app.bsky.feed.post",
        "text": args.text,
        "createdAt": now,
    }

    # indicate included languages (optional)
    if args.lang:
        post["langs"] = args.lang

    # parse out mentions and URLs as "facets"
    parsed_facets = []
    if len(args.text) > 0:
        parsed_facets = parse_facets(args.pds_url, post["text"])
    extra_facets = getattr(args, "extra_facets", None)
    combined_facets = []
    if parsed_facets:
        combined_facets.extend(parsed_facets)
    if extra_facets:
        combined_facets.extend(extra_facets)
    if combined_facets:
        post["facets"] = combined_facets

    # if this is a reply, get references to the parent and root
    if args.reply_to:
        post["reply"] = get_reply_refs(args.pds_url, args.reply_to)

    if args.image:
        post["embed"] = upload_images(
            args.pds_url, session["accessJwt"], args.image, args.alt_text
        )
    elif args.embed_url:
        post["embed"] = fetch_embed_url_card(
            args.pds_url, session["accessJwt"], args.embed_url
        )
    elif args.embed_ref:
        post["embed"] = get_embed_ref(args.pds_url, args.embed_ref)

    #print("creating post:", file=sys.stderr)
    #print(json.dumps(post, indent=2), file=sys.stderr)

    resp = _tracked_post(
        args.pds_url + "/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": "Bearer " + session["accessJwt"]},
        json={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": post,
        },
    )
    #print("createRecord response:", file=sys.stderr)
    #print(json.dumps(resp.json(), indent=2))
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="bsky.app post upload example script")
    parser.add_argument(
        "--pds-url", default=os.environ.get("ATP_PDS_HOST") or "https://bsky.social"
    )
    parser.add_argument("--handle", default=os.environ.get("ATP_AUTH_HANDLE"))
    parser.add_argument("--password", default=os.environ.get("ATP_AUTH_PASSWORD"))
    parser.add_argument("text", default="")
    parser.add_argument("--image", action="append")
    parser.add_argument("--alt-text")
    parser.add_argument("--lang", action="append")
    parser.add_argument("--reply-to")
    parser.add_argument("--embed-url")
    parser.add_argument("--embed-ref")
    args = parser.parse_args()
    if not (args.handle and args.password):
        #print("both handle and password are required", file=sys.stderr)
        sys.exit(-1)
    if args.image and len(args.image) > 4:
        #print("at most 4 images per post", file=sys.stderr)
        sys.exit(-1)
    create_post(args)


if __name__ == "__main__":
    main()
