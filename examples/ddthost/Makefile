# DDT host CCPP example Makefile
#
# Directory layout:
#   scheme/    — scheme Fortran source, meta files, suite XMLs, Python wrappers
#   host_ftn/  — Fortran host driver (source + meta files)
#   host_cpp/  — C++ host driver (source + meta files)
#   bindc/     — generated caps for both drivers (regenerate with make caps)
#
# Build targets:
#   make [all]               — build the Fortran host test executable
#   make ftn_host            — same as all
#   make cxx_host            — build the C++ host-model driver (chost cap)
#
# Run / check:
#   make run                 — build and run the Fortran host test
#   make check               — build, run, and verify PASS/FAIL (Fortran host)
#   make run-cxx-host        — build and run the C++ host-model driver
#   make check-cxx-host      — build, run, and verify PASS (C++ host)
#
# Code generation (requires xdsl-ccpp):
#   make caps                — regenerate Fortran host caps into bindc/
#   make gen-chost-caps      — regenerate C++ chost caps + headers into bindc/
#
# Debug:
#   make compile-suite-caps  — compile only the suite caps (no host driver)
#
# Utility:
#   make clean               — remove build artefacts (bindc/ is kept; rm -rf bindc/ to wipe)

# ── Compilers & flags ─────────────────────────────────────────────────────────
FC     ?= gfortran
FFLAGS  = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none

# Derive CXX and per-family flags from FC.
ifeq ($(FC),nvfortran)
  CXX      ?= nvc++
  CXXFLAGS  = -g -O2
  MOD_OUT   = -module
  NOMAIN    = -Mnomain
else ifeq ($(FC),ifx)
  CXX      ?= icpx
  CXXFLAGS  = -g -O2
  MOD_OUT   = -module
  NOMAIN    = -nofor-main
else
  CXX      ?= g++
  CXXFLAGS  = -g -Wall -O2
  MOD_OUT   = -J
  NOMAIN    =
endif

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Directories ───────────────────────────────────────────────────────────────
DIR          = examples/ddthost
SCHEME_DIR   = $(DIR)/scheme
HOST_FTN_DIR = $(DIR)/host_ftn
HOST_CPP_DIR = $(DIR)/host_cpp
BINDC_DIR    = $(DIR)/bindc
BUILD_DIR    = $(DIR)/build
FTN_BUILD    = $(BUILD_DIR)/ftn_host

# ── Generated caps (Fortran host) ─────────────────────────────────────────────
GEN_KINDS      = $(BINDC_DIR)/ccpp_kinds.F90
GEN_SUITE_CAPS = $(BINDC_DIR)/ddt_suite_cap.F90 $(BINDC_DIR)/temp_suite_cap.F90
GEN_CCPP_CAP   = $(BINDC_DIR)/test_host_ccpp_cap.F90

CAPS_SUITES  = $(SCHEME_DIR)/ddt_suite.xml,$(SCHEME_DIR)/temp_suite.xml
CAPS_SCHEMES = $(SCHEME_DIR)/make_ddt.meta,$(SCHEME_DIR)/environ_conditions.meta,$(SCHEME_DIR)/setup_coeffs.meta,$(SCHEME_DIR)/temp_set.meta,$(SCHEME_DIR)/temp_calc_adjust.meta,$(SCHEME_DIR)/temp_adjust.meta
CAPS_HOSTS   = $(SCHEME_DIR)/host_ccpp_ddt.meta,$(HOST_FTN_DIR)/test_host_data.meta,$(HOST_FTN_DIR)/test_host_mod.meta,$(HOST_FTN_DIR)/test_host.meta

CAPS_PREREQS = \
    $(SCHEME_DIR)/ddt_suite.xml \
    $(SCHEME_DIR)/temp_suite.xml \
    $(SCHEME_DIR)/make_ddt.meta \
    $(SCHEME_DIR)/environ_conditions.meta \
    $(SCHEME_DIR)/setup_coeffs.meta \
    $(SCHEME_DIR)/temp_set.meta \
    $(SCHEME_DIR)/temp_calc_adjust.meta \
    $(SCHEME_DIR)/temp_adjust.meta \
    $(SCHEME_DIR)/host_ccpp_ddt.meta \
    $(HOST_FTN_DIR)/test_host_data.meta \
    $(HOST_FTN_DIR)/test_host_mod.meta \
    $(HOST_FTN_DIR)/test_host.meta

