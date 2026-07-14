# Kessler microphysics example Makefile
#
# Build targets:
#   make [all]     — build all three drivers
#   make ccpp      — CCPP-generated Fortran driver
#   make hand      — hand-written Fortran driver
#   make cxx       — plain C++ driver (BIND(C) caps)
#
# Run targets:
#   make run       — build and run all three (for easy comparison)
#   make run-ccpp  — build and run the CCPP Fortran driver
#   make run-hand  — build and run the hand-written driver
#   make run-cxx   — build and run the C++ driver
#
# Numerical parity:
#   make check     — run all three drivers and verify bit-for-bit identical output
#
# GPU (OpenMP target offload):
#   make ARCH=GPU [FC=nvfortran]
#
# Code generation (laptop, requires xdsl-ccpp):
#   make caps      — regenerate standard Fortran caps into examples/kessler/
#   make gen-chost — regenerate chost BIND(C) caps + headers into examples/kessler/bindc/
#   ./gen_kessler_bindc  — regenerate BIND(C) caps + C++ header into examples/kessler/bindc/
#   ./gen_kessler_chost  — regenerate chost BIND(C) caps + headers into examples/kessler/bindc/
#
# Utility:
#   make clean     — remove build artefacts and generated caps

# ── Compilers & flags ─────────────────────────────────────────────────────────
FC   ?= gfortran
ARCH ?= CPU

# Derive the C++ compiler and per-family flags from FC.
# FMA is defined once here and appended to both FFLAGS and CXXFLAGS.
ifeq ($(FC),nvfortran)
  CXX     ?= nvc++
  CC       = nvc
  FMA      = -Mnofma
  FC_CPU   = -g -O2 -Mfree -Mpreprocess
  FC_GPU   = -g -O2 -Mfree -mp=gpu -Minfo=accel -Mpreprocess -DUSE_GPU
  CXX_BASE = -g -O2
  MOD_OUT  = -module
  NOMAIN   = -Mnomain
else ifeq ($(FC),ifx)
  CXX     ?= icpx
  CC       = icx
  FMA      = -fp-model=precise
  FC_CPU   = -g -O2 -fpp
  FC_GPU   = -g -O2 -fpp -fiopenmp -fopenmp-targets=spir64 -DUSE_GPU
  CXX_BASE = -g -O2
  MOD_OUT  = -module
  NOMAIN   = -nofor-main
else
  # GNU (gfortran / g++)
  CXX     ?= g++
  CC       = gcc
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
CFLAGS   = -g -O2 $(FMA)

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Directories ───────────────────────────────────────────────────────────────
DIR          = examples/kessler
BUILD        = $(DIR)/build
CXX_OBJ      = $(BUILD)/cxx
CXX_HOST_OBJ = $(BUILD)/cxx_host

# ── Generated caps — standard Fortran (make caps) ────────────────────────────
GEN_KINDS     = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAP = $(DIR)/kessler_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/Kessler_ccpp_cap.F90

CAPS_SUITE   = $(DIR)/kessler_suite.xml
CAPS_SCHEMES = $(DIR)/kessler.meta,$(DIR)/kessler_update.meta
CAPS_HOSTS   = $(DIR)/kessler_host_mod.meta,$(DIR)/kessler_host_sub.meta
CAPS_PREREQS = \
    $(DIR)/kessler_suite.xml \
    $(DIR)/kessler.meta \
    $(DIR)/kessler_update.meta \
    $(DIR)/kessler_host_mod.meta \
    $(DIR)/kessler_host_sub.meta

# ── Generated caps — BIND(C) (./gen_kessler_bindc, committed) ────────────────
BINDC_SRC   = $(DIR)/bindc
BINDC_KINDS = $(BINDC_SRC)/ccpp_kinds.F90
BINDC_SUITE = $(BINDC_SRC)/kessler_suite_cap.F90
BINDC_CAP   = $(BINDC_SRC)/Kessler_ccpp_cap.F90
BINDC_HDR   = $(BINDC_SRC)/Kessler_ccpp_cap.h

# ── Source lists (modules before their users) ─────────────────────────────────
CCPP_SRCS = \
  $(GEN_KINDS) \
  $(DIR)/kessler_host_mod.F90 \
  $(DIR)/kessler.F90 \
  $(DIR)/kessler_update.F90 \
  $(GEN_SUITE_CAP) \
  $(GEN_CCPP_CAP) \
  $(DIR)/driver_kessler_ccpp.F90

HAND_SRCS = \
  $(GEN_KINDS) \
  $(DIR)/kessler_host_mod.F90 \
  $(DIR)/kessler.F90 \
  $(DIR)/kessler_update.F90 \
  $(DIR)/driver_kessler_old.F90

# ── Executables ───────────────────────────────────────────────────────────────
EXE_CCPP     = $(BUILD)/kessler_ccpp
EXE_HAND     = $(BUILD)/kessler_hand
EXE_CXX      = $(BUILD)/kessler_cxx
EXE_CXX_HOST = $(BUILD)/kessler_cxx_host

