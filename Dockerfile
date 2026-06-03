FROM python:3.12-slim AS generator

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY fixtures/ ./fixtures/
COPY public/assets/ ./public/assets/
COPY README.md ./
COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt \
    && python -m py_compile scripts/generate_report.py scripts/ghstar_agent.py scripts/run_smoke_test.py

CMD ["python", "scripts/generate_report.py"]

FROM nginx:1.27-alpine AS web

COPY public/ /usr/share/nginx/html/
