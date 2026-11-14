FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# libpq for psycopg; node for the TypeScript-compiler AST fallback (Tree-sitter is primary)
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 nodejs npm \
    && npm install -g typescript@5.5.4 && rm -rf /var/lib/apt/lists/*
ENV TYPESCRIPT_MODULE=/usr/local/lib/node_modules/typescript

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 skillforge && chown -R skillforge /app
USER skillforge

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
