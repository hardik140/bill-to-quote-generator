FROM python:3.11-slim

# Install system packages needed for Tesseract OCR and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_TESSERACT_CMD=tesseract

# Expose port (Render automatically sets $PORT)
EXPOSE 8000

# Start FastAPI via uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
