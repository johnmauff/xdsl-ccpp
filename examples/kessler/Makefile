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
#   ./gen_kessler        — regenerate standard Fortran caps into examples/kessler/
#   ./gen_kessler_bindc  — regenerate BIND(C) caps + C++ header into examples/kessler/bindc/
#
# Utility:
#   make caps      — regenerate standard Fortran caps only
#   make clean     — remove build artefacts and generated caps

# ── Compilers & flags ─────────────────────────────────────────────────────────
FC   ?= gfortran
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
else ifeq ($(FC),ifx)
  CXX     ?= icpx
  FMA      = -fp-model=precise
  FC_CPU   = -g -O2 -fpp
  FC_GPU   = -g -O2 -fpp -fiopenmp -fopenmp-targets=spir64 -DUSE_GPU
  CXX_BASE = -g -O2
  MOD_OUT  = -module
else
  # GNU (gfortran / g++)
  CXX     ?= g++
  FMA      = -ffp-contract=off
  FC_CPU   = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none -O2 -cpp
  FC_GPU   = -g -O2 -ffree-line-length-none -fiopenmp -fopenmp-targets=spir64 -cpp -DUSE_GPU
  CXX_BASE = -g -Wall -O2
  MOD_OUT  = -J
endif

ifeq ($(ARCH),GPU)
  FFLAGS = $(FC_GPU) $(FMA)
else
  FFLAGS = $(FC_CPU) $(FMA)
endif
CXXFLAGS = $(CXX_BASE) $(FMA)

# ── Directories ───────────────────────────────────────────────────────────────
DIR     = examples/kessler
BUILD   = $(DIR)/build
CXX_OBJ = $(BUILD)/cxx

# ── Generated caps — standard Fortran (./gen_kessler) ────────────────────────
GEN_KINDS     = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAP = $(DIR)/kessler_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/Kessler_ccpp_cap.F90

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
  $(DIR)/kessler.F90 \
  $(DIR)/kessler_update.F90 \
  $(DIR)/driver_kessler_old.F90

# ── Executables ───────────────────────────────────────────────────────────────
EXE_CCPP = $(BUILD)/kessler_ccpp
EXE_HAND = $(BUILD)/kessler_hand
EXE_CXX  = $(BUILD)/kessler_cxx

CCPP_OBJS = $(addprefix $(BUILD)/,$(notdir $(CCPP_SRCS:.F90=.o)))
HAND_OBJS = $(addprefix $(BUILD)/,$(notdir $(HAND_SRCS:.F90=.o)))

CXX_OBJS = \
  $(CXX_OBJ)/ccpp_kinds.o \
  $(CXX_OBJ)/kessler_host_mod.o \
  $(CXX_OBJ)/kessler.o \
  $(CXX_OBJ)/kessler_update.o \
  $(CXX_OBJ)/kessler_suite_cap.o \
  $(CXX_OBJ)/Kessler_ccpp_cap.o \
  $(CXX_OBJ)/kessler_host_init_c.o \
  $(CXX_OBJ)/driver_kessler_cpp.o

# ── Phony targets ─────────────────────────────────────────────────────────────
.PHONY: all ccpp hand cxx run run-ccpp run-hand run-cxx check caps clean

all: ccpp hand cxx

ccpp: $(EXE_CCPP)
hand: $(EXE_HAND)
cxx:  $(EXE_CXX)

run-ccpp: $(EXE_CCPP)
	@echo "=== CCPP Fortran driver ===" && $(EXE_CCPP)

run-hand: $(EXE_HAND)
	@echo "=== Hand-written Fortran driver ===" && $(EXE_HAND)

run-cxx: $(EXE_CXX)
	@echo "=== C++ BIND(C) driver ===" && $(EXE_CXX)

run: run-ccpp run-hand run-cxx

check: ccpp hand cxx
	@echo "=== Numerical parity check ==="
	@$(EXE_CCPP) | grep -v "Elapsed" > $(BUILD)/out_ccpp.txt
	@$(EXE_HAND) | grep -v "Elapsed" > $(BUILD)/out_hand.txt
	@$(EXE_CXX)  | grep -v "Elapsed" > $(BUILD)/out_cxx.txt
	@result=0; \
	 diff -q $(BUILD)/out_ccpp.txt $(BUILD)/out_hand.txt > /dev/null \
	     && echo "PASS: ccpp == hand (bit-for-bit)" \
	     || { echo "FAIL: ccpp != hand"; diff $(BUILD)/out_ccpp.txt $(BUILD)/out_hand.txt; result=1; }; \
	 diff -q $(BUILD)/out_ccpp.txt $(BUILD)/out_cxx.txt > /dev/null \
	     && echo "PASS: ccpp == cxx  (bit-for-bit)" \
	     || { echo "FAIL: ccpp != cxx";  diff $(BUILD)/out_ccpp.txt $(BUILD)/out_cxx.txt; result=1; }; \
	 [ $$result -eq 0 ] && echo "=== All three drivers produce identical numerical output. ===" || exit 1

# ── Build directories ─────────────────────────────────────────────────────────
$(BUILD) $(CXX_OBJ):
	mkdir -p $@

# ── Fortran compilation (shared by ccpp and hand) ─────────────────────────────
$(BUILD)/%.o: $(DIR)/%.F90 | $(BUILD)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(BUILD) -I $(BUILD)

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
	$(FC) $(FFLAGS) -o $@ $^ -lstdc++

# ── Cap generation ────────────────────────────────────────────────────────────
caps: $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS): \
    $(DIR)/kessler.meta $(DIR)/kessler_update.meta \
    $(DIR)/kessler_host_mod.meta $(DIR)/kessler_host_sub.meta \
    $(DIR)/kessler_suite.xml
	./gen_kessler

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(BUILD)
	rm -f $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)
