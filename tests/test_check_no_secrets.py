from __future__ import annotations

import zipfile

from scripts.check_no_secrets import scan_paths, scan_text


def test_secret_scan_detects_env_assignment():
    findings = scan_text("runtime.env", "OPENAI_API_KEY=live-model-provider-key\n")

    assert findings
    assert findings[0].kind == "OPENAI_API_KEY assignment"


def test_secret_scan_ignores_env_examples():
    findings = scan_text(".env.production.example", "OPENAI_API_KEY=\nAI_OFFICE_API_KEY=change-me-long-random\n")

    assert findings == []


def test_secret_scan_detects_release_archive_secret(tmp_path):
    archive_path = tmp_path / "release.zip"
    fake_token = "ghp_" + "1234567890abcdefghijklmnop"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("config.env", f"GITHUB_TOKEN={fake_token}\n")

    findings = scan_paths([archive_path])

    assert findings
    assert findings[0].path == "config.env"
