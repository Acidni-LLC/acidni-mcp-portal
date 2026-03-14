FROM python:3.12-slim

WORKDIR /app

# Install UV for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy all source files (needed for hatchling build)
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies (non-editable for container)
RUN uv pip install --system --no-cache .

# Copy application (already done above, but ensures templates are included)
# COPY src/ ./src/

# Create non-root user
RUN groupadd -r app && useradd -r -g app app
USER app

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health', timeout=5).raise_for_status()"

# Run
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
