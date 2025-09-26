### BEGIN: Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Minimal dependencies
RUN pip install --no-cache-dir aiohttp

COPY audiohook_collector.py topics.json .env.example /app/

CMD ["python", "-u", "audiohook_collector.py"]
### END: Dockerfile
