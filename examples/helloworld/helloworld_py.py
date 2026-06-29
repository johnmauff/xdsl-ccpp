"""Python suite definition for the helloworld example.

Loads scheme metadata from the existing .meta files, keeping them as the
single source of truth.  Only the suite orchestration is written here.

Run to emit MLIR IR:
    python3 examples/helloworld/helloworld_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/helloworld/helloworld_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

CLI override — repeat hello_scheme N times (N baked in at IR-generation time):
    python3 examples/helloworld/helloworld_py.py hello_repeats=3 | ...
"""

from xdsl_ccpp.frontend.py_api import ccpp_param, ccpp_scheme_from_meta, ccpp_suite, emit_ir

# ---------------------------------------------------------------------------
# Schemes (loaded from .meta files)
# ---------------------------------------------------------------------------

hello_scheme = ccpp_scheme_from_meta("examples/helloworld/hello_scheme.meta")
temp_adjust  = ccpp_scheme_from_meta("examples/helloworld/temp_adjust.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

# Number of times to repeat hello_scheme (resolved at IR-generation time).
# Override from CLI: python3 helloworld_py.py hello_repeats=3
hello_repeats = ccpp_param("hello_repeats", default=1)


@ccpp_suite("hello_world_suite", version="1.0")
class hello_world:
    physics = [hello_scheme, temp_adjust]

    def run():
        for i in range(hello_repeats):
            hello_scheme()
        temp_adjust()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(hello_world)
