FROM python:3.14-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY core/ ./core/
RUN uv pip install --system --no-cache ./core

COPY api/ ./api/
RUN uv pip install --system --no-cache ./api

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
