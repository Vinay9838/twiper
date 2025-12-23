# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for building wheels (e.g., pycryptodome)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install -r requirements.txt \
    && pip install "tenacity>=8.2.3"

# App source
COPY tweet_manager.py media_manager.py mega_manager.py db_manager.py ./
COPY data/.gitkeep ./data/.gitkeep
COPY data/caption.txt ./data/caption.txt

# Default logging level; override via env
ENV LOG_LEVEL=INFO

# One-shot job entry (runs then exits)
CMD ["python", "tweet_manager.py"]
