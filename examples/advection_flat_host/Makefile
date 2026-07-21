# advection_flat_host CCPP example Makefile (CPU only)
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
#   make caps   — regenerate CCPP caps into examples/advection_flat_host/
#
# Utility:
#   make clean  — remove build artefacts and generated caps
#
# This is a CPU-only Makefile -- it does not build the OpenACC (ARCH=GPU)
# path advection/kessler's Makefiles support. temp/qv's memory_space=device
# annotations are inert without a GPU pass invocation; this target exists to
# confirm the example is otherwise a correct, complete, buildable CCPP host,
# independent of the (b)/(c) GPU work it was built to test.

FC     = gfortran
FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none
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
	    --suites       $(CAPS_SUITES) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --host-name    flat_host \
	    -o             $(DIR)/

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

$(TEST_EXE): $(OBJS) $(TEST_EXTRA_OBJS) $(BUILD_DIR)/test_flat_host_integration.o
	$(FC) $(FFLAGS) -o $@ $^
