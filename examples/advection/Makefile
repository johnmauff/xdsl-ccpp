FC     = gfortran
FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none
DIR    = examples/advection
BUILD_DIR = $(DIR)/build

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Generated caps ─────────────────────────────────────────────────────────────
GEN_KINDS     = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAP = $(DIR)/cld_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/test_host_ccpp_cap.F90

CAPS_SUITES  = $(DIR)/cld_suite.xml
CAPS_SCHEMES = $(DIR)/const_indices.meta,$(DIR)/cld_liq.meta,$(DIR)/apply_constituent_tendencies.meta,$(DIR)/cld_ice.meta
CAPS_HOSTS   = $(DIR)/test_host_data.meta,$(DIR)/test_host_mod.meta,$(DIR)/test_host.meta
CAPS_PREREQS = \
    $(DIR)/cld_suite.xml \
    $(DIR)/const_indices.meta \
    $(DIR)/cld_liq.meta \
    $(DIR)/apply_constituent_tendencies.meta \
    $(DIR)/cld_ice.meta \
    $(DIR)/test_host_data.meta \
    $(DIR)/test_host_mod.meta \
    $(DIR)/test_host.meta

# Compiles the generated suite cap and top-level cap together with their
# scheme and host dependencies.
#
# ccpp_constituent_prop_mod.F90 and ccpp_scheme_utils.F90 are stubs for the
# CCPP framework library modules used by the scheme files.

SRCS = \
    $(GEN_KINDS) \
    $(DIR)/ccpp_constituent_prop_mod.F90 \
    $(DIR)/ccpp_scheme_utils.F90 \
    $(DIR)/test_host_data.F90 \
    $(DIR)/test_host_mod.F90 \
    $(DIR)/const_indices.F90 \
    $(DIR)/cld_liq.F90 \
    $(DIR)/cld_ice.F90 \
    $(DIR)/dlc_liq.F90 \
    $(DIR)/apply_constituent_tendencies.F90 \
    $(GEN_SUITE_CAP) \
    $(GEN_CCPP_CAP)

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

# test_utils lives in examples/capgen (shared across examples)
TEST_EXTRA_SRCS = \
    examples/capgen/test_utils.F90 \
    $(DIR)/test_host.F90

TEST_EXTRA_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(TEST_EXTRA_SRCS:.F90=.o)))
TEST_EXE = $(BUILD_DIR)/test_advection

.PHONY: all clean caps test

all: $(OBJS)
	@echo "Advection caps compiled successfully."

clean:
	rm -rf $(BUILD_DIR)

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
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

$(BUILD_DIR)/test_utils.o: examples/capgen/test_utils.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

$(TEST_EXE): $(OBJS) $(TEST_EXTRA_OBJS) $(BUILD_DIR)/test_advection_host_integration.o
	$(FC) $(FFLAGS) -o $@ $^

test: $(TEST_EXE)
	@echo "Running advection integration test..."
	@$(TEST_EXE) && echo "Test PASSED" || (echo "Test FAILED"; exit 1)
