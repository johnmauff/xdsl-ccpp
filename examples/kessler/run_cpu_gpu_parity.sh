#!/usr/bin/env bash
# Runs examples/kessler's cross-build CPU-vs-GPU numerical parity check
# end to end: configures/builds a CPU tree and a GPU tree (both from this
# same checkout), then runs ctest_kessler_cpu_gpu_parity from the GPU tree
# against the CPU tree as reference. Wraps the 4 cmake commands + 1 ctest
# command from the README's own manual recipe into one script.
#
# Usage: examples/kessler/run_cpu_gpu_parity.sh [cpu_build_dir] [gpu_build_dir]
#   cpu_build_dir defaults to build-cpu, gpu_build_dir defaults to build-gpu
#   (both resolved relative to the repo root -- this script cd's there
#   first, so it can be run from anywhere).
#
# Requires nvfortran already on PATH (e.g. `module load nvhpc` on Derecho)
# -- this script does not load modules itself, since how modules get set up
# in a non-interactive shell varies by system.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

CPU_BUILD_DIR="${1:-build-cpu}"
GPU_BUILD_DIR="${2:-build-gpu}"

if ! command -v nvfortran >/dev/null 2>&1; then
  echo "error: nvfortran not found on PATH -- load it first (e.g. 'module load nvhpc' on Derecho)" >&2
  exit 1
fi

KESSLER_TARGETS=(kessler_ccpp.exe kessler_hand.exe kessler_cxx.exe kessler_cxx_host.exe)
TARGET_ARGS=()
for t in "${KESSLER_TARGETS[@]}"; do
  TARGET_ARGS+=(--target "$t")
done

echo "=== Configuring CPU build (${CPU_BUILD_DIR}) ==="
cmake -S . -B "${CPU_BUILD_DIR}"
echo "=== Building CPU kessler drivers ==="
cmake --build "${CPU_BUILD_DIR}" "${TARGET_ARGS[@]}"

CPU_BUILD_ABS="$(cd "${CPU_BUILD_DIR}" && pwd)"

echo "=== Configuring GPU build (${GPU_BUILD_DIR}) ==="
cmake -S . -B "${GPU_BUILD_DIR}" -DARCH=GPU \
  -DKESSLER_CPU_GPU_REFERENCE_BUILD="${CPU_BUILD_ABS}"
echo "=== Building GPU kessler drivers ==="
cmake --build "${GPU_BUILD_DIR}" "${TARGET_ARGS[@]}"

echo "=== Running cross-build CPU-vs-GPU parity check ==="
ctest --test-dir "${GPU_BUILD_DIR}" -R kessler_cpu_gpu_parity --output-on-failure
