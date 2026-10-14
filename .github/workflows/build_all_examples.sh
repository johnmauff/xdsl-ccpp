#!/usr/bin/env bash
#
# Shared build+test driver for compile-tests-cmake.yml's gnu and intel jobs.
#
# Configures the whole repo once, then builds and ctests every wired-in
# example in turn, inside a single runner -- so adding a second compiler
# costs one extra job (and one extra toolchain install) instead of one
# extra job PER EXAMPLE (ci-multi-compiler, BACKLOG.md). Each entry here
# must stay in sync with the example/targets/ctest_filter that used to
# live in compile-tests-cmake.yml's own matrix -- there is no single
# source of truth to generate this from, so an example's CMakeLists.txt
# changing its own target name(s) needs a matching edit here.
#
# Env vars read:
#   FC/CC/CXX      -- compiler to configure with (unset = CMake's
#                     platform default, i.e. gfortran/gcc/g++)
#   COMPILER_LABEL -- which job is calling this script (gnu/intel/nvhpc);
#                     used only to scope EXPECTED_FAILURES below to the
#                     exact compiler a known bug was found under. Default
#                     "gnu" matches the gnu job, which sets no FC/CC/CXX.

set -uo pipefail

EXAMPLES=(
  "nested_suite|nested_suite_host_integration|"
  "var_compat|var_compatibility_host_integration|"
  "tinyddt|tinyddt_cxx_host|"
  "advection|advection.exe|advection_host"
  "advection_flat_host|advection_flat.exe|"
  "kessler|kessler_ccpp.exe kessler_hand.exe kessler_cxx.exe kessler_cxx_host.exe|"
  "nestedddt|nestedddt_cxx_host|"
  "chararg|chararg_cxx_host|"
  "constadv|constadv_cxx_host|"
  "constprop|constprop_cxx_host|"
  "ddthost|ddthost_ftn_host.exe ddthost_cxx_host.exe|"
  "capgen|capgen_ftn_host.exe capgen_cxx_host.exe|"
  "helloworld|helloworld.exe|"
  "chunked_data|chunked_data.exe|"
  "constituents_dim|constituents_dim.exe|"
  "opt_arg|opt_arg_host_integration|"
  "suite_allocate|suite_allocate.exe|"
  "instances|instances.exe|instances\$"
  "instances_advection|instances_advection.exe|"
  "threads|threads.exe|"
)

# Expected failures: real, already-tracked bugs, each with its own
# BACKLOG.md item -- found by this very script under Intel ifx (passes
# silently under gfortran and has never been run under nvhpc). Listed
# here, not silently swallowed, so a failure here still shows up in the
# summary table and the job log; it just doesn't fail the job, since
# fixing each is separate, larger work than this CI change. Scoped to
# the exact compiler/phase a bug was actually found under (Copilot
# review on PR #133) -- a GNU regression in either example, or an Intel
# failure in the OTHER phase than documented, is a NEW problem and must
# still fail the job. Format: "compiler|example|status". Remove an
# entry once its backlog item is closed.
#   intel|instances|BUILD_FAIL:  ccpp-validator-length-check (CHANGELOG.md L11491)
EXPECTED_FAILURES=(
  "intel|instances|BUILD_FAIL"
)
COMPILER_LABEL="${COMPILER_LABEL:-gnu}"

cmake -S . -B build

overall_status=0
result_lines=()

for entry in "${EXAMPLES[@]}"; do
  IFS="|" read -r example targets ctest_filter <<< "$entry"
  filter="${ctest_filter:-$example}"

  # ::group::/::endgroup:: collapses each example's noisy cmake/ctest
  # output into its own foldable section in the GitHub Actions log, so
  # the one-line status printed right after (outside the group) is what
  # actually shows up in the unfolded log stream.
  echo "::group::Building and testing $example"
  status="PASS"
  if ! cmake --build build --target ${targets}; then
    status="BUILD_FAIL"
  # --no-tests=error: ctest's own default is to exit 0 when -R matches
  # zero tests, so a stale/mistyped filter would otherwise silently
  # report PASS without running anything (Copilot review on PR #133).
  elif ! ctest --test-dir build --output-on-failure --no-tests=error -R "$filter"; then
    status="TEST_FAIL"
  fi
  echo "::endgroup::"

  # expected_status: the status EXPECTED_FAILURES documents for this
  # EXACT (compiler, example) pair, if any -- not just the example name,
  # so a GNU run of instances/constituents_dim (no matching entry) or an
  # Intel run that fails in the OTHER phase than documented (status
  # mismatch below) both still count as a real, job-failing result.
  expected_status=""
  for entry2 in "${EXPECTED_FAILURES[@]}"; do
    IFS="|" read -r ef_compiler ef_example ef_status <<< "$entry2"
    if [ "$ef_compiler" = "$COMPILER_LABEL" ] && [ "$ef_example" = "$example" ]; then
      expected_status="$ef_status"
    fi
  done

  if [ "$status" != "PASS" ] && [ "$status" = "$expected_status" ]; then
    echo "[EXPECTED FAIL] $example: $status -- see build_all_examples.sh's own EXPECTED_FAILURES comment"
    status="${status} (expected)"
  elif [ "$status" != "PASS" ]; then
    echo "::error::[FAIL] $example: $status"
    overall_status=1
  else
    echo "[PASS] $example"
    if [ -n "$expected_status" ]; then
      echo "::notice::$example: PASS under $COMPILER_LABEL, but still listed in EXPECTED_FAILURES (expected $expected_status) -- its backlog item may be fixed already, remove the entry"
    fi
  fi
  result_lines+=("${example}|${status}")
done

echo
echo "===== Example build/test results ====="
printf '%-22s %s\n' "Example" "Status"
for r in "${result_lines[@]}"; do
  IFS="|" read -r ex st <<< "$r"
  printf '%-22s %s\n' "$ex" "$st"
done
echo "======================================="

{
  echo "## Example build/test results"
  echo
  echo "| Example | Status |"
  echo "|---|---|"
  for r in "${result_lines[@]}"; do
    IFS="|" read -r ex st <<< "$r"
    echo "| $ex | $st |"
  done
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

exit $overall_status
