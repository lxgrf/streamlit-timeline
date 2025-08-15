# timeline/notion.py
import os
import streamlit as st
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

@st.cache_resource
def get_notion_client():
    """Initialise Notion client with API key from environment"""
    notion_key = os.getenv("NOTION_KEY")
    if not notion_key:
        st.error("NOTION_KEY not found in environment variables. Please check your .env file.")
        st.stop()
    return Client(auth=notion_key)

@st.cache_data(ttl=300)
def get_all_database_entries(_notion_client, database_id):
    """Get ALL entries from the database once, with caching"""
    try:
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