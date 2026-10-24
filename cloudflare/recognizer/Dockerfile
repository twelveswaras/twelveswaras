# Recognizer container for Cloudflare Containers: FastAPI + essentia (predominant pitch and tonic)
# + xgboost, numpy<2 (compiam stays installed only to hold numpy below 2). Build context is this dir;
# ./app is produced by assemble.sh (app code + the chosen model). essentia gets real x86_64 Linux
# wheels here (unlike an arm64 Mac), so the pip install that works on HF works here.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libsndfile1 build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY app/ .
# The first librosa.load in a process makes numba compile librosa's code: ~30 s on the 0.5 vCPU
# container, paid by the first visitor after every wake (measured 2026-10-24: first answer 42.6 s).
# Compile it here instead, into a cache that ships in the image. NUMBA_CPU_NAME=generic is what
# makes that cache reusable: the image is built under emulation and runs on Cloudflare's CPUs, and
# numba only reuses a cache built for the same CPU name, so a host-specific one would silently miss.
ENV MODEL_PATH=/app/models/raaga_xgb.json \
    NUMBA_CACHE_DIR=/app/.numba_cache \
    NUMBA_CPU_NAME=generic
RUN python -c "import api; api._prime()"
EXPOSE 7860
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]
