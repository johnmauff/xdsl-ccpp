#------------------------------------------------------------------------------
#
# kessler_omp: examples/kessler with OpenMP target offload instead of OpenACC
# (omp-derive-memory-space). The scheme sources in scheme/ are OpenMP
# versions of examples/kessler/scheme/{kessler,kessler_update}.F90 -- the
# same numerics, the kernels written as `!$omp target teams distribute
# parallel do` -- and the caps are generated with --directive omp. The host
# (host_ftn/kessler_host_mod.*), the suite and the CCPP driver
# (host_ftn/driver_kessler_ccpp.F90) are examples/kessler's own, so on the
# CPU this example's output must match kessler_ccpp.exe bit-for-bit.
#
# scheme/*.meta declare no memory_space: with --directive omp the
# generator derives it from the schemes' OpenMP (every array a target
# loop maps is device data), giving the same caps as examples/kessler's
# explicit memory_space lines.
#
# The first example whose generated caps carry OpenMP target directives:
# with ARCH=GPU (nvfortran -mp=gpu, via examples/kessler's
# kessler_apply_arch_flags) it is the end-to-end test of --directive omp.
#
#------------------------------------------------------------------------------

set(KESSLER_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../kessler")
set(KESSLER_OMP_SCHEME_META scheme/kessler.meta scheme/kessler_update.meta)

set(KESSLER_OMP_CAP_DIR "${CMAKE_CURRENT_BINARY_DIR}/caps")
xdsl_ccpp_capgen(HOSTFILES ${KESSLER_DIR}/host_ftn/kessler_host_mod.meta
                           ${KESSLER_DIR}/host_ftn/kessler_host_sub.meta
                 SCHEMEFILES ${KESSLER_OMP_SCHEME_META}
                 SUITES ${KESSLER_DIR}/scheme/kessler_suite.xml
                 DIRECTIVE "omp"
                 OUTPUT_ROOT "${KESSLER_OMP_CAP_DIR}")
set(KESSLER_OMP_KINDS     "${KESSLER_OMP_CAP_DIR}/ccpp_kinds.F90")
set(KESSLER_OMP_SUITE_CAP "${KESSLER_OMP_CAP_DIR}/kessler_suite_cap.F90")
set(KESSLER_OMP_CCPP_CAP  "${KESSLER_OMP_CAP_DIR}/Kessler_ccpp_cap.F90")

if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_C)
  # Own module directory: the modules share examples/kessler's names
  # (kessler, kessler_update, kessler_host_mod, the caps).
  add_executable(kessler_omp_ccpp.exe
    ${KESSLER_OMP_KINDS}
    ${KESSLER_DIR}/host_ftn/kessler_host_mod.F90
    scheme/kessler.F90
    scheme/kessler_update.F90
    ${KESSLER_OMP_SUITE_CAP}
    ${KESSLER_OMP_CCPP_CAP}
    ${KESSLER_DIR}/host_ftn/driver_kessler_ccpp.F90
    ${KESSLER_DIR}/shared/kessler_rng.c)
  set_target_properties(kessler_omp_ccpp.exe PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  kessler_apply_arch_flags(kessler_omp_ccpp.exe)
  # kessler_apply_arch_flags sets -mp=gpu as a compile option only; nvhpc
  # also needs it at link time to put the device code into the program.
  # Without it the target regions silently run on the host
  # (OMP_TARGET_OFFLOAD=MANDATORY: "Could not run target region on device
  # 0"; nsys: no CUDA kernels), and the GPU tests pass on host results.
  if(ARCH STREQUAL "GPU" AND CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    target_link_options(kessler_omp_ccpp.exe PRIVATE -mp=gpu)
  endif()

  if(ARCH STREQUAL "GPU")
    # MANDATORY: fail instead of silently running the target regions on
    # the host.
    add_test(NAME ctest_kessler_omp_run COMMAND "$<TARGET_FILE:kessler_omp_ccpp.exe>")
    set_tests_properties(ctest_kessler_omp_run PROPERTIES
      ENVIRONMENT "OMP_TARGET_OFFLOAD=MANDATORY")
  else()
    # Same numerics and driver as examples/kessler: identical output.
    add_test(NAME ctest_kessler_omp_parity
             COMMAND "${Python3_EXECUTABLE}" "${KESSLER_DIR}/check_parity.py"
                     "$<TARGET_FILE:kessler_ccpp.exe>" "$<TARGET_FILE:kessler_omp_ccpp.exe>")
  endif()

  # GPU tree against a CPU tree, as examples/kessler's
  # ctest_kessler_cpu_gpu_parity (KESSLER_CPU_GPU_REFERENCE_BUILD is
  # declared there).
  if(NOT KESSLER_CPU_GPU_REFERENCE_BUILD STREQUAL "")
    add_test(NAME ctest_kessler_omp_cpu_gpu_parity
             COMMAND "${Python3_EXECUTABLE}" "${KESSLER_DIR}/check_cpu_gpu_parity.py"
                     "${KESSLER_CPU_GPU_REFERENCE_BUILD}/examples/kessler_omp"
                     "$<TARGET_FILE_DIR:kessler_omp_ccpp.exe>"
                     "kessler_omp_ccpp.exe")
    set_tests_properties(ctest_kessler_omp_cpu_gpu_parity PROPERTIES
      ENVIRONMENT "OMP_TARGET_OFFLOAD=MANDATORY")
  endif()
endif()
