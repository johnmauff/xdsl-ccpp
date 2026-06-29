FC     = gfortran
FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none
DIR    = examples/advection
BUILD_DIR = $(DIR)/build

# Compiles the generated suite cap and top-level cap together with their
# scheme and host dependencies.
#
# ccpp_constituent_prop_mod.F90 and ccpp_scheme_utils.F90 are stubs for the
# CCPP framework library modules used by the scheme files.

SRCS = \
    $(DIR)/ccpp_kinds.F90 \
    $(DIR)/ccpp_constituent_prop_mod.F90 \
    $(DIR)/ccpp_scheme_utils.F90 \
    $(DIR)/test_host_data.F90 \
    $(DIR)/test_host_mod.F90 \
    $(DIR)/const_indices.F90 \
    $(DIR)/cld_liq.F90 \
    $(DIR)/cld_ice.F90 \
    $(DIR)/dlc_liq.F90 \
    $(DIR)/apply_constituent_tendencies.F90 \
    $(DIR)/cld_suite_cap.F90 \
    $(DIR)/test_host_ccpp_cap.F90

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

# test_utils lives in examples/capgen (shared across examples)
TEST_EXTRA_SRCS = \
    examples/capgen/test_utils.F90 \
    $(DIR)/test_host.F90

TEST_EXTRA_OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(TEST_EXTRA_SRCS:.F90=.o)))
TEST_EXE = $(BUILD_DIR)/test_advection

.PHONY: all clean generate test

all: $(OBJS)
	@echo "Advection caps compiled successfully."

clean:
	rm -rf $(BUILD_DIR)

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

generate:
	cd ../.. && ./gen_advection
