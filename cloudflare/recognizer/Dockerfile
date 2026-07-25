# Recognizer container for Cloudflare Containers. Same stack as the HF Docker Space: FastAPI +
# essentia (predominant pitch) + compiam (tonic) + xgboost, numpy<2. Build context is this dir;
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
ENV MODEL_PATH=/app/models/raaga_xgb.json
EXPOSE 7860
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]
