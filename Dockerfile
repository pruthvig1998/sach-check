FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir beautifulsoup4 anthropic
COPY sach ./sach
COPY data/seed_debunks.json ./data/seed_debunks.json
ENV PORT=8080 SACH_CACHE_DIR=/tmp/cache SACH_LEDGER=/tmp/ledger.json
CMD ["python", "-m", "sach.web"]