CCPP_OBJS = $(addprefix $(BUILD)/,$(notdir $(CCPP_SRCS:.F90=.o))) $(BUILD)/kessler_rng.o
HAND_OBJS = $(addprefix $(BUILD)/,$(notdir $(HAND_SRCS:.F90=.o))) $(BUILD)/kessler_rng.o

CXX_OBJS = \
  $(CXX_OBJ)/ccpp_kinds.o \
  $(CXX_OBJ)/kessler_host_mod.o \
  $(CXX_OBJ)/kessler_rng.o \
  $(CXX_OBJ)/kessler.o \
  $(CXX_OBJ)/kessler_update.o \
  $(CXX_OBJ)/kessler_suite_cap.o \
  $(CXX_OBJ)/Kessler_ccpp_cap.o \
  $(CXX_OBJ)/kessler_host_init_c.o \
  $(CXX_OBJ)/driver_kessler_cpp.o

CHOST_F90 = $(BINDC_SRC)/Kessler_ccpp_chost_cap.F90
CHOST_HDR = $(DIR)/Kessler_ccpp_chost_cap.h

CXX_HOST_OBJS = \
  $(CXX_HOST_OBJ)/ccpp_kinds.o \
  $(CXX_HOST_OBJ)/kessler.o \
  $(CXX_HOST_OBJ)/kessler_update.o \
  $(CXX_HOST_OBJ)/kessler_suite_cap.o \
  $(CXX_HOST_OBJ)/Kessler_ccpp_chost_cap.o \
  $(CXX_HOST_OBJ)/kessler_chost_print.o \
  $(BUILD)/kessler_rng.o \
  $(BUILD)/init_data_c.o \
  $(CXX_HOST_OBJ)/driver_kessler_cxx_host.o

# ── Phony targets ─────────────────────────────────────────────────────────────
.PHONY: all ccpp hand cxx cxx_host run run-ccpp run-hand run-cxx run-cxx-host check caps gen-chost clean

all: ccpp hand cxx cxx_host

ccpp:     $(EXE_CCPP)
hand:     $(EXE_HAND)
cxx:      $(EXE_CXX)
cxx_host: $(EXE_CXX_HOST)

run-ccpp: $(EXE_CCPP)
	@echo "=== CCPP Fortran driver ===" && $(EXE_CCPP)

run-hand: $(EXE_HAND)
	@echo "=== Hand-written Fortran driver ===" && $(EXE_HAND)

run-cxx: $(EXE_CXX)
	@echo "=== C++ BIND(C) driver ===" && $(EXE_CXX)

run-cxx-host: $(EXE_CXX_HOST)
	@echo "=== C++ host-model driver ===" && $(EXE_CXX_HOST)

run: run-ccpp run-hand run-cxx run-cxx-host

check: ccpp hand cxx cxx_host
	@echo "=== Numerical parity check ==="
	@$(EXE_CCPP)     | grep -v "Elapsed" > $(BUILD)/out_ccpp.txt
	@$(EXE_HAND)     | grep -v "Elapsed" > $(BUILD)/out_hand.txt
	@$(EXE_CXX)      | grep -v "Elapsed" > $(BUILD)/out_cxx.txt
	@$(EXE_CXX_HOST) | grep -v "Elapsed" > $(BUILD)/out_cxx_host.txt
	@result=0; \
	 diff -q $(BUILD)/out_ccpp.txt $(BUILD)/out_hand.txt > /dev/null \
	     && echo "PASS: ccpp == hand     (bit-for-bit)" \
	     || { echo "FAIL: ccpp != hand";     diff $(BUILD)/out_ccpp.txt $(BUILD)/out_hand.txt;     result=1; }; \
	 diff -q $(BUILD)/out_ccpp.txt $(BUILD)/out_cxx.txt > /dev/null \
	     && echo "PASS: ccpp == cxx      (bit-for-bit)" \
	     || { echo "FAIL: ccpp != cxx";      diff $(BUILD)/out_ccpp.txt $(BUILD)/out_cxx.txt;      result=1; }; \
	 diff -q $(BUILD)/out_ccpp.txt $(BUILD)/out_cxx_host.txt > /dev/null \
	     && echo "PASS: ccpp == cxx_host (bit-for-bit)" \
	     || { echo "FAIL: ccpp != cxx_host"; diff $(BUILD)/out_ccpp.txt $(BUILD)/out_cxx_host.txt; result=1; }; \
	 [ $$result -eq 0 ] && echo "=== All four drivers produce identical numerical output. ===" || exit 1

# ── Build directories ─────────────────────────────────────────────────────────
$(BUILD) $(CXX_OBJ) $(CXX_HOST_OBJ):
	mkdir -p $@

