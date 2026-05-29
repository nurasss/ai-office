from pathlib import Path

from scripts.parse_knowledge_sources import (
    classify_source,
    html_to_markdown,
    iter_source_files,
    load_catalog,
    parse_owner_sources,
    render_source_plan,
    seed_local_raw_sources,
)


def test_html_to_markdown_keeps_headings_and_lists():
    markdown = html_to_markdown(
        "<html><body><h1>FAQ</h1><p>Hello <b>team</b></p>"
        "<ul><li>First</li><li>Second</li></ul></body></html>"
    )

    assert "# FAQ" in markdown
    assert "Hello team" in markdown
    assert "- First" in markdown
    assert "- Second" in markdown


def test_classify_source_uses_matching_folder(tmp_path):
    input_root = tmp_path / "copywriter"
    source_file = input_root / "brandbook" / "voice.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("# Tone of voice", encoding="utf-8")

    source_id = classify_source(
        "copywriter",
        source_file,
        input_root,
        source_file.read_text(encoding="utf-8"),
    )

    assert source_id == "brandbook_communications"


def test_parse_owner_sources_writes_to_agent_source_folder(tmp_path):
    input_root = tmp_path / "raw" / "copywriter"
    source_file = input_root / "brandbook" / "voice.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "<h1>Voice</h1><p>OPENAI_API_KEY=secret-value</p>",
        encoding="utf-8",
    )

    output_root = tmp_path / "knowledge"
    parsed = parse_owner_sources(
        owner="copywriter",
        input_path=input_root,
        output_root=output_root,
        catalog=load_catalog(),
        force_source=None,
        dry_run=False,
        redact=True,
    )

    assert len(parsed) == 1
    output_path = parsed[0].output_path
    assert output_path.parent == output_root / "copywriter" / "brandbook"
    content = output_path.read_text(encoding="utf-8")
    assert "Owner: `copywriter`" in content
    assert "Source id: `brandbook_communications`" in content
    assert "OPENAI_API_KEY=[REDACTED]" in content
    assert "secret-value" not in content


def test_parser_ignores_generated_source_hints(tmp_path):
    input_root = tmp_path / "raw" / "copywriter" / "brandbook"
    input_root.mkdir(parents=True)
    (input_root / "_SOURCE_HINT.md").write_text("hint", encoding="utf-8")
    (input_root / "brandbook.md").write_text("# Brandbook", encoding="utf-8")

    files = list(iter_source_files(tmp_path / "raw"))

    assert input_root / "_SOURCE_HINT.md" not in files
    assert input_root / "brandbook.md" in files


def test_source_plan_contains_user_requested_systems():
    plan = render_source_plan(load_catalog(), ["copywriter", "data_analyst"])

    assert "Google Docs" in plan
    assert "Habr" in plan
    assert "pg_dump -s" in plan
    assert "Metabase/Tableau" in plan


def test_seed_local_raw_sources_callable():
    assert callable(seed_local_raw_sources)
