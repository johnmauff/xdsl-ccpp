# Makefile for the HelloWorld CCPP test using xdsl-ccpp generated caps.
#
# From the repo root:
#   make -f examples/helloworld/Makefile        # build (auto-generates caps)
#   make -f examples/helloworld/Makefile run
#   make -f examples/helloworld/Makefile test
#   make -f examples/helloworld/Makefile caps   # regenerate caps only
#   make -f examples/helloworld/Makefile clean

FC     = gfortran
FFLAGS = -g -Wall
DIR    = examples/helloworld
BUILD_DIR = $(DIR)/build

# ── Tools ─────────────────────────────────────────────────────────────────────
CCPP_XDSL ?= ccpp_xdsl

# ── Generated caps ─────────────────────────────────────────────────────────────
GEN_KINDS     = $(DIR)/ccpp_kinds.F90
GEN_SUITE_CAP = $(DIR)/hello_world_suite_cap.F90
GEN_CCPP_CAP  = $(DIR)/HelloWorld_ccpp_cap.F90

CAPS_SUITES  = $(DIR)/hello_world_suite.xml
CAPS_SCHEMES = $(DIR)/hello_scheme.meta,$(DIR)/temp_adjust.meta
CAPS_HOSTS   = $(DIR)/hello_world_host.meta,$(DIR)/hello_world_mod.meta
CAPS_PREREQS = \
    $(DIR)/hello_world_suite.xml \
    $(DIR)/hello_scheme.meta \
    $(DIR)/temp_adjust.meta \
    $(DIR)/hello_world_host.meta \
    $(DIR)/hello_world_mod.meta

# Source files in compilation order (modules must precede their users)
SRCS = \
    $(GEN_KINDS) \
    $(DIR)/hello_world_mod.F90 \
    $(DIR)/hello_scheme.F90 \
    $(DIR)/temp_adjust.F90 \
    $(GEN_SUITE_CAP) \
    $(GEN_CCPP_CAP) \
    $(DIR)/hello_world_host.F90

OBJS = $(addprefix $(BUILD_DIR)/,$(notdir $(SRCS:.F90=.o)))

EXE = $(BUILD_DIR)/hello_world

.PHONY: all run test clean caps

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

caps: $(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS)

$(GEN_SUITE_CAP) $(GEN_CCPP_CAP) $(GEN_KINDS): $(CAPS_PREREQS)
	$(CCPP_XDSL) \
	    --suites       $(CAPS_SUITES) \
	    --scheme-files $(CAPS_SCHEMES) \
	    --host-files   $(CAPS_HOSTS) \
	    --kind-map     kind_dyn:REAL32 \
	    -o             $(DIR)/

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: $(DIR)/%.F90 | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@ -J $(BUILD_DIR) -I $(BUILD_DIR)

$(EXE): $(OBJS)
	$(FC) $(FFLAGS) -o $@ $^
