# DDT host CCPP example Makefile
#
# Directory layout:
#   scheme/    — scheme Fortran source, meta files, suite XMLs
#   host_ftn/  — Fortran host driver (source + meta files)
#   host_cpp/  — C++ host driver (source + meta files)
#   bindc/     — generated caps for both drivers (regenerate with make gen-*)
#
# Build targets:
#   make [all]     — build both drivers
#   make ftn_host  — Fortran driver (full ddt_suite + temp_suite)
#   make cxx_host  — C++ host-model driver (chost cap, make_ddt only)
#
# Run targets:
#   make run            — build and run both drivers
#   make run-ftn        — build and run the Fortran driver
#   make run-cxx-host   — build and run the C++ host-model driver
#
# Check:
#   make check     — build and run both drivers, verify both pass
#
# Code generation (requires xdsl-ccpp):
#   make caps      — regenerate Fortran host caps into bindc/
#   make gen-chost — regenerate C++ chost caps + headers into bindc/
#
# Utility:
#   make clean     — remove build artefacts and generated caps

# ── Compilers & flags ─────────────────────────────────────────────────────────
ifeq ($(origin FC),default)
FC   := gfortran
endif
ARCH ?= CPU

# Derive the C++ compiler and per-family flags from FC.
# FMA is defined once here and appended to both FFLAGS and CXXFLAGS.
ifeq ($(FC),nvfortran)
  CXX     ?= nvc++
  FMA      = -Mnofma
  FC_CPU   = -g -O2 -Mfree -Mpreprocess
  FC_GPU   = -g -O2 -Mfree -mp=gpu -Minfo=accel -Mpreprocess -DUSE_GPU
  CXX_BASE = -g -O2
  MOD_OUT  = -module
  NOMAIN   = -Mnomain
else ifeq ($(FC),ifx)
  CXX     ?= icpx
  FMA      = -fp-model=precise
  FC_CPU   = -g -O2 -fpp
  FC_GPU   = -g -O2 -fpp -fiopenmp -fopenmp-targets=spir64 -DUSE_GPU
  CXX_BASE = -g -O2
  MOD_OUT  = -module
  NOMAIN   = -nofor-main
else
  # GNU (gfortran / g++)
  CXX     ?= g++
  FMA      = -ffp-contract=off
  FC_CPU   = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none -O2 -cpp
  FC_GPU   = -g -O2 -ffree-line-length-none -fiopenmp -fopenmp-targets=spir64 -cpp -DUSE_GPU
  CXX_BASE = -g -Wall -O2
  MOD_OUT  = -J
  NOMAIN   =
endif

ifeq ($(ARCH),GPU)
  FFLAGS = $(FC_GPU) $(FMA)
else
  FFLAGS = $(FC_CPU) $(FMA)
endif
CXXFLAGS = $(CXX_BASE) $(FMA)

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Directories ───────────────────────────────────────────────────────────────
DIR          = examples/ddthost
SCHEME_DIR   = $(DIR)/scheme
HOST_FTN_DIR = $(DIR)/host_ftn
HOST_CPP_DIR = $(DIR)/host_cpp
BINDC_DIR    = $(DIR)/bindc
BUILD        = $(DIR)/build
FTN_OBJ      = $(BUILD)/ftn_host
CXX_HOST_OBJ = $(BUILD)/cxx_host

# ── Generated caps — Fortran host (make caps) ─────────────────────────────────
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

# ── Generated caps — chost C++ host (make gen-chost) ─────────────────────────
CAPS_CHOST_SUITES  = $(SCHEME_DIR)/ddthost_suite.xml
CAPS_CHOST_SCHEMES = $(SCHEME_DIR)/make_ddt.meta
CAPS_CHOST_HOSTS   = $(HOST_CPP_DIR)/ddthost_host_mod.meta,$(HOST_CPP_DIR)/ddthost_host_sub.meta,$(SCHEME_DIR)/host_ccpp_ddt.meta

