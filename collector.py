#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genesys AudioHook Operational Event Collector -> Elastic Bulk

WHAT IT DOES
- Authenticates to Genesys Cloud (OAuth2 Client Credentials).
- Auto-discovers available notifications topics containing AudioHook operational signals.
- Opens a Notifications WebSocket channel with auto-reconnect + resubscribe.
- Normalizes operational events (code, severity, entityId, integrationId) for alerting & KPIs.
- Batches and ships JSON docs to Elastic via _bulk with backoff.
- Emits in-memory counters for quick success/error trending (and optional /stats endpoint).

RUNTIME REQUIREMENTS
- Python 3.9+ recommended.
- pip install aiohttp

CONFIG (environment variables)
  # Genesys
  GENESYS_ENV=usw2.pure.cloud
  GENESYS_CLIENT_ID=...
  GENESYS_CLIENT_SECRET=...

  # Topic selection
  AUTO_DISCOVER_AUDIOHOOK=true         # if true and topics.json not provided/non-empty, query available topics
  TOPICS_FILE=./topics.json            # optional; if present with topics[], those are used
  TOPIC_INCLUDE_REGEX=audiohook        # optional regex to further filter discovered topics (default 'audiohook')
  TOPIC_EXCLUDE_REGEX=                 # optional regex to exclude noisy topics
  FALLBACK_TOPICS=channel.metadata,v2.users.me.presence  # used if discovery yields nothing

  # Elastic sink
  ELASTIC_URL=https://elastic.example:9200
  ELASTIC_AUTH=elastic:changeme        # "user:pass" for Basic OR raw bearer token; ApiKey <base64> also works
  ELASTIC_DATASTREAM=false             # true => use ELASTIC_INDEX as a data stream name (no date suffix)
  ELASTIC_INDEX=genesys-audiohook      # base index name (or data stream name if ELASTIC_DATASTREAM=true)

  # Bulk behavior
  BULK_MAX_DOCS=200
  BULK_MAX_SECONDS=5
  BULK_CONCURRENCY=2
  RETRY_BASE_SLEEP=1.5
  RETRY_MAX_SLEEP=30

  # Optional mini HTTP status server
  HTTP_STATUS_ENABLED=true
  HTTP_STATUS_HOST=0.0.0.0
  HTTP_STATUS_PORT=8077
