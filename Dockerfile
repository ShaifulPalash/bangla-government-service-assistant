# The API for the Bangla Government-Service Assistant
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Dependencies first, so Docker reuses this layer when only the code changes
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# The code and the prebuilt search indexes
COPY src ./src
COPY data/index ./data/index

# Run as a normal user, not as root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Render tells the app which port to use through the PORT variable. Locally it is 8000.
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]