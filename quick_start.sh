#!/bin/bash
# Quick start script for AudioHook Collector

echo "=== Genesys AudioHook Collector - Quick Start ==="

# Check if config exists
if [ ! -f ".env" ]; then
    echo "Creating configuration file from template..."
    cp .env.example .env
    echo "Please edit .env with your Genesys Cloud credentials before running!"
    echo ""
fi

# Check if Python dependencies are available
echo "Checking dependencies..."
python3 -c "import aiohttp" 2>/dev/null || {
    echo "Installing required dependencies..."
    pip install aiohttp
}

echo "Dependencies OK!"
echo ""

# Show current configuration
echo "Current configuration:"
echo "- Output file: ${OUTPUT_FILE:-./audiohook_events.jsonl}"
echo "- HTTP port: ${HTTP_PORT:-8077}"
echo "- Elasticsearch: ${ELASTIC_URL:-disabled}"
echo ""

# Offer to start
read -p "Start AudioHook collector now? (y/n): " -n 1 -r
echo
if [[ $REPLYY =~ ^[Yy]$ ]]; then
    echo "Starting AudioHook collector..."
    python3 audiohook_collector.py
else
    echo "To start manually: python3 audiohook_collector.py"
    echo "Health check: curl http://localhost:8077/health"
    echo "View events: tail -f audiohook_events.jsonl"
fi