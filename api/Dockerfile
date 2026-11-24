# =============================================================================
#  API d'inférence du rendement agricole — image multi-étapes
#  Section 4.2 : python:3.12-slim, utilisateur non root, < 500 Mo, HEALTHCHECK
#
#  Contexte de construction = RACINE du dépôt, car l'image embarque aussi le
#  modèle versionné de model/ :
#      docker build -f api/Dockerfile -t crop-yield-api:1.0.0 .
#
#  Une première version naïve pesait 816 Mo, au-dessus de la limite. Les
#  mesures et le détail des réductions sont dans le README, section 4.2.
# =============================================================================

# --- Étape 1 : construction et dégraissage des dépendances ------------------
FROM python:3.12-slim AS builder

# binutils fournit « strip ». Il reste dans cette étape et ne pèse rien dans
# l'image finale : c'est tout l'intérêt du multi-étapes.
RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY api/requirements.txt /tmp/requirements.txt
# Cache de pip monté hors image : les reconstructions sont rapides et le
# cache ne se retrouve pas dans une couche.
# --no-compile : pas de .pyc, le conteneur les recréera s'il en a besoin.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile -r /tmp/requirements.txt

# Dégraissage, du plus rentable au moins rentable :
#   1. suites de tests des bibliothèques scientifiques  (~100 Mo)
#   2. symboles de débogage des bibliothèques natives   (~205 Mo de .so)
#   3. pip, setuptools et wheel, inutiles à l'exécution (~13 Mo)
RUN find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -type d \( -name "tests" -o -name "test" \) -prune -exec rm -rf {} + 2>/dev/null; \
    rm -rf /opt/venv/lib/python3.12/site-packages/pip \
           /opt/venv/lib/python3.12/site-packages/pip-* \
           /opt/venv/lib/python3.12/site-packages/setuptools \
           /opt/venv/lib/python3.12/site-packages/setuptools-* \
           /opt/venv/lib/python3.12/site-packages/pkg_resources \
           /opt/venv/lib/python3.12/site-packages/wheel*; \
    find /opt/venv -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null; \
    true

# --- Étape 2 : image d'exécution --------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MODEL_PATH=/app/model/model-1.0.0.joblib \
    MODEL_VERSION=1.0.0 \
    API_VERSION=1.0.0 \
    PORT=8000

# Utilisateur non root : exigé par l'énoncé, et de toute façon la bonne
# pratique pour un conteneur exposé sur Internet.
RUN useradd --create-home --uid 10001 apiuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY api/main.py /app/main.py
COPY model/model-1.0.0.joblib /app/model/model-1.0.0.joblib

RUN chown -R apiuser:apiuser /app
USER apiuser

EXPOSE 8000

# HEALTHCHECK sans curl : l'image slim n'en contient pas, et l'installer pour
# trois lignes de vérification serait du poids gratuit. urllib suffit.
# start-period couvre le chargement du modèle, mesuré à 1,2 s à froid.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
