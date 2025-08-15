import streamlit as st
import os
from dotenv import load_dotenv

from timeline import build_timeline_model, display_interactive_flowchart

load_dotenv()

def main():
    st.set_page_config(
        page_title="Timeline",
        page_icon="📅",
        layout="wide"
    )

    query_params = st.query_params
    url_chapter = query_params.get("chapter", None)
    if url_chapter:
        url_chapter = url_chapter.replace('%20', ' ')

    database_id = os.getenv("TIMELINE_DATABASE_ID")

    if not database_id:
        st.error("TIMELINE_DATABASE_ID not found in environment variables.")
        st.stop()

    refresh_clicked = st.button(
        "🔄 Fetch fresh data",
        help="Poll Notion now and update the local snapshot (otherwise, load from local cache)",
        use_container_width=False,
    )

    with st.spinner("Loading timeline model…"):
        if refresh_clicked:
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

    entries = model["entries_by_chapter"].get(selected_chapter, [])
    nodes = model["nodes_by_chapter"].get(selected_chapter, {})

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

# Re-export symbols for backward-compatibility with tests and callers
from timeline.cache import load_snapshot_from_disk, save_snapshot_to_disk
from timeline.model import (
    EventNode,
    extract_property_value,
    parse_entries_to_nodes,
    build_model_from_entries,
    build_timeline_model,
)
from timeline.graph import create_graphviz_flowchart, display_interactive_flowchart

if __name__ == "__main__":
    main()