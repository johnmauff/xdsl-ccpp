# advection_flat_host CCPP example Makefile
#
# Build targets:
#   make [all]  — build the test executable (auto-generates caps if needed)
#
# Run targets:
#   make run    — build and run
#
# Verification:
#   make check  — build, run, and verify pass/fail
#
# GPU (OpenACC, same pattern as examples/kessler's Makefile):
#   make ARCH=GPU [FC=nvfortran]
#
# Code generation (requires xdsl-ccpp):
#   make caps   — regenerate CCPP caps into examples/advection_flat_host/
#
# Utility:
#   make clean  — remove build artefacts and generated caps

# ── Compilers & flags ─────────────────────────────────────────────────────────
ifeq ($(origin FC),default)
FC   := gfortran
endif
ARCH ?= CPU

# Same three-way compiler-family branch as examples/kessler's Makefile.
# No C/C++ objects in this example (single Fortran driver), so there's no
# ACC_OFF_C-style accelerator-runtime-hook concern to carry over here.
ifeq ($(FC),nvfortran)
  FC_CPU  = -g -O2 -Mfree -Mpreprocess -noacc
  FC_GPU  = -g -O2 -Mfree -mp=gpu -Minfo=accel -Mpreprocess -DUSE_GPU
  MOD_OUT = -module
else ifeq ($(FC),ifx)
  FC_CPU  = -g -O2 -fpp
  FC_GPU  = -g -O2 -fpp -fiopenmp -fopenmp-targets=spir64 -DUSE_GPU
  MOD_OUT = -module
else
  # GNU (gfortran)
  FC_CPU  = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none -O2 -cpp
  FC_GPU  = -g -O2 -ffree-line-length-none -fiopenmp -fopenmp-targets=spir64 -cpp -DUSE_GPU
  MOD_OUT = -J
endif

ifeq ($(ARCH),GPU)
  FFLAGS = $(FC_GPU)
else
  FFLAGS = $(FC_CPU)
endif

DIR    = examples/advection_flat_host
BUILD_DIR = $(DIR)/build

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Generated caps ─────────────────────────────────────────────────────────────
GEN_KINDS     = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAP = $(DIR)/flat_cld_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/flat_host_ccpp_cap.F90

CAPS_SUITES  = $(DIR)/cld_suite.xml
CAPS_SCHEMES = $(DIR)/const_indices.meta,$(DIR)/cld_liq.meta,$(DIR)/apply_constituent_tendencies.meta,$(DIR)/cld_ice.meta
CAPS_HOSTS   = $(DIR)/flat_host_data.meta,$(DIR)/flat_host_mod.meta,$(DIR)/flat_host.meta
CAPS_PREREQS = \
    $(DIR)/cld_suite.xml \
    $(DIR)/const_indices.meta \
    $(DIR)/cld_liq.meta \
    $(DIR)/apply_constituent_tendencies.meta \
    $(DIR)/cld_ice.meta \
    $(DIR)/flat_host_data.meta \
    $(DIR)/flat_host_mod.meta \
    $(DIR)/flat_host.meta

# Compiles the generated suite cap and top-level cap together with their
# scheme and host dependencies.
#
# ccpp_constituent_prop_mod.F90 and ccpp_scheme_utils.F90 are stubs for the
# CCPP framework library modules used by the scheme files (copied unchanged
# from examples/advection).

SRCS = \
    $(GEN_KINDS) \
    $(DIR)/ccpp_constituent_prop_mod.F90 \
    $(DIR)/ccpp_scheme_utils.F90 \
    $(DIR)/flat_host_data.F90 \
    $(DIR)/flat_host_mod.F90 \
    $(DIR)/const_indices.F90 \
    $(DIR)/cld_liq.F90 \
    $(DIR)/cld_ice.F90 \
    $(DIR)/apply_constituent_tendencies.F90 \
    $(GEN_SUITE_CAP) \
    $(GEN_CCPP_CAP)

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

TEST_EXTRA_SRCS = $(DIR)/flat_host.F90
TEST_EXTRA_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(TEST_EXTRA_SRCS:.F90=.o)))
TEST_EXE = $(BUILD_DIR)/test_advection_flat_host

.PHONY: all run check clean caps

all: $(TEST_EXE)

run: $(TEST_EXE)
	$(TEST_EXE)

check: $(TEST_EXE)
	@echo "Running advection_flat_host integration test..."
	@$(TEST_EXE) && echo "TEST PASSED" || (echo "TEST FAILED"; exit 1)

clean:
	rm -rf $(BUILD_DIR)
	rm -f $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

caps: $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS)
	$(CCPP_XDSL) \
	    --directive    acc \
	    --suites       $(CAPS_SUITES) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --host-name    flat_host \
	    -o             $(DIR)/

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(BUILD_DIR) -I $(BUILD_DIR)

$(TEST_EXE): $(OBJS) $(TEST_EXTRA_OBJS) $(BUILD_DIR)/test_flat_host_integration.o
	$(FC) $(FFLAGS) -o $@ $^
