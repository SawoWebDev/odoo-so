# Playwright image ships Chromium + all system libs (Python 3.12).
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# LibreOffice (DOCX -> PDF) and fonts that cover common label text.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer fonts-dejavu fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY pytest.ini .

RUN useradd -m app && mkdir -p /data/storage && chown -R app /data /srv
USER app
EXPOSE 8000
# The backend is only reachable through the frontend (nginx), so trusting its X-Forwarded-For is safe: the login
# throttle then keys on the real client address. Do NOT publish port 8000 directly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
