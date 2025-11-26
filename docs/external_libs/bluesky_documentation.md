Title: Creating a post | Bluesky

URL Source: https://docs.bsky.app/docs/tutorials/creating-a-post

Markdown Content:
Bluesky posts are repository records with the [Lexicon type](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/post.json)`app.bsky.feed.post`.

Here is what a basic post record should look like, as a JSON object:

`{  "$type": "app.bsky.feed.post",  "text": "Hello World!",  "createdAt": "2023-08-07T05:31:12.156888Z"}`

Each post requires these fields: `text` and `createdAt` (a timestamp).

*   Typescript
*   Python

This script below will create a simple post with just a text field and a timestamp.

`import { BskyAgent } from '@atproto/api'const agent = new BskyAgent({  service: 'https://bsky.social'})await agent.login({  identifier: 'handle.example.com',  password: 'hunter2'})await agent.post({  text: 'Hello world! I posted this via the API.',  createdAt: new Date().toISOString()})`

It will respond with the `at://` URI of the post and a content-hash of the post (the `cid`).

`{  "uri": "at://did:plc:u5cwb2mwiv2bfq53cjufe6yn/app.bsky.feed.post/3k4duaz5vfs2b",  "cid": "bafyreibjifzpqj6o6wcq3hejh7y4z4z2vmiklkvykc57tw3pcbx3kxifpm"}`

