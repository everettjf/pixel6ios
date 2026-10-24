#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
export PATH="$root/artifacts/build-bin:/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/opt/gnu-sed/libexec/gnubin:$PATH"
export CROSS_PREFIX=aarch64-elf-
export CROSS_OBJDUMP=aarch64-elf-objdump
export CROSS_NM=aarch64-elf-nm
export PYTHON="$root/artifacts/build-venv/bin/python"
cd "$root/research/pixelios-kernel"
exec bash shim/build.sh "$@"
