from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.image_finder import (  # noqa: E402
    clear_image_finder_runtime_state,
    get_first_image_url_jp,
    get_first_image_url_pp,
)


JETPHOTOS_URL = "https://www.jetphotos.com/showphotos.php"
JETPHOTOS_PARAMS = {
    "aircraft": "all",
    "airline": "all",
    "category": "all",
    "country-location": "all",
    "genre": "all",
    "keywords-contain": "1",
    "keywords-type": "all",
    "photo-year": "all",
    "photographer-group": "all",
    "search-type": "Advanced",
    "sort-order": "0",
    "page": "1",
}

JETPHOTOS_IMAGE_SELECTORS = [
    "img.result__photo",
    "a.result__photoLink img",
    "img.result-photo__img",
    "img[src*='jetphotos']",
]

PLANESPOTTERS_IMAGE_SELECTORS = [
    "img.photo_card__photo",
    "div.photo_card img",
    "img[data-photo-id]",
    "img[src*='plnspttrs']",
    "img[src*='planespotters']",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_text(value: str, limit: int = 1500) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def _extract_json(payload: str) -> dict[str, Any] | None:
    stripped = payload.strip()
    if not stripped:
        return None

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    for line in reversed(lines):
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    return None


def _build_jetphotos_url(registration: str) -> str:
    params = dict(JETPHOTOS_PARAMS)
    params["keywords"] = registration
    query = urlencode(params)
    return f"{JETPHOTOS_URL}?{query}"


def _build_planespotters_url(registration: str) -> str:
    return f"https://www.planespotters.net/photos/reg/{registration}?sort=latest"


def _registration_insertion_strategy(provider: str, registration: str) -> dict[str, Any]:
    if provider == "jetphotos":
        return {
            "provider": provider,
            "type": "query_param",
            "base_url": JETPHOTOS_URL,
            "parameter": "keywords",
            "example_value": registration,
            "example_url": _build_jetphotos_url(registration),
            "note": "Set aircraft registration in query string parameter 'keywords'.",
        }

    return {
        "provider": provider,
        "type": "path_segment",
        "base_url": "https://www.planespotters.net/photos/reg/{registration}",
        "parameter": "registration_path",
        "example_value": registration,
        "example_url": _build_planespotters_url(registration),
        "note": "Set aircraft registration in URL path segment '/photos/reg/{registration}'.",
    }


def _image_extraction_strategy(provider: str) -> dict[str, Any]:
    selectors = JETPHOTOS_IMAGE_SELECTORS if provider == "jetphotos" else PLANESPOTTERS_IMAGE_SELECTORS
    return {
        "provider": provider,
        "selectors": selectors,
        "attributes_order": ["src", "data-src", "data-lazy-src", "srcset"],
        "normalization": ["// -> https://", "relative path -> absolute URL"],
    }


def _extract_eval_result(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    current: Any = payload
    if isinstance(current.get("data"), dict):
        current = current["data"]
    if isinstance(current, dict) and isinstance(current.get("result"), dict):
        current = current["result"]
    return current if isinstance(current, dict) else {}


def _probe_eval_script(provider: str) -> str:
    selectors = JETPHOTOS_IMAGE_SELECTORS if provider == "jetphotos" else PLANESPOTTERS_IMAGE_SELECTORS

    selectors_json = json.dumps(selectors)
    return (
        "(() => {"
        f"const selectors = {selectors_json};"
        "const candidates = [];"
        "const counts = {};"
        "const add = (raw) => {"
        "  if (!raw) return;"
        "  let url = String(raw).trim();"
        "  if (!url) return;"
        "  if (url.startsWith('//')) url = 'https:' + url;"
        "  else if (url.startsWith('/')) url = location.origin + url;"
        "  else if (!url.startsWith('http')) url = location.origin + '/' + url.replace(/^\\/+/, '');"
        "  if (!/^https?:\\/\\//.test(url)) return;"
        "  candidates.push(url);"
        "};"
        "for (const selector of selectors) {"
        "  const elements = Array.from(document.querySelectorAll(selector));"
        "  counts[selector] = elements.length;"
        "  for (const element of elements.slice(0, 8)) {"
        "    add(element.getAttribute('src'));"
        "    add(element.getAttribute('data-src'));"
        "    add(element.getAttribute('data-lazy-src'));"
        "    const srcset = element.getAttribute('srcset');"
        "    if (srcset) {"
        "      for (const part of srcset.split(',')) {"
        "        const pieces = part.trim().split(/\\s+/);"
        "        if (pieces.length > 0) add(pieces[0]);"
        "      }"
        "    }"
        "  }"
        "}"
        "const bodyText = (document.body && document.body.innerText ? document.body.innerText : '').toLowerCase();"
        "const challengeMarkers = ['captcha', 'verify you are human', 'challenge-platform', 'cloudflare', 'access denied'];"
        "const detectedChallenges = challengeMarkers.filter((marker) => bodyText.includes(marker));"
        "const unique = Array.from(new Set(candidates));"
        "const forms = Array.from(document.querySelectorAll('form')).map((form, index) => ({"
        "  index,"
        "  action: form.getAttribute('action') || '',"
        "  method: form.getAttribute('method') || '',"
        "  input_names: Array.from(form.querySelectorAll('input,select,textarea'))"
        "    .map((el) => el.getAttribute('name') || el.getAttribute('id') || '')"
        "    .filter(Boolean)"
        "    .slice(0, 40)"
        "}));"
        "const registrationFields = Array.from(document.querySelectorAll('input,select,textarea'))"
        "  .map((el) => ({"
        "    tag: el.tagName.toLowerCase(),"
        "    type: el.getAttribute('type') || '',"
        "    name: el.getAttribute('name') || '',"
        "    id: el.id || '',"
        "    placeholder: el.getAttribute('placeholder') || ''"
        "  }))"
        "  .filter((item) => (item.name + ' ' + item.id + ' ' + item.placeholder).toLowerCase().match(/reg|keyword|search|tail|serial|aircraft/));"
        "return {"
        "  title: document.title,"
        "  current_url: location.href,"
        "  selector_counts: counts,"
        "  candidate_urls: unique.slice(0, 20),"
        "  candidate_count: unique.length,"
        "  challenge_markers: detectedChallenges,"
        "  forms_count: forms.length,"
        "  forms: forms.slice(0, 8),"
        "  candidate_registration_fields: registrationFields.slice(0, 20)"
        "};"
        "})()"
    )


@dataclass
class StepResult:
    command: str
    ok: bool
    return_code: int
    elapsed_ms: float
    stdout: str
    stderr: str
    parsed_json: dict[str, Any] | None


def _run_command(args: list[str], *, timeout_seconds: int) -> StepResult:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        parsed = _extract_json(stdout)
        ok = proc.returncode == 0
        return StepResult(
            command=shlex.join(args),
            ok=ok,
            return_code=proc.returncode,
            elapsed_ms=round(elapsed_ms, 2),
            stdout=_compact_text(stdout),
            stderr=_compact_text(stderr),
            parsed_json=parsed,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return StepResult(
            command=shlex.join(args),
            ok=False,
            return_code=124,
            elapsed_ms=round(elapsed_ms, 2),
            stdout="",
            stderr=f"Command timed out after {timeout_seconds}s",
            parsed_json=None,
        )


def _agent_browser_cmd(*parts: str, session: str, as_json: bool = True) -> list[str]:
    args = ["agent-browser"]
    if as_json:
        args.append("--json")
    args.extend(["--session", session])
    args.extend(parts)
    return args


def _probe_provider_with_agent_browser(
    provider: str,
    registration: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    session = f"probe-{provider}-{int(time.time())}"
    target_url = _build_jetphotos_url(registration) if provider == "jetphotos" else _build_planespotters_url(registration)
    eval_script = _probe_eval_script(provider)

    steps: list[StepResult] = []
    open_step = _run_command(
        _agent_browser_cmd("open", target_url, session=session),
        timeout_seconds=timeout_seconds,
    )
    steps.append(open_step)

    if open_step.ok:
        steps.append(
            _run_command(
                _agent_browser_cmd("wait", "--load", "domcontentloaded", session=session),
                timeout_seconds=timeout_seconds,
            )
        )
        steps.append(
            _run_command(
                _agent_browser_cmd("get", "title", session=session),
                timeout_seconds=timeout_seconds,
            )
        )
        steps.append(
            _run_command(
                _agent_browser_cmd("get", "url", session=session),
                timeout_seconds=timeout_seconds,
            )
        )
        steps.append(
            _run_command(
                _agent_browser_cmd("snapshot", "-i", session=session),
                timeout_seconds=timeout_seconds,
            )
        )
        steps.append(
            _run_command(
                _agent_browser_cmd("eval", eval_script, session=session),
                timeout_seconds=timeout_seconds,
            )
        )

    close_step = _run_command(
        _agent_browser_cmd("close", session=session),
        timeout_seconds=max(20, timeout_seconds // 2),
    )
    steps.append(close_step)

    eval_payload = None
    for step in steps:
        if step.command.endswith(" eval " + shlex.quote(eval_script)):
            eval_payload = step.parsed_json
            break
    if eval_payload is None:
        for step in reversed(steps):
            if " eval " in step.command and step.parsed_json:
                eval_payload = step.parsed_json
                break

    return {
        "provider": provider,
        "target_url": target_url,
        "session": session,
        "ok": open_step.ok,
        "steps": [asdict(step) for step in steps],
        "eval_payload": eval_payload,
        "registration_insertion_strategy": _registration_insertion_strategy(provider, registration),
        "image_extraction_strategy": _image_extraction_strategy(provider),
    }


def _probe_parser_flow(registration: str) -> dict[str, Any]:
    clear_image_finder_runtime_state()

    started = time.perf_counter()
    try:
        jp_url = get_first_image_url_jp(registration)
        jp_error = None
    except Exception as exc:
        jp_url = None
        jp_error = str(exc)
    jp_elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)

    started = time.perf_counter()
    try:
        pp_url = get_first_image_url_pp(registration)
        pp_error = None
    except Exception as exc:
        pp_url = None
        pp_error = str(exc)
    pp_elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)

    return {
        "registration": registration,
        "jetphotos": {
            "url": jp_url,
            "error": jp_error,
            "elapsed_ms": jp_elapsed_ms,
        },
        "planespotters": {
            "url": pp_url,
            "error": pp_error,
            "elapsed_ms": pp_elapsed_ms,
        },
    }


def _extract_step_errors(provider_report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for step in provider_report.get("steps", []):
        if step.get("ok"):
            continue
        stderr = str(step.get("stderr") or "")
        stdout = str(step.get("stdout") or "")
        message = stderr or stdout or "unknown error"
        errors.append(message)
    return errors


def _build_findings(report: dict[str, Any]) -> list[str]:
    findings: list[str] = []

    parser_report = report.get("parser_probe", {})
    agent_report = report.get("agent_browser_probe", {})

    for provider in ("jetphotos", "planespotters"):
        provider_report = agent_report.get(provider, {})
        errors = _extract_step_errors(provider_report)
        for error in errors:
            lowered = error.lower()
            if "err_name_not_resolved" in lowered:
                findings.append(
                    f"{provider}: DNS/network resolution error from agent-browser (ERR_NAME_NOT_RESOLVED)."
                )
            elif "timed out" in lowered:
                findings.append(f"{provider}: agent-browser command timeout detected.")
            elif "captcha" in lowered or "challenge" in lowered:
                findings.append(f"{provider}: anti-bot challenge detected in browser automation.")

        eval_payload = provider_report.get("eval_payload") or {}
        payload_data = _extract_eval_result(eval_payload)
        if payload_data:
            marker_hits = payload_data.get("challenge_markers")
            if isinstance(marker_hits, list) and marker_hits:
                findings.append(
                    f"{provider}: challenge markers in DOM -> {', '.join(str(item) for item in marker_hits)}"
                )
            candidate_count = payload_data.get("candidate_count")
            if isinstance(candidate_count, int):
                findings.append(f"{provider}: browser probe found {candidate_count} image URL candidates in DOM.")
            forms_count = payload_data.get("forms_count")
            if isinstance(forms_count, int):
                findings.append(f"{provider}: browser probe found {forms_count} forms in DOM.")
            reg_fields = payload_data.get("candidate_registration_fields")
            if isinstance(reg_fields, list) and reg_fields:
                findings.append(f"{provider}: browser detected candidate registration input fields ({len(reg_fields)}).")

        parser_provider = parser_report.get(provider, {})
        parser_url = parser_provider.get("url") if isinstance(parser_provider, dict) else None
        if parser_url:
            findings.append(f"{provider}: parser resolved image URL successfully ({parser_url}).")
        else:
            parser_error = parser_provider.get("error") if isinstance(parser_provider, dict) else None
            if parser_error:
                findings.append(f"{provider}: parser raised error -> {parser_error}")
            else:
                findings.append(f"{provider}: parser did not resolve any image URL.")

    if not findings:
        findings.append("No strong signal detected. Collect more runs with different registrations.")

    unique = []
    seen = set()
    for item in findings:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _build_debug_plan(findings: list[str]) -> list[str]:
    plan = [
        "Run `test/integration/image_scrape_probe.py` with 5-10 real registrations and keep JSON outputs under `test/artifacts/`.",
        "For each provider, compare `eval_payload.candidate_urls` from browser probe vs parser output; if browser has URLs but parser fails, update selectors/parsing first.",
        "When anti-bot markers appear, increase provider cooldown and reduce retry pressure instead of hard-failing the full social publish flow.",
        "Track HTTP status, challenge markers, and parser reasons in monitoring to spot drift after site DOM changes.",
        "Add regression fixtures with captured HTML snippets and test parser extraction against them before deploying.",
    ]

    lower_findings = " ".join(findings).lower()
    if "dns/network" in lower_findings or "err_name_not_resolved" in lower_findings:
        plan.insert(
            0,
            "Fix runtime DNS/egress access first; browser automation and scraper validation are blocked while domains cannot resolve.",
        )
    if "anti-bot" in lower_findings or "challenge markers" in lower_findings:
        plan.insert(
            0,
            "Add canary checks (single registration per provider) and alert on challenge spikes before running full scraping batches.",
        )
    return plan


def run(registration: str, timeout_seconds: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "timestamp": _now_iso(),
        "registration": registration,
        "agent_browser_available": bool(shutil.which("agent-browser")),
    }

    if not report["agent_browser_available"]:
        report["agent_browser_probe"] = {
            "error": "agent-browser binary not found in PATH"
        }
    else:
        report["agent_browser_probe"] = {
            "jetphotos": _probe_provider_with_agent_browser(
                "jetphotos",
                registration,
                timeout_seconds=timeout_seconds,
            ),
            "planespotters": _probe_provider_with_agent_browser(
                "planespotters",
                registration,
                timeout_seconds=timeout_seconds,
            ),
        }

    report["parser_probe"] = _probe_parser_flow(registration)
    report["findings"] = _build_findings(report)
    report["debug_plan"] = _build_debug_plan(report["findings"])
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe JetPhotos/Planespotters scraping flow")
    parser.add_argument(
        "--registration",
        default="EC-NGS",
        help="Aircraft registration to probe",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Timeout (seconds) per agent-browser command",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write the JSON report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run(args.registration.strip().upper(), args.timeout)
        payload = {"ok": True, "report": report}
        if args.output:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = PROJECT_ROOT / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
