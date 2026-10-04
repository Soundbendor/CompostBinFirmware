#!/usr/bin/env python3
"""Validate repository-owned workflow metadata and sanitized JSON fixtures."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "AGENTS.md",
    "CONTRIBUTING.md",
    "README.md",
    "Makefile",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/workflows/repository-checks.yml",
    "docs/architecture.md",
    "docs/protocols/scan-upload.md",
    "docs/protocols/bluetooth.md",
    "docs/runbooks/development.md",
    "docs/runbooks/hardware-validation.md",
    "docs/runbooks/deployment.md",
    "docs/adr/README.md",
)

SCAN_FIELDS = {
    "colorImage",
    "depthImage",
    "heatmapImage",
    "topologyMap",
    "voiceRecording",
    "total_weight",
    "weight_delta",
    "temperature",
    "pressure",
    "humidity",
    "iaq",
    "co2_eq",
    "tvoc",
    "transcription",
    "userTrigger",
    "deviceID",
    "commitID",
}

SCAN_STRING_FIELDS = {
    "colorImage",
    "depthImage",
    "heatmapImage",
    "topologyMap",
    "voiceRecording",
    "transcription",
    "deviceID",
}

SCAN_NUMBER_FIELDS = {
    "total_weight",
    "weight_delta",
    "temperature",
    "pressure",
    "humidity",
    "iaq",
    "co2_eq",
    "tvoc",
}

MARKDOWN_LINK = re.compile(r"\[[^]]*]\(([^)]+)\)")


def fail(message: str) -> None:
    print(f"repository validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid JSON fixture {path.relative_to(ROOT)}: {error}")


def validate_required_paths() -> None:
    missing = [path for path in REQUIRED_PATHS if not ROOT.joinpath(path).is_file()]
    if missing:
        fail(f"missing required workflow files: {', '.join(missing)}")

    workflow = ROOT.joinpath(".github/workflows/repository-checks.yml").read_text(
        encoding="utf-8"
    )
    if "run: make check" not in workflow:
        fail("repository-checks workflow must call the canonical 'make check' target")


def validate_json_fixtures() -> int:
    fixture_root = ROOT / "src/tests/fixtures"
    fixtures = sorted(fixture_root.rglob("*.json"))
    if not fixtures:
        fail("no JSON contract fixtures found")

    parsed = {path: load_json(path) for path in fixtures}
    scan_path = fixture_root / "contracts/scan_payload.json"
    scan = parsed.get(scan_path)
    if not isinstance(scan, dict) or set(scan) != SCAN_FIELDS:
        fail("scan_payload.json fields do not match the documented current contract")
    if any(not isinstance(scan[field], str) for field in SCAN_STRING_FIELDS):
        fail("scan_payload.json string fields have an unexpected type")
    if any(
        isinstance(scan[field], bool) or not isinstance(scan[field], (int, float))
        for field in SCAN_NUMBER_FIELDS
    ):
        fail("scan_payload.json numeric fields have an unexpected type")
    if not isinstance(scan["userTrigger"], bool):
        fail("scan_payload.json userTrigger must be a boolean")
    if scan["commitID"] is not None and not isinstance(scan["commitID"], str):
        fail("scan_payload.json commitID must be null or a string")
    if not str(scan["deviceID"]).startswith("fixture-"):
        fail("scan fixture deviceID must be synthetic and start with 'fixture-'")

    api_setup = parsed[fixture_root / "bluetooth/api_setup_request.json"]
    if not isinstance(api_setup, dict):
        fail("Bluetooth API setup fixture must be a JSON object")
    if api_setup.get("endpoint") != "api.example.invalid":
        fail("Bluetooth API fixture must use the reserved example.invalid domain")
    if not str(api_setup.get("apiKey", "")).startswith("fixture-"):
        fail("Bluetooth API fixture key must be clearly synthetic")

    wifi_setup = parsed[fixture_root / "bluetooth/wifi_credentials_request.json"]
    if not isinstance(wifi_setup, dict):
        fail("Bluetooth Wi-Fi setup fixture must be a JSON object")
    if not str(wifi_setup.get("password", "")).startswith("fixture-"):
        fail("Bluetooth Wi-Fi fixture password must be clearly synthetic")

    return len(fixtures)


def validate_markdown_links() -> int:
    markdown_files = sorted(
        [ROOT / "AGENTS.md", ROOT / "CONTRIBUTING.md", *ROOT.joinpath("docs").rglob("*.md")]
    )
    checked = 0
    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (markdown_file.parent / target).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                fail(f"link escapes repository in {markdown_file.relative_to(ROOT)}: {raw_target}")
            if not resolved.exists():
                fail(f"broken link in {markdown_file.relative_to(ROOT)}: {raw_target}")
            checked += 1
    return checked


def validate_shell_syntax() -> int:
    scripts = sorted(ROOT.glob("*.sh"))
    scripts.extend(sorted(ROOT.joinpath("diagnostics").glob("*.sh")))
    scripts.append(ROOT / "src/runTest.sh")

    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "unknown bash syntax error"
            fail(f"shell syntax error in {script.relative_to(ROOT)}: {detail}")
    return len(scripts)


def main() -> None:
    validate_required_paths()
    fixture_count = validate_json_fixtures()
    link_count = validate_markdown_links()
    script_count = validate_shell_syntax()
    print(
        "repository metadata valid: "
        f"{fixture_count} JSON fixtures, {link_count} local links, "
        f"{script_count} shell scripts"
    )


if __name__ == "__main__":
    main()
