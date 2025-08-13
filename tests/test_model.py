import os
import json
import tempfile

import importlib


def make_entry(
    *,
    notion_id: str,
    title: str = "Untitled",
    chapter: str = "Chapter 1",
    url: str | None = None,
    chapter_heading: bool = False,
    aside_heading: bool = False,
    next_ids: list[str] | None = None,
    prior_ids: list[str] | None = None,
):
    props = {
        "Name": {
            "type": "title",
            "title": [{"plain_text": title}],
        },
        "Title": {
            "type": "title",
            "title": [{"plain_text": title}],
        },
        "Chapter": {
            "type": "select",
            "select": {"name": chapter},
        },
        "URL": {
            "type": "url",
            "url": url or "",
        },
        "Chapter Heading": {
            "type": "checkbox",
            "checkbox": chapter_heading,
        },
        "Aside Heading": {
            "type": "checkbox",
            "checkbox": aside_heading,
        },
        "Next Event": {
            "type": "relation",
            "relation": [{"id": i} for i in (next_ids or [])],
        },
        "Prior Event": {
            "type": "relation",
            "relation": [{"id": i} for i in (prior_ids or [])],
        },
    }
    return {"id": notion_id, "properties": props}


def import_main():
    # Ensure project root is importable
    import sys
    project_root = os.path.dirname(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return importlib.import_module("main")


def test_extract_property_value_and_parse_nodes():
    main = import_main()

    e1 = make_entry(notion_id="A", title="Alpha", url="https://x", chapter_heading=True)
    e2 = make_entry(notion_id="B", title="Beta", next_ids=["A"], prior_ids=["A"])

    nodes = main.parse_entries_to_nodes([e1, e2])
    assert set(nodes.keys()) == {"A", "B"}
    assert nodes["A"].is_chapter_heading is True
    assert nodes["A"].url == "https://x"
    assert nodes["B"].next_events == ["A"]
    assert nodes["B"].prior_events == ["A"]


def test_build_model_and_aside_mapping():
    main = import_main()

    # Main chapter has an Aside Heading title that matches an Aside chapter's Chapter Heading
    main_e = make_entry(
        notion_id="M1",
        title="Shared Title",
        chapter="Chapter 5",
        aside_heading=True,
    )
    aside_heading_e = make_entry(
        notion_id="S1",
        title="Shared Title",
        chapter="Aside 1 - Notes",
        chapter_heading=True,
    )
    prologue_e = make_entry(notion_id="P1", title="Prologue Start", chapter="Prologue")

    model = main.build_model_from_entries([main_e, aside_heading_e, prologue_e])

    # Prologue first, then Chapter 5
    assert model["chapters"][0] == "Prologue"
    assert "Chapter 5" in model["chapters"]
    # Aside chapter discovered
    assert "Aside 1 - Notes" in model["aside_chapters"]
    # Mapping established
    mapping = model["chapter_aside_mapping"]
    assert mapping.get("Chapter 5") == ["Aside 1 - Notes"]


def test_graphviz_has_no_global_label_and_internal_aside_links():
    main = import_main()

    # Prepare entries and nodes
    m = make_entry(notion_id="M1", title="Shared", chapter="Chapter 2", aside_heading=True, url="https://x")
    s = make_entry(notion_id="S1", title="Shared", chapter="Aside A", chapter_heading=True)
    model = main.build_model_from_entries([m, s])

    nodes = model["nodes_by_chapter"]["Chapter 2"]
    current_entries = model["entries_by_chapter"]["Chapter 2"]
    aside_titles = {"Aside A": model["headings_by_aside"]["Aside A"]}

    dot = main.create_graphviz_flowchart(
        nodes,
        chapter_name="Chapter 2",
        aside_mapping=model["chapter_aside_mapping"],
        current_entries=current_entries,
        aside_heading_titles_by_aside=aside_titles,
    )

    # No global label should be present
    assert "label=\"Chapter 2\"" not in dot
    # The aside outlink node should be prefixed and link internally
    assert "🔗" in dot
    assert "?chapter=Aside%20A" in dot


def test_snapshot_roundtrip(tmp_path: tempfile.TemporaryDirectory):
    main = import_main()
    entries = [make_entry(notion_id="X", title="X", chapter="Chapter 1")]

    cache_file = tmp_path / "snapshot.json"
    os.environ["TIMELINE_CACHE_PATH"] = str(cache_file)

    # Save and load
    main.save_snapshot_to_disk("db-1", entries)
    # Manually patch the database_id to ensure filtering works
    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["database_id"] == "db-1"

    loaded = main.load_snapshot_from_disk("db-1")
    assert isinstance(loaded, list)
    assert loaded and loaded[0]["id"] == "X"

