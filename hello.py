import streamlit as st
import os
from notion_client import Client
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
import json
from typing import Dict, List, Set, Optional

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

def build_flowchart_order(nodes: Dict[str, EventNode]) -> List[str]:
    """Determine the correct order for the flowchart"""
    # Find starting nodes (nodes with no prior events)
    starting_nodes = [node_id for node_id, node in nodes.items() if not node.prior_events]
    
    if not starting_nodes:
        # If no clear starting point, just return all nodes
        return list(nodes.keys())
    
    # Build order using topological sort approach
    visited = set()
    order = []
    
    def visit_node(node_id: str):
        if node_id in visited or node_id not in nodes:
            return
        
        visited.add(node_id)
        order.append(node_id)
        
        # Visit next events
        for next_id in nodes[node_id].next_events:
            if next_id not in visited:
                visit_node(next_id)
    
    # Start from each starting node
    for start_id in starting_nodes:
        visit_node(start_id)
    
    # Add any remaining nodes that weren't connected
    for node_id in nodes:
        if node_id not in visited:
            order.append(node_id)
    
    return order

def create_mermaid_flowchart(nodes: Dict[str, EventNode], order: List[str]) -> str:
    """Generate Mermaid flowchart syntax"""
    
    mermaid_lines = ["flowchart TD"]
    
    # Create node definitions
    for i, node_id in enumerate(order):
        if node_id not in nodes:
            continue
            
        node = nodes[node_id]
        safe_id = f"node_{i}"
        
        # Style based on whether it's a chapter heading
        if node.is_chapter_heading:
            # Chapter headings get a special style (hexagon shape)
            mermaid_lines.append(f'    {safe_id}{{{{{node.title}}}}}')
            mermaid_lines.append(f'    style {safe_id} fill:#e1f5fe,stroke:#01579b,stroke-width:3px')
        else:
            # Regular events (rectangular shape)
            mermaid_lines.append(f'    {safe_id}["{node.title}"]')
            mermaid_lines.append(f'    style {safe_id} fill:#f3e5f5,stroke:#4a148c,stroke-width:2px')
    
    # Create connections
    node_id_to_safe = {node_id: f"node_{i}" for i, node_id in enumerate(order)}
    
    for i, node_id in enumerate(order):
        if node_id not in nodes:
            continue
            
        node = nodes[node_id]
        safe_id = f"node_{i}"
        
        # Connect to next events
        for next_id in node.next_events:
            if next_id in node_id_to_safe:
                next_safe_id = node_id_to_safe[next_id]
                mermaid_lines.append(f'    {safe_id} --> {next_safe_id}')
    
    return "\n".join(mermaid_lines)

def display_interactive_flowchart(nodes: Dict[str, EventNode], order: List[str]):
    """Display the flowchart with interactive features"""
    
    st.subheader("📊 Event Flowchart")
    
    # Generate and display Mermaid flowchart
    mermaid_code = create_mermaid_flowchart(nodes, order)
    
    try:
        # Display the Mermaid diagram
        st.write("**Visual Flowchart:**")
        
        # Try to render the actual Mermaid diagram
        try:
            from antml_tools import create_mermaid_diagram
            # This would be the ideal way, but we'll show both approaches
            pass
        except:
            pass
        
        # Show the mermaid code in an expander for debugging
        with st.expander("View Mermaid Code", expanded=False):
            st.code(mermaid_code, language="mermaid")
            st.info("💡 You can copy this code and paste it into mermaid.live to see the visual diagram")
        
        # Show a structured text representation
        st.write("**Flowchart Structure:**")
        for i, node_id in enumerate(order):
            if node_id not in nodes:
                continue
                
            node = nodes[node_id]
            
            # Display the node with proper styling
            if node.is_chapter_heading:
                st.markdown(f"### 🏛️ **{node.title}** (Chapter Heading)")
            else:
                st.markdown(f"#### 📅 {node.title}")
            
            # Show connections
            if node.next_events:
                next_titles = []
                for next_id in node.next_events:
                    if next_id in nodes:
                        next_titles.append(nodes[next_id].title)
                if next_titles:
                    st.write(f"   ↓ *Next:* {', '.join(next_titles)}")
            
            if node.url:
                st.markdown(f"   🔗 [Open Link]({node.url})")
            
            st.write("---")
        
        # Display clickable event list
        st.subheader("🔗 Interactive Event List")
        st.write("Click on any event below to open its URL:")
        
        # Create columns for better layout
        col1, col2 = st.columns(2)
        
        for i, node_id in enumerate(order):
            if node_id not in nodes:
                continue
                
            node = nodes[node_id]
            col = col1 if i % 2 == 0 else col2
            
            with col:
                # Style the button based on chapter heading
                if node.is_chapter_heading:
                    button_style = "🏛️"  # Special icon for chapter headings
                else:
                    button_style = "📅"
                
                # Create button with URL functionality
                if node.url:
                    try:
                        # Use st.link_button for better UX (Streamlit 1.26+)
                        st.link_button(
                            f"{button_style} {node.title}",
                            node.url,
                            help=f"Open {node.title} in new tab"
                        )
                    except AttributeError:
                        # Fallback for older Streamlit versions
                        st.markdown(f"[{button_style} {node.title}]({node.url})")
                else:
                    st.write(f"{button_style} {node.title} (No URL available)")
        
    except Exception as e:
        st.error(f"Error creating flowchart: {str(e)}")
        st.write("Falling back to simple list view...")
        
        # Simple fallback display
        for node_id in order:
            if node_id not in nodes:
                continue
            node = nodes[node_id]
            
            if node.is_chapter_heading:
                st.markdown(f"### 🏛️ {node.title}")
            else:
                st.markdown(f"- 📅 {node.title}")
            
            if node.url:
                st.markdown(f"  [🔗 Open Link]({node.url})")

