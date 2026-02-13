# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt \
    && pip check


FROM python:3.12-slim-bookworm AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --home /home/app --shell /usr/sbin/nologin app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

COPY --chown=app:app main.py ./main.py
COPY --chown=app:app requirements.txt ./requirements.txt
COPY --chown=app:app api ./api
COPY --chown=app:app config ./config
COPY --chown=app:app database ./database
COPY --chown=app:app monitoring ./monitoring
COPY --chown=app:app socials ./socials
COPY --chown=app:app utils ./utils
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/logs \
    && chown -R app:app /app

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "main.py"]
