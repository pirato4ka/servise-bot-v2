FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/bot.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Каталоги под базу:
#   /data     — постоянный том (см. docker-compose.yml)
#   /app/data — резервный: если том примонтирован от root и недоступен на запись,
#               бот автоматически положит базу сюда (см. app/database/bootstrap.py)
RUN mkdir -p /data /app/data && chmod 777 /data /app/data

VOLUME ["/data"]

# Запускаем от root: на хостингах том монтируется от root, и процесс под
# непривилегированным пользователем не может создать файл базы —
# получается «sqlite3.OperationalError: unable to open database file».
# Если принципиален запуск без root: создайте пользователя и заранее сделайте
# chown каталога с базой на хосте (uid должен совпадать с uid в контейнере).
CMD ["python", "-m", "app.bot"]