CAPS_CHOST_PREREQS = \
    $(SCHEME_DIR)/ddthost_suite.xml \
    $(SCHEME_DIR)/make_ddt.meta \
    $(SCHEME_DIR)/host_ccpp_ddt.meta \
    $(HOST_CPP_DIR)/ddthost_host_mod.meta \
    $(HOST_CPP_DIR)/ddthost_host_sub.meta

CHOST_SUITE_CAP = $(BINDC_DIR)/ddthost_suite_cap.F90
CHOST_F90       = $(BINDC_DIR)/Ddthost_ccpp_chost_cap.F90
CHOST_HDR       = $(BINDC_DIR)/Ddthost_ccpp_chost_cap.h
CHOST_HPP       = $(BINDC_DIR)/Ddthost_chost.hpp

# ── Source lists ──────────────────────────────────────────────────────────────
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

FTN_OBJS = $(addprefix $(FTN_OBJ)/,$(notdir $(FTN_SRCS:.F90=.o)))

# ── Executables ───────────────────────────────────────────────────────────────
EXE_FTN = $(BUILD)/test_ddthost
EXE_CXX = $(BUILD)/ddthost_cxx_host

CXX_HOST_OBJS = \
    $(CXX_HOST_OBJ)/ccpp_kinds.o \
    $(CXX_HOST_OBJ)/host_ccpp_ddt.o \
    $(CXX_HOST_OBJ)/make_ddt.o \
    $(CXX_HOST_OBJ)/ddthost_suite_cap.o \
    $(CXX_HOST_OBJ)/Ddthost_ccpp_chost_cap.o \
    $(CXX_HOST_OBJ)/driver_ddthost_chost.o

# ── Phony targets ─────────────────────────────────────────────────────────────
.PHONY: all ftn_host cxx_host run run-ftn run-cxx-host check caps gen-chost clean

all: ftn_host cxx_host

ftn_host: $(EXE_FTN)
cxx_host: $(EXE_CXX)

run-ftn: $(EXE_FTN)
	@echo "=== Fortran host driver ===" && $(EXE_FTN)

run-cxx-host: $(EXE_CXX)
	@echo "=== C++ host-model driver ===" && $(EXE_CXX)

run: run-ftn run-cxx-host

check: ftn_host cxx_host
	@echo "=== ddthost CCPP check ==="
	@$(EXE_FTN) > /dev/null; STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "PASS: ftn_host"; \
	  else echo "FAIL: ftn_host (exit $$STATUS)"; exit 1; fi
	@$(EXE_CXX) > /dev/null; STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "PASS: cxx_host"; \
	  else echo "FAIL: cxx_host (exit $$STATUS)"; exit 1; fi

# ── Build directories ─────────────────────────────────────────────────────────
$(BUILD) $(FTN_OBJ) $(CXX_HOST_OBJ):
	mkdir -p $@

