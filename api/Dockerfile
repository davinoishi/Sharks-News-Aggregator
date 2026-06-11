FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -m nltk.downloader stopwords punkt punkt_tab

# Copy application code
COPY app app

# Copy Alembic config + migrations (brief 07, C6) so the API container can run
# `alembic upgrade head` on startup.
COPY alembic.ini .
COPY alembic alembic

# Default command (can be overridden in docker-compose). Apply DB migrations
# before serving so the schema is current; on an already-current DB this is a
# fast no-op.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
