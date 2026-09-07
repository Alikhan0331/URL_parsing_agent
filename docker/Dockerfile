FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src ./src
COPY scripts ./scripts

RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium

ENTRYPOINT ["python", "scripts/run_crawl.py"]
