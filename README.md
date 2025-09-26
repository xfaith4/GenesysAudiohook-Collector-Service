# Genesys AudioHook Event Collector - Streamlined Version

A focused, efficient collector service for **Genesys Cloud AudioHook operational events**. This streamlined version consolidates the original complex codebase into a single, maintainable solution that provides:

- **Real-time AudioHook event collection** from Genesys Cloud
- **Readable JSONL output file** with automatic rotation
- **AudioHook-specific event validation** and formatting
- **Optional Elasticsearch integration** for search and analytics
- **Built-in health monitoring** and statistics
- **Docker containerization** for easy deployment

## What It Does

1. **Authenticates** to Genesys Cloud using OAuth2 client credentials
2. **Subscribes** to AudioHook operational event topics via WebSocket
3. **Validates and filters** events to ensure they are AudioHook-related
4. **Writes readable events** to a continuously updated JSONL file
5. **Optionally sends** events to Elasticsearch for indexing
6. **Provides health endpoints** for monitoring

## Quick Start

### 1. Configuration
Copy the example configuration:
```bash
cp .env.example .env
```

Edit `.env` with your Genesys Cloud credentials:
```bash
GENESYS_ENV=usw2.pure.cloud
GENESYS_CLIENT_ID=your-client-id
GENESYS_CLIENT_SECRET=your-client-secret
OUTPUT_FILE=./audiohook_events.jsonl
```

### 2. Run with Docker (Recommended)
```bash
# Build and run
docker-compose up --build -d

# Check logs
docker-compose logs -f

# Check health
curl http://localhost:8077/health
```

### 3. Run Directly with Python
```bash
# Install dependencies
pip install aiohttp

# Run collector
python audiohook_collector.py
```

## Output Format

Events are written to `audiohook_events.jsonl` in readable JSONL format:
```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "event_type": "audiohook_operational",
  "event_id": "AUDIOHOOK-0001",
  "event_name": "AudioHook integration error",
  "description": "The provisioned server URI is invalid.",
  "conversation_id": "34c18827-77a6-4970-ad66-6f2966c85bad",
  "entity_type": "integration",
  "entity_id": "0f8f91f9-a27d-4ddf-9026-7e1e3a8d73a6",
  "entity_name": "AudioHook Integration Name",
  "version": "1.0",
  "topic": "platform.integration.audiohook",
  "channel": "streaming-channel-12345",
  "raw_event": { ... }
}
```

## AudioHook Event Types Supported

Based on the [Genesys AudioHook operational event catalog](https://developer.genesys.cloud/platform/operational-event-catalog/audiohook/), this collector handles:

- **AUDIOHOOK-0001**: Integration configuration errors
- **AUDIOHOOK-0002**: Connection timeouts
- **AUDIOHOOK-0003**: Authentication failures
- **All other AUDIOHOOK-*** events** as they are added

## Configuration Options

### Required Settings
- `GENESYS_ENV`: Your Genesys Cloud environment (e.g., `usw2.pure.cloud`)
- `GENESYS_CLIENT_ID`: OAuth2 client ID
- `GENESYS_CLIENT_SECRET`: OAuth2 client secret

### Output Settings  
- `OUTPUT_FILE`: Path to JSONL output file (default: `./audiohook_events.jsonl`)
- `MAX_FILE_SIZE`: File size before rotation in bytes (default: 10MB)
- `BACKUP_COUNT`: Number of rotated files to keep (default: 5)
- `CONSOLE_OUTPUT`: Also log to console (default: `true`)

### Optional Elasticsearch
- `ELASTIC_URL`: Elasticsearch cluster URL (leave blank to disable)
- `ELASTIC_AUTH`: Authentication (`user:pass` or `Bearer token`)
- `ELASTIC_INDEX`: Index name (default: `genesys-audiohook`)
- `BULK_SIZE`: Batch size for bulk indexing (default: 50)

### Topics Configuration
- `TOPICS_FILE`: Custom topics JSON file (default: `./topics.json`)

### HTTP Status Server
- `HTTP_HOST`: HTTP server bind address (default: `0.0.0.0`)
- `HTTP_PORT`: HTTP server port (default: `8077`)

## Monitoring

### Health Check
```bash
curl http://localhost:8077/health
```
Returns status, statistics, and current topics.

### Recent Events
```bash
curl http://localhost:8077/events
```
Returns the last 50 processed events.

### Log Monitoring
The collector outputs structured JSON logs:
```bash
# Follow logs in Docker
docker-compose logs -f

# Monitor output file
tail -f audiohook_events.jsonl
```

## Key Improvements from Original

1. **Consolidated Code**: Reduced from 491 lines to ~450 lines of focused functionality
2. **AudioHook-Specific**: Proper validation and handling of AudioHook operational events  
3. **Readable Output**: JSONL format with human-readable structure and automatic rotation
4. **Simplified Configuration**: Fewer, clearer configuration options
5. **Better Error Handling**: Focused error handling for AudioHook scenarios
6. **Streamlined Dependencies**: Only requires `aiohttp`
7. **Improved Monitoring**: Clear health endpoints and statistics

## Troubleshooting

### No Events Received
1. Check your Genesys Cloud credentials
2. Verify OAuth client has notification permissions
3. Check if AudioHook integrations are configured in your org
4. Review topics in `topics.json`

### File Not Updating  
1. Check file permissions for `OUTPUT_FILE` directory
2. Monitor console logs for write errors
3. Verify disk space availability

### Connection Issues
1. Verify `GENESYS_ENV` matches your organization
2. Check firewall rules for WebSocket connections
3. Monitor reconnection attempts in logs

## Development

The collector is designed as a single, focused Python file for easy maintenance:
- `audiohook_collector.py` - Main collector class and logic
- `.env.example` - Configuration template
- `topics.json` - AudioHook topic definitions
- `example_audiohook_events.jsonl` - Sample output format

## Previous Version

The original `collector.py` is preserved for reference but the new `audiohook_collector.py` is recommended for all new deployments.
