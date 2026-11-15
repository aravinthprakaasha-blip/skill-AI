# SkillForge code runner: Python 3.11, Node 22 (JS + TypeScript via --experimental-strip-types), Java 17.
FROM node:22-bookworm-slim AS node

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install fastapi uvicorn
COPY main.py .
RUN chmod -R a-w /app
# Runs as root ONLY so each submission can be dropped to the unprivileged `nobody` user.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