# ── Fortran compilation — ftn_host ────────────────────────────────────────────
$(FTN_OBJ)/%.o: $(BINDC_DIR)/%.F90 | $(FTN_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(FTN_OBJ) -I $(FTN_OBJ)

$(FTN_OBJ)/%.o: $(SCHEME_DIR)/%.F90 | $(FTN_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(FTN_OBJ) -I $(FTN_OBJ)

$(FTN_OBJ)/%.o: $(HOST_FTN_DIR)/%.F90 | $(FTN_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(FTN_OBJ) -I $(FTN_OBJ)

# ── Fortran module ordering (parallel-make safety) ────────────────────────────
# Order-only prerequisites ensure .mod files are fully written before any
# dependent source reads them (prevents "Unexpected EOF" with make -j).
$(FTN_OBJ)/test_utils.o:         | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/host_ccpp_ddt.o:      | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/test_host_data.o:     | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/test_host_mod.o:      | $(FTN_OBJ)/ccpp_kinds.o \
                                    $(FTN_OBJ)/host_ccpp_ddt.o \
                                    $(FTN_OBJ)/test_host_data.o
$(FTN_OBJ)/make_ddt.o:           | $(FTN_OBJ)/ccpp_kinds.o \
                                    $(FTN_OBJ)/host_ccpp_ddt.o
$(FTN_OBJ)/environ_conditions.o: | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/setup_coeffs.o:       | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/temp_set.o:           | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/temp_calc_adjust.o:   | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/temp_adjust.o:        | $(FTN_OBJ)/ccpp_kinds.o
$(FTN_OBJ)/ddt_suite_cap.o:      | $(FTN_OBJ)/make_ddt.o \
                                    $(FTN_OBJ)/host_ccpp_ddt.o
$(FTN_OBJ)/temp_suite_cap.o:     | $(FTN_OBJ)/environ_conditions.o \
                                    $(FTN_OBJ)/setup_coeffs.o \
                                    $(FTN_OBJ)/temp_set.o \
                                    $(FTN_OBJ)/temp_calc_adjust.o \
                                    $(FTN_OBJ)/temp_adjust.o
$(FTN_OBJ)/test_host_ccpp_cap.o: | $(FTN_OBJ)/ddt_suite_cap.o \
                                    $(FTN_OBJ)/temp_suite_cap.o \
                                    $(FTN_OBJ)/test_host_mod.o
$(FTN_OBJ)/test_host.o:          | $(FTN_OBJ)/test_host_ccpp_cap.o
$(FTN_OBJ)/test_ddt_host_integration.o: | $(FTN_OBJ)/test_host.o

$(EXE_FTN): $(FTN_OBJS) | $(BUILD)
	$(FC) $(FFLAGS) -o $@ $^

# ── C++ host-model build ──────────────────────────────────────────────────────
$(CXX_HOST_OBJ)/ccpp_kinds.o: $(GEN_KINDS) | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/host_ccpp_ddt.o: $(SCHEME_DIR)/host_ccpp_ddt.F90 \
    $(CXX_HOST_OBJ)/ccpp_kinds.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/make_ddt.o: $(SCHEME_DIR)/make_ddt.F90 \
    $(CXX_HOST_OBJ)/host_ccpp_ddt.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/ddthost_suite_cap.o: $(CHOST_SUITE_CAP) \
    $(CXX_HOST_OBJ)/make_ddt.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/Ddthost_ccpp_chost_cap.o: $(CHOST_F90) \
    $(CXX_HOST_OBJ)/ddthost_suite_cap.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/driver_ddthost_chost.o: $(HOST_CPP_DIR)/driver_ddthost_chost.cpp \
    $(CHOST_HDR) $(CHOST_HPP) | $(CXX_HOST_OBJ)
	$(CXX) $(CXXFLAGS) -I$(BINDC_DIR) -c $< -o $@

$(EXE_CXX): $(CXX_HOST_OBJS) | $(BUILD)
	$(FC) $(FFLAGS) $(NOMAIN) -o $@ $^ -lstdc++

# ── Cap generation ────────────────────────────────────────────────────────────
caps: $(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS)
	mkdir -p $(BINDC_DIR)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_SUITES) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --host-name    test_host \
	    -o             $(BINDC_DIR)

gen-chost: $(CHOST_F90) $(CHOST_HDR) $(CHOST_HPP)

$(CHOST_SUITE_CAP) $(CHOST_F90) $(CHOST_HDR) $(CHOST_HPP): $(CAPS_CHOST_PREREQS)
	mkdir -p $(BINDC_DIR)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_CHOST_SUITES) \
	    --scheme-files $(CAPS_CHOST_SCHEMES) \
	    --host-files   $(CAPS_CHOST_HOSTS) \
	    -o             $(BINDC_DIR)

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(BUILD)
	rm -rf $(BINDC_DIR)
