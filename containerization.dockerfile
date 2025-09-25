### BEGIN: Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Minimal dependencies
RUN pip install --no-cache-dir aiohttp

COPY collector.py topics.json /app/

CMD ["python", "-u", "collector.py"]
### END: Dockerfile