# ── Fortran host source list (compilation order) ──────────────────────────────
FTN_SRCS = \
    $(GEN_KINDS) \
    $(HOST_FTN_DIR)/test_utils.F90 \
    $(SCHEME_DIR)/host_ccpp_ddt.F90 \
    $(HOST_FTN_DIR)/test_host_data.F90 \
    $(HOST_FTN_DIR)/test_host_mod.F90 \
    $(SCHEME_DIR)/make_ddt.F90 \
    $(SCHEME_DIR)/environ_conditions.F90 \
    $(SCHEME_DIR)/setup_coeffs.F90 \
    $(SCHEME_DIR)/temp_set.F90 \
    $(SCHEME_DIR)/temp_calc_adjust.F90 \
    $(SCHEME_DIR)/temp_adjust.F90 \
    $(GEN_SUITE_CAPS) \
    $(GEN_CCPP_CAP) \
    $(HOST_FTN_DIR)/test_host.F90 \
    $(HOST_FTN_DIR)/test_ddt_host_integration.F90

FTN_OBJS = $(addprefix $(FTN_BUILD)/,$(notdir $(FTN_SRCS:.F90=.o)))

EXE_FTN = $(BUILD_DIR)/test_ddthost

# ── C++ host variables ────────────────────────────────────────────────────────
CXX_BUILD     = $(BUILD_DIR)/cxx_host

# Generated chost caps (ddthost_suite only, make_ddt scheme, C++ host meta)
CAPS_CHOST_SUITES  = $(SCHEME_DIR)/ddthost_suite.xml
CAPS_CHOST_SCHEMES = $(SCHEME_DIR)/make_ddt.meta
CAPS_CHOST_HOSTS   = $(HOST_CPP_DIR)/ddthost_host_mod.meta,$(HOST_CPP_DIR)/ddthost_host_sub.meta,$(SCHEME_DIR)/host_ccpp_ddt.meta

CAPS_CHOST_PREREQS = \
    $(SCHEME_DIR)/ddthost_suite.xml \
    $(SCHEME_DIR)/make_ddt.meta \
    $(SCHEME_DIR)/host_ccpp_ddt.meta \
    $(HOST_CPP_DIR)/ddthost_host_mod.meta \
    $(HOST_CPP_DIR)/ddthost_host_sub.meta

CHOST_KINDS     = $(BINDC_DIR)/ccpp_kinds.F90
CHOST_SUITE_CAP = $(BINDC_DIR)/ddthost_suite_cap.F90
CHOST_F90       = $(BINDC_DIR)/Ddthost_ccpp_chost_cap.F90
CHOST_HDR       = $(BINDC_DIR)/Ddthost_ccpp_chost_cap.h
CHOST_HPP       = $(BINDC_DIR)/Ddthost_chost.hpp

CXX_HOST_OBJS = \
    $(CXX_BUILD)/ccpp_kinds.o \
    $(CXX_BUILD)/host_ccpp_ddt.o \
    $(CXX_BUILD)/make_ddt.o \
    $(CXX_BUILD)/ddthost_suite_cap.o \
    $(CXX_BUILD)/Ddthost_ccpp_chost_cap.o \
    $(CXX_BUILD)/driver_ddthost_chost.o

EXE_CXX = $(BUILD_DIR)/ddthost_cxx_host

# ── Phony targets ─────────────────────────────────────────────────────────────
.PHONY: all ftn_host cxx_host run check run-cxx-host check-cxx-host \
        caps gen-chost-caps compile-suite-caps clean

all: ftn_host

ftn_host: $(EXE_FTN)

cxx_host: $(EXE_CXX)

run: $(EXE_FTN)
	$(EXE_FTN)

check: $(EXE_FTN)
	@echo "Running ddthost CCPP test..."
	@$(EXE_FTN); STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "TEST PASSED"; \
	  else echo "TEST FAILED (exit $$STATUS)"; exit 1; fi

run-cxx-host: $(EXE_CXX)
	@echo "=== C++ host-model driver ===" && $(EXE_CXX)

check-cxx-host: $(EXE_CXX)
	@echo "=== Correctness check (C++ chost) ==="
	@$(EXE_CXX); STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "PASS"; \
	  else echo "FAIL (exit $$STATUS)"; exit 1; fi

# ── Cap generation ────────────────────────────────────────────────────────────
caps: $(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS) | $(BINDC_DIR)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_SUITES) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --host-name    test_host \
	    -o             $(BINDC_DIR)/

# ── Chost cap generation (C++ host, ddthost_suite, make_ddt only) ─────────────
gen-chost-caps: $(CHOST_F90) $(CHOST_HDR) $(CHOST_HPP)

