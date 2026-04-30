# ── Liberty Basketball Analysis – Dockerfile ─────────────────────────
# Uses Python 3.12 slim. PyTorch is installed CPU-only to keep the image
# manageable (~3 GB). For GPU support swap the torch install line below.

FROM python:3.12-slim

WORKDIR /app

# System libs required by OpenCV headless + scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────
# Install PyTorch CPU-only first (smaller than CUDA build, ~700 MB)
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.docker.txt .
RUN pip install --no-cache-dir -r requirements.docker.txt

# ── Application code ───────────────────────────────────────────────────
COPY . .

# Pre-download YOLO model so first-run doesn't need internet access
# (comment out if you prefer lazy download on first use)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" 2>/dev/null || true

# Ensure uploads dir exists inside the image (volume mount will overlay it)
RUN mkdir -p uploads

EXPOSE 8080

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Use a production-friendly command (no debug reloader in container)
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=8080"]
