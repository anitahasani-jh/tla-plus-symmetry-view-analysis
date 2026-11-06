# SymView -- reproducible TLC experiments.
#
# The image ships Python 3.11 and a Java runtime; TLC 2.16 (tla2tools-1.7.1.jar)
# is copied from the repository.  TLC needs Java 8 or newer and is verified on
# Java 8 and JDK 17; default-jre-headless on Debian bookworm is JDK 17.
#
# Build:
#   docker build -t symview .
# Run:
#   docker run --rm -it -v "$PWD/results:/opt/symview/results" symview
# then inside the container:
#   bash run_all.sh --quick
#
# Keep the TLC jar alone in tools/: its manifest declares
# "Class-Path: CommunityModules.jar", which the JVM resolves relative to the
# jar's directory.  Never COPY a CommunityModules.jar into tools/.

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/symview/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-jre-headless \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/symview

# Dependencies first so that the layer is cached across source edits.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY . .

# Offline path: requirements are installed above and the pinned jar is part of
# the repository, so setup.sh must not download anything.  It verifies the
# SHA-256, creates the output directories and runs the static smoke test.
RUN bash setup.sh --offline

ENTRYPOINT ["bash"]