$(CHOST_KINDS) $(CHOST_SUITE_CAP) $(CHOST_F90) $(CHOST_HDR) $(CHOST_HPP): $(CAPS_CHOST_PREREQS) | $(BINDC_DIR)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_CHOST_SUITES) \
	    --scheme-files $(CAPS_CHOST_SCHEMES) \
	    --host-files   $(CAPS_CHOST_HOSTS) \
	    -o             $(BINDC_DIR)

# ── Debug: compile only the suite caps (no host driver) ───────────────────────
# Mirrors the old Makefile.suite_only — useful to isolate suite-cap correctness.
SUITE_ONLY_SRCS = \
    $(GEN_KINDS) \
    $(SCHEME_DIR)/host_ccpp_ddt.F90 \
    $(HOST_FTN_DIR)/test_host_data.F90 \
    $(HOST_FTN_DIR)/test_host_mod.F90 \
    $(SCHEME_DIR)/make_ddt.F90 \
    $(SCHEME_DIR)/environ_conditions.F90 \
    $(SCHEME_DIR)/setup_coeffs.F90 \
    $(SCHEME_DIR)/temp_set.F90 \
    $(SCHEME_DIR)/temp_calc_adjust.F90 \
    $(SCHEME_DIR)/temp_adjust.F90 \
    $(GEN_SUITE_CAPS)

SUITE_ONLY_BUILD = $(BUILD_DIR)/suite_only
SUITE_ONLY_OBJS  = $(addprefix $(SUITE_ONLY_BUILD)/,$(notdir $(SUITE_ONLY_SRCS:.F90=.o)))

compile-suite-caps: $(SUITE_ONLY_OBJS)
	@echo "Suite caps compiled successfully."

$(SUITE_ONLY_BUILD):
	mkdir -p $@

$(SUITE_ONLY_BUILD)/%.o: $(SUITE_ONLY_SRCS) | $(SUITE_ONLY_BUILD)
	$(FC) $(FFLAGS) -c $(filter %/$(notdir $(@:.o=.F90)),$^) -o $@ \
	    -J $(SUITE_ONLY_BUILD) -I $(SUITE_ONLY_BUILD)

# ── Build directories ─────────────────────────────────────────────────────────
$(BUILD_DIR) $(FTN_BUILD) $(CXX_BUILD) $(BINDC_DIR):
	mkdir -p $@

# ── Fortran host build ────────────────────────────────────────────────────────
$(FTN_BUILD)/%.o: | $(FTN_BUILD)
	$(FC) $(FFLAGS) -c $(filter %/$(notdir $(@:.o=.F90)),$(FTN_SRCS)) -o $@ \
	    -J $(FTN_BUILD) -I $(FTN_BUILD)

$(EXE_FTN): $(FTN_OBJS) | $(BUILD_DIR)
	$(FC) $(FFLAGS) -o $@ $^

# ── C++ host build ────────────────────────────────────────────────────────────
$(CXX_BUILD)/ccpp_kinds.o: $(CHOST_KINDS) | $(CXX_BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_BUILD)

$(CXX_BUILD)/host_ccpp_ddt.o: $(SCHEME_DIR)/host_ccpp_ddt.F90 \
    $(CXX_BUILD)/ccpp_kinds.o | $(CXX_BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_BUILD) -I $(CXX_BUILD)

$(CXX_BUILD)/make_ddt.o: $(SCHEME_DIR)/make_ddt.F90 \
    $(CXX_BUILD)/host_ccpp_ddt.o | $(CXX_BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_BUILD) -I $(CXX_BUILD)

$(CXX_BUILD)/ddthost_suite_cap.o: $(CHOST_SUITE_CAP) \
    $(CXX_BUILD)/make_ddt.o | $(CXX_BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_BUILD) -I $(CXX_BUILD)

$(CXX_BUILD)/Ddthost_ccpp_chost_cap.o: $(CHOST_F90) \
    $(CXX_BUILD)/ddthost_suite_cap.o | $(CXX_BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_BUILD) -I $(CXX_BUILD)

$(CXX_BUILD)/driver_ddthost_chost.o: $(HOST_CPP_DIR)/driver_ddthost_chost.cpp \
    $(CHOST_HDR) $(CHOST_HPP) | $(CXX_BUILD)
	$(CXX) $(CXXFLAGS) -I$(BINDC_DIR) -c $< -o $@

$(EXE_CXX): $(CXX_HOST_OBJS) | $(BUILD_DIR)
	$(FC) $(FFLAGS) $(NOMAIN) -o $@ $^ -lstdc++

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(BUILD_DIR)
