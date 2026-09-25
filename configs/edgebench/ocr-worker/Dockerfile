# Pinned base image by digest: python:3.11-slim (Debian trixie / arm64)
FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

# Install Tesseract 5.x and iproute2 (for tc netem)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    iproute2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies for ocr_service
RUN pip install --no-cache-dir pillow

WORKDIR /app

# Record Tesseract version
RUN tesseract --version > /app/tesseract-version.txt && cat /app/tesseract-version.txt

# Fetch pinned OCR weights and verify SHA-256
RUN mkdir -p /app/weights/tessdata_fast /app/weights/tessdata_best \
    && curl -sSL -o /app/weights/tessdata_fast/eng.traineddata \
       https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata \
    && echo "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2  /app/weights/tessdata_fast/eng.traineddata" | sha256sum -c - \
    && curl -sSL -o /app/weights/tessdata_best/eng.traineddata \
       https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/e12c65a915945e4c28e237a9b52bc4a8f39a0cec/eng.traineddata \
    && echo "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba  /app/weights/tessdata_best/eng.traineddata" | sha256sum -c -

# Copy code
COPY src/ocr_service.py /app/src/ocr_service.py
COPY configs/edgebench/ocr-worker/entrypoint.py /app/entrypoint.py

ENV PYTHONPATH=/app
EXPOSE 18764

ENTRYPOINT ["python3", "/app/entrypoint.py"]
