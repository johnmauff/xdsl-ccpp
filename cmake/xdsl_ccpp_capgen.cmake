# CMake wrapper for xdsl_ccpp's ccpp_xdsl tool (xdsl_ccpp.tools.ccpp_dsl).
#
# Modeled directly on capgen-v1's own cmake/ccpp_capgen.cmake (same
# keyword-argument shape: HOSTFILES/SCHEMEFILES/SUITES/HOST_NAME/
# OUTPUT_ROOT/VERBOSITY) so that a per-example CMakeLists.txt ported from
# capgen-v1's own end-to-end-tests needs only to swap the function name --
# everything else about the file's structure stays the same.
#
# HOST_NAME    - String name of host
# OUTPUT_ROOT  - String path to put generated caps (defaults to the build
#                tree, not the source tree -- unlike the Makefile-based
#                examples, which generate directly into their own source
#                directory; this keeps the CMake and Makefile build paths
#                from writing over each other while both exist side by side)
# VERBOSITY    - passed through as a single "--verbose N" flag (xdsl_ccpp's
#                own CLI takes one integer level, 0/1/2 -- unlike
#                capgen-v1's ccpp_capgen.cmake, which repeats "--verbose"
#                N times for its own CLI's different convention)
# DIRECTIVE    - optional GPU directive style passed straight through as
#                "--directive <value>" (xdsl_ccpp's own CLI accepts "acc" or
#                "omp" -- see ccpp_dsl.py). Has no capgen-v1 ccpp_capgen.cmake
#                analog; needed by GPU-capable examples like
#                examples/advection, which always generate the same
#                directive-annotated source regardless of target
#                architecture -- only the compile flags differ between a
#                plain-CPU and a GPU build (see that example's own
#                CMakeLists.txt for the ARCH-selection side of this).
# BIND_C       - boolean option (no value); passes --bind-c straight through,
#                forcing BIND(C) Fortran cap + C++ header generation even for
#                a Fortran-language host (as opposed to a C++-language host,
#                which auto-enables the equivalent behavior on its own --
#                see ccpp_dsl.py's _host_lang_cpp). Needed by
#                examples/kessler's plain C++ BIND(C) driver, which calls
#                into a still-Fortran-owned host state through a BIND(C)
#                cap rather than a genuine C++-owned chost one.
# HOSTFILES    - CMake list of host metadata filenames (no extension needed
#                by the caller; pass full relative/absolute paths as-is)
# SCHEMEFILES  - CMake list of scheme metadata files
# SUITES       - CMake list of suite xml files
# PY_SUITE     - a Python suite script (xdsl_ccpp.frontend.py_api), used
#                instead of SUITES (passed as "--py <script>"). Its
#                ccpp_scheme_ref() references take their metadata from
#                SCHEMEFILES/HOSTFILES, exactly as an XML suite's do.
# PY_DEPENDS   - CMake list of further Python files the PY_SUITE script
#                imports (e.g. physics-package modules); editing one
#                triggers regeneration, like editing the script itself.
# KIND_MAP     - CMake list of "KIND:ISO" entries (e.g. "kind_dyn:REAL32"),
#                each passed as its own repeated "--kind-map KIND:ISO" flag
#                -- ccpp_dsl.py's own CLI explicitly supports repeating this
#                flag for multiple mappings, unlike DIRECTIVE/HOST_NAME
#                above, which each take a single value. Needed by
#                examples/helloworld, which supplements the built-in
#                kind_phys/kind_dyn table to demonstrate cap-generation's
#                kind-mismatch/kind-cast handling.
#
# cmake-configure-regen (Part B): cap generation itself is deferred to
# BUILD time via add_custom_command(OUTPUT ...) -- only --list-outputs/
# --list-dependencies (cheap metadata-only prediction, no codegen) run at
# configure time, so `cmake -S . -B build` no longer pays for all 20
# examples' full generation on every configure regardless of which
# example a given `cmake --build ... --target X` actually builds.
#
# Sets, in the parent scope:
#   CCPP_CAPS_LIST         - the predicted .F90 cap file paths (same
#                            contract as before: absolute paths, .F90
#                            cap files only -- usable directly as an
#                            add_executable/add_library source list, same
#                            as when this was read back from a real
#                            datatable.xml after an eager generation).
#   CCPP_DEPENDENCIES_LIST - the predicted <dependencies> file paths (a
#                            .meta's own dependencies/dependencies_path
#                            keys, e.g. temp_kinds.F90) -- same contract
#                            as before.
#   CCPP_CAPGEN_TARGET     - the add_custom_target() name driving this
#                            call's generation. Any target that
#                            references a generated cap ONLY via
#                            target_include_directories (never as a
#                            source file -- e.g. a C++ "partial
#                            verification" OBJECT library that just
#                            #includes a generated header) MUST
#                            add_dependencies(<that target>
#                            ${CCPP_CAPGEN_TARGET}) itself, since CMake's
#                            own "OUTPUT used as a source auto-builds it"
#                            mechanism has no equivalent for
#                            include-directory-only consumers. A target
#                            that already lists a generated .F90/.h/.hpp
#                            file as one of its own sources needs no such
#                            addition -- CMake wires that automatically.
# A caller making more than one xdsl_ccpp_capgen() call in the same
# CMakeLists.txt (e.g. a plain + chost pair) must capture each of these
# three PARENT_SCOPE variables into its own call-specific variable
# immediately after each call, before the next call overwrites them --
# the same existing convention examples/capgen and examples/ddthost
# already follow for CCPP_CAPS_LIST/CCPP_DEPENDENCIES_LIST.
function(xdsl_ccpp_capgen)
  set(options BIND_C)
  set(oneValueArgs HOST_NAME OUTPUT_ROOT VERBOSITY DIRECTIVE PY_SUITE)
  set(multiValueArgs HOSTFILES SCHEMEFILES SUITES KIND_MAP PY_DEPENDS)
  cmake_parse_arguments(arg "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

  if(NOT DEFINED XDSL_CCPP_ROOT)
    message(FATAL_ERROR
      "xdsl_ccpp_capgen: XDSL_CCPP_ROOT must be set (the checkout's own "
      "repo root) before calling this function -- see examples/*/CMakeLists.txt.")
  endif()
  if(DEFINED arg_SUITES AND DEFINED arg_PY_SUITE)
    message(FATAL_ERROR "xdsl_ccpp_capgen: pass SUITES or PY_SUITE, not both.")
  endif()

  # Shared flags between the real generation command and the two cheap
  # "predict" commands (--list-outputs/--list-dependencies): host/scheme/
  # suite/host-name/bind-c, i.e. everything that affects WHAT gets
  # generated or its filenames. DIRECTIVE/KIND_MAP affect only generated
  # *content*, never filenames or the dependency list, so they're added
  # only to the real command below, not to CCPP_XDSL_CMD_PREDICT.
  set(CCPP_XDSL_CMD_PREDICT "${Python3_EXECUTABLE}" -m xdsl_ccpp.tools.ccpp_dsl)

  if(DEFINED arg_HOSTFILES)
    list(JOIN arg_HOSTFILES "," HOSTFILES_SEPARATED)
    list(APPEND CCPP_XDSL_CMD_PREDICT "--host-files" "${HOSTFILES_SEPARATED}")
  endif()
  if(DEFINED arg_SCHEMEFILES)
    list(JOIN arg_SCHEMEFILES "," SCHEMEFILES_SEPARATED)
    list(APPEND CCPP_XDSL_CMD_PREDICT "--scheme-files" "${SCHEMEFILES_SEPARATED}")
  endif()
  if(DEFINED arg_SUITES)
    list(JOIN arg_SUITES "," SUITES_SEPARATED)
    list(APPEND CCPP_XDSL_CMD_PREDICT "--suites" "${SUITES_SEPARATED}")
  endif()
  if(DEFINED arg_PY_SUITE)
    list(APPEND CCPP_XDSL_CMD_PREDICT "--py" "${arg_PY_SUITE}")
  endif()
  if(DEFINED arg_HOST_NAME)
    list(APPEND CCPP_XDSL_CMD_PREDICT "--host-name" "${arg_HOST_NAME}")
  endif()
  if(arg_BIND_C)
    list(APPEND CCPP_XDSL_CMD_PREDICT "--bind-c")
  endif()

  # The real generation command: CCPP_XDSL_CMD_PREDICT plus everything
  # that affects content (DIRECTIVE/KIND_MAP) plus the output-directory/
  # datatable flags --list-outputs/--list-dependencies don't need at all.
  set(CCPP_XDSL_CMD ${CCPP_XDSL_CMD_PREDICT})

  # NOT arg_DIRECTIVE STREQUAL "", not just DEFINED: an empty string (e.g.
  # from a caller-set cache variable like -DDIRECTIVE=) still counts as
  # "defined" in CMake, which would append a bare "--directive" with an
  # empty value -- ccpp_dsl.py restricts --directive to acc|omp and rejects
  # that outright, turning a no-op-intended empty value into a hard
  # cap-generation failure instead of "no directive requested".
  if(DEFINED arg_DIRECTIVE AND NOT arg_DIRECTIVE STREQUAL "")
    list(APPEND CCPP_XDSL_CMD "--directive" "${arg_DIRECTIVE}")
  endif()
  if(DEFINED arg_KIND_MAP)
    foreach(_kind_map_entry IN LISTS arg_KIND_MAP)
      list(APPEND CCPP_XDSL_CMD "--kind-map" "${_kind_map_entry}")
    endforeach()
  endif()

  set(OUTPUT_ROOT_DIR "${CMAKE_CURRENT_BINARY_DIR}/ccpp")
  if(DEFINED arg_OUTPUT_ROOT)
    set(OUTPUT_ROOT_DIR "${arg_OUTPUT_ROOT}")
  endif()
  file(MAKE_DIRECTORY "${OUTPUT_ROOT_DIR}")
  list(APPEND CCPP_XDSL_CMD "-o" "${OUTPUT_ROOT_DIR}")
  list(APPEND CCPP_XDSL_CMD "--tempdir" "${OUTPUT_ROOT_DIR}/tmp")

  if(DEFINED arg_VERBOSITY)
    list(APPEND CCPP_XDSL_CMD "--verbose" "${arg_VERBOSITY}")
  endif()

  set(DATATABLE_PATH "${OUTPUT_ROOT_DIR}/datatable.xml")
  list(APPEND CCPP_XDSL_CMD "--emit-datatable" "${DATATABLE_PATH}")

  # PYTHONPATH, not relying on a bare `ccpp_xdsl` console script or however
  # Python3_EXECUTABLE's own site-packages resolve xdsl_ccpp: an unrelated
  # xdsl-ccpp editable install elsewhere on the machine can otherwise
  # silently shadow this checkout's own code -- the identical precaution
  # every example's existing Makefile already takes.
  if(DEFINED ENV{PYTHONPATH} AND NOT "$ENV{PYTHONPATH}" STREQUAL "")
    set(_capgen_env "PYTHONPATH=${XDSL_CCPP_ROOT}:$ENV{PYTHONPATH}")
  else()
    set(_capgen_env "PYTHONPATH=${XDSL_CCPP_ROOT}")
  endif()

  message(STATUS "Predicting xdsl_ccpp outputs for ${CMAKE_CURRENT_SOURCE_DIR} (${OUTPUT_ROOT_DIR})")

  # --- Cheap, configure-time prediction (no codegen) ------------------
  execute_process(
    COMMAND ${CMAKE_COMMAND} -E env "${_capgen_env}" ${CCPP_XDSL_CMD_PREDICT} --list-outputs
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    OUTPUT_VARIABLE CCPP_LIST_OUTPUTS_STDOUT
    ERROR_VARIABLE CCPP_LIST_OUTPUTS_STDERR
    RESULT_VARIABLE RES_LIST_OUTPUTS
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  if(NOT RES_LIST_OUTPUTS EQUAL 0)
    message(FATAL_ERROR
      "xdsl_ccpp_capgen: --list-outputs failed (result = ${RES_LIST_OUTPUTS}):\n"
      "${CCPP_LIST_OUTPUTS_STDERR}")
  endif()

  string(REPLACE "," ";" CCPP_ALL_OUTPUTS_BARE "${CCPP_LIST_OUTPUTS_STDOUT}")
  set(CCPP_CAPS_LIST "${CCPP_ALL_OUTPUTS_BARE}")
  list(FILTER CCPP_CAPS_LIST INCLUDE REGEX "\\.F90$")
  list(TRANSFORM CCPP_CAPS_LIST PREPEND "${OUTPUT_ROOT_DIR}/")
  set(CCPP_CAPS_LIST "${CCPP_CAPS_LIST}" PARENT_SCOPE)

  set(CCPP_ALL_OUTPUTS "${CCPP_ALL_OUTPUTS_BARE}")
  list(TRANSFORM CCPP_ALL_OUTPUTS PREPEND "${OUTPUT_ROOT_DIR}/")

  # cmake-dep-manifest: the datatable's own <dependencies> section --
  # extra compiled files (e.g. temp_kinds.F90/ddt2.F90) that a table's own
  # `dependencies =`/`dependencies_path =` .meta properties declare and
  # that have no .meta of their own, so they're invisible to SCHEMEFILES/
  # HOSTFILES. Most examples declare none, in which case this is an empty
  # list (not an error).
  execute_process(
    COMMAND ${CMAKE_COMMAND} -E env "${_capgen_env}" ${CCPP_XDSL_CMD_PREDICT} --list-dependencies
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    OUTPUT_VARIABLE CCPP_DEPENDENCIES
    ERROR_VARIABLE CCPP_LIST_DEPENDENCIES_STDERR
    RESULT_VARIABLE RES_LIST_DEPENDENCIES
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  if(NOT RES_LIST_DEPENDENCIES EQUAL 0)
    message(FATAL_ERROR
      "xdsl_ccpp_capgen: --list-dependencies failed (result = ${RES_LIST_DEPENDENCIES}):\n"
      "${CCPP_LIST_DEPENDENCIES_STDERR}")
  endif()

  string(REPLACE "," ";" CCPP_DEPENDENCIES_LIST "${CCPP_DEPENDENCIES}")
  set(CCPP_DEPENDENCIES_LIST "${CCPP_DEPENDENCIES_LIST}" PARENT_SCOPE)

  # --- Deferred, build-time generation ---------------------------------
  #
  # An args fingerprint file: file(CONFIGURE) only updates its own mtime
  # when its CONTENT actually changes, unlike reconfiguring (which
  # changes nothing CCPP_XDSL_CMD's own mtime-based DEPENDS tracking
  # would notice). Covers a CLI-flag-only example edit (e.g. flipping
  # DIRECTIVE "acc" -> "omp") that touches no real input file -- without
  # this, such an edit would stop being picked up by `cmake --build`
  # alone under the Makefiles generator (no command-line hashing the way
  # Ninja has), a regression versus today's execute_process, which always
  # reran on every single configure.
  set(_capgen_args_fingerprint "${OUTPUT_ROOT_DIR}/.capgen_args")
  file(CONFIGURE OUTPUT "${_capgen_args_fingerprint}" CONTENT "${CCPP_XDSL_CMD}")

  # A sentinel/stamp file, in addition to every real generated file, as
  # one more OUTPUT: split_fortran_output() (ccpp_dsl.py) writes each
  # generated file in a loop, so a mid-generation crash can leave some
  # declared outputs written and others missing. The sentinel is only
  # touched by a second, sequential COMMAND (add_custom_command runs
  # multiple COMMANDs in order) that only runs once the first COMMAND
  # has already exited 0 -- a cheap, portable "did this fully succeed"
  # marker that doesn't depend on which Make multi-output-rule strategy
  # the detected Make version happens to use.
  set(_capgen_sentinel "${OUTPUT_ROOT_DIR}/.capgen-complete")

  # Real inputs this call's generation depends on, beyond the
  # caller-supplied HOSTFILES/SCHEMEFILES/SUITES: every generation call
  # auto-includes the bundled ccpp_constituent_prop_mod.meta
  # (ccpp_dsl.py's run_frontend()), but no example's own HOSTFILES lists
  # it -- without this, editing that bundled file wouldn't trigger
  # regeneration.
  set(_capgen_bundled_const_meta
    "${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_constituent_prop_mod.meta")

  add_custom_command(
    OUTPUT ${CCPP_ALL_OUTPUTS} "${_capgen_sentinel}"
    COMMAND ${CMAKE_COMMAND} -E env "${_capgen_env}" ${CCPP_XDSL_CMD}
    COMMAND ${CMAKE_COMMAND} -E touch "${_capgen_sentinel}"
    DEPENDS
      ${arg_HOSTFILES} ${arg_SCHEMEFILES} ${arg_SUITES}
      ${arg_PY_SUITE} ${arg_PY_DEPENDS}
      "${_capgen_bundled_const_meta}"
      "${_capgen_args_fingerprint}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Generating CCPP caps for ${CMAKE_CURRENT_SOURCE_DIR} (${OUTPUT_ROOT_DIR})"
    VERBATIM
  )

  # A target referencing a generated cap only via
  # target_include_directories (never as a source) has no dependency
  # edge on the custom command above and must add_dependencies() on this
  # target explicitly -- see this function's own header comment.
  string(MD5 _capgen_target_hash "${OUTPUT_ROOT_DIR}")
  set(_capgen_target_name "xdsl_ccpp_capgen_${_capgen_target_hash}")
  add_custom_target("${_capgen_target_name}" DEPENDS ${CCPP_ALL_OUTPUTS} "${_capgen_sentinel}")
  set(CCPP_CAPGEN_TARGET "${_capgen_target_name}" PARENT_SCOPE)
endfunction()
