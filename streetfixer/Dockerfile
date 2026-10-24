# Street Fixer web app for Cloud Run (listens on $PORT, default 8080).
# Secrets (GEMINI_API_KEY, MONGODB_URI, ...) come from Cloud Run env vars, never the image.
FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY data data
ENV PYTHONUNBUFFERED=1
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'
