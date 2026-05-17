FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY pyproject.toml ./

RUN pip install --no-cache-dir -e .

# SQLite link-token store lives here. Mount a volume to persist it.
VOLUME ["/data"]
ENV NAKOPAY_TG_DB_PATH=/data/nakopay-telegram.sqlite3

CMD ["python", "-m", "nakopay_telegram.bot"]
