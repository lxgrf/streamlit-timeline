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

def get_database_entries(notion_client, database_id, chapter_filter="Prologue"):
    """Retrieve database entries filtered by Chapter column"""
    
    try:
        # Query the database with Chapter filter (using select type)
        response = notion_client.databases.query(
            database_id=database_id,
            filter={
                "property": "Chapter",
                "select": {
                    "equals": chapter_filter
                }
            }
        )
        
        return response["results"]
    
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

def create_graphviz_flowchart(nodes: Dict[str, EventNode]) -> str:
    """Generate a Graphviz DOT string for use with st.graphviz_chart()."""
    
    # Create a mapping from notion_id to simple node IDs for DOT
    notion_id_to_dot_id = {node_id: f"node_{i}" for i, node_id in enumerate(nodes.keys())}
    
    # Build DOT string manually
    dot_lines = [
        'digraph {',
        '    rankdir=TB;',
        '    node [shape=box, style=filled, fontname="Helvetica", fontsize=12];',
        '    graph [bgcolor=transparent];',
        ''
    ]
    
    # Add nodes with proper styling and clickable URLs
    for notion_id, node in nodes.items():
        dot_id = notion_id_to_dot_id[notion_id]
        
        # Wrap long titles for better readability
        wrapped_title = textwrap.fill(node.title, width=30)
        # Escape quotes and backslashes for DOT format
        safe_title = wrapped_title.replace('"', '\\"').replace('\\', '\\\\')
        
        # Different styling for chapter headings
        if node.is_chapter_heading:
            if node.url:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="#1976d2", fontcolor=white, penwidth=3, fontsize=14, href="{node.url}", target="_blank"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="#1976d2", fontcolor=white, penwidth=3, fontsize=14];')
        else:
            if node.url:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="#4a148c", fontcolor=white, href="{node.url}", target="_blank"];')
            else:
                dot_lines.append(f'    {dot_id} [label="{safe_title}", fillcolor="#4a148c", fontcolor=white];')
    
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

def display_interactive_flowchart(nodes: Dict[str, EventNode]):
    """Renders a Graphviz flowchart with clickable nodes using st.graphviz_chart()."""
    
    st.subheader("📊 Event Timeline")
    st.info("💡 Click any node in the diagram to open its URL in a new tab.")
    
    if not nodes:
        st.warning("No events found for this chapter to create a flowchart.")
        return
        
    try:
        # Generate the DOT string for Graphviz
        dot_source = create_graphviz_flowchart(nodes)
        
        # Display using Streamlit's native graphviz_chart
        st.graphviz_chart(dot_source, use_container_width=True)
        
        st.markdown("---")
        st.info("🎯 **Legend:** Blue nodes are chapter headings, purple nodes are regular events. All nodes with URLs are clickable and open in new tabs.")

    except Exception as e:
        st.error(f"An error occurred while rendering the flowchart: {e}")
        st.warning("Falling back to a simple list display.")
        
        for node in nodes.values():
            icon = "🏛️" if node.is_chapter_heading else "📅"
            if node.url:
                st.markdown(f"*   {icon} [{node.title}]({node.url})")
            else:
                st.markdown(f"*   {icon} {node.title} (No URL)")


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
        page_title="Timeline from Notion",
        page_icon="📅",
        layout="wide"
    )
    
    st.title("📅 Timeline from Notion")
    st.write("Retrieving events from Notion database, filtered by Chapter = 'Prologue'")
    
    database_id = os.getenv("TIMELINE_DATABASE_ID")
    
    if not database_id:
        st.error("TIMELINE_DATABASE_ID not found in environment variables. Please check your .env file.")
        st.info("Make sure to set both NOTION_KEY and TIMELINE_DATABASE_ID in your .env file")
        st.stop()
    
    st.sidebar.header("Configuration")
    st.sidebar.write(f"**Database ID:** `{database_id[:10]}...`")
    st.sidebar.write("**Chapter Filter:** Prologue")
    
    with st.spinner("Connecting to Notion..."):
        notion_client = get_notion_client()
    
    with st.expander("🔍 Database Schema (for debugging)", expanded=False):
        schema = get_database_schema(notion_client, database_id)
        if schema:
            st.write("**Available Properties:**")
            for prop_name, prop_info in schema.items():
                prop_type = prop_info.get("type", "unknown")
                st.write(f"- **{prop_name}:** `{prop_type}`")
                
                if prop_type == "select" and "select" in prop_info:
                    options = prop_info["select"].get("options", [])
                    if options:
                        option_names = [opt.get("name", "") for opt in options]
                        st.write(f"  - Options: {', '.join(option_names)}")
        else:
            st.write("Could not retrieve schema")
    
    with st.spinner("Retrieving database entries..."):
        entries = get_database_entries(notion_client, database_id, "Prologue")
    
    if entries:
        st.success(f"Found {len(entries)} entries with Chapter = 'Prologue'")
        
        with st.spinner("Building flowchart..."):
            nodes = parse_entries_to_nodes(entries)
        
        display_interactive_flowchart(nodes)
        
        with st.expander("📋 Detailed Entry Information", expanded=False):
            st.write("Raw entry data for debugging:")
            for i, entry in enumerate(entries):
                display_entry(entry)
    else:
        st.warning("No entries found with Chapter = 'Prologue'")
        st.info("Let's try to debug this:")
        
        with st.spinner("Checking what entries exist in the database..."):
            try:
                response = notion_client.databases.query(
                    database_id=database_id,
                    page_size=5
                )
                all_entries = response.get("results", [])
                
                if all_entries:
                    st.write(f"Found {len(all_entries)} entries in database (showing first 5):")
                    
                    chapter_values = set()
                    for entry in all_entries:
                        chapter_prop = entry.get("properties", {}).get("Chapter", {})
                        if chapter_prop.get("type") == "select" and chapter_prop.get("select"):
                            chapter_value = chapter_prop["select"].get("name", "")
                            if chapter_value:
                                chapter_values.add(chapter_value)
                    
                    if chapter_values:
                        st.write(f"**Chapter values found:** {', '.join(sorted(chapter_values))}")
                    else:
                        st.write("No Chapter values found in sample entries")
                        
                    with st.expander("Sample entry structure"):
                        st.json(all_entries[0], expanded=False)
                else:
                    st.write("No entries found in database at all")
                    
            except Exception as e:
                st.error(f"Error checking database contents: {str(e)}")

if __name__ == "__main__":
    main()
