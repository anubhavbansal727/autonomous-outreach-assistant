FROM python:3.12-slim

# Install system dependencies required by Playwright (Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    # Chromium dependencies
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libgles2 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

# Install Playwright Chromium (only needed in worker; api target skips this)
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        uv run python -m playwright install chromium --with-deps; \
    fi

# Copy source
COPY . .

# Railway injects $PORT; docker-compose overrides this CMD per service.
# Shell form is required so ${PORT:-8000} is expanded at runtime.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
