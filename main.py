import streamlit as st
import os
import json
from datetime import datetime, timezone
from notion_client import Client
from dotenv import load_dotenv
from typing import Dict, List
import textwrap

# Load environment variables
load_dotenv()

@st.cache_resource
def get_notion_client():
    """Initialise Notion client with API key from environment"""
    notion_key = os.getenv("NOTION_KEY")
    if not notion_key:
        st.error("NOTION_KEY not found in environment variables. Please check your .env file.")
        st.stop()
    return Client(auth=notion_key)

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_all_database_entries(_notion_client, database_id):
    """Get ALL entries from the database once, with caching"""
    try:
        # Query all entries with pagination
        all_entries = []
        has_more = True
        next_cursor = None
        
        while has_more:
            query_params = {"database_id": database_id}
            if next_cursor:
                query_params["start_cursor"] = next_cursor
                
            response = _notion_client.databases.query(**query_params)
            all_entries.extend(response["results"])
            
            has_more = response.get("has_more", False)
            next_cursor = response.get("next_cursor")
        
        return all_entries
    
    except Exception as e:
        st.error(f"Error retrieving database: {str(e)}")
        return []

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
        
        # Extract basic information
        title = extract_property_value(properties, "Name") or extract_property_value(properties, "Title") or "Untitled"
        url = extract_property_value(properties, "URL")
        is_chapter_heading = extract_property_value(properties, "Chapter Heading")
        
        # Create node
        node = EventNode(notion_id, title, url, is_chapter_heading)
        
        # Extract relationships
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

    # Group entries by chapter
    entries_by_chapter = {}
    for entry in all_entries:
        chapter_prop = entry.get("properties", {}).get("Chapter", {})
        chapter = ""
        if chapter_prop.get("type") == "select" and chapter_prop.get("select"):
            chapter = chapter_prop["select"].get("name", "")
        if chapter:
            entries_by_chapter.setdefault(chapter, []).append(entry)

    # Ordered chapter list: Prologue first, then numbered chapters
    chapters_set = set(entries_by_chapter.keys())
    chapters = []
    if "Prologue" in chapters_set:
        chapters.append("Prologue")
    chapters.extend([ch for ch in sorted(chapters_set) if ch.startswith("Chapter")])

    # Aside chapters
    aside_chapters = sorted([ch for ch in chapters_set if ch.startswith("Aside")])

    def _title_from_props(props: Dict) -> str:
        return (
            extract_property_value(props, "Name")
            or extract_property_value(props, "Title")
            or "Untitled"
        )

    # Precompute titles marked as "Chapter Heading" per aside
    headings_by_aside = {}
    for aside in aside_chapters:
        titles = []
        for entry in entries_by_chapter.get(aside, []):
            props = entry.get("properties", {})
            if extract_property_value(props, "Chapter Heading"):
                titles.append(_title_from_props(props))
        headings_by_aside[aside] = set(titles)

    # Precompute titles marked as "Aside Heading" per main chapter
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

    # Match main ↔ aside by intersecting titles
    chapter_aside_mapping = {}
    for main, out_titles in outlinks_by_main.items():
        for aside, head_titles in headings_by_aside.items():
            if out_titles & head_titles:
                chapter_aside_mapping.setdefault(main, []).append(aside)

    # Parse nodes once per chapter
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


def _get_cache_path() -> str:
    """Return the file path used for the local snapshot cache."""
    return os.getenv("TIMELINE_CACHE_PATH", ".timeline_model_snapshot.json")


def load_snapshot_from_disk(database_id: str) -> List[Dict] | None:
    """Load cached snapshot of Notion entries from disk if available and matching database_id."""
    cache_path = _get_cache_path()
    try:
        if not os.path.exists(cache_path):
            return None
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if data.get("database_id") != database_id:
            return None
        entries = data.get("all_entries")
        if isinstance(entries, list):
            return entries
        return None
    except Exception:
        return None


