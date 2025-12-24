# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /appsrc

# System deps (build + cron)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cron \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt \
    && pip install "tenacity>=8.2.3"

# App source
COPY app/ ./app/
COPY job.py ./job.py

COPY run_job.sh /appsrc/run_job.sh
RUN chmod +x /appsrc/run_job.sh

# Data (copy entire folder; safe even if only caption.txt exists)
COPY data/ ./data/

# Cron config
COPY crontab /etc/cron.d/app-cron
RUN chmod 0644 /etc/cron.d/app-cron \
    && crontab /etc/cron.d/app-cron \
    && touch /var/log/cron.log

# Default logging level
ENV LOG_LEVEL=INFO

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]