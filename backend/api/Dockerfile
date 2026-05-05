FROM python:3.11-slim

WORKDIR /app

# Install core first (local dependency)
COPY core/ ./core/
RUN pip install --no-cache-dir ./core

# Install api and its dependencies
COPY api/ ./api/
RUN pip install --no-cache-dir ./api

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
