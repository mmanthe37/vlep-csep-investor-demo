# ==========================================
# Base Image
# ==========================================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # App location
    APP_HOME=/app

WORKDIR $APP_HOME

# Install system dependencies required for build and pg connections
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# Builder Image
# ==========================================
FROM base as builder

COPY pyproject.toml README.md* ./
# If using requirements.txt or pip install directly from pyproject:
COPY . .
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels . && \
    pip wheel --no-cache-dir --wheel-dir /app/wheels -e .

# ==========================================
# Production Image
# ==========================================
FROM base as production

# Create a non-root user
RUN addgroup --system appgroup && adduser --system --group appuser

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed wheels from builder
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app /app

# Install dependencies from wheels
RUN pip install --no-cache /wheels/*

# Change ownership
RUN chown -R appuser:appgroup $APP_HOME

USER appuser

EXPOSE 8000

# Run Uvicorn server by default
CMD ["uvicorn", "vlep.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
