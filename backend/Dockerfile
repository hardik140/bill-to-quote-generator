FROM python:3.11-slim

# Lightweight OCR for Render's 512 MB free instance.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.render.txt

# Copy backend source code
COPY . .

RUN tesseract --version

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_OCR_PROCESSOR_NAME=tesseract
ENV APP_OCR_PROCESSOR_VERSION=5
ENV OMP_THREAD_LIMIT=1

# Expose port (Render automatically sets $PORT)
EXPOSE 8000

# Start FastAPI via uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
