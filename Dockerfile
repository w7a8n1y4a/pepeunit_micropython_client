FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ca-certificates \
    make cmake ninja-build ccache \
    python3 python3-pip python3-venv python3-dev python3-setuptools \
    gcc g++ \
    flex bison gperf \
    libffi-dev libssl-dev \
    dfu-util libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir esptool pyserial

WORKDIR /project
COPY . .

ARG BOARDS=ALL
ARG TAG
ARG VERSION

RUN chmod +x micropython_pepeunit_build.sh \
    && ./micropython_pepeunit_build.sh "${BOARDS}" "${TAG}" "${VERSION}" \
    && mkdir -p /output && cp ./*.bin /output/

FROM busybox:stable
COPY --from=builder /output /output
CMD ["ls", "/output"]
