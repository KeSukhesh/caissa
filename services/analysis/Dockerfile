# Caïssa analysis service — FastAPI + python-chess + Stockfish.
FROM python:3.12-slim

# Stockfish binary (GPL) — invoked via UCI as a separate process.
RUN apt-get update && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip install --no-cache-dir uvicorn[standard]

COPY app ./app
ENV STOCKFISH_PATH=/usr/games/stockfish
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
