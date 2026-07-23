# var_compat CCPP example Makefile
#
# Ported from NCAR/ccpp-framework's feature/capgen-v1 branch,
# end-to-end-tests/var_compat -- see README.md for what this example is for
# and its current known-limitations.
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
# Code generation (requires xdsl-ccpp):
#   make caps   — regenerate CCPP caps into examples/var_compat/
#
# Utility:
#   make clean  — remove build artefacts and generated caps
#
# No GPU/OpenACC target: this example has no memory_space = device
# declarations anywhere, so ARCH=GPU support (as offered by e.g.
# examples/advection's Makefile) isn't relevant here.

# ── Compilers & flags ─────────────────────────────────────────────────────────
ifeq ($(origin FC),default)
FC   := gfortran
endif

ifeq ($(FC),nvfortran)
  FFLAGS  = -g -O2 -Mfree -Mpreprocess
  MOD_OUT = -module
else ifeq ($(FC),ifx)
  FFLAGS  = -g -O2 -fpp
  MOD_OUT = -module
else
  # GNU (gfortran)
  FFLAGS  = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none -O2 -cpp
  MOD_OUT = -J
endif

DIR    = examples/var_compat
BUILD_DIR = $(DIR)/build

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Generated caps ─────────────────────────────────────────────────────────────
GEN_KINDS     = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAP = $(DIR)/var_compatibility_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/test_host_ccpp_cap.F90

CAPS_SUITES  = $(DIR)/var_compatibility_suite.xml
CAPS_SCHEMES = $(DIR)/effr_pre.meta,$(DIR)/effr_calc.meta,$(DIR)/effr_post.meta,$(DIR)/effrs_calc.meta,$(DIR)/effr_diag.meta,$(DIR)/rad_lw.meta,$(DIR)/rad_sw.meta
CAPS_HOSTS   = $(DIR)/test_host_data.meta,$(DIR)/test_host_mod.meta,$(DIR)/test_host.meta
CAPS_PREREQS = \
    $(DIR)/var_compatibility_suite.xml \
    $(DIR)/effr_pre.meta \
    $(DIR)/effr_calc.meta \
    $(DIR)/effr_post.meta \
    $(DIR)/effrs_calc.meta \
    $(DIR)/effr_diag.meta \
    $(DIR)/rad_lw.meta \
    $(DIR)/rad_sw.meta \
    $(DIR)/test_host_data.meta \
    $(DIR)/test_host_mod.meta \
    $(DIR)/test_host.meta

# Compiles the generated suite cap and top-level cap together with their
# scheme and host dependencies. module_rad_ddt.F90 must come before
# rad_lw.F90/rad_sw.F90 -- both schemes' .meta declare
# "dependencies = module_rad_ddt.F90" (a real Fortran USE dependency).
SRCS = \
    $(GEN_KINDS) \
    $(DIR)/module_rad_ddt.F90 \
    $(DIR)/test_host_data.F90 \
    $(DIR)/test_host_mod.F90 \
    $(DIR)/effr_pre.F90 \
    $(DIR)/effr_calc.F90 \
    $(DIR)/effr_post.F90 \
    $(DIR)/effrs_calc.F90 \
    $(DIR)/effr_diag.F90 \
    $(DIR)/rad_lw.F90 \
    $(DIR)/rad_sw.F90 \
    $(GEN_SUITE_CAP) \
    $(GEN_CCPP_CAP)

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

# test_utils lives in examples/capgen/host_ftn (shared across examples)
TEST_EXTRA_SRCS = \
    examples/capgen/host_ftn/test_utils.F90 \
    $(DIR)/test_host.F90

TEST_EXTRA_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(TEST_EXTRA_SRCS:.F90=.o)))
TEST_EXE = $(BUILD_DIR)/test_var_compat

.PHONY: all run check clean caps known-issue

# Printed unconditionally before any build attempt below (not just on
# failure) so a compile error is understood rather than mysterious -- see
# README.md's "Other features this example carries" section and
# ccpp_cap_refactor_plan.md's backlog for the full writeup.
known-issue:
	@echo "NOTE: examples/var_compat has a known compile blocker unrelated to"
	@echo "      nested-subcycle support -- a dummy-argument-name collision"
	@echo "      (see README.md). If the build below fails, this is why."

all: known-issue $(TEST_EXE)

run: known-issue $(TEST_EXE)
	$(TEST_EXE)

check: known-issue $(TEST_EXE)
	@echo "Running var_compat integration test..."
	@$(TEST_EXE) && echo "TEST PASSED" || (echo "TEST FAILED"; exit 1)

clean:
	rm -rf $(BUILD_DIR)
	rm -f $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

caps: $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_SUITES) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --host-name    test_host \
	    -o             $(DIR)/

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(BUILD_DIR) -I $(BUILD_DIR)

$(BUILD_DIR)/test_utils.o: examples/capgen/host_ftn/test_utils.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ $(MOD_OUT) $(BUILD_DIR) -I $(BUILD_DIR)

$(TEST_EXE): $(OBJS) $(TEST_EXTRA_OBJS) $(BUILD_DIR)/test_var_compat_host_integration.o
	$(FC) $(FFLAGS) -o $@ $^
