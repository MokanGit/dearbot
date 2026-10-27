FROM python:3.13-slim

WORKDIR /app

# Install system dependencies & create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -s /bin/bash -m appuser \
    && mkdir -p /app/backend/data \
    && chown -R appuser:appgroup /app

# Install Python packages
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r /app/backend/requirements.lock

# Copy only application source and config (avoid copying secrets or databases)
COPY --chown=appuser:appgroup backend/app /app/backend/app
COPY --chown=appuser:appgroup pytest.ini /app/pytest.ini

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

USER appuser

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "65"]
