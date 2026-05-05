# ── Liberty Basketball Analysis – Dockerfile ─────────────────────────
# CPU is the default build. Override TORCH_INDEX_URL (for example to the
# PyTorch CUDA wheel index) to build a GPU-capable image on hosts with the
# NVIDIA container runtime installed.

FROM python:3.12-slim

WORKDIR /app

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_PACKAGES="torch torchvision"

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
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ${TORCH_PACKAGES} --index-url ${TORCH_INDEX_URL}

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

ENV PYTHONUNBUFFERED=1
ENV LIBERTY_DEBUG=0
ENV PORT=8080
ENV LIBERTY_DATABASE=/app/film_analysis.db
ENV LIBERTY_UPLOAD_FOLDER=/app/uploads
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Use the same app entrypoint as the standalone install, but with debug off.
CMD ["python", "app.py"]
