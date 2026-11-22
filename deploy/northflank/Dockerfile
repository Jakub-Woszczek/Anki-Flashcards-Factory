FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 REMOTE_DATA_DIR=/data PORT=8080
WORKDIR /app
COPY deploy/northflank/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir /data && chown 10001:10001 /data

# Build context is the repository root. No Anki data, .env, word lists or media.
COPY backend/settings.py /app/backend/settings.py
COPY external_apis/diki_api.py external_apis/diki_audio.py external_apis/diki_entries.py \
     external_apis/diki_page.py external_apis/diki_resources.py external_apis/diki_transfer.py /app/external_apis/
COPY deploy/northflank/*.py /app/deploy/northflank/
EXPOSE 8080
CMD ["python", "-m", "deploy.northflank.app"]
