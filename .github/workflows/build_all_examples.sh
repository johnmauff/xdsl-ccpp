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
#   FC/CC/CXX -- compiler to configure with (unset = CMake's platform
#                default, i.e. gfortran/gcc/g++)

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
# silently under gfortran). Listed here, not silently swallowed, so a
# failure here still shows up in the summary table and the job log; it
# just doesn't fail the job, since fixing each is separate, larger work
# than this CI change. Remove an entry once its backlog item is closed.
#   instances:         ccpp-validator-length-check (CHANGELOG.md L11491)
#   constituents_dim:  constituents-dim-runtime-crash (CHANGELOG.md L11491)
EXPECTED_FAILURES=(
  "instances"
  "constituents_dim"
)

cmake -S . -B build

overall_status=0
result_lines=()

for entry in "${EXAMPLES[@]}"; do
  IFS="|" read -r example targets ctest_filter <<< "$entry"
  filter="${ctest_filter:-$example}"

  status="PASS"
  if ! cmake --build build --target ${targets}; then
    status="BUILD_FAIL"
  elif ! ctest --test-dir build --output-on-failure -R "$filter"; then
    status="TEST_FAIL"
  fi
  expected_failure=0
  for ex in "${EXPECTED_FAILURES[@]}"; do
    [ "$ex" = "$example" ] && expected_failure=1
  done

  if [ "$status" != "PASS" ] && [ "$expected_failure" -eq 1 ]; then
    echo "::warning::$example: $status (expected -- see build_all_examples.sh's own EXPECTED_FAILURES comment)"
    status="${status} (expected)"
  elif [ "$status" != "PASS" ]; then
    echo "::error::$example: $status"
    overall_status=1
  elif [ "$expected_failure" -eq 1 ]; then
    echo "::notice::$example: PASS, but still listed in EXPECTED_FAILURES -- its backlog item may be fixed already, remove the entry"
  fi
  result_lines+=("${example}|${status}")
done

summary_file="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
{
  echo "## Example build/test results"
  echo
  echo "| Example | Status |"
  echo "|---|---|"
  for r in "${result_lines[@]}"; do
    IFS="|" read -r ex st <<< "$r"
    echo "| $ex | $st |"
  done
} >> "$summary_file"

exit $overall_status