def save_snapshot_to_disk(database_id: str, all_entries: List[Dict]) -> None:
    """Persist Notion entries snapshot to disk for reuse across sessions."""
    cache_path = _get_cache_path()
    try:
        payload = {
            "database_id": database_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "all_entries": all_entries,
            "schema_version": 1,
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
    except Exception:
        # Silently ignore disk caching errors to avoid breaking the app
        pass


@st.cache_data(ttl=None)
def build_timeline_model(database_id: str, force_refresh: bool = False):
    """Load timeline model from a local snapshot, or fetch from Notion when forced or missing.

    - When force_refresh is False, prefer disk snapshot to avoid network calls.
    - When force_refresh is True, always poll Notion, then update the disk snapshot.
    """
    entries: List[Dict] | None = None

    if not force_refresh:
        entries = load_snapshot_from_disk(database_id)

    if entries is None:
        notion_client = get_notion_client()
        entries = get_all_database_entries(notion_client, database_id)
        # Persist to disk for subsequent sessions
        save_snapshot_to_disk(database_id, entries)

    return build_model_from_entries(entries)

def create_graphviz_flowchart(
    nodes: Dict[str, EventNode],
    chapter_name: str = "",
    aside_mapping: Dict[str, List[str]] = None,
    current_entries: List = None,
    aside_heading_titles_by_aside: Dict[str, set] = None,
) -> str:
    """Generate a Graphviz DOT string for use with st.graphviz_chart()."""

    notion_id_to_dot_id = {node_id: f"node_{i}" for i, node_id in enumerate(nodes.keys())}

    # Theme detection
    try:
        import streamlit.config as config
        is_dark_mode = config.get_option("theme.base") == "dark"
    except Exception:
        is_dark_mode = False

    if is_dark_mode:
        chapter_color = "#5dade2"
        event_color = "#85c1e9"
        edge_color = "#ffffff"
        font_color = "black"
    else:
        chapter_color = "#2c3e50"
        event_color = "#34495e"
        edge_color = "#2c3e50"
        font_color = "white"

    clean_chapter_name = ''.join(c if c.isalnum() else '_' for c in chapter_name) if chapter_name else "timeline"
    graph_name = f"timeline_{clean_chapter_name}"

    node_count = len(nodes)
    is_simple_graph = node_count <= 5
    is_aside = chapter_name.startswith("Aside") if chapter_name else False

    if is_simple_graph or is_aside:
        dot_lines = [
            f'digraph {graph_name} {{',
            '    rankdir=TB;',
            '    node [shape=box, style=filled, fontname="Helvetica", fontsize=12, width=3, height=1.2];',
            '    graph [bgcolor=transparent, nodesep=0.5, ranksep=0.8, size="10,8!", ratio=fill];',
            f'    edge [color="{edge_color}"];',
            ''
        ]
    else:
        dot_lines = [
            f'digraph {graph_name} {{',
            '    rankdir=TB;',
            '    node [shape=box, style=filled, fontname="Helvetica", fontsize=11];',
            '    graph [bgcolor=transparent, nodesep=0.3, ranksep=0.5, ratio=auto, margin=0.2];',
            f'    edge [color="{edge_color}"];',
            ''
        ]

    # Use precomputed current entries to identify aside outlinks
    entry_props_by_id = {e.get("id", ""): e.get("properties", {}) for e in (current_entries or [])}

    def find_aside_for_title(node_title):
        if not aside_heading_titles_by_aside:
            return None
        for aside, titles in aside_heading_titles_by_aside.items():
            if node_title in titles:
                return aside
        return None

    for notion_id, node in nodes.items():
        dot_id = notion_id_to_dot_id[notion_id]

        wrapped_title = textwrap.fill(node.title, width=30)
        safe_title = (wrapped_title
                      .replace('\\', '\\\\')
                      .replace('"', '\\"')
                      .replace('\n', '\\n')
                      .replace('\r', '')
                      .replace('\t', ' '))
        tooltip_title = wrapped_title.replace('\n', ' ')

        node_url = node.url
        is_aside_outlink = False

        if entry_props_by_id:
            props = entry_props_by_id.get(notion_id)
            if props:
                aside_heading = extract_property_value(props, "Aside Heading")
                if aside_heading and node.url:
                    is_aside_outlink = True
                    matching_aside = find_aside_for_title(node.title)
                    if matching_aside:
                        node_url = f"?chapter={matching_aside.replace(' ', '%20')}"

        base_font_size = 12 if (is_simple_graph or is_aside) else 11
        heading_font_size = base_font_size + 2

        if is_aside_outlink:
            safe_title = f"🔗 {safe_title}"

        if node.is_chapter_heading:
            if node_url:
                target = "_self" if is_aside_outlink else "_blank"
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{chapter_color}", fontcolor={font_color}, penwidth=3, fontsize={heading_font_size}, href="{node_url}", target="{target}", tooltip="{tooltip_title}"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{chapter_color}", fontcolor={font_color}, penwidth=3, fontsize={heading_font_size}, tooltip="{tooltip_title}"];')
        else:
            if node_url:
                target = "_self" if is_aside_outlink else "_blank"
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{event_color}", fontcolor={font_color}, fontsize={base_font_size}, href="{node_url}", target="{target}", tooltip="{tooltip_title}"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{event_color}", fontcolor={font_color}, fontsize={base_font_size}, tooltip="{tooltip_title}"];')

    dot_lines.append('')

    for notion_id, node in nodes.items():
        source_dot_id = notion_id_to_dot_id[notion_id]
        for next_notion_id in node.next_events:
            if next_notion_id in notion_id_to_dot_id:
                target_dot_id = notion_id_to_dot_id[next_notion_id]
                dot_lines.append(f'    {source_dot_id} -> {target_dot_id};')

    dot_lines.append('}')
    return '\n'.join(dot_lines)


