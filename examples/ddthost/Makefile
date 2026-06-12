FC     = gfortran
FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none
DIR    = examples/ddthost
BUILD_DIR = $(DIR)/build

# Source files in compilation order (modules must precede their users)
SRCS = \
    $(DIR)/ccpp_kinds.F90 \
    $(DIR)/test_utils.F90 \
    $(DIR)/host_ccpp_ddt.F90 \
    $(DIR)/test_host_data.F90 \
    $(DIR)/test_host_mod.F90 \
    $(DIR)/make_ddt.F90 \
    $(DIR)/environ_conditions.F90 \
    $(DIR)/setup_coeffs.F90 \
    $(DIR)/temp_set.F90 \
    $(DIR)/temp_calc_adjust.F90 \
    $(DIR)/temp_adjust.F90 \
    $(DIR)/ddt_suite_cap.F90 \
    $(DIR)/temp_suite_cap.F90 \
    $(DIR)/test_host_ccpp_cap.F90 \
    $(DIR)/test_host.F90 \
    $(DIR)/test_ddt_host_integration.F90

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

EXE = $(BUILD_DIR)/test_ddthost

.PHONY: all run test clean generate

all: $(EXE)

run: $(EXE)
	$(EXE)

test: $(EXE)
	@echo "Running ddthost CCPP test..."
	@$(EXE); STATUS=$$?; \
	  if [ $$STATUS -eq 0 ]; then echo "TEST PASSED"; \
	  else echo "TEST FAILED (exit $$STATUS)"; exit 1; fi

clean:
	rm -rf $(BUILD_DIR)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

$(EXE): $(OBJS)
	$(FC) $(FFLAGS) -o $@ $^

generate:
	ccpp_xdsl \
	  --suites $(DIR)/ddt_suite.xml,$(DIR)/temp_suite.xml \
	  --scheme-files $(DIR)/make_ddt.meta,$(DIR)/environ_conditions.meta,$(DIR)/setup_coeffs.meta,$(DIR)/temp_set.meta,$(DIR)/temp_calc_adjust.meta,$(DIR)/temp_adjust.meta \
	  --host-files $(DIR)/host_ccpp_ddt.meta,$(DIR)/test_host_data.meta,$(DIR)/test_host_mod.meta,$(DIR)/test_host.meta \
	  --host-name test_host \
	  -o $(DIR)/