Setting the language[​](https://docs.bsky.app/docs/tutorials/creating-a-post#setting-the-language "Direct link to Setting the language")
----------------------------------------------------------------------------------------------------------------------------------------

Setting the post's language helps custom feeds or other services filter and parse posts.

*   Typescript
*   Python

This snippet sets the `text` and `langs` value of a post to be Thai and English.

`// an example with Thai and English (US) languagesawait agent.post({  text: 'สวัสดีชาวโลก!\nHello World!',  langs: ["th", "en-US"],  createdAt: new Date().toISOString()})`

The resulting post record object looks like:

`{  "$type": "app.bsky.feed.post",  "text": "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e0a\u0e32\u0e27\u0e42\u0e25\u0e01!\\nHello World!",  "createdAt": "2023-08-07T05:44:04.395087Z",  "langs": [ "th", "en-US" ]}`

You can include multiple values in the array if there are multiple languages present in the post.

Mentions and Links[​](https://docs.bsky.app/docs/tutorials/creating-a-post#mentions-and-links "Direct link to Mentions and Links")
----------------------------------------------------------------------------------------------------------------------------------

Mentions and links are annotations that point into the text of a post.

*   Typescript
*   Python

Use the RichText API to detect links and mentions.

`import { RichText } from '@atproto/api'// creating richtextconst rt = new RichText({  text: '✨ example mentioning @atproto.com to share the URL 👨‍❤️‍👨 https://en.wikipedia.org/wiki/CBOR.',})await rt.detectFacets(agent) // automatically detects mentions and linksconst postRecord = {  $type: 'app.bsky.feed.post',  text: rt.text,  facets: rt.facets,  createdAt: new Date().toISOString(),}// rendering as markdownlet markdown = ''for (const segment of rt.segments()) {  if (segment.isLink()) {    markdown += `[${segment.text}](${segment.link?.uri})`  } else if (segment.isMention()) {    markdown += `[${segment.text}](https://my-bsky-app.com/user/${segment.mention?.did})`  } else {    markdown += segment.text  }}// calculating string lengthsconst rt2 = new RichText({ text: 'Hello' })console.log(rt2.length) // => 5console.log(rt2.graphemeLength) // => 5const rt3 = new RichText({ text: '👨‍👩‍👧‍👧' })console.log(rt3.length) // => 25console.log(rt3.graphemeLength) // => 1`

Replies, quote posts, and embeds[​](https://docs.bsky.app/docs/tutorials/creating-a-post#replies-quote-posts-and-embeds "Direct link to Replies, quote posts, and embeds")
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

Replies and quote posts contain **strong references** to other records. A strong reference is a combination of:

*   **AT URI:** indicates the repository DID, collection, and record key
*   **CID:** the hash of the record itself

Posts can have several types of embeds: record embeds, images and external embeds (like link/webpage cards, which is the preview that shows up when you post a URL).

A complete reply post record looks like:

`{  "$type": "app.bsky.feed.post",  "text": "example of a reply",  "createdAt": "2023-08-07T05:49:40.501974Z",  "reply": {    "root": {      "uri": "at://did:plc:u5cwb2mwiv2bfq53cjufe6yn/app.bsky.feed.post/3k43tv4rft22g",      "cid": "bafyreig2fjxi3rptqdgylg7e5hmjl6mcke7rn2b6cugzlqq3i4zu6rq52q"    },    "parent": {      "uri": "at://did:plc:u5cwb2mwiv2bfq53cjufe6yn/app.bsky.feed.post/3k43tv4rft22g",      "cid": "bafyreig2fjxi3rptqdgylg7e5hmjl6mcke7rn2b6cugzlqq3i4zu6rq52q"    }  }}`

Since threads of replies can get pretty long, reply posts need to reference both the immediate parent post and the original root post of the thread.

*   Typescript
*   Python

Here's what this should look like when posting:

`await agent.post({  text: 'lol!',  reply: {    root: {      uri: threadRootPost.uri,      cid: threadRootPost.cid,    },    parent: {      uri: postReplyingTo.uri,      cid: postReplyingTo.cid,    }  },  createdAt: new Date().toISOString()})`

### Quote posts[​](https://docs.bsky.app/docs/tutorials/creating-a-post#quote-posts "Direct link to Quote posts")

A quote post embeds a reference to another post record. A complete quote post record would look like:

`{  "$type": "app.bsky.feed.post",  "text": "example of a quote-post",  "createdAt": "2023-08-07T05:49:39.417839Z",  "embed": {    "$type": "app.bsky.embed.record",    "record": {      "uri": "at://did:plc:u5cwb2mwiv2bfq53cjufe6yn/app.bsky.feed.post/3k44deefqdk2g",      "cid": "bafyreiecx6dujwoeqpdzl27w67z4h46hyklk3an4i4cvvmioaqb2qbyo5u"    }  }}`

The record embedded here is the post that's getting quoted. The post record type is `app.bsky.feed.post`, but you can also embed other record types in a post, like lists (`app.bsky.graph.list`) and feed generators (`app.bsky.feed.generator`).

### Images embeds[​](https://docs.bsky.app/docs/tutorials/creating-a-post#images-embeds "Direct link to Images embeds")

Images are also embedded objects in a post.

*   Typescript
*   Python

Here's an example script of posting an image:

`const image = 'data:image/png;base64,...'const { data } = await agent.uploadBlob(convertDataURIToUint8Array(image), {  encoding,})await agent.post({  text: 'I love my cat',  embed: {    $type: 'app.bsky.embed.images',    images: [      // can be an array up to 4 values      {        alt: 'My cat mittens', // the alt text        image: data.blob,        aspectRatio: {          // a hint to clients          width: 1000,          height: 500        }    }],  },  createdAt: new Date().toISOString()})`

A complete post record, containing two images, would look something like:

`{  "$type": "app.bsky.feed.post",  "text": "example post with multiple images attached",  "createdAt": "2023-08-07T05:49:35.422015Z",  "embed": {    "$type": "app.bsky.embed.images",    "images": [      {        "alt": "brief alt text description of the first image",        "image": {          "$type": "blob",          "ref": {            "$link": "bafkreibabalobzn6cd366ukcsjycp4yymjymgfxcv6xczmlgpemzkz3cfa"          },          "mimeType": "image/webp",          "size": 760898        }      },      {        "alt": "brief alt text description of the second image",        "image": {          "$type": "blob",          "ref": {            "$link": "bafkreif3fouono2i3fmm5moqypwskh3yjtp7snd5hfq5pr453oggygyrte"          },          "mimeType": "image/png",          "size": 13208        }      }    ]  }}`

Each post contains up to four images, and each image can have its own alt text and is limited to 1,000,000 bytes in size. Image files are _referenced_ by posts, but are not actually _included_ in the post (eg, using `bytes` with base64 encoding). The image files are first uploaded as "blobs" using `com.atproto.repo.uploadBlob`, which returns a `blob` metadata object, which is then embedded in the post record itself.

It's strongly recommended best practice to strip image metadata before uploading. The server (PDS) may be more strict about blocking upload of such metadata by default in the future, but it is currently the responsibility of clients (and apps) to sanitize files before upload today.

### Website card embeds[​](https://docs.bsky.app/docs/tutorials/creating-a-post#website-card-embeds "Direct link to Website card embeds")

A website card embed, often called a "social card," is the rendered preview of a website link. A complete post record with an external embed, including image thumbnail blob, looks like:

`{  "$type": "app.bsky.feed.post",  "text": "post which embeds an external URL as a card",  "createdAt": "2023-08-07T05:46:14.423045Z",  "embed": {    "$type": "app.bsky.embed.external",    "external": {      "uri": "https://bsky.app",      "title": "Bluesky Social",      "description": "See what's next.",      "thumb": {        "$type": "blob",        "ref": {          "$link": "bafkreiash5eihfku2jg4skhyh5kes7j5d5fd6xxloaytdywcvb3r3zrzhu"        },        "mimeType": "image/png",        "size": 23527      }    }  }}`

*   Typescript
*   Python

Here's an example of embedding a website card:

`const thumbnail = 'data:image/png;base64,...'const { data } = await agent.uploadBlob(convertDataURIToUint8Array(thumbnail), {  encoding,})await agent.post({  text: 'check out this website!',  embed: {    $type: 'app.bsky.embed.external',    external: {      uri: 'https://bsky.app',      title: 'Bluesky Social',      description: 'See what\'s next.',      thumb: data.blob    }  },  createdAt: new Date().toISOString()})`

On Bluesky, each client fetches and embeds this card metadata, including blob upload if needed. Embedding the card content in the record ensures that it appears consistently to everyone and reduces waves of automated traffic being sent to the referenced website, but it does require some extra work by the client.