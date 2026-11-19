# Builds the Linux package (tools/dolphin-build/build-linux-mainline.py) in Ubuntu 22.04, whose glibc (2.35) sets the
# oldest Linux the package runs on. It needs no root on the host, so it also suits a machine where you can't apt
# install the build packages. From the repo root (docs/plan-linux.md):
#
#   docker build -t asv-linux -f tools/dolphin-build/linux.Dockerfile tools/dolphin-build
#   mkdir -p ~/.cache/AlphaSolveVideo-docker
#   docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/repo -v ~/.cache/AlphaSolveVideo-docker:/asv asv-linux \
#       python3 tools/dolphin-build/build-linux-mainline.py
#
# The package lands in packages/slippi-playback-mainline/, as with a build on the machine itself.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git pkg-config curl ca-certificates xz-utils python3 python3-venv nasm \
        zlib1g-dev libasound2-dev libegl-dev \
    && rm -rf /var/lib/apt/lists/*

# Rust 1.88.0 (Externals/SlippiRustExtensions/rust-toolchain.toml), usable by whichever user runs the container
ENV RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/rust/cargo PATH=/opt/rust/cargo/bin:$PATH
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal \
        --default-toolchain 1.88.0 --component rustfmt \
    && chmod -R a+rwX /opt/rust

# The work folder is a volume (/asv), so the source, the build and the crates downloaded survive the container.
ENV ALPHASOLVE_CACHE=/asv CARGO_HOME=/asv/cargo HOME=/tmp PYTHONDONTWRITEBYTECODE=1
WORKDIR /repo
