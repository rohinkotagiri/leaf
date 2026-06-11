#!/usr/bin/env bash
# setup.sh — Pull required Ollama models for PrivateMailAI
#
# Usage: ./scripts/setup.sh
#
# Prerequisites: Ollama must be running (either via Docker or natively)

set -euo pipefail

OLLAMA_HOST="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"

echo "╔══════════════════════════════════════════════╗"
echo "║     PrivateMailAI — Model Setup Script       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Check if Ollama is reachable
echo "→ Checking Ollama at ${OLLAMA_HOST}..."
if ! curl -sf "${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; then
    echo "✗ Ollama is not reachable at ${OLLAMA_HOST}"
    echo "  Start Ollama first: docker compose up -d"
    exit 1
fi
echo "✓ Ollama is running"
echo ""

# Models to pull
MODELS=(
    "mistral:7b"
    "llama3.2:3b"
    "nomic-embed-text"
)

for model in "${MODELS[@]}"; do
    echo "→ Pulling ${model}..."
    if ollama pull "${model}"; then
        echo "✓ ${model} ready"
    else
        echo "✗ Failed to pull ${model}"
        exit 1
    fi
    echo ""
done

echo "═══════════════════════════════════════════════"
echo "All models pulled successfully!"
echo ""
echo "Verify with: ollama list"
echo "═══════════════════════════════════════════════"
