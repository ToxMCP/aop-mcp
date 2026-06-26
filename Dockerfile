# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AOP_MCP_ARTIFACT_OUTPUT_DIR=/app/output

WORKDIR /app

RUN addgroup --system aopmcp \
    && adduser --system --ingroup aopmcp --home /app aopmcp

COPY pyproject.toml README.md LICENSE ./
COPY docs ./docs
COPY governance ./governance
COPY src ./src
COPY tests/golden ./tests/golden
COPY vendor ./vendor

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && mkdir -p /app/output \
    && chown -R aopmcp:aopmcp /app

USER aopmcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=8s --start-period=20s --retries=3 \
    CMD python -c "import http.client, sys; conn = http.client.HTTPConnection('127.0.0.1', 8000, timeout=5); conn.request('GET', '/health'); response = conn.getresponse(); sys.exit(0 if response.status < 500 else 1)"

CMD ["uvicorn", "src.server.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
