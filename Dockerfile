FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /bin/uv
WORKDIR /srv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
# The OpenSSL inside the cryptography wheel dies with "Illegal instruction" while probing CPU features in
# Docker Desktop's VM on Apple Silicon. 0 turns the probe and the ARM fast paths off; x86 ignores it.
ENV OPENSSL_armcap=0
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
