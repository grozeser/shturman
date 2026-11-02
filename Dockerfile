# 1. Сборка фронтенда
FROM node:22.12.0-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. Зависимости Python в отдельном venv — в рантайм попадает только он
FROM python:3.12.7-slim-bookworm AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

# 3. Рантайм: без node, pip-кэша и dev-инструментов, под непривилегированным пользователем
FROM python:3.12.7-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    STATIC_DIR=/srv/static
WORKDIR /srv
COPY --from=deps /opt/venv /opt/venv
COPY backend/app ./app
COPY --from=web /web/dist ./static
# data/ — единственная папка, куда приложение пишет (отчёт эталонного прогона для страницы «Метрики»)
RUN useradd --create-home --uid 10001 app && chown -R app:app /srv/app/data
USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
