FROM --platform=$BUILDPLATFORM node:25-alpine AS vite
ARG USER_ID=1000
ARG GROUP_ID=1000
WORKDIR /app
# Create a user with the specified UID/GID or use existing one
RUN if getent group ${GROUP_ID} >/dev/null 2>&1; then \
        EXISTING_GROUP=$(getent group ${GROUP_ID} | cut -d: -f1); \
    else \
        addgroup -g ${GROUP_ID} nodeuser; \
        EXISTING_GROUP=nodeuser; \
    fi; \
    if getent passwd ${USER_ID} >/dev/null 2>&1; then \
        EXISTING_USER=$(getent passwd ${USER_ID} | cut -d: -f1); \
    else \
        adduser -u ${USER_ID} -G $EXISTING_GROUP -D nodeuser; \
        EXISTING_USER=nodeuser; \
    fi
RUN mkdir -p /app/node_modules && chown -R ${USER_ID}:${GROUP_ID} /app
# Switch to the user with specified UID
USER ${USER_ID}:${GROUP_ID}

COPY package-lock.json .
COPY package.json .
COPY vite.config.js .
COPY tailwind.config.js .

RUN mkdir -p frontend static/dist
COPY frontend frontend/
COPY templates templates/
RUN npm ci && npm run vite build


FROM python:3.11-slim AS django
# Build arguments for user/group IDs
ARG USER_ID=1000
ARG GROUP_ID=1000


# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Create user with specified UID/GID
RUN groupadd -g ${GROUP_ID} appuser && \
    useradd -u ${USER_ID} -g ${GROUP_ID} -d /home/appuser -m -s /bin/bash appuser

# Set up application directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen

# Create necessary directories with correct permissions
RUN mkdir -p /app/logs /app/media /app/staticfiles /app/static && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000
ENV PATH="/app/.venv/bin:$PATH"

# Default command
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM django AS django-prod
COPY --from=vite /app/static/dist ./static/dist
RUN uv run python manage.py collectstatic --noinput
