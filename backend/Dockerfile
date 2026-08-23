FROM python:3.11-slim

# Install system packages needed for OpenCV and PaddlePaddle's OpenMP
# runtime (libgomp1 -- paddlepaddle fails to import without it on a
# Debian/Ubuntu base).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY . .

# Pre-download PaddleOCR's model weights into this image layer at build
# time, not on the first request -- Render's filesystem is ephemeral, so a
# lazy download would otherwise repeat on every deploy/restart. If the
# Windows/oneDNN crash this app worked around (see Settings.ocr_enable_mkldnn)
# turns out to be Windows-specific, this build step is also where that
# would first surface for the Linux target -- watch the build log.
RUN python -c "from app.services.ocr.engine import _get_engine; _get_engine()"

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (Render automatically sets $PORT)
EXPOSE 8000

# Start FastAPI via uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
