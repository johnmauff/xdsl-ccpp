# Kessler microphysics example Makefile
#
# Targets:
#   make              — CCPP-cap driver (CPU, gfortran)
#   make old          — original hand-written driver (CPU, gfortran)
#   make ARCH=GPU     — CCPP-cap driver (OpenMP target GPU, requires FC=nvfortran)
#   make run          — build and run the CCPP driver
#   make run_old      — build and run the original driver
#   make test         — run and diff against reference output
#   make caps         — (re)generate cap .F90 files only
#   make clean        — remove build artefacts and generated caps
#
# Usage from the repo root:
#   make -f examples/kessler/Makefile
#   make -f examples/kessler/Makefile old

FC      = gfortran
ARCH   ?= CPU
DIR     = examples/kessler
BUILD_DIR = $(DIR)/build

# ── compiler flags ────────────────────────────────────────────────────────────
ifeq ($(ARCH),GPU)
  ifeq ($(FC),nvfortran)
    FFLAGS = -g -O2 -Mfree -mp=gpu -Minfo=accel -DUSE_GPU
  else
    FFLAGS = -g -O2 -ffree-line-length-none -fiopenmp -fopenmp-targets=spir64 -DUSE_GPU
  endif
else
  FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none -fopenmp -cpp
endif

# ── cap generation ────────────────────────────────────────────────────────────
GEN_SUITE_CAP = $(DIR)/kessler_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/Kessler_ccpp_cap.F90
GEN_KINDS     = $(DIR)/ccpp_kinds.F90

# ── source lists (compilation order: modules before users) ───────────────────
CCPP_SRCS = \
  $(GEN_KINDS) \
  $(DIR)/kessler_host_mod.F90 \
  $(DIR)/kessler.F90 \
  $(DIR)/kessler_update.F90 \
  $(GEN_SUITE_CAP) \
  $(GEN_CCPP_CAP) \
  $(DIR)/driver_kessler_ccpp.F90

OLD_SRCS = \
  $(DIR)/kessler.F90 \
  $(DIR)/kessler_update.F90 \
  $(DIR)/driver_kessler_old.F90

CCPP_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(CCPP_SRCS:.F90=.o)))
OLD_OBJS  = $(addprefix $(BUILD_DIR)/,$(notdir $(OLD_SRCS:.F90=.o)))

EXE_CCPP = $(BUILD_DIR)/test_kessler_ccpp
EXE_OLD  = $(BUILD_DIR)/test_kessler_old

# ── phony targets ─────────────────────────────────────────────────────────────
.PHONY: all old caps run run_old test clean

all: $(EXE_CCPP)

old: $(EXE_OLD)

run_old: $(EXE_OLD)
	$(EXE_OLD)

run: $(EXE_CCPP)
	$(EXE_CCPP)

test: $(EXE_CCPP)
	@echo "Running Kessler CCPP driver..."
	@$(EXE_CCPP); STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "TEST PASSED"; \
	  else echo "TEST FAILED (exit $$STATUS)"; exit 1; fi

# ── cap generation ────────────────────────────────────────────────────────────
caps: $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS): \
    $(DIR)/kessler.meta $(DIR)/kessler_update.meta \
    $(DIR)/kessler_host_mod.meta $(DIR)/kessler_host_sub.meta \
    $(DIR)/kessler_suite.xml
	./gen_kessler

# ── build directory ───────────────────────────────────────────────────────────
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# ── compilation rule ──────────────────────────────────────────────────────────
$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

# ── link ──────────────────────────────────────────────────────────────────────
$(EXE_CCPP): $(CCPP_OBJS)
	$(FC) $(FFLAGS) -o $@ $^

$(EXE_OLD): $(OLD_OBJS)
	$(FC) $(FFLAGS) -o $@ $^

# ── clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(BUILD_DIR)
	rm -f $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)
