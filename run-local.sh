#!/bin/bash

# Build and run Streamlit Timeline locally with Docker
# Usage: ./run-local.sh

set -e

echo "�� Building Streamlit Timeline Docker image..."
docker build -t streamlit-timeline .

echo "�� Starting container..."
echo "📱 App will be available at: http://localhost:8501"
echo "⏹️  Press Ctrl+C to stop"

docker run -p 8501:8501 --env-file .env streamlit-timeline
