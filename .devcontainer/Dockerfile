FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-tk sqlite3 xvfb \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
