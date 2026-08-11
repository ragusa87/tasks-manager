FROM --platform=$BUILDPLATFORM node:26-alpine AS vite
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

# Install node deps first so that editing frontend/templates does not
# invalidate the (expensive) `npm ci` layer.
COPY package-lock.json package.json ./
RUN --mount=type=cache,target=/tmp/npm-cache,uid=${USER_ID},gid=${GROUP_ID} \
    npm ci --cache /tmp/npm-cache --prefer-offline

COPY vite.config.js .
RUN mkdir -p frontend static/dist
COPY frontend frontend/
COPY templates templates/
RUN npm run vite build


FROM python:3.14-slim AS django
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
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv
ENV UV_PROJECT_ENVIRONMENT=/opt/python/venv
ENV PATH="/opt/python/venv/bin:$PATH"

# Create user with specified UID/GID
RUN groupadd -g ${GROUP_ID} appuser && \
    useradd -u ${USER_ID} -g ${GROUP_ID} -d /home/appuser -m -s /bin/bash appuser

# Set up application directory
WORKDIR /app

# Create necessary directories with correct permissions
RUN mkdir -p /app/logs /app/media /app/staticfiles /app/static /opt/python && \
    chown -R appuser:appuser /app /opt/python

# Switch to non-root user
USER appuser
ENV PATH="/opt/python/venv/bin:$PATH"

# Install Python dependencies BEFORE copying the source. This is a
# non-package project, so the venv only needs pyproject.toml + uv.lock;
# editing application code no longer busts the dependency layer, and a
# BuildKit cache mount keeps the uv download cache across rebuilds.
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=${USER_ID},gid=${GROUP_ID} \
    uv sync --frozen --no-install-project

# Copy application code
COPY --chown=appuser:appuser . .

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM django AS django-prod
COPY --from=vite /app/static/dist ./static/dist
RUN python manage.py collectstatic --noinput
