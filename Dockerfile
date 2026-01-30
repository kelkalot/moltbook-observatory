FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /data

# Set environment variables
ENV DATABASE_PATH="/data/observatory.db"
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "observatory.main:app", "--host", "0.0.0.0", "--port", "8080"]
