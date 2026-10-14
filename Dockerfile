# Security remediation candidate. Compare its scan with the Bookworm baseline
# and verify that the real PDF/OCR tests pass before using it for a release.
FROM python:3.11-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install local OCR using Debian 13's maintained OS packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*

# Build-time package utilities are not intentionally used by this HTTP service.
# Remove them from the runtime image to eliminate vulnerable vendored copies;
# validate runtime imports, OCR, and API behavior in Docker before merging.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall --yes setuptools wheel \
    && python -m pip check

COPY governed_ap/ ./governed_ap/

# Preserve the previously implemented unprivileged runtime.
RUN useradd --system --uid 10001 --create-home appuser
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "governed_ap.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
