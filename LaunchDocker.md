# Build + run (Docker)
docker compose --env-file .env up --build -d

# Logs
docker compose logs -f genesys-audiohook-collector

3) Elastic index policy (optional but smart)

If you prefer a data stream, pre-create it with ILM + templates. Otherwise, plain index rollover is fine. (Keeping it light here—your team already has conventions. I can draft templates if you want.)

4) End-to-end Test Procedure (10–20 minutes)

Goal: Prove the path Genesys → WS Notifications → Collector → Elastic and validate resiliency.

Create a test OAuth client (Client Credentials) in your Genesys org

Scopes: enough for notifications (notifications:channel:create, notifications:channel:manageSubscriptions typically bundled under standard API client permissions in your org).

Prepare topics

For a low-risk smoke test, keep:

channel.metadata

v2.users.me.presence

(Later, add one queue observations topic or a conversation stream if you’re comfortable with volume.)

Launch the collector

docker compose up -d

Confirm logs show WS connected and Subscribed topics.

Generate events

Change your Genesys presence (Available → Busy → Available).

Optionally place a quick internal call if you included a conversation topic.

Verify in Elastic

Kibana / Discover query:
index: genesys-events*
KQL: genesys.topic:"v2.users.me.presence" OR genesys.topic:"channel.metadata"

You should see docs with fields:

@timestamp, genesys.topic, and full payload under event.

Failure simulation (resilience)

Temporarily block outbound network or kill the container and restart.

Watch logs for WS connect failed then Resubscribed after reconnect.

Confirm new presence change events continue to index.

Throughput sanity (optional)

Add one higher-volume topic for 2–5 minutes.

Ensure Elastic bulk ok continues and container memory stays stable.

If you see backoff, raise BULK_MAX_DOCS or BULK_CONCURRENCY, or reduce topics.

5) Safety / Ops Notes (no sugar-coating)

WebSocket coverage: not all org/platform “operational” events are on Notifications; some are EventBridge-only. Use this collector for what’s available via Notifications; don’t assume parity.

Backpressure: Elastic slowdowns will surface as backoff logs. If persistent, your options are (a) reduce topics/volume, (b) increase batch size/concurrency, (c) add a queue (SQS/Kafka) in front of Elastic.

Auth hygiene: restrict the Genesys OAuth client to minimal scopes; store creds as secrets in your orchestrator.

Index bloat: conversation streams are chatty. Start with specific topics you need for your dashboard panels.

6) What to tweak for your team
7)
topics.json: lock to the exact KPIs you dashboard today (e.g., queue observations instead of raw conversations).

Mapping/templates: if you want painless querying, we can normalize common fields (e.g., conversationId, participantId, queueId) into top-level fields alongside event.

Logstash: if you prefer, point the collector at Logstash HTTP input instead of Elastic directly—just change ELASTIC_URL and keep the same NDJSON.
