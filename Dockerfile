FROM pytorch/pytorch:2.14.0-cuda13.0-cudnn9-runtime@sha256:9c99fafa01edfaa3d16da8c209b38b5970bb6fd6e72725ef60efc901489f70c6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/traffic \
    YOLO_CONFIG_DIR=/home/traffic/.config/ultralytics \
    MPLCONFIGDIR=/home/traffic/.cache/matplotlib \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 traffic \
    && useradd --uid 10001 --gid traffic --create-home traffic \
    && python -m venv --system-site-packages /opt/venv

COPY requirements-container.txt ./
RUN python -m pip install -r requirements-container.txt && python -m pip check

COPY app/ ./app/
COPY configs/runtime/ ./configs/runtime/
COPY data/evaluation/dedicated_crowd_counting.json ./data/evaluation/dedicated_crowd_counting.json
COPY scripts/migrate_database.py ./scripts/migrate_database.py
COPY scripts/check_backend_runtime.py ./scripts/check_backend_runtime.py
RUN mkdir -p data/input data/output models /home/traffic/.config/ultralytics /home/traffic/.cache/matplotlib \
    && chown -R traffic:traffic data/input data/output /home/traffic

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=8).close()"]
CMD ["python", "-m", "uvicorn", "app.api.application:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
