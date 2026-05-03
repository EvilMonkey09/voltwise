# docker build -t voltwise-sd-builder tools/image-build
# See tools/image-build/build-image.sh
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates xz-utils fdisk dosfstools kpartx coreutils mount util-linux \
    rsync file sudo \
    && rm -rf /var/lib/apt/lists/*

COPY docker-build-inner.sh /docker-build-inner.sh
RUN chmod +x /docker-build-inner.sh

ENV SOURCE_DIR=/src OUTPUT_DIR=/out CACHE_DIR=/cache

ENTRYPOINT ["/docker-build-inner.sh"]
