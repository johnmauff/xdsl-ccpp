FC     = gfortran
FFLAGS = -g -Wall -Wno-unused-dummy-argument -ffree-line-length-none
DIR    = examples/capgen
BUILD_DIR = $(DIR)/build

# Source files in compilation order (modules must precede their users)
SRCS = \
    $(DIR)/ccpp_kinds.F90 \
    $(DIR)/test_utils.F90 \
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
    $(DIR)/test_capgen_host_integration.F90

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

EXE = $(BUILD_DIR)/test_capgen

.PHONY: all run test clean generate

all: $(EXE)

run: $(EXE)
	$(EXE)

test: $(EXE)
	@echo "Running capgen CCPP test..."
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
	cd ../.. && ./gen_capgen
