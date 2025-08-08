# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Resolve and cache the environment (honours lockfile)
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
RUN apt-get update && apt-get install -y --no-install-recommends graphviz && rm -rf /var/lib/apt/lists/*

# Now copy the application code
COPY . .

# Streamlit will listen on this port; Cloudflared maps to it
EXPOSE 8501

ENV PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Run the app via uv in a reproducible environment
CMD ["uv", "run", "--frozen", "streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=8501"]