# Jogan API image for Cloud Run (DECISIONS.md D-022).
# The demo bundle (world, forecaster, every test day's plan) is rebuilt from its seed during
# the build, so no data or model file is ever committed (D-002 #7).
FROM python:3.12-slim-trixie

# LightGBM needs the OpenMP runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# dependencies first, so code changes reuse this layer
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project

COPY jogan ./jogan
COPY configs ./configs
RUN uv sync --locked --no-dev

ARG JOGAN_PROFILE=full
ARG JOGAN_SEED=42
RUN .venv/bin/python -m jogan.api.bundle --profile "$JOGAN_PROFILE" --seed "$JOGAN_SEED" --out /app/bundle

RUN useradd --system --uid 10001 --no-create-home jogan
USER jogan

# Cloud Run's front end appends the client address to X-Forwarded-For; the rate limits read
# it one entry from the right, since anything further left can be forged (D-024)
ENV PATH=/app/.venv/bin:$PATH \
    JOGAN_BUNDLE_DIR=/app/bundle \
    JOGAN_ENV=production \
    JOGAN_TRUSTED_PROXY_HOPS=1 \
    PORT=8080

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn --factory jogan.api.app:from_env --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips '*'"]
