FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/bot.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Бот не должен работать от root
RUN useradd --create-home --shell /bin/bash bot \
    && mkdir -p /data && chown -R bot:bot /data /app
USER bot

# Данные живут в отдельном томе (см. docker-compose.yml), иначе при
# перезапуске контейнера теряются админы и история заявок
VOLUME ["/data"]

CMD ["python", "-m", "app.bot"]
