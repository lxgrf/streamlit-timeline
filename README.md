# Streamlit Timeline

An interactive Streamlit app that visualises a narrative timeline sourced from a Notion database. It builds a chapter/aside model and renders an interactive flowchart using Graphviz, including internal navigation between main chapters and their related asides.

## Features

- **Notion integration**: Fetches all entries (with pagination) from a Notion database
- **Model building**: Groups entries into chapters and asides, derives relationships, and maps chapters to related asides by intersecting titles
- **Interactive flowchart**: Clickable nodes; aside outlinks navigate within the app via URL parameters
- **Local snapshot cache**: Persists the fetched entries to disk to avoid repeated network calls
- **Dark/light theme aware**: Adapts Graphviz colours to Streamlit's theme

## Architecture

- `main.py`: Thin Streamlit UI and entrypoint
- `timeline/notion.py`: Notion client and database fetch with caching
- `timeline/cache.py`: Load/save local snapshot JSON with versioning
- `timeline/model.py`: Domain model (`EventNode`), property extraction, entries → nodes, and full timeline model builder
- `timeline/graph.py`: Graphviz DOT generation and Streamlit rendering helper
- `timeline/__init__.py`: Tidy exports

## Requirements

- Python 3.13+
- A Notion integration token and database ID
- Graphviz system package (for local development; already included in the Docker image)

## Environment Variables

Create a `.env` file next to `main.py`:

```bash
NOTION_KEY=your_notion_integration_token
TIMELINE_DATABASE_ID=your_notion_database_id
# Optional: override cache location
# TIMELINE_CACHE_PATH=.timeline_model_snapshot.json
```

**Never commit secrets.**

## Local Development (uv)

Install dependencies:

```bash
uv sync
```

Run the app:

```bash
uv run streamlit run main.py
```

Run tests:

```bash
uv run pytest
```

## Docker

### Build and Run Locally

```bash
docker build -t streamlit-timeline .
docker run -p 8501:8501 --env-file .env streamlit-timeline
```

### Using Docker Compose

The provided compose file references a published image:

```bash
docker compose up -d
```

To build locally via Compose, create `docker-compose.override.yml`:

```yaml
services:
  app:
    build: .
    image: streamlit-timeline:local
    pull_policy: never
```

Then:

```bash
docker compose up --build -d
```

## Notion Database Schema

The app expects the following properties per entry:

- **Name/Title**: title
- **URL**: url (optional; used for external links)
- **Chapter**: select (e.g. Prologue, Chapter N, Aside …)
- **Chapter Heading**: checkbox (marks key nodes)
- **Aside Heading**: checkbox (used to link from a main chapter to an aside)
- **Next Event**: relation (forward edges)
- **Prior Event**: relation (back edges)

### Chapter/Aside Mapping

- For each main chapter, any entry marked with **Aside Heading** contributes its title to a set
- For each aside, any entry marked with **Chapter Heading** contributes its title to a set
- An aside is linked to a main chapter if these title sets intersect

## Caching Behaviour

- On first load (or when the refresh button is pressed), all entries are fetched and written to the snapshot at `TIMELINE_CACHE_PATH` (default: `.timeline_model_snapshot.json`)
- On subsequent loads, the model is built from the local snapshot unless you press "🔄 Fetch fresh data"

## URL Navigation

- You can deep-link to a chapter via a query string, e.g.:
  ```
  http://localhost:8501/?chapter=Chapter%205
  ```
- Nodes that act as aside outlinks are rendered with a "🔗" prefix and navigate internally, e.g. `?chapter=Aside%20A`

## Troubleshooting

- **"NOTION_KEY not found"**: ensure `.env` is mounted/visible and contains `NOTION_KEY`
- **No chapters found**: verify `TIMELINE_DATABASE_ID` and that your database has the expected properties
- **Graphviz issues locally**: install the system package (e.g., `brew install graphviz` on macOS)
- **Stale data**: use the "🔄 Fetch fresh data" button to repoll Notion and refresh the snapshot