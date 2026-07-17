# constprop example Makefile — chost cap with constituent DDT array support (gap 4c)
#
# Directory layout:
#   host_cpp/  — C++ host model driver (chost cap; C++ owns all arrays)
#   bindc/     — Generated chost BIND(C) caps and C++ headers (regenerate with make gen-chost)
#
# Build targets:
#   make [all]      — build the C++ host-model driver
#   make cxx_host   — C++ host-model driver (chost cap, C++ owns all arrays)
#
# Run targets:
#   make run          — build and run the C++ host-model driver
#   make run-cxx-host — build and run the C++ host-model driver
#
# Verification:
#   make check     — run the driver and verify PASS
#
# Code generation (requires xdsl-ccpp):
#   make caps      — regenerate chost BIND(C) caps + C++ headers into bindc/
#   make gen-chost — alias for caps

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
DIR          = examples/constprop
HOST_CPP     = $(DIR)/host_cpp
BUILD        = $(DIR)/build
CXX_HOST_OBJ = $(BUILD)/cxx_host

# ── Generated caps — chost (make gen-chost) ───────────────────────────────────
BINDC_SRC = $(DIR)/bindc

CHOST_F90 = $(BINDC_SRC)/constprop_host_sub_ccpp_chost_cap.F90
CHOST_HDR = $(BINDC_SRC)/constprop_host_sub_ccpp_chost_cap.h
CHOST_HPP = $(BINDC_SRC)/constprop_host_sub_chost.hpp

CAPS_SUITE     = $(DIR)/constprop_suite.xml
CAPS_SCHEMES   = $(DIR)/constprop.meta
CAPS_HOSTS_CPP = $(HOST_CPP)/constprop_host_mod.meta,$(HOST_CPP)/constprop_host_sub.meta

CAPS_PREREQS_CPP = \
    $(DIR)/constprop_suite.xml \
    $(DIR)/constprop.meta \
    $(HOST_CPP)/constprop_host_mod.meta \
    $(HOST_CPP)/constprop_host_sub.meta

# ── Executables ───────────────────────────────────────────────────────────────
EXE_CXX_HOST = $(BUILD)/constprop_cxx_host

BINDC_KINDS = $(BINDC_SRC)/ccpp_kinds.F90
BINDC_SUITE = $(BINDC_SRC)/constprop_suite_cap.F90

CXX_HOST_OBJS = \
  $(CXX_HOST_OBJ)/ccpp_kinds.o \
  $(CXX_HOST_OBJ)/ccpp_constituent_prop_mod.o \
  $(CXX_HOST_OBJ)/constprop.o \
  $(CXX_HOST_OBJ)/constprop_suite_cap.o \
  $(CXX_HOST_OBJ)/constprop_host_sub_ccpp_chost_cap.o \
  $(CXX_HOST_OBJ)/driver_constprop_chost.o

# ── Phony targets ─────────────────────────────────────────────────────────────
.PHONY: all cxx_host run run-cxx-host check caps gen-chost clean

all: cxx_host

cxx_host: $(EXE_CXX_HOST)

run-cxx-host: $(EXE_CXX_HOST)
	@echo "=== C++ host-model driver ===" && $(EXE_CXX_HOST)

run: run-cxx-host

check: cxx_host
	@echo "=== Correctness check ==="
	@$(EXE_CXX_HOST); STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "PASS"; \
	  else echo "FAIL (exit $$STATUS)"; exit 1; fi

# ── Build directories ─────────────────────────────────────────────────────────
$(BUILD) $(CXX_HOST_OBJ):
	mkdir -p $@

# ── C++ host-model build ──────────────────────────────────────────────────────

$(CXX_HOST_OBJ)/ccpp_kinds.o: $(BINDC_KINDS) | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/ccpp_constituent_prop_mod.o: $(DIR)/ccpp_constituent_prop_mod.F90 \
    $(CXX_HOST_OBJ)/ccpp_kinds.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/constprop.o: $(DIR)/constprop.F90 \
    $(CXX_HOST_OBJ)/ccpp_constituent_prop_mod.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/constprop_suite_cap.o: $(BINDC_SUITE) \
    $(CXX_HOST_OBJ)/ccpp_constituent_prop_mod.o \
    $(CXX_HOST_OBJ)/constprop.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/constprop_host_sub_ccpp_chost_cap.o: $(CHOST_F90) \
    $(CXX_HOST_OBJ)/constprop_suite_cap.o \
    $(CXX_HOST_OBJ)/ccpp_constituent_prop_mod.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/driver_constprop_chost.o: $(HOST_CPP)/driver_constprop_chost.cpp \
    $(CHOST_HDR) $(CHOST_HPP) | $(CXX_HOST_OBJ)
	$(CXX) $(CXXFLAGS) -I$(BINDC_SRC) -c $< -o $@

$(EXE_CXX_HOST): $(CXX_HOST_OBJS)
	$(FC) $(FFLAGS) $(NOMAIN) -o $@ $^ -lstdc++

# ── Cap generation ────────────────────────────────────────────────────────────
caps: $(CHOST_F90) $(CHOST_HDR) $(CHOST_HPP)

gen-chost: caps

$(BINDC_KINDS) $(BINDC_SUITE) $(CHOST_F90) $(CHOST_HDR) $(CHOST_HPP): $(CAPS_PREREQS_CPP)
	mkdir -p $(BINDC_SRC)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_SUITE) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS_CPP) \
	    --host-name    constprop_host_sub \
	    -o             $(BINDC_SRC)

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(BUILD)
	rm -rf $(BINDC_SRC)
