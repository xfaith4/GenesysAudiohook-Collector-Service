#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genesys AudioHook Event Collector - Streamlined Version

Focuses specifically on AudioHook operational events as documented at:
https://developer.genesys.cloud/platform/operational-event-catalog/audiohook/

Features:
- Streamlined code structure (single focused class)
- AudioHook-specific event processing and validation
- Readable output file with continuous updates
- Efficient WebSocket handling with auto-reconnect
- Optional Elasticsearch integration
- Built-in health monitoring
"""

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

import aiohttp
from aiohttp import web

# ----------------------- Configuration -----------------------
def getenv_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes', 'on')

# Genesys Cloud Configuration
GENESYS_ENV = os.environ.get('GENESYS_ENV', 'usw2.pure.cloud')
CLIENT_ID = os.environ.get('GENESYS_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('GENESYS_CLIENT_SECRET', '')

# AudioHook Topic Configuration
AUDIOHOOK_TOPICS = [
    'platform.integration.audiohook',
    'platform.operations.audiohook',
    'v2.auditing.integration.audiohook'
]
CUSTOM_TOPICS_FILE = os.environ.get('TOPICS_FILE', './topics.json')
FALLBACK_TOPICS = ['channel.metadata']  # Safe fallback for testing

# Output Configuration
OUTPUT_FILE = os.environ.get('OUTPUT_FILE', './audiohook_events.jsonl')
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '10485760'))  # 10MB default
BACKUP_COUNT = int(os.environ.get('BACKUP_COUNT', '5'))
CONSOLE_OUTPUT = getenv_bool('CONSOLE_OUTPUT', True)

# Elasticsearch Configuration (Optional)
ELASTIC_URL = os.environ.get('ELASTIC_URL', '')
ELASTIC_AUTH = os.environ.get('ELASTIC_AUTH', '')
ELASTIC_INDEX = os.environ.get('ELASTIC_INDEX', 'genesys-audiohook')
BULK_SIZE = int(os.environ.get('BULK_SIZE', '50'))

# HTTP Status Server
HTTP_PORT = int(os.environ.get('HTTP_PORT', '8077'))
HTTP_HOST = os.environ.get('HTTP_HOST', '0.0.0.0')

# Connection Settings
RECONNECT_DELAY = float(os.environ.get('RECONNECT_DELAY', '5.0'))
MAX_RECONNECT_DELAY = float(os.environ.get('MAX_RECONNECT_DELAY', '60.0'))

# ----------------------- Utilities -----------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def log(level: str, message: str, **kwargs):
    """Structured logging"""
    entry = {
        'timestamp': now_iso(),
        'level': level,
        'message': message,
        **kwargs
    }
    output = json.dumps(entry, ensure_ascii=False)
    if CONSOLE_OUTPUT:
        print(output, flush=True)

def rotate_file(filepath: Path):
    """Simple file rotation"""
    if not filepath.exists():
        return
    
    # Check if rotation is needed
    if filepath.stat().st_size < MAX_FILE_SIZE:
        return
    
    try:
        # Rotate existing backups
        for i in range(BACKUP_COUNT - 1, 0, -1):
            old_file = filepath.with_suffix(f'{filepath.suffix}.{i}')
            new_file = filepath.with_suffix(f'{filepath.suffix}.{i + 1}')
            if old_file.exists():
                if new_file.exists():
                    new_file.unlink()
                old_file.rename(new_file)
        
        # Move current file to .1
        backup_file = filepath.with_suffix(f'{filepath.suffix}.1')
        if backup_file.exists():
            backup_file.unlink()
        filepath.rename(backup_file)
    except Exception as e:
        log('WARN', 'File rotation failed', error=str(e))

# ----------------------- AudioHook Event Collector -----------------------
class AudioHookCollector:
    """Streamlined AudioHook event collector"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.token_expires: float = 0
        self.channel_id: Optional[str] = None
        self.ws_url: Optional[str] = None
        self.topics: List[str] = []
        self.running = False
        self.stats = {
            'events_total': 0,
            'audiohook_events': 0,
            'errors': 0,
            'last_event': None,
            'started_at': now_iso(),
            'reconnects': 0
        }
        
        # Setup output file
        self.output_file = Path(OUTPUT_FILE)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Elasticsearch bulk buffer (if enabled)
        self.elastic_buffer: List[Dict] = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_access_token(self) -> str:
        """Get OAuth2 token for Genesys Cloud"""
        if self.token and time.time() < self.token_expires - 300:  # 5min buffer
            return self.token
            
        url = f'https://login.{GENESYS_ENV}/oauth/token'
        auth = aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)
        data = {'grant_type': 'client_credentials'}
        
        async with self.session.post(url, data=data, auth=auth) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f'Token request failed: {resp.status} {text}')
            
            result = await resp.json()
            self.token = result['access_token']
            self.token_expires = time.time() + result.get('expires_in', 3600)
            log('INFO', 'Access token obtained')
            return self.token

    async def api_request(self, method: str, path: str, **kwargs) -> Any:
        """Make authenticated API request to Genesys Cloud"""
        token = await self.get_access_token()
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {token}'
        
        if method.upper() in ('POST', 'PUT', 'PATCH'):
            headers['Content-Type'] = 'application/json'
        
        url = f'https://api.{GENESYS_ENV}{path}'
        
        async with self.session.request(method, url, headers=headers, **kwargs) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f'API request failed: {method} {path} -> {resp.status} {text[:200]}')
            
            if 'application/json' in resp.headers.get('Content-Type', ''):
                return await resp.json()
            return await resp.text()

    async def setup_notification_channel(self):
        """Create notification channel and subscribe to AudioHook topics"""
        # Create channel
        result = await self.api_request('POST', '/api/v2/notifications/channels', data='{}')
        self.channel_id = result['id']
        self.ws_url = result['connectUri']
        log('INFO', 'Notification channel created', channel_id=self.channel_id)
        
        # Load topics
        self.topics = await self.load_topics()
        log('INFO', 'Topics to subscribe', topics=self.topics, count=len(self.topics))
        
        # Subscribe to topics
        subscription_data = {'topics': [{'id': topic} for topic in self.topics]}
        await self.api_request(
            'PUT',
            f'/api/v2/notifications/channels/{self.channel_id}/subscriptions',
            data=json.dumps(subscription_data)
        )
        log('INFO', 'Subscribed to topics', count=len(self.topics))

    async def load_topics(self) -> List[str]:
        """Load topics from file or use AudioHook defaults"""
        topics_file = Path(CUSTOM_TOPICS_FILE)
        
        if topics_file.exists():
            try:
                with topics_file.open() as f:
                    data = json.load(f)
                    custom_topics = [t.strip() for t in data.get('topics', []) if t.strip()]
                    if custom_topics:
                        log('INFO', 'Loaded topics from file', file=str(topics_file), count=len(custom_topics))
                        return custom_topics
            except Exception as e:
                log('WARN', 'Failed to load topics file', error=str(e))
        
        # Try to discover AudioHook topics
        try:
            available = await self.api_request('GET', '/api/v2/notifications/availabletopics')
            audiohook_topics = [
                topic['id'] for topic in available 
                if isinstance(topic, dict) and 
                'audiohook' in topic.get('id', '').lower()
            ]
            
            if audiohook_topics:
                log('INFO', 'Discovered AudioHook topics', topics=audiohook_topics)
                return audiohook_topics
        except Exception as e:
            log('WARN', 'Failed to discover topics', error=str(e))
        
        # Use predefined AudioHook topics
        log('INFO', 'Using predefined AudioHook topics')
        return AUDIOHOOK_TOPICS

    def is_audiohook_event(self, event: Dict[str, Any]) -> bool:
        """Validate if event is an AudioHook operational event"""
        # Check for AudioHook event structure
        event_entity = event.get('eventEntity', {})
        event_id = event_entity.get('id', '')
        
        # AudioHook events have specific ID patterns like AUDIOHOOK-0001
        if event_id.startswith('AUDIOHOOK-'):
            return True
            
        # Check entity type and name
        entity_type = event.get('entityType', '').lower()
        entity_name = event_entity.get('name', '').lower()
        
        return 'audiohook' in entity_type or 'audiohook' in entity_name

    def format_audiohook_event(self, raw_event: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """Format AudioHook event for output"""
        timestamp = now_iso()
        
        # Extract AudioHook-specific fields
        event_entity = raw_event.get('eventEntity', {})
        
        formatted = {
            'timestamp': timestamp,
            'event_type': 'audiohook_operational',
            'event_id': event_entity.get('id'),
            'event_name': event_entity.get('name'),
            'description': event_entity.get('description'),
            'conversation_id': raw_event.get('conversationId'),
            'entity_type': raw_event.get('entityType'),
            'entity_id': raw_event.get('entityId'), 
            'entity_name': raw_event.get('entityName'),
            'version': raw_event.get('version'),
            'topic': topic,
            'channel': self.channel_id,
            'raw_event': raw_event  # Preserve complete original event
        }
        
        return formatted

    async def write_event(self, event: Dict[str, Any]):
        """Write event to output file and optionally to Elasticsearch"""
        # Rotate file if needed
        rotate_file(self.output_file)
        
        # Write to file
        try:
            with self.output_file.open('a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
                f.flush()
        except Exception as e:
            log('ERROR', 'Failed to write event to file', error=str(e))
            self.stats['errors'] += 1
        
        # Add to Elasticsearch buffer if configured
        if ELASTIC_URL:
            self.elastic_buffer.append(event)
            if len(self.elastic_buffer) >= BULK_SIZE:
                await self.flush_to_elasticsearch()

    async def flush_to_elasticsearch(self):
        """Flush events to Elasticsearch"""
        if not ELASTIC_URL or not self.elastic_buffer:
            return
            
        try:
            # Prepare bulk request
            bulk_data = []
            for event in self.elastic_buffer:
                index_action = {'index': {'_index': ELASTIC_INDEX}}
                bulk_data.append(json.dumps(index_action))
                bulk_data.append(json.dumps(event))
            
            ndjson_data = '\n'.join(bulk_data) + '\n'
            headers = {'Content-Type': 'application/x-ndjson'}
            
            # Add auth if configured
            if ELASTIC_AUTH:
                if ':' in ELASTIC_AUTH:
                    import base64
                    encoded = base64.b64encode(ELASTIC_AUTH.encode()).decode()
                    headers['Authorization'] = f'Basic {encoded}'
                else:
                    headers['Authorization'] = f'Bearer {ELASTIC_AUTH}'
            
            async with self.session.post(
                f'{ELASTIC_URL}/_bulk',
                data=ndjson_data.encode('utf-8'),
                headers=headers
            ) as resp:
                if resp.status in (200, 201):
                    log('INFO', 'Flushed events to Elasticsearch', count=len(self.elastic_buffer))
                else:
                    log('WARN', 'Elasticsearch bulk request failed', status=resp.status)
                    self.stats['errors'] += 1
            
            self.elastic_buffer.clear()
        except Exception as e:
            log('ERROR', 'Failed to send events to Elasticsearch', error=str(e))
            self.stats['errors'] += 1
            self.elastic_buffer.clear()

    async def handle_websocket_message(self, message: Dict[str, Any]):
        """Process WebSocket message"""
        self.stats['events_total'] += 1
        
        topic = message.get('topicName', '')
        event_body = message.get('eventBody', {})
        
        if not event_body or not isinstance(event_body, dict):
            return
        
        # Check if this is an AudioHook event
        if self.is_audiohook_event(event_body):
            self.stats['audiohook_events'] += 1
            self.stats['last_event'] = now_iso()
            
            # Format and write the event
            formatted_event = self.format_audiohook_event(event_body, topic)
            await self.write_event(formatted_event)
            
            log('INFO', 'AudioHook event processed',
                event_id=formatted_event['event_id'],
                event_name=formatted_event['event_name'],
                conversation_id=formatted_event['conversation_id'])

    async def websocket_loop(self):
        """Main WebSocket connection loop with auto-reconnect"""
        reconnect_delay = RECONNECT_DELAY
        
        while self.running:
            try:
                # Setup channel if needed
                if not self.ws_url:
                    await self.setup_notification_channel()
                
                log('INFO', 'Connecting to WebSocket', url=self.ws_url)
                async with self.session.ws_connect(self.ws_url, heartbeat=30) as ws:
                    log('INFO', 'WebSocket connected')
                    reconnect_delay = RECONNECT_DELAY  # Reset delay on successful connection
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                await self.handle_websocket_message(data)
                            except json.JSONDecodeError:
                                log('WARN', 'Failed to decode WebSocket message')
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            log('WARN', 'WebSocket closed, will reconnect')
                            break
                            
            except Exception as e:
                log('ERROR', 'WebSocket connection failed', error=str(e))
                self.stats['errors'] += 1
            
            if self.running:
                self.stats['reconnects'] += 1
                log('INFO', f'Reconnecting in {reconnect_delay} seconds')
                await asyncio.sleep(reconnect_delay)
                
                # Exponential backoff
                reconnect_delay = min(reconnect_delay * 1.5, MAX_RECONNECT_DELAY)
                
                # Reset channel info to force recreation
                self.channel_id = None
                self.ws_url = None

    async def start_http_server(self):
        """Start HTTP status server"""
        app = web.Application()
        
        async def health(request):
            return web.json_response({
                'status': 'healthy',
                'timestamp': now_iso(),
                'channel_id': self.channel_id,
                'topics': self.topics,
                'stats': self.stats
            })
        
        async def events(request):
            """Stream recent events"""
            lines = []
            if self.output_file.exists():
                try:
                    with self.output_file.open('r', encoding='utf-8') as f:
                        lines = f.readlines()[-50:]  # Last 50 events
                except Exception:
                    pass
            
            return web.json_response({
                'recent_events': [json.loads(line.strip()) for line in lines if line.strip()]
            })
        
        app.router.add_get('/health', health)
        app.router.add_get('/events', events)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
        await site.start()
        log('INFO', 'HTTP server started', host=HTTP_HOST, port=HTTP_PORT)

    async def run(self):
        """Main run method"""
        log('INFO', 'Starting AudioHook Collector',
            output_file=str(self.output_file),
            elasticsearch=bool(ELASTIC_URL),
            http_port=HTTP_PORT)
        
        # Validate configuration
        if not all([CLIENT_ID, CLIENT_SECRET, GENESYS_ENV]):
            raise ValueError('Missing required Genesys Cloud credentials')
        
        self.running = True
        
        # Start HTTP server
        await self.start_http_server()
        
        # Start WebSocket loop
        await self.websocket_loop()

    def stop(self):
        """Stop the collector"""
        self.running = False
        log('INFO', 'Stopping AudioHook Collector')

# ----------------------- Main Entry Point -----------------------
async def main():
    collector = AudioHookCollector()
    
    # Setup signal handlers
    def signal_handler():
        collector.stop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass  # Windows doesn't support signal handlers in asyncio
    
    async with collector:
        try:
            await collector.run()
        finally:
            # Flush any remaining events
            if collector.elastic_buffer:
                await collector.flush_to_elasticsearch()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log('FATAL', 'Application crashed', error=str(e))
        sys.exit(1)