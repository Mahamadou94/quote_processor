# ============================
# Stage 1: Builder
# ============================
FROM python:3.10-slim AS builder

WORKDIR /app

# Installer les dépendances nécessaires au build Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libc6-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements.txt puis installer les dépendances Python
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# ============================
# Stage 2: Runtime
# ============================
FROM python:3.10-slim

WORKDIR /app

# Installer les dépendances système nécessaires à PaddleOCR, OpenCV, PyMuPDF et pdftotext
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    poppler-utils \
    libgthread-2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier les dépendances Python installées depuis le builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Variables d'environnement de base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Créer un utilisateur non-root
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copier le code applicatif
COPY fastapi_ocr_llm_light_app.py /app/fastapi_ocr_llm_light_app.py

# Donner les droits au user applicatif
RUN chown -R appuser:appuser /app

# Passer en utilisateur non-root
USER appuser

# Exposer le port FastAPI
EXPOSE 8000

# Healthcheck local au container
# Ici on utilise curl installé dans l'image runtime.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Démarrage de l'application
# 1 worker conseillé car PaddleOCR consomme beaucoup de RAM donc une seule instance paddelocr est préférable pour éviter les conflits de ressources.
CMD ["uvicorn", "fastapi_ocr_llm_light_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]