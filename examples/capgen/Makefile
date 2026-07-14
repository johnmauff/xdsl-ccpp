# Capgen CCPP example Makefile
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
#   make caps   — regenerate CCPP caps into examples/capgen/
#
# Utility:
#   make clean  — remove build artefacts and generated caps

FC     = gfortran
FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none
DIR    = examples/capgen
BUILD_DIR = $(DIR)/build

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Generated caps ─────────────────────────────────────────────────────────────
GEN_KINDS      = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAPS = $(DIR)/ddt_suite_cap.F90 $(DIR)/temp_suite_cap.F90
GEN_CCPP_CAP   = $(DIR)/test_host_ccpp_cap.F90

CAPS_SUITES  = $(DIR)/ddt_suite.xml,$(DIR)/temp_suite.xml
CAPS_SCHEMES = $(DIR)/make_ddt.meta,$(DIR)/environ_conditions.meta,$(DIR)/setup_coeffs.meta,$(DIR)/temp_set.meta,$(DIR)/temp_calc_adjust.meta,$(DIR)/temp_adjust.meta
CAPS_HOSTS   = $(DIR)/test_host_data.meta,$(DIR)/test_host_mod.meta,$(DIR)/test_host.meta
CAPS_PREREQS = \
    $(DIR)/ddt_suite.xml \
    $(DIR)/temp_suite.xml \
    $(DIR)/make_ddt.meta \
    $(DIR)/environ_conditions.meta \
    $(DIR)/setup_coeffs.meta \
    $(DIR)/temp_set.meta \
    $(DIR)/temp_calc_adjust.meta \
    $(DIR)/temp_adjust.meta \
    $(DIR)/test_host_data.meta \
    $(DIR)/test_host_mod.meta \
    $(DIR)/test_host.meta

# Source files in compilation order (modules must precede their users)
SRCS = \
    $(GEN_KINDS) \
    $(DIR)/test_utils.F90 \
    $(DIR)/test_host_data.F90 \
    $(DIR)/test_host_mod.F90 \
    $(DIR)/make_ddt.F90 \
    $(DIR)/environ_conditions.F90 \
    $(DIR)/setup_coeffs.F90 \
    $(DIR)/temp_set.F90 \
    $(DIR)/temp_calc_adjust.F90 \
    $(DIR)/temp_adjust.F90 \
    $(GEN_SUITE_CAPS) \
    $(GEN_CCPP_CAP) \
    $(DIR)/test_host.F90 \
    $(DIR)/test_capgen_host_integration.F90

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

EXE = $(BUILD_DIR)/test_capgen

.PHONY: all run check clean caps

all: $(EXE)

run: $(EXE)
	$(EXE)

check: $(EXE)
	@echo "Running capgen CCPP test..."
	@$(EXE); STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "TEST PASSED"; \
	  else echo "TEST FAILED (exit $$STATUS)"; exit 1; fi

clean:
	rm -rf $(BUILD_DIR)
	rm -f $(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS)

caps: $(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAPS) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS)
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

$(EXE): $(OBJS)
	$(FC) $(FFLAGS) -o $@ $^
