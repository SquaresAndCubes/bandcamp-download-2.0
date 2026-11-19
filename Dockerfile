FROM python:3.12-slim

LABEL org.opencontainers.image.title="Bandcamp Download 2.0" \
      org.opencontainers.image.version="2.0"

# tzdata so TZ=America/Denver etc. works for the daily schedule.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Only the code goes in the image: the login cookie comes from .env at runtime.
COPY bandcamp_latest.py scheduler.py ./

ENV PYTHONUNBUFFERED=1 \
    TZ=UTC \
    SYNC_TIME=04:00 \
    BANDCAMP_SYNC_DEST=/music \
    BANDCAMP_TEMP_DIR=/tmp \
    BANDCAMP_LOG_DIR=/music/.bandcamp-sync-logs

CMD ["python", "-u", "/app/scheduler.py"]
