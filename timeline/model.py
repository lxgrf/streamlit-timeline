# timeline/model.py
from typing import Dict, List
import streamlit as st
from .notion import get_notion_client, get_all_database_entries
from .cache import load_snapshot_from_disk, save_snapshot_to_disk

class EventNode:
    """Represents an event node in the flowchart"""
    def __init__(self, notion_id: str, title: str, url: str = "", is_chapter_heading: bool = False):
        self.notion_id = notion_id
        self.title = title
        self.url = url
        self.is_chapter_heading = is_chapter_heading
        self.next_events: List[str] = []
        self.prior_events: List[str] = []

def extract_property_value(properties: Dict, prop_name: str, prop_type: str = None) -> str:
    """Extract value from a Notion property"""
    prop_data = properties.get(prop_name, {})
    detected_type = prop_data.get("type", "")

    if detected_type == "title" and prop_data.get("title"):
        return prop_data["title"][0].get("plain_text", "") if prop_data["title"] else ""
    elif detected_type == "rich_text" and prop_data.get("rich_text"):
        return " ".join([item.get("plain_text", "") for item in prop_data["rich_text"]])
    elif detected_type == "url":
        return prop_data.get("url", "")
    elif detected_type == "checkbox":
        return prop_data.get("checkbox", False)
    elif detected_type == "select" and prop_data.get("select"):
        return prop_data["select"].get("name", "")
    elif detected_type == "relation" and prop_data.get("relation"):
        return [rel.get("id", "") for rel in prop_data["relation"]]

    return ""

def parse_entries_to_nodes(entries: List) -> Dict[str, EventNode]:
    """Parse Notion entries into EventNode objects"""
    nodes = {}

    for entry in entries:
        notion_id = entry.get("id", "")
        properties = entry.get("properties", {})

        title = extract_property_value(properties, "Name") or extract_property_value(properties, "Title") or "Untitled"
        url = extract_property_value(properties, "URL")
        is_chapter_heading = extract_property_value(properties, "Chapter Heading")

        node = EventNode(notion_id, title, url, is_chapter_heading)

        next_events = extract_property_value(properties, "Next Event")
        prior_events = extract_property_value(properties, "Prior Event")

        if isinstance(next_events, list):
            node.next_events = next_events
        if isinstance(prior_events, list):
            node.prior_events = prior_events

        nodes[notion_id] = node

    return nodes

def build_model_from_entries(all_entries: List[Dict]):
    """Build the in-memory timeline model from a list of Notion entries."""
    entries_by_chapter = {}
    for entry in all_entries:
        chapter_prop = entry.get("properties", {}).get("Chapter", {})
        chapter = ""
        if chapter_prop.get("type") == "select" and chapter_prop.get("select"):
            chapter = chapter_prop["select"].get("name", "")
        if chapter:
            entries_by_chapter.setdefault(chapter, []).append(entry)

    chapters_set = set(entries_by_chapter.keys())
    chapters = []
    if "Prologue" in chapters_set:
        chapters.append("Prologue")
    chapters.extend([ch for ch in sorted(chapters_set) if ch.startswith("Chapter")])

    aside_chapters = sorted([ch for ch in chapters_set if ch.startswith("Aside")])

    def _title_from_props(props: Dict) -> str:
        return (
            extract_property_value(props, "Name")
            or extract_property_value(props, "Title")
            or "Untitled"
        )

    headings_by_aside = {}
    for aside in aside_chapters:
        titles = []
        for entry in entries_by_chapter.get(aside, []):
            props = entry.get("properties", {})
            if extract_property_value(props, "Chapter Heading"):
                titles.append(_title_from_props(props))
        headings_by_aside[aside] = set(titles)

    outlinks_by_main = {}
    for main in chapters:
        if main == "Prologue":
            continue
        titles = []
        for entry in entries_by_chapter.get(main, []):
            props = entry.get("properties", {})
            if extract_property_value(props, "Aside Heading"):
                titles.append(_title_from_props(props))
        if titles:
            outlinks_by_main[main] = set(titles)

    chapter_aside_mapping = {}
    for main, out_titles in outlinks_by_main.items():
        for aside, head_titles in headings_by_aside.items():
            if out_titles & head_titles:
                chapter_aside_mapping.setdefault(main, []).append(aside)

    nodes_by_chapter = {}
    for chapter in set(list(chapters) + aside_chapters):
        entries = entries_by_chapter.get(chapter, [])
        nodes_by_chapter[chapter] = parse_entries_to_nodes(entries)

    return {
        "chapters": chapters,
        "aside_chapters": aside_chapters,
        "entries_by_chapter": entries_by_chapter,
        "nodes_by_chapter": nodes_by_chapter,
        "chapter_aside_mapping": chapter_aside_mapping,
        "headings_by_aside": headings_by_aside,
        "entry_count": len(all_entries),
    }

@st.cache_data(ttl=None)
def build_timeline_model(database_id: str, force_refresh: bool = False):
    """Load timeline model from a local snapshot, or fetch from Notion when forced or missing."""
    entries: List[Dict] | None = None

    if not force_refresh:
        entries = load_snapshot_from_disk(database_id)

    if entries is None:
        notion_client = get_notion_client()
        entries = get_all_database_entries(notion_client, database_id)
        save_snapshot_to_disk(database_id, entries)

    return build_model_from_entries(entries)