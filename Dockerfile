FROM node:24-alpine AS frontend
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/yingji
COPY pyproject.toml ./
COPY requirements.lock ./
COPY app/ ./app/
COPY THIRD_PARTY_NOTICES.md ./
COPY licenses/ ./licenses/
RUN pip install --no-cache-dir --timeout 120 --retries 3 -r requirements.lock \
    && pip install --no-cache-dir --no-deps . && useradd --create-home --uid 10001 yingji \
    && mkdir -p data && chown -R yingji:yingji data
COPY --from=frontend /web/dist ./frontend/dist/
USER yingji
EXPOSE 8000
CMD ["python", "-m", "app.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
