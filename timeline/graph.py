# timeline/graph.py
import textwrap
import streamlit as st
from typing import Dict, List
from .model import EventNode, extract_property_value

def create_graphviz_flowchart(
    nodes: Dict[str, EventNode],
    chapter_name: str = "",
    aside_mapping: Dict[str, List[str]] = None,
    current_entries: List = None,
    aside_heading_titles_by_aside: Dict[str, set] = None,
) -> str:
    """Generate a Graphviz DOT string for use with st.graphviz_chart()."""
    notion_id_to_dot_id = {node_id: f"node_{i}" for i, node_id in enumerate(nodes.keys())}

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
        chapter_color = "#ffffff"
        event_color = "#ffffff"
        edge_color = "#666666"
        font_color = "black"

    clean_chapter_name = ''.join(c if c.isalnum() else '_' for c in chapter_name) if chapter_name else "timeline"
    graph_name = f"timeline_{clean_chapter_name}"

    node_count = len(nodes)
    is_simple_graph = node_count <= 5
    is_aside = chapter_name.startswith("Aside") if chapter_name else False

    if is_simple_graph or is_aside:
        dot_lines = [
            f'digraph {graph_name} {{',
            '    rankdir=TB;',
            '    node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, width=3, height=1.2, margin=0.2];',
            '    graph [bgcolor=transparent, nodesep=0.5, ranksep=0.8, size="10,8!", ratio=fill];',
            f'    edge [color="{edge_color}", penwidth=1, arrowsize=0.6];',
            ''
        ]
    else:
        dot_lines = [
            f'digraph {graph_name} {{',
            '    rankdir=TB;',
            '    node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, margin=0.2];',
            '    graph [bgcolor=transparent, nodesep=0.3, ranksep=0.5, ratio=auto, margin=0.2];',
            f'    edge [color="{edge_color}", penwidth=1, arrowsize=0.6];',
            ''
        ]

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
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="#f5f5f5", fontcolor={font_color}, penwidth=1, fontsize={heading_font_size}, href="{node_url}", target="{target}", tooltip="{tooltip_title}", color="#000000", fontweight="bold"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="#f5f5f5", fontcolor={font_color}, penwidth=1, fontsize={heading_font_size}, tooltip="{tooltip_title}", color="#000000", fontweight="bold"];')
        else:
            if node_url:
                target = "_self" if is_aside_outlink else "_blank"
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{event_color}", fontcolor={font_color}, fontsize={base_font_size}, href="{node_url}", target="{target}", tooltip="{tooltip_title}", color="{edge_color}"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{event_color}", fontcolor={font_color}, fontsize={base_font_size}, tooltip="{tooltip_title}", color="{edge_color}"];')

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
        
        # Add CSS for zoom functionality
        st.markdown("""
        <style>
        .graphviz-container {
            overflow: auto;
            max-height: 80vh;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Render with zoom support
        st.graphviz_chart(dot_source, use_container_width=False)
        
    except Exception as e:
        st.error(f"Error rendering timeline: {e}")
        for node in nodes.values():
            if node.url:
                st.markdown(f"• [{node.title}]({node.url})")
            else:
                st.markdown(f"• {node.title}")