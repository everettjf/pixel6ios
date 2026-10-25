#!/bin/bash
# Build the pinned Pixel 6 framebuffer diagnostic entirely on this Mac.
# Produces a temporary-boot image; never contacts or writes to the phone.
set -euo pipefail
cd "$(dirname "$0")/.."

# Host tests in shim/build.sh use gcc directly and require GCC's noipa
# attribute. The local tool directory points to Homebrew GCC on this Mac.
if [ -x private/gate-bin/gcc ]; then
	export PATH="$(pwd)/private/gate-bin:$PATH"
fi
# The shim's mkbootimg step imports lz4.frame. Prefer the repository's
# already-provisioned local venv when the system Python lacks it.
if ! python3 -c 'import lz4.frame' >/dev/null 2>&1 &&
   [ -x private/gate-venv/bin/python3 ]; then
	export PATH="$(pwd)/private/gate-venv/bin:$PATH"
fi
python3 -c 'import lz4.frame' || {
	printf 'Missing Python lz4; install it in a local venv before building.\n' >&2
	exit 2
}

export CROSS_PREFIX="${CROSS_PREFIX:-/opt/homebrew/bin/aarch64-elf-}"
export CROSS_CC="${CROSS_CC:-${CROSS_PREFIX}gcc}"
export CROSS_OBJDUMP="${CROSS_OBJDUMP:-${CROSS_PREFIX}objdump}"
export CROSS_OBJCOPY="${CROSS_OBJCOPY:-${CROSS_PREFIX}objcopy}"
export CROSS_READELF="${CROSS_READELF:-${CROSS_PREFIX}readelf}"
export CROSS_NM="${CROSS_NM:-${CROSS_PREFIX}nm}"

kernel=private/fbsnap-work/local-relink/kernel.oriole-fbsnap
adt=private/fbsnap-work/payload/oriole-ufsroot-cow.adt
payload=private/fbsnap-work/payload/rebuilt.bin
image=research/pixelios-kernel/shim/out/shim-boot-avb.img
"$CROSS_CC" --version >/dev/null
python3 tools/relink-oriole-fbsnap-xnu.py
python3 research/pixelios-kernel/tools/oriole_ufsroot_cow_pool512_fbsnap.py \
  --kernel "$kernel" --adt "$adt" --out "$payload"
research/pixelios-kernel/shim/build.sh --board oriole --avb \
  --xnu-ufsroot-cow-pool512-fbsnap "$(pwd)/$payload"
python3 research/pixelios-kernel/tools/oriole_ufsroot_cow_pool512_fbsnap.py \
  --check-image "$image"
python3 research/pixelios-kernel/tools/imgmeta.py check "$image" --expect xnu
shasum -a 256 "$kernel" "$payload" "$image"
printf 'LOCAL BUILD PASS: %s\n' "$image"
