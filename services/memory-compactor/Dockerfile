FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir asyncpg httpx pydantic

COPY . .

CMD ["python", "-m", "compactor"]