FROM python:3.12-slim
WORKDIR /app

# Some Coolify versions generate an HTTP probe that requires curl or wget.
# Install curl in the container (not just on the host) for that fallback.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY server.py Coloring_Book_Forge.html index.html coloring_prompts_master_36000.json ./
COPY sample_pages/ sample_pages/
COPY niche_packs/ niche_packs/
RUN mkdir -p output_production

EXPOSE 8080
ENV PORT=8080

# Image-owned check: GET the live API, and require the full prompt library.
# Coolify versions that honor Dockerfile HEALTHCHECK can use this directly.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD ["python3", "-c", "import json,sys,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/meta',timeout=5)); sys.exit(0 if d.get('total_prompts',0)>=36000 else 1)"]

CMD ["python3", "server.py"]

