# Data Universe Miner Doctor
#
# NOTE: Docker is OPTIONAL. The primary, recommended workflow is a local
# `pip install -e .` on the miner's Ubuntu/Linux server so the tool can read
# PM2, processes, logs, and local data directly. This image is provided for
# convenience and CI only.
#
# The bittensor SDK is NOT installed here by default (it is heavy). Build with
#   docker build --build-arg WITH_BITTENSOR=1 -t du-doctor .
# to include it for live chain/metagraph checks.

FROM python:3.11-slim

ARG WITH_BITTENSOR=0

# git is needed for repo checks; procps gives a usable process table.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -e . \
    && if [ "$WITH_BITTENSOR" = "1" ]; then pip install --no-cache-dir ".[bittensor]"; fi

# Run as a non-root user by default (read-only tool; no need for root).
RUN useradd --create-home --uid 1000 doctor
USER doctor

ENTRYPOINT ["du-doctor"]
CMD ["check"]
