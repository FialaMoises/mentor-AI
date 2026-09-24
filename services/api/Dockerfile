FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/services/api

COPY services/api/pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[dev]"

COPY services/api/app ./app
COPY services/api/tests ./tests
COPY db /srv/db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
