import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
EN = (ROOT / "README.md").read_text(encoding="utf-8")
JA = (ROOT / "README.ja.md").read_text(encoding="utf-8")

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LINK_RE = re.compile(r"\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#{1,6} .+$", re.MULTILINE)

# Date recorded in the English README before the split into two languages;
# the status tables must keep this number unchanged in both files.
EXPECTED_STATUS_DATE = "2026-10-12"

EXPECTED_HEADINGS = [
    ("# AITuber Agent", "# AITuber Agent"),
    ("## What it does", "## できること"),
    ("## How it is built", "## 作り方"),
    ("## Status", "## 状態"),
    ("## Where it could go", "## 展望"),
]

EXPECTED_EXTERNAL_LINKS = [
    "https://github.com/johnknash2025",
    "https://ollama.com",
]


def headings(text):
    return HEADING_RE.findall(text)


def slug(heading):
    title = re.sub(r"^#+ ", "", heading)
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", title.lower())).strip("-")


def anchors(text):
    return {slug(h) for h in headings(text)}


def external_links(text):
    return sorted(u for u in LINK_RE.findall(text) if u.startswith("http"))


def relative_links(text):
    return [u for u in LINK_RE.findall(text) if not u.startswith("http")]


def status_rows(text, heading):
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.strip().startswith("|")]


def split_anchor(target):
    path, _, fragment = target.partition("#")
    return unquote(path), fragment


def test_status_dates_match_across_readmes():
    en_dates = set(DATE_RE.findall(EN))
    ja_dates = set(DATE_RE.findall(JA))
    assert en_dates == {EXPECTED_STATUS_DATE}, (
        "English README status date changed: expected "
        f"{EXPECTED_STATUS_DATE}, found {sorted(en_dates)}"
    )
    assert ja_dates == en_dates, (
        "status dates differ between README.md and README.ja.md"
    )


def test_status_date_is_the_recorded_run():
    en_status_rows = "\n".join(status_rows(EN, "## Status"))
    assert EXPECTED_STATUS_DATE in en_status_rows, (
        "English README status table no longer records the offline demo date"
    )
    assert re.search(r"\bran\b", en_status_rows, re.IGNORECASE), (
        "English README no longer presents the offline demo as a completed run"
    )
    assert "fixed comments" in en_status_rows.lower(), (
        "English README no longer records the fixed-comment run"
    )
    assert "planned for" not in EN, (
        "English README turns the completed run into a plan"
    )
    assert "the run has not been recorded" not in EN, (
        "English README adds a claim that the recorded run did not happen"
    )
    assert f"{EXPECTED_STATUS_DATE} に固定コメントで実行しました" in JA, (
        "Japanese README no longer presents the offline demo as a completed run"
    )
    assert "実行予定" not in JA, (
        "Japanese README turns the completed run into a plan"
    )
    assert "記録されていません" not in JA, (
        "Japanese README adds a claim that the recorded run did not happen"
    )


def test_status_table_header_is_preserved():
    assert "| Verified | How |" in EN, (
        "English README status table header was changed"
    )
    assert "| Status | Item | How |" not in EN, (
        "English README adds a new status column header"
    )
    assert "| 確認済み | 方法 |" in JA, (
        "Japanese README status table header was changed"
    )
    assert "| 状態 | 項目 | 方法 |" not in JA, (
        "Japanese README adds a new status column header"
    )


def test_original_ollama_bullet_has_no_extra_tts_privacy_claim():
    assert "so viewers' comments are not sent to a cloud AI service" in EN
    assert "only the generated reply text" not in EN, (
        "English README adds a Google Cloud Text-to-Speech privacy sentence"
    )
    assert "視聴者のコメントはクラウドの AI サービスに送られません" in JA
    assert "生成した返信テキストだけ" not in JA, (
        "Japanese README adds a Google Cloud Text-to-Speech privacy sentence"
    )


def test_source_note_has_no_extra_license_claims():
    assert "Source is private and can be shared on request" in EN
    assert "documentation only" not in EN
    assert "not included in this public repository" not in EN
    assert "no license is granted" not in EN
    assert "owner may share it on request" not in EN
    assert "ソースは非公開で、希望に応じて共有できます" in JA
    assert "ドキュメントのみ" not in JA
    assert "この公開リポジトリには含まれていません" not in JA
    assert "ライセンスは付与されていません" not in JA
    assert "持ち主の判断" not in JA


def test_status_table_has_consistent_columns():
    for name, text, heading in (
        ("README.md", EN, "## Status"),
        ("README.ja.md", JA, "## 状態"),
    ):
        rows = status_rows(text, heading)
        assert rows, f"{name} has no status table"
        widths = set()
        for row in rows:
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            widths.add(len(cells))
        assert len(widths) == 1, f"inconsistent status table columns in {name}"


def test_both_readmes_have_a_language_switch_line():
    en_lines = [l for l in EN.splitlines() if l.strip()][:2]
    ja_lines = [l for l in JA.splitlines() if l.strip()][:2]
    assert en_lines[1] == "English | [日本語](README.ja.md)"
    assert ja_lines[1] == "[English](README.md) | 日本語"


def test_heading_order_and_text_correspond():
    en = headings(EN)
    ja = headings(JA)
    assert len(en) == len(ja) == len(EXPECTED_HEADINGS), (
        f"READMEs must have exactly {len(EXPECTED_HEADINGS)} headings each; "
        f"README.md has {len(en)}, README.ja.md has {len(ja)}"
    )
    assert list(zip(en, ja)) == EXPECTED_HEADINGS


def test_external_link_set_is_the_expected_set():
    assert external_links(EN) == EXPECTED_EXTERNAL_LINKS
    assert external_links(JA) == EXPECTED_EXTERNAL_LINKS


def test_external_links_resolve():
    urls = sorted(set(external_links(EN)) | set(external_links(JA)))
    assert urls == EXPECTED_EXTERNAL_LINKS, (
        f"unexpected external links: {urls}"
    )
    for url in urls:
        parts = urlsplit(url)
        assert parts.scheme in ("http", "https") and parts.netloc, (
            f"malformed external URL: {url}"
        )
        status = None
        blocked = False
        network_failure = None
        for method in ("HEAD", "GET"):
            request = urllib.request.Request(
                url, method=method, headers={"User-Agent": "readme-link-check"}
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status = response.status
                break
            except urllib.error.HTTPError as error:
                if error.code in (403, 405):
                    blocked = True
                    continue
                pytest.fail(f"broken external link (HTTP {error.code}): {url}")
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as error:
                network_failure = error
                break
        if network_failure is not None:
            pytest.skip(
                f"network unavailable, cannot verify external link {url}: {network_failure}"
            )
        if status is None and blocked:
            pytest.skip(
                f"external link {url} returned HTTP 403/405 for HEAD and GET, "
                "so its resolution cannot be verified"
            )
        assert status is not None and status < 400, (
            f"broken external link (HTTP {status}): {url}"
        )


def test_relative_links_resolve():
    for name, text in (("README.md", EN), ("README.ja.md", JA)):
        for target in relative_links(text):
            path, fragment = split_anchor(target)
            file = ROOT / path if path else ROOT / name
            assert file.is_file(), f"broken link in {name}: {target}"
            if fragment:
                assert fragment in anchors(file.read_text(encoding="utf-8")), (
                    f"anchor not found for link in {name}: {target}"
                )
