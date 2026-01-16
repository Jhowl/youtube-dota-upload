FROM python:3.13-slim

WORKDIR /app

# System deps (minimal)
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY obs_youtube_uploader /app/obs_youtube_uploader

# Default watch dir inside container
RUN mkdir -p /app/watch

ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "obs_youtube_uploader.main"]
