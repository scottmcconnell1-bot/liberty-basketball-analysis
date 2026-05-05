# Deployment and Operations

This document covers standalone installation, container installation, GPU container enablement, server transfer, and restore steps.

## 1. Recommended setup path

Run the project setup TUI:

```bash
python3 scripts/setup_project.py
```

It provides menu options for:

1. standalone install
2. container install with automatic CPU/GPU selection
3. forced CPU container install
4. forced GPU container install
5. building the transfer bundle

## 2. Standalone installation

### Prerequisites

- Python 3.12+
- `python3-venv`
- `ffmpeg`
- enough disk for uploads, model weights, and SQLite data

### Manual commands

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -c "from app import app, init_db; ctx = app.app_context(); ctx.push(); init_db(); ctx.pop()"
LIBERTY_DEBUG=0 PORT=8080 .venv/bin/python app.py
```

### Standalone environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `LIBERTY_DATABASE` | `film_analysis.db` | SQLite file path |
| `LIBERTY_UPLOAD_FOLDER` | `uploads` | upload directory |
| `PORT` | `8080` | app bind port |
| `LIBERTY_DEBUG` | `1` | turn this off on servers |

### Systemd service

Use `deploy/liberty-basketball-analysis.service` as the template for a long-running server install.

Basic flow:

1. copy the repo to `/opt/liberty-basketball-analysis`
2. customize `User`, `WorkingDirectory`, and `ExecStart`
3. copy the file to `/etc/systemd/system/liberty-basketball-analysis.service`
4. run `sudo systemctl daemon-reload`
5. run `sudo systemctl enable --now liberty-basketball-analysis`

## 3. Container installation

### CPU container

```bash
docker compose up -d --build
```

### GPU container

The GPU path uses the same base compose file plus the GPU override:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

### GPU prerequisites

- NVIDIA drivers installed on the host
- NVIDIA Container Toolkit configured for Docker
- `nvidia-smi` works on the host

### How GPU support works

- `Dockerfile` defaults to CPU wheels using `https://download.pytorch.org/whl/cpu`
- `docker-compose.gpu.yml` overrides the build arg to the CUDA wheel index
- `docker-compose.gpu.yml` also requests `gpus: all`
- the app itself already detects GPU availability at runtime via `nvidia-smi`

## 4. Runtime files and persistence

These paths hold the project state and should be preserved during migration:

- `film_analysis.db`
- `uploads/`
- local model weights such as `yolov8n.pt`, `yolov8m.pt`, `yolo11m.pt`

## 5. Build a transfer bundle

Create the archive:

```bash
bash scripts/build_transfer_bundle.sh
```

Output location:

```text
transfer-bundles/liberty-basketball-analysis-transfer-<timestamp>.tar.gz
```

Included content:

- application code
- templates
- docs
- tests
- Docker/compose files
- setup and transfer scripts
- `film_analysis.db`
- `uploads/`
- local `.pt` model files in the repo root

Excluded content:

- `.git/`
- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- previously generated transfer bundles

## 6. Restore on another server

### Standalone restore

1. copy the tarball to the target server
2. extract it:
   ```bash
   tar -xzf liberty-basketball-analysis-transfer-<timestamp>.tar.gz
   cd liberty-basketball-analysis
   ```
3. run `python3 scripts/setup_project.py`
4. choose **Install standalone**
5. start the app or install the systemd service

### Container restore

1. copy and extract the tarball
2. run `python3 scripts/setup_project.py`
3. choose the container path
4. let the setup script choose the GPU override automatically when applicable

## 7. Validation commands

### App tests

```bash
.venv/bin/python -m pytest tests/ -q
```

### Container logs

```bash
docker compose logs -f
```

### GPU visibility in a container

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec web nvidia-smi
```

## 8. Troubleshooting

### The standalone install fails on system packages

Install the required OS dependencies first, especially `ffmpeg` and the OpenCV shared libraries used in the Docker image (`libglib2.0-0`, `libsm6`, `libxext6`, `libxrender1`, `libgomp1`).

### Docker GPU mode builds but the app does not use the GPU

Check the host first:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If those fail, the issue is the host/container runtime, not the application.

### Resource panel shows unavailable power/GPU values

That is expected when the host does not expose the corresponding telemetry sources (`nvidia-smi` or Linux powercap/RAPL).
