# The CRT on Linux, in Docker: builds librashader-cli (tools/crt/install_librashader.py) and runs the renderer on
# Mesa's lavapipe, Vulkan on the CPU, so it needs no GPU. Ubuntu 22.04, like the Dolphin package (glibc 2.35).
# From the repo root (tools/crt/README.md):
#
#   docker build -t asv-crt -f tools/crt/linux.Dockerfile tools/crt
#   docker run --rm -v "$PWD":/repo -v asv-crt-packages:/repo/packages -v asv-crt-cache:/asv asv-crt \
#       python3 tools/crt/install_librashader.py
#   docker run --rm -v "$PWD":/repo -v asv-crt-packages:/repo/packages -v asv-crt-cache:/asv asv-crt \
#       python3 tools/crt/render_video.py IN.mov OUT.mov --physical-pixels
#
# The packages volume keeps the Linux build of librashader-cli apart from the Mac's packages/ folder.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates python3 libvulkan1 mesa-vulkan-drivers ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Rust 1.88.0, as in tools/dolphin-build/linux.Dockerfile, usable by whichever user runs the container
ENV RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/rust/cargo PATH=/opt/rust/cargo/bin:$PATH
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal --default-toolchain 1.88.0 \
    && chmod -R a+rwX /opt/rust

# The cache (/asv) is a volume, so the crates and the build survive the container.
ENV ALPHASOLVE_CACHE=/asv CARGO_HOME=/asv/cargo HOME=/tmp PYTHONDONTWRITEBYTECODE=1
WORKDIR /repo
