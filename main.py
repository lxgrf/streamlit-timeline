import streamlit as st
import os
from notion_client import Client
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
import json
from typing import Dict, List, Set, Optional
import graphviz
import textwrap

# Load environment variables
load_dotenv()

console = Console()

def get_notion_client():
    """Initialise Notion client with API key from environment"""
    notion_key = os.getenv("NOTION_KEY")
    if not notion_key:
        st.error("NOTION_KEY not found in environment variables. Please check your .env file.")
        st.stop()
    return Client(auth=notion_key)

def get_database_schema(notion_client, database_id):
    """Retrieve database schema to understand property types"""
    try:
        response = notion_client.databases.retrieve(database_id=database_id)
        return response.get("properties", {})
    except Exception as e:
        st.error(f"Error retrieving database schema: {str(e)}")
        return {}

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

def get_all_chapters(all_entries):
    """Get all unique chapter values from cached entries"""
    chapters = set()
    for entry in all_entries:
        chapter_prop = entry.get("properties", {}).get("Chapter", {})
        if chapter_prop.get("type") == "select" and chapter_prop.get("select"):
            chapter_value = chapter_prop["select"].get("name", "")
            if chapter_value:
                chapters.add(chapter_value)
    
    # Filter and order: Prologue first, then chapters in order
    filtered_chapters = []
    
    # Add Prologue first if it exists
    if "Prologue" in chapters:
        filtered_chapters.append("Prologue")
    
    # Add numbered chapters in sorted order
    chapter_list = [ch for ch in sorted(chapters) if ch.startswith("Chapter")]
    filtered_chapters.extend(chapter_list)
    
    return filtered_chapters

def get_database_entries(all_entries, chapter_filter="Prologue"):
    """Filter cached entries by chapter"""
    filtered_entries = []
    for entry in all_entries:
        chapter_prop = entry.get("properties", {}).get("Chapter", {})
        if chapter_prop.get("type") == "select" and chapter_prop.get("select"):
            chapter_value = chapter_prop["select"].get("name", "")
            if chapter_value == chapter_filter:
                filtered_entries.append(entry)
    
    return filtered_entries

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

def create_graphviz_flowchart(nodes: Dict[str, EventNode], chapter_name: str = "") -> str:
    """Generate a Graphviz DOT string for use with st.graphviz_chart()."""
    
    # Create a mapping from notion_id to simple node IDs for DOT
    notion_id_to_dot_id = {node_id: f"node_{i}" for i, node_id in enumerate(nodes.keys())}
    
    # Detect theme for adaptive colors
    # Check if we're in dark mode by looking at Streamlit's theme
    try:
        # Try to detect theme from Streamlit config
        import streamlit.config as config
        theme = config.get_option("theme.base")
        is_dark_mode = theme == "dark"
    except:
        # Fallback: assume light mode if we can't detect
        is_dark_mode = False
    
    # Adaptive color scheme
    if is_dark_mode:
        # Dark mode: lighter colors for better contrast
        chapter_color = "#5dade2"      # Light blue
        event_color = "#85c1e9"        # Lighter blue
        edge_color = "#ffffff"         # White arrows
        font_color = "black"           # Black text on light backgrounds
    else:
        # Light mode: darker colors
        chapter_color = "#2c3e50"      # Dark slate
        event_color = "#34495e"        # Slate gray  
        edge_color = "#2c3e50"         # Dark arrows
        font_color = "white"           # White text on dark backgrounds
    
    # Build DOT string manually with unique graph name to prevent caching issues
    # Clean the chapter name to only include valid DOT identifier characters
    clean_chapter_name = ''.join(c if c.isalnum() else '_' for c in chapter_name) if chapter_name else "timeline"
    graph_name = f"timeline_{clean_chapter_name}"
    dot_lines = [
        f'digraph {graph_name} {{',
        '    rankdir=TB;',
        '    node [shape=box, style=filled, fontname="Helvetica", fontsize=14];',
        '    graph [bgcolor=transparent, nodesep=0.3, ranksep=0.8];',
        f'    edge [color="{edge_color}"];',
        f'    label="{chapter_name}";',
        f'    labelloc="t";',
        f'    labelfontsize=18;',
        ''
    ]
    
    # Add nodes with proper styling and clickable URLs
    for notion_id, node in nodes.items():
        dot_id = notion_id_to_dot_id[notion_id]
        
        # Wrap long titles for better readability
        wrapped_title = textwrap.fill(node.title, width=30)
        # Escape quotes, backslashes, and other problematic characters for DOT format
        safe_title = (wrapped_title
                     .replace('\\', '\\\\')  # Escape backslashes first
                     .replace('"', '\\"')    # Escape quotes
                     .replace('\n', '\\n')   # Escape newlines
                     .replace('\r', '')      # Remove carriage returns
                     .replace('\t', ' ')     # Replace tabs with spaces
                     )
        
        # Different styling for chapter headings
        if node.is_chapter_heading:
            if node.url:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{chapter_color}", fontcolor={font_color}, penwidth=3, fontsize=16, href="{node.url}", target="_blank"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{chapter_color}", fontcolor={font_color}, penwidth=3, fontsize=16];')
        else:
            if node.url:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{event_color}", fontcolor={font_color}, href="{node.url}", target="_blank"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="{event_color}", fontcolor={font_color}];')
    
    dot_lines.append('')
    
    # Add edges based on next_events relationships
    for notion_id, node in nodes.items():
        source_dot_id = notion_id_to_dot_id[notion_id]
        for next_notion_id in node.next_events:
            if next_notion_id in notion_id_to_dot_id:
                target_dot_id = notion_id_to_dot_id[next_notion_id]
                dot_lines.append(f'    {source_dot_id} -> {target_dot_id};')
    
    dot_lines.append('}')
    
    return '\n'.join(dot_lines)

