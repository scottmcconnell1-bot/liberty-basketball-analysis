FROM python:3.11-slim
Install OS packages required for building common Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git cmake libpq-dev curl unzip \
    libgl1-mesa-glx libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

Copy requirements first to leverage Docker cache
COPY requirements.txt .

ENV PIP_NO_CACHE_DIR=1
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -r requirements.txt

Copy application code
COPY . .

Default port used by Render (override via Render service settings)
ENV PORT=10000
EXPOSE $PORT

Run with gunicorn, binding to the runtime PORT env var
CMD ["sh","-c","gunicorn app:app --bind 0.0.0.0:$PORT --workers 1"]