def display_interactive_flowchart(
    nodes: Dict[str, EventNode],
    chapter_name: str = "",
    aside_mapping: Dict[str, List[str]] = None,
    current_entries: List = None,
    aside_heading_titles_by_aside: Dict[str, set] = None,
):
    """Renders a Graphviz flowchart with clickable nodes using st.graphviz_chart()."""
    if not nodes:
        st.warning("No events found for this chapter.")
        return

    try:
        dot_source = create_graphviz_flowchart(
            nodes,
            chapter_name,
            aside_mapping,
            current_entries=current_entries,
            aside_heading_titles_by_aside=aside_heading_titles_by_aside,
        )
        st.graphviz_chart(dot_source, use_container_width=True)


    except Exception as e:
        st.error(f"Error rendering timeline: {e}")
        for node in nodes.values():
            if node.url:
                st.markdown(f"• [{node.title}]({node.url})")
            else:
                st.markdown(f"• {node.title}")


def main():
    st.set_page_config(
        page_title="Timeline",
        page_icon="📅",
        layout="wide"
    )
    
    # Check for URL parameters to set initial chapter selection
    query_params = st.query_params
    url_chapter = query_params.get("chapter", None)
    if url_chapter:
        # URL decode the chapter name
        url_chapter = url_chapter.replace('%20', ' ')
    
    database_id = os.getenv("TIMELINE_DATABASE_ID")
    
    if not database_id:
        st.error("TIMELINE_DATABASE_ID not found in environment variables.")
        st.stop()

    # Top-level refresh: poll Notion only when pressed; otherwise use local snapshot
    refresh_clicked = st.button(
        "🔄 Fetch fresh data",
        help="Poll Notion now and update the local snapshot (otherwise, load from local cache)",
        use_container_width=False,
    )

    # Build and cache the full model (single hash and cache entry)
    with st.spinner("Loading timeline model…"):
        if refresh_clicked:
            # Force rebuild: clear memoised cache entry first, to avoid returning stale value
            st.cache_data.clear()
            model = build_timeline_model(database_id, force_refresh=True)
        else:
            model = build_timeline_model(database_id, force_refresh=False)

    available_chapters = model["chapters"]
    aside_chapters = model["aside_chapters"]
    chapter_aside_mapping = model["chapter_aside_mapping"]

    if not available_chapters:
        st.error("No chapters found in database.")
        st.stop()

    # Create hierarchical chapter list for dropdown
    chapter_options = []
    chapter_display_names = []
    for main_chapter in available_chapters:
        chapter_options.append(main_chapter)
        chapter_display_names.append(main_chapter)
        if main_chapter in chapter_aside_mapping:
            for aside_chapter in sorted(chapter_aside_mapping[main_chapter]):
                chapter_options.append(aside_chapter)
                chapter_display_names.append(f"    ↳ {aside_chapter}")

    initial_index = 0
    if url_chapter:
        for i, option in enumerate(chapter_options):
            if option == url_chapter:
                initial_index = i
                break

    selected_index = st.selectbox(
        "📖 Select Chapter:",
        range(len(chapter_options)),
        format_func=lambda i: chapter_display_names[i],
        index=initial_index
    )
    selected_chapter = chapter_options[selected_index]

    # Pull precomputed entries and nodes
    entries = model["entries_by_chapter"].get(selected_chapter, [])
    nodes = model["nodes_by_chapter"].get(selected_chapter, {})

    # Precompute aside heading titles only for asides related to this chapter
    related_asides = chapter_aside_mapping.get(selected_chapter, [])
    aside_heading_titles_by_aside = {a: model["headings_by_aside"].get(a, set()) for a in related_asides}

    if nodes:
        display_interactive_flowchart(
            nodes,
            selected_chapter,
            chapter_aside_mapping,
            current_entries=entries,
            aside_heading_titles_by_aside=aside_heading_titles_by_aside,
        )
    else:
        st.warning(f"No events found for {selected_chapter}")

if __name__ == "__main__":
    main()
