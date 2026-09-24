FROM python:3.10-slim

WORKDIR /app

# Install system build dependencies and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev,mcp]" ortools sqlalchemy psycopg[binary]

COPY src/ src/
COPY data/ data/

ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "logistics_tower.api.main"]
