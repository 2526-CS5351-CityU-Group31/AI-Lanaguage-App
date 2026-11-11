# syntax=docker/dockerfile:1
# Production image for the AI-Companion backend (Render web service).
# Implements: ADR-011 (single web service), ADR-001 (guarded monolith),
#   INV-SEC-002 (no upload surface), configuration-governance (PORT, S5)
#
# The image runs ONLY the FastAPI app. There is no debug server, no reload,
# and no shell tools beyond the slim base. Secrets are injected at runtime by
# Render (secret group); none are baked into the image.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install pinned runtime dependencies only (no dev/test tooling in the image).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source. Only what the server needs at runtime.
COPY src ./src

# Run as a non-root user (defence in depth; Render also runs unprivileged).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Render injects PORT; the app reads it via the config module (S5) and binds
# 0.0.0.0 inside run(). HEALTHCHECK uses the static liveness route (RP-011).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health', timeout=4)"

# Exec form: the interpreter is PID 1 and receives SIGTERM for a clean shutdown.
CMD ["python", "-m", "src.backend.main"]
