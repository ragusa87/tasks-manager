FROM python:3.11-slim

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
RUN mkdir -p /app/logs /app/media /app/staticfiles && \
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
