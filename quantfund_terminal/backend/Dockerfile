# QuantFund Research Terminal — backend gateway image.
# BUILD CONTEXT MUST BE THE REPO ROOT (so the core `quantfund` package + reports
# are available):  docker build -f quantfund_terminal/backend/Dockerfile .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# System deps for numpy/pandas/psycopg wheels are usually prebuilt; keep slim.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install the UNMODIFIED core package (editable-equivalent) + gateway deps.
# README.md is required because pyproject.toml declares readme = "README.md".
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && pip install --no-cache-dir \
        "fastapi>=0.111" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
        "psycopg[binary]>=3.1" "redis>=5.0"

# Product layer + reports (read-only moat inputs).
COPY quantfund_terminal ./quantfund_terminal
COPY reports ./reports

EXPOSE 8000
# QFT_DATABASE_URL / QFT_REDIS_URL are injected by the orchestrator (RDS/ElastiCache).
CMD ["python", "-m", "uvicorn", "quantfund_terminal.backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