# ── Fortran compilation (shared by ccpp and hand) ─────────────────────────────
$(BUILD)/%.o: $(DIR)/%.F90 | $(BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(BUILD) -I $(BUILD)

# ── C compilation ─────────────────────────────────────────────────────────────
$(BUILD)/%.o: $(DIR)/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(CXX_OBJ)/%.o: $(DIR)/%.c | $(CXX_OBJ)
	$(CC) $(CFLAGS) -c $< -o $@

# ── Link: Fortran drivers ─────────────────────────────────────────────────────
$(EXE_CCPP): $(CCPP_OBJS)
	$(FC) $(FFLAGS) -o $@ $^

$(EXE_HAND): $(HAND_OBJS)
	$(FC) $(FFLAGS) -o $@ $^

# ── C++ BIND(C) build ─────────────────────────────────────────────────────────
# Sources in $(BINDC_SRC)/ are committed; regenerate with ./gen_kessler_bindc.

$(CXX_OBJ)/ccpp_kinds.o: $(BINDC_KINDS) | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ)

$(CXX_OBJ)/kessler_host_mod.o: $(DIR)/kessler_host_mod.F90 \
    $(CXX_OBJ)/ccpp_kinds.o | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ) -I $(CXX_OBJ)

$(CXX_OBJ)/kessler.o: $(DIR)/kessler.F90 \
    $(CXX_OBJ)/ccpp_kinds.o | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ) -I $(CXX_OBJ)

$(CXX_OBJ)/kessler_update.o: $(DIR)/kessler_update.F90 \
    $(CXX_OBJ)/ccpp_kinds.o | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ) -I $(CXX_OBJ)

$(CXX_OBJ)/kessler_suite_cap.o: $(BINDC_SUITE) \
    $(CXX_OBJ)/kessler.o $(CXX_OBJ)/kessler_update.o | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ) -I $(CXX_OBJ)

$(CXX_OBJ)/Kessler_ccpp_cap.o: $(BINDC_CAP) \
    $(CXX_OBJ)/kessler_suite_cap.o $(CXX_OBJ)/kessler_host_mod.o | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ) -I $(CXX_OBJ)

$(CXX_OBJ)/kessler_host_init_c.o: $(DIR)/kessler_host_init_c.F90 \
    $(CXX_OBJ)/kessler_host_mod.o $(CXX_OBJ)/ccpp_kinds.o | $(CXX_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_OBJ) -I $(CXX_OBJ)

$(CXX_OBJ)/driver_kessler_cpp.o: $(DIR)/driver_kessler_cpp.cpp $(BINDC_HDR)
	$(CXX) $(CXXFLAGS) -I$(BINDC_SRC) -c $< -o $@

$(EXE_CXX): $(CXX_OBJS)
	$(FC) $(FFLAGS) $(NOMAIN) -o $@ $^ -lstdc++

# ── C++ host-model build ──────────────────────────────────────────────────────
# kessler_host_mod is NOT used here — the C++ host owns all arrays.
# kessler_rng.o and init_data_c.o are shared C objects from $(BUILD)/.

$(CXX_HOST_OBJ)/ccpp_kinds.o: $(BINDC_KINDS) | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/kessler.o: $(DIR)/kessler.F90 \
    $(CXX_HOST_OBJ)/ccpp_kinds.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/kessler_update.o: $(DIR)/kessler_update.F90 \
    $(CXX_HOST_OBJ)/ccpp_kinds.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/kessler_suite_cap.o: $(BINDC_SUITE) \
    $(CXX_HOST_OBJ)/kessler.o $(CXX_HOST_OBJ)/kessler_update.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/Kessler_ccpp_chost_cap.o: $(CHOST_F90) \
    $(CXX_HOST_OBJ)/kessler_suite_cap.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/kessler_chost_print.o: $(DIR)/kessler_chost_print.F90 \
    $(CXX_HOST_OBJ)/ccpp_kinds.o | $(CXX_HOST_OBJ)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(CXX_HOST_OBJ) -I $(CXX_HOST_OBJ)

$(CXX_HOST_OBJ)/driver_kessler_cxx_host.o: $(DIR)/driver_kessler_cxx_host.cpp $(CHOST_HDR)
	$(CXX) $(CXXFLAGS) -I$(DIR) -c $< -o $@

$(EXE_CXX_HOST): $(CXX_HOST_OBJS)
	$(FC) $(FFLAGS) $(NOMAIN) -o $@ $^ -lstdc++

# ── Cap generation ────────────────────────────────────────────────────────────
caps: $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS)
	$(CCPP_XDSL) \
	    --directive    acc \
	    --suites       $(CAPS_SUITE) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    -o             $(DIR)

gen-chost: $(CHOST_F90) $(CHOST_HDR)

$(CHOST_F90) $(CHOST_HDR): \
    $(DIR)/kessler.meta $(DIR)/kessler_update.meta \
    $(DIR)/kessler_host_mod.meta $(DIR)/kessler_host_sub.meta \
    $(DIR)/kessler_suite.xml
	mkdir -p $(BINDC_SRC)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_SUITE) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --explicit-args \
	    -o             $(BINDC_SRC)

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(BUILD)
	rm -f $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)
