# Makefile for the HelloWorld CCPP test using xdsl-ccpp generated caps.
#
# All source files (generated and hand-written) live in the same directory.
# Generate the caps first, then build from this directory:
#
#   ccpp_xdsl --suites examples/helloworld/hello_world_suite.xml \
#             --scheme-files examples/helloworld/hello_scheme.meta,... \
#             --host-files   examples/helloworld/hello_world_host.meta,... \
#             -o examples/helloworld/
#
# Then inside the gcc Docker container from /work:
#   make -f examples/helloworld/Makefile
#   make -f examples/helloworld/Makefile run
#   make -f examples/helloworld/Makefile test
#   make -f examples/helloworld/Makefile clean

FC     = gfortran
FFLAGS = -g -Wall
DIR    = examples/helloworld
BUILD_DIR = $(DIR)/build

# Source files in compilation order (modules must precede their users)
SRCS = \
    $(DIR)/ccpp_kinds.F90 \
    $(DIR)/hello_world_mod.F90 \
    $(DIR)/hello_scheme.F90 \
    $(DIR)/temp_adjust.F90 \
    $(DIR)/hello_world_suite_cap.F90 \
    $(DIR)/HelloWorld_ccpp_cap.F90 \
    $(DIR)/hello_world_host.F90

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

EXE = $(BUILD_DIR)/hello_world

.PHONY: all run test clean

all: $(EXE)

run: $(EXE)
	$(EXE)

test: $(EXE)
	@echo "Running HelloWorld CCPP test..."
	@$(EXE) | tee /tmp/hello_world_output.txt
	@grep -q "Answers are correct" /tmp/hello_world_output.txt \
	    && echo "TEST PASSED" \
	    || (echo "TEST FAILED" && exit 1)

clean:
	rm -rf $(BUILD_DIR)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# ── Pattern rule ──────────────────────────────────────────────────────────────

$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

# ── Link ──────────────────────────────────────────────────────────────────────

$(EXE): $(OBJS)
	$(FC) $(FFLAGS) -o $@ $^
