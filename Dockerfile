# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		gcc \
		libpq-dev \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

# Keep Docker build resilient if requirements.txt was saved in UTF-16.
RUN python -c "from pathlib import Path; raw=Path('requirements.txt').read_bytes(); text=raw.decode('utf-16') if raw[:2] in (b'\\xff\\xfe', b'\\xfe\\xff') else raw.decode('utf-8'); Path('requirements.docker.txt').write_text(text, encoding='utf-8')"

RUN python -m pip install --upgrade pip setuptools wheel \
	&& pip wheel --wheel-dir /wheels -r requirements.docker.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		libpq5 \
	&& rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.docker.txt /app/requirements.docker.txt

RUN python -m pip install --upgrade pip \
	&& pip install --no-index --find-links=/wheels -r requirements.docker.txt \
	&& rm -rf /wheels

COPY . /app

RUN addgroup --system app \
	&& adduser --system --ingroup app app \
	&& chown -R app:app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py runserver 0.0.0.0:8000"]
