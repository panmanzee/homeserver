FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# All deps (incl. lxml/trafilatura, psycopg[binary]) ship manylinux wheels for
# amd64/arm64. If pip tries to build from source on your arch, add:
#   RUN apt-get update && apt-get install -y --no-install-recommends \
#         build-essential libxml2-dev libxslt1-dev && rm -rf /var/lib/apt/lists/*
# Chromium + Thai/emoji fonts for the morning infographic (HTML -> PNG).
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium fonts-noto-core fonts-thai-tlwg fonts-noto-color-emoji fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
