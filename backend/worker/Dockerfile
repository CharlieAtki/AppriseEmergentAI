FROM python:3.14-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY core/ ./core/
RUN uv pip install --system --no-cache ./core

COPY worker/ ./worker/
RUN uv pip install --system --no-cache ./worker

CMD ["arq", "worker.settings.WorkerSettings"]
