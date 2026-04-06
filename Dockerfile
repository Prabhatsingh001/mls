# ===================== BUILDER =====================
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/opt/venv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

COPY requirements.txt /app/requirements.txt

RUN python -c "from pathlib import Path; raw=Path('/app/requirements.txt').read_bytes(); text=raw.decode('utf-16') if raw[:2] in (b'\\xff\\xfe', b'\\xfe\\xff') else raw.decode('utf-8'); Path('/app/requirements.docker.txt').write_text(text, encoding='utf-8')"

RUN pip install --upgrade pip && pip install -r /app/requirements.docker.txt


# ===================== RUNTIME =====================
FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    XDG_CACHE_HOME=/home/app/.cache

WORKDIR /app

# WeasyPrint dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd --system app && useradd --system --gid app --home-dir /home/app --create-home app

# 🔥 Create cache directory with correct permissions
RUN mkdir -p /home/app/.cache/fontconfig && \
    chown -R app:app /home/app/.cache

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . /app

# Media directory
RUN mkdir -p /app/media/service_items && \
    chown -R app:app /app/media

USER app

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]