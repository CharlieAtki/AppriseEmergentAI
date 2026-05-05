FROM python:3.11-slim

WORKDIR /app

# Install core first (local dependency)
COPY core/ ./core/
RUN pip install --no-cache-dir ./core

# Install worker and its dependencies
COPY worker/ ./worker/
RUN pip install --no-cache-dir ./worker

CMD ["python", "-m", "worker.main"]
