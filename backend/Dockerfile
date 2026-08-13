# MIDIgen API — Python 3.12 + FastAPI + llama-cpp-python (CPU)
# Build: docker build -t midigen-backend ./backend
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt pyproject.toml README.md ./
COPY app ./app

RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /venv/bin/pip install --no-cache-dir .


FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin midigen

COPY --from=builder /venv /venv

ENV PATH="/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    UVICORN_RELOAD=0 \
    LOCAL_N_GPU_LAYERS=0 \
    LOCAL_MODEL_PATH=/app/models/Qwen3-4B-Q4_K_M.gguf

WORKDIR /app

COPY run.py ./
COPY models/README.txt ./models/README.txt

RUN mkdir -p /app/models /app/generated \
    && chown -R midigen:midigen /app

USER midigen

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "run.py"]
