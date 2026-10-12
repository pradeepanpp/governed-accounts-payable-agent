
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install local OCR with English and Arabic language support.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*

# Install Python application dependencies.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy the existing Python package, including our new API.
COPY governed_ap/ ./governed_ap/

# Do not run the application as root.
RUN useradd --system --uid 10001 --create-home appuser
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "governed_ap.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