def display_interactive_flowchart(nodes: Dict[str, EventNode], chapter_name: str = ""):
    """Renders a Graphviz flowchart with clickable nodes using st.graphviz_chart()."""
    
    if not nodes:
        st.warning("No events found for this chapter.")
        return
        
    try:
        # Generate the DOT string for Graphviz
        dot_source = create_graphviz_flowchart(nodes, chapter_name)
        
        # Display using Streamlit's native graphviz_chart with full width
        st.graphviz_chart(dot_source, use_container_width=True)

    except Exception as e:
        st.error(f"Error rendering timeline: {e}")
        
        # Fallback to simple list
        for node in nodes.values():
            if node.url:
                st.markdown(f"• [{node.title}]({node.url})")
            else:
                st.markdown(f"• {node.title}")


def display_entry(entry):
    """Display a single database entry in a readable format"""
    
    title = "Untitled"
    properties = entry.get("properties", {})
    
    for prop_name, prop_data in properties.items():
        if prop_name.lower() in ["title", "name", "event"] and prop_data.get("type") == "title":
            title_content = prop_data.get("title", [])
            if title_content:
                title = title_content[0].get("plain_text", "Untitled")
            break
    
    with st.expander(f"📅 {title}"):
        st.json(properties, expanded=False)
        
        if properties:
            st.write("**Properties:**")
            for prop_name, prop_data in properties.items():
                prop_type = prop_data.get("type")
                
                if prop_type == "rich_text" and prop_data.get("rich_text"):
                    text_content = " ".join([item.get("plain_text", "") for item in prop_data["rich_text"]])
                    if text_content.strip():
                        st.write(f"- **{prop_name}:** {text_content}")
                
                elif prop_type == "date" and prop_data.get("date"):
                    date_info = prop_data["date"]
                    start_date = date_info.get("start", "")
                    end_date = date_info.get("end", "")
                    date_display = start_date
                    if end_date and end_date != start_date:
                        date_display += f" to {end_date}"
                    st.write(f"- **{prop_name}:** {date_display}")
                
                elif prop_type == "select" and prop_data.get("select"):
                    select_value = prop_data["select"].get("name", "")
                    if select_value:
                        st.write(f"- **{prop_name}:** {select_value}")
                
                elif prop_type == "checkbox":
                    checkbox_value = prop_data.get("checkbox", False)
                    st.write(f"- **{prop_name}:** {'✅' if checkbox_value else '❌'}")
                
                elif prop_type == "url" and prop_data.get("url"):
                    url_value = prop_data["url"]
                    st.write(f"- **{prop_name}:** [🔗 Link]({url_value})")
                
                elif prop_type == "relation" and prop_data.get("relation"):
                    relations = prop_data["relation"]
                    if relations:
                        relation_count = len(relations)
                        st.write(f"- **{prop_name}:** {relation_count} related item(s)")

def main():
    st.set_page_config(
        page_title="Timeline",
        page_icon="📅",
        layout="wide"
    )
    
    database_id = os.getenv("TIMELINE_DATABASE_ID")
    
    if not database_id:
        st.error("TIMELINE_DATABASE_ID not found in environment variables.")
        st.stop()
    
    notion_client = get_notion_client()
    
    # Load ALL database entries once (cached for 5 minutes)
    with st.spinner("Loading database..."):
        all_entries = get_all_database_entries(notion_client, database_id)
    
    if not all_entries:
        st.error("No entries found in database.")
        st.stop()
    
    # Get available chapters from cached data
    available_chapters = get_all_chapters(all_entries)
    
    if not available_chapters:
        st.error("No chapters found in database.")
        st.stop()
    
    # Chapter navigation in top bar
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_chapter = st.selectbox(
            "📖 Select Chapter:",
            available_chapters,
            index=0  # Prologue is now first in the list
        )
    with col2:
        st.write("")  # Empty space for alignment
    
    # Get entries for selected chapter from cached data
    entries = get_database_entries(all_entries, selected_chapter)
    
    if entries:
        nodes = parse_entries_to_nodes(entries)
        display_interactive_flowchart(nodes, selected_chapter)
    else:
        st.warning(f"No events found for {selected_chapter}")

if __name__ == "__main__":
    main()
