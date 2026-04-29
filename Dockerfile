# SPDX-License-Identifier: GPL-3.0-or-later
# Logs go to stdout by default (LOG_OUTPUT=stdout, LOG_FORMAT=json).
# ECS awslogs driver, Docker log driver, and k8s kubectl logs all consume stdout.

FROM python:3.13-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

FROM python:3.13-slim
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/

RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/')" || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", \
     "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
