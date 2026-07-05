# Headless recognizer API as a Hugging Face Docker Space (or any container host).
# The assembled build (space/assemble.sh output, or the repo) provides raaga_id/, models/, api.py.
FROM python:3.10-slim

# ffmpeg: decode webm/opus/m4a the browser sends. libsndfile: soundfile backend.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libsndfile1 build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY . .
ENV MODEL_PATH=/app/models/raaga_xgb.json
# HF Spaces route to $PORT (7860). Warm the model on the first request, not at build.
EXPOSE 7860
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]