"""

import asyncio, json, os, re, signal, sys, time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import aiohttp
from aiohttp import web

# ----------------------- Config -----------------------
def getenv_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name, str(default)).strip().lower()
    return val in ("1", "true", "yes", "y", "on")

GENESYS_ENV        = os.environ.get("GENESYS_ENV", "usw2.pure.cloud")
CLIENT_ID          = os.environ.get("GENESYS_CLIENT_ID", "")
CLIENT_SECRET      = os.environ.get("GENESYS_CLIENT_SECRET", "")

AUTO_DISCOVER      = getenv_bool("AUTO_DISCOVER_AUDIOHOOK", True)
TOPICS_FILE        = os.environ.get("TOPICS_FILE", "./topics.json")
TOPIC_INCLUDE_RGX  = os.environ.get("TOPIC_INCLUDE_REGEX", "audiohook").strip()
TOPIC_EXCLUDE_RGX  = os.environ.get("TOPIC_EXCLUDE_REGEX", "").strip()
FALLBACK_TOPICS    = [t for t in os.environ.get("FALLBACK_TOPICS", "channel.metadata,v2.users.me.presence").split(",") if t]

ELASTIC_URL        = os.environ.get("ELASTIC_URL", "")
ELASTIC_AUTH       = os.environ.get("ELASTIC_AUTH", "")
ELASTIC_DATASTREAM = getenv_bool("ELASTIC_DATASTREAM", False)
ELASTIC_INDEX      = os.environ.get("ELASTIC_INDEX", "genesys-audiohook")

BULK_MAX_DOCS      = int(os.environ.get("BULK_MAX_DOCS", "200"))
BULK_MAX_SECONDS   = float(os.environ.get("BULK_MAX_SECONDS", "5"))
BULK_CONCURRENCY   = int(os.environ.get("BULK_CONCURRENCY", "2"))
RETRY_BASE_SLEEP   = float(os.environ.get("RETRY_BASE_SLEEP", "1.5"))
RETRY_MAX_SLEEP    = float(os.environ.get("RETRY_MAX_SLEEP", "30"))

HTTP_STATUS_ENABLED= getenv_bool("HTTP_STATUS_ENABLED", True)
HTTP_STATUS_HOST   = os.environ.get("HTTP_STATUS_HOST", "0.0.0.0")
HTTP_STATUS_PORT   = int(os.environ.get("HTTP_STATUS_PORT", "8077"))

# ----------------------- Logging -----------------------
def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def log(msg, **kv):
    line = {"ts": now_utc_iso(), "lvl": "INFO", "msg": msg, **kv}
    print(json.dumps(line, ensure_ascii=False), flush=True)

def wlog(msg, **kv):
    line = {"ts": now_utc_iso(), "lvl": "WARN", "msg": msg, **kv}
    print(json.dumps(line, ensure_ascii=False), flush=True, file=sys.stderr)

def elog(msg, **kv):
    line = {"ts": now_utc_iso(), "lvl": "ERROR", "msg": msg, **kv}
    print(json.dumps(line, ensure_ascii=False), flush=True, file=sys.stderr)

# ----------------------- Auth helpers -----------------------
def elastic_auth_headers() -> Dict[str, str]:
    if not ELASTIC_AUTH:
        return {}
    # Decide between Basic vs Bearer/ApiKey based on presence of colon
    if ":" in ELASTIC_AUTH and not ELASTIC_AUTH.strip().lower().startswith(("bearer ", "apikey ")):
        import base64
        token = base64.b64encode(ELASTIC_AUTH.encode()).decode()
        return {"Authorization": f"Basic {token}"}
    return {"Authorization": ELASTIC_AUTH if ELASTIC_AUTH.lower().startswith(("bearer ", "apikey ")) else f"Bearer {ELASTIC_AUTH}"}

# ----------------------- Genesys API -----------------------
class GenesysClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.token: Optional[str] = None
        self.expires_at: float = 0.0

    async def _get_token(self) -> str:
        # Reuse token until near expiry
        if self.token and time.time() < self.expires_at - 30:
            return self.token
        url = f"https://login.{GENESYS_ENV}/oauth/token"
        data = {"grant_type": "client_credentials"}
        auth = aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)
        async with self.session.post(url, data=data, auth=auth) as r:
            txt = await r.text()
            if r.status != 200:
                raise RuntimeError(f"TokenFailed {r.status} {txt[:400]}")
            js = json.loads(txt)
            self.token = js["access_token"]
            self.expires_at = time.time() + int(js.get("expires_in", 3600))
            return self.token

    async def _authed(self, method: str, url: str, **kw):
        token = await self._get_token()
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        if method.upper() in ("POST","PUT","PATCH"):
            headers.setdefault("Content-Type","application/json")
        async with self.session.request(method, url, headers=headers, **kw) as r:
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"API {method} {url} -> {r.status} {text[:500]}")
            if "application/json" in (r.headers.get("Content-Type") or ""):
                return await r.json()
            return await r.text()

    async def create_channel(self):
        url = f"https://api.{GENESYS_ENV}/api/v2/notifications/channels"
        js = await self._authed("POST", url, data=json.dumps({}))
        return js["id"], js["connectUri"]

    async def subscribe_topics(self, channel_id: str, topic_ids: List[str]):
        url = f"https://api.{GENESYS_ENV}/api/v2/notifications/channels/{channel_id}/subscriptions"
        body = {"topics": [{"id": t} for t in topic_ids]}
        return await self._authed("PUT", url, data=json.dumps(body))

    async def list_available_topics(self) -> List[Dict[str, Any]]:
        url = f"https://api.{GENESYS_ENV}/api/v2/notifications/availabletopics"
        js = await self._authed("GET", url)
        # API returns a list of {id, description, schema, ...}
        return js if isinstance(js, list) else []

# ----------------------- Elastic Bulk Sink -----------------------
class ElasticSink:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.queue: asyncio.Queue = asyncio.Queue()
        self.stop_evt = asyncio.Event()
        self.sent_docs = 0
        self.errors = 0

    async def start(self):
        workers = [asyncio.create_task(self._worker(i)) for i in range(BULK_CONCURRENCY)]
        await self.stop_evt.wait()
        for w in workers:
            w.cancel()
        for w in workers:
            try:
                await w
            except asyncio.CancelledError:
                pass

    async def _worker(self, wid: int):
        headers = {"Content-Type": "application/x-ndjson", **elastic_auth_headers()}
        pending: List[str] = []
        last_flush = time.time()

        async def flush():
            nonlocal pending, last_flush
            if not pending:
                return
            ndjson = "\n".join(pending) + "\n"
            url = f"{ELASTIC_URL}/_bulk"
            try:
                async with self.session.post(url, data=ndjson.encode("utf-8"), headers=headers) as r:
                    txt = await r.text()
                    if r.status in (200, 201):
                        try:
                            js = json.loads(txt)
                            if js.get("errors"):
                                self.errors += 1
                                wlog("Elastic bulk partial errors", worker=wid)
                            else:
                                self.sent_docs += len(pending)//2
                                log("Elastic bulk ok", worker=wid, items=len(pending)//2)
                        except Exception:
                            # If body can't parse, still count it as success but warn
                            wlog("Elastic bulk response parse warn", worker=wid)
                    elif r.status in (429, 500, 502, 503, 504):
                        # brief backoff then single retry
                        wlog("Elastic backoff", status=r.status, worker=wid)
                        await asyncio.sleep(RETRY_BASE_SLEEP)
                        async with self.session.post(url, data=ndjson.encode("utf-8"), headers=headers) as r2:
                            if r2.status >= 300:
                                self.errors += 1
                                elog("Elastic bulk failed after retry", status=r2.status, worker=wid)
                            else:
                                self.sent_docs += len(pending)//2
                                log("Elastic bulk ok after retry", worker=wid, items=len(pending)//2)
                    else:
                        self.errors += 1
                        elog("Elastic bulk failed (non-retryable)", status=r.status, worker=wid, body=txt[:300])
            except Exception as e:
                self.errors += 1
                elog("Elastic bulk exception", worker=wid, err=str(e))
            pending = []
            last_flush = time.time()

        try:
            while True:
                timeout = max(0.1, BULK_MAX_SECONDS - (time.time() - last_flush))
                try:
                    action, source = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                    pending.append(action)
                    pending.append(source)
                except asyncio.TimeoutError:
                    pass
                if len(pending) >= BULK_MAX_DOCS * 2 or (time.time() - last_flush) >= BULK_MAX_SECONDS:
                    await flush()
        except asyncio.CancelledError:
            await flush()

    async def enqueue(self, doc: Dict[str, Any]):
        index_name = ELASTIC_INDEX if ELASTIC_DATASTREAM else f"{ELASTIC_INDEX}-{datetime.utcnow():%Y.%m.%d}"
        action = json.dumps({"index": {"_index": index_name}}, ensure_ascii=False)
        source = json.dumps(doc, ensure_ascii=False)
        await self.queue.put((action, source))

# ----------------------- Runner -----------------------
class Runner:
    def __init__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None))
        self.gc = GenesysClient(self.session)
        self.sink = ElasticSink(self.session)
        self.stop_evt = asyncio.Event()
        self.channel_id: Optional[str] = None
        self.connect_uri: Optional[str] = None
        self.topic_ids: List[str] = []
        self.include_rgx = re.compile(TOPIC_INCLUDE_RGX, re.I) if TOPIC_INCLUDE_RGX else None
        self.exclude_rgx = re.compile(TOPIC_EXCLUDE_RGX, re.I) if TOPIC_EXCLUDE_RGX else None
        # In-memory counters (best-effort)
        self.counters = {
            "events_total": 0,
            "op_errors": 0,
            "op_warns": 0,
            "op_infos": 0,
            "audiohook_evts": 0
        }

    async def _load_topics_from_file(self) -> List[str]:
        if not os.path.exists(TOPICS_FILE):
            return []
        try:
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                js = json.load(f)
            topics = js.get("topics") or []
            return [t for t in topics if t]
        except Exception as e:
            wlog("Failed to read topics.json, ignoring", err=str(e))
            return []

    async def _discover_audiohook_topics(self) -> List[str]:
        try:
            all_topics = await self.gc.list_available_topics()
        except Exception as e:
            wlog("AvailableTopics fetch failed", err=str(e))
            return []

        selected = []
        for t in all_topics:
            tid = (t.get("id") or t.get("topicName") or "").strip()
            if not tid:
                continue
            name = tid.lower()
            # Base include: contains 'audiohook' OR looks like an operational event stream mentioning audio/audiohook
            include = ("audiohook" in name) or ("operational" in name and ("audio" in name or "hook" in name))
            if include and self.include_rgx and not self.include_rgx.search(tid):
                include = False
            if include and self.exclude_rgx and self.exclude_rgx.search(tid):
                include = False
            if include:
                selected.append(tid)

        if not selected:
            wlog("No AudioHook topics discovered; using FALLBACK_TOPICS")
            selected = FALLBACK_TOPICS[:]
        return selected

    async def select_topics(self):
        # Priority: topics.json (if non-empty) else discovery (if enabled) else fallback
        topics = await self._load_topics_from_file()
        if topics:
            log("Using topics from topics.json", count=len(topics))
        elif AUTO_DISCOVER:
            topics = await self._discover_audiohook_topics()
            log("Auto-discovered topics", count=len(topics), samples=topics[:5])
        else:
            topics = FALLBACK_TOPICS[:]
            log("Using fallback topics", count=len(topics))
        self.topic_ids = topics or FALLBACK_TOPICS[:]

    async def _ws_loop(self):
        # Create channel + subscribe
        ch_id, ws_url = await self.gc.create_channel()
        self.channel_id = ch_id
        self.connect_uri = ws_url
        await self.gc.subscribe_topics(ch_id, self.topic_ids)
        log("Subscribed topics", count=len(self.topic_ids))

        backoff = RETRY_BASE_SLEEP
        while not self.stop_evt.is_set():
            try:
                async with self.session.ws_connect(self.connect_uri, heartbeat=30) as ws:
                    log("WS connected", channel=self.channel_id)
                    backoff = RETRY_BASE_SLEEP
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                payload = msg.json(loads=json.loads)
                            except Exception:
                                payload = {"raw": msg.data}
                            await self.handle_event(payload)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                            wlog("WS closed or error; reconnecting")
                            break
            except Exception as e:
                wlog("WS connect failed", err=str(e))

            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.7, RETRY_MAX_SLEEP)
            # Recreate channel + resubscribe (channels expire)
            try:
                ch_id, ws_url = await self.gc.create_channel()
                self.channel_id = ch_id
                self.connect_uri = ws_url
                await self.gc.subscribe_topics(ch_id, self.topic_ids)
                log("Resubscribed after reconnect", channel=self.channel_id)
            except Exception as e:
                wlog("Resubscribe failed; retrying", err=str(e))

    # ---------- Event normalization ----------
    @staticmethod
    def _extract_first_nonempty(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
        for k in keys:
            v = d.get(k)
            if v not in (None, "", [], {}):
                return v
        return None

    async def handle_event(self, payload: Dict[str, Any]):
        self.counters["events_total"] += 1

        topic = payload.get("topicName") or payload.get("topic")
        body = payload.get("eventBody") or payload.get("body") or payload

        if isinstance(body, dict):
            ev = body
        else:
            # Sometimes heartbeat or unknown payloads
            ev = {"_raw": body}

        # Try to map operational-event fields that matter for AudioHook alerting
        code = self._extract_first_nonempty(ev, ["eventDefinitionId", "code", "eventId"])
        sev  = (self._extract_first_nonempty(ev, ["severity", "level", "logLevel"]) or "").upper()
        ent  = self._extract_first_nonempty(ev, ["entityId", "conversationId", "deploymentId", "sessionId"])
        intg = self._extract_first_nonempty(ev, ["integrationId", "integration", "integrationName"])
        comp = self._extract_first_nonempty(ev, ["component", "source", "service"])  # sometimes present

        # Heuristic for AudioHook classification
        is_audiohook = ("audiohook" in (str(code or "") + " " + str(comp or "")).lower()) or \
                       ("audiohook" in (topic or "").lower())

        if is_audiohook:
            self.counters["audiohook_evts"] += 1

        if sev in ("ERROR", "CRITICAL", "SEVERE"):
            self.counters["op_errors"] += 1
        elif sev in ("WARN", "WARNING"):
            self.counters["op_warns"] += 1
        else:
            self.counters["op_infos"] += 1

        doc = {
            "@timestamp": now_utc_iso(),
            "genesys": {
                "topic": topic,
                "channel": self.channel_id
            },
            "op": {
                "code": code,                 # e.g., "AUDIOHOOK-0001"
                "severity": sev,              # "ERROR" | "WARN" | "INFO"...
                "entityId": ent,
                "integrationId": intg,
                "component": comp,
                "isAudioHook": is_audiohook
            },
            "event": ev                      # Preserve full original payload for deep dive
        }
        await self.sink.enqueue(doc)

    # ---------- Mini HTTP status server (optional) ----------
    async def _http_app(self):
        app = web.Application()

        async def health(_req):
            return web.json_response({
                "ok": True,
                "ts": now_utc_iso(),
                "channel": self.channel_id,
                "topics": self.topic_ids,
                "elastic_sent_docs": self.sink.sent_docs,
                "elastic_errors": self.sink.errors
            })

        async def stats(_req):
            return web.json_response({
                "ts": now_utc_iso(),
                "counters": self.counters
            })

        app.router.add_get("/health", health)
        app.router.add_get("/stats", stats)
        return app

    async def start(self):
        # Basic config validation
        if not (CLIENT_ID and CLIENT_SECRET and GENESYS_ENV and ELASTIC_URL):
            raise SystemExit("Missing required env: GENESYS_CLIENT_ID / GENESYS_CLIENT_SECRET / GENESYS_ENV / ELASTIC_URL")

        await self.select_topics()

        # Start sink workers
        sink_task = asyncio.create_task(self.sink.start())

        # Optional status server
        if HTTP_STATUS_ENABLED:
            app = await self._http_app()
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host=HTTP_STATUS_HOST, port=HTTP_STATUS_PORT)
            await site.start()
            log("HTTP status server started", host=HTTP_STATUS_HOST, port=HTTP_STATUS_PORT)

        # WS loop
        ws_task = asyncio.create_task(self._ws_loop())

        def _stop():
            log("Shutdown signal received")
            self.stop_evt.set()
            self.sink.stop_evt.set()

        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_running_loop().add_signal_handler(s, _stop)
            except NotImplementedError:
                pass

        await asyncio.wait([ws_task], return_when=asyncio.FIRST_COMPLETED)
        self.sink.stop_evt.set()
        await sink_task
        await self.session.close()

# ----------------------- Entrypoint -----------------------
if __name__ == "__main__":
    try:
        asyncio.run(Runner().start())
    except KeyboardInterrupt:
        pass
