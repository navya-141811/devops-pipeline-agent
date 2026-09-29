# ── Stage: base ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Security: run as non-root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Fix ownership
RUN chown -R appuser:appgroup /app

USER appuser

# Default port — overridden by docker-compose per service
EXPOSE 8000

# Default command (overridden per service in docker-compose.yml)
CMD ["uvicorn", "mock_api:app", "--host", "0.0.0.0", "--port", "8000"]