def display_entry(entry):
    """Display a single database entry in a readable format"""
    
    # Extract the title (assuming there's a title property)
    title = "Untitled"
    properties = entry.get("properties", {})
    
    # Look for common title properties
    for prop_name, prop_data in properties.items():
        if prop_name.lower() in ["title", "name", "event"] and prop_data.get("type") == "title":
            title_content = prop_data.get("title", [])
            if title_content:
                title = title_content[0].get("plain_text", "Untitled")
            break
    
    # Create a display card for each entry
    with st.expander(f"📅 {title}"):
        st.json(properties, expanded=False)
        
        # Show some key properties in a more readable format
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
    
    # Get environment variables
    database_id = os.getenv("TIMELINE_DATABASE_ID")
    
    if not database_id:
        st.error("TIMELINE_DATABASE_ID not found in environment variables. Please check your .env file.")
        st.info("Make sure to set both NOTION_KEY and TIMELINE_DATABASE_ID in your .env file")
        st.stop()
    
    # Display current configuration
    st.sidebar.header("Configuration")
    st.sidebar.write(f"**Database ID:** `{database_id[:10]}...`")
    st.sidebar.write("**Chapter Filter:** Prologue")
    
    # Get Notion client
    with st.spinner("Connecting to Notion..."):
        notion_client = get_notion_client()
    
    # Show database schema for debugging
    with st.expander("🔍 Database Schema (for debugging)", expanded=False):
        schema = get_database_schema(notion_client, database_id)
        if schema:
            st.write("**Available Properties:**")
            for prop_name, prop_info in schema.items():
                prop_type = prop_info.get("type", "unknown")
                st.write(f"- **{prop_name}:** `{prop_type}`")
                
                # Show select options if it's a select property
                if prop_type == "select" and "select" in prop_info:
                    options = prop_info["select"].get("options", [])
                    if options:
                        option_names = [opt.get("name", "") for opt in options]
                        st.write(f"  - Options: {', '.join(option_names)}")
        else:
            st.write("Could not retrieve schema")
    
    # Retrieve database entries
    with st.spinner("Retrieving database entries..."):
        entries = get_database_entries(notion_client, database_id, "Prologue")
    
    # Display results
    if entries:
        st.success(f"Found {len(entries)} entries with Chapter = 'Prologue'")
        
        # Parse entries into nodes and create flowchart
        with st.spinner("Building flowchart..."):
            nodes = parse_entries_to_nodes(entries)
            flow_order = build_flowchart_order(nodes)
        
        # Display the interactive flowchart
        display_interactive_flowchart(nodes, flow_order)
        
        # Also create and display the actual Mermaid diagram
        st.subheader("🎨 Visual Mermaid Diagram")
        mermaid_code = create_mermaid_flowchart(nodes, flow_order)
        
        # Use create_diagram tool to render the actual Mermaid diagram
        st.write("Here's the interactive visual flowchart:")
        # We'll show this after we create it with the create_diagram tool
        
        # Show detailed entries in an expandable section
        with st.expander("📋 Detailed Entry Information", expanded=False):
            st.write("Raw entry data for debugging:")
            for i, entry in enumerate(entries):
                display_entry(entry)
    else:
        st.warning("No entries found with Chapter = 'Prologue'")
        st.info("Let's try to debug this:")
        
        # Try to get a few entries without filter to see what's available
        with st.spinner("Checking what entries exist in the database..."):
            try:
                response = notion_client.databases.query(
                    database_id=database_id,
                    page_size=5  # Just get a few to examine
                )
                all_entries = response.get("results", [])
                
                if all_entries:
                    st.write(f"Found {len(all_entries)} entries in database (showing first 5):")
                    
                    # Show Chapter values from existing entries
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
                        
                    # Show a sample entry structure
                    with st.expander("Sample entry structure"):
                        st.json(all_entries[0], expanded=False)
                else:
                    st.write("No entries found in database at all")
                    
            except Exception as e:
                st.error(f"Error checking database contents: {str(e)}")

if __name__ == "__main__":
    main()
