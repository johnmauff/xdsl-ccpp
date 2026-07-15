"""Python suite definition for the Kessler microphysics example.

Loads all scheme and host metadata from the existing .meta files, keeping
them as the single source of truth.  Only the suite orchestration is written
in Python.  OpenACC GPU data directives are generated automatically from the
memory_space = device attributes in kessler.meta and kessler_update.meta.

Run to emit MLIR IR:
    python3 examples/kessler/scheme/kessler_py.py

Full pipeline — CPU Fortran only:
    python3 examples/kessler/scheme/kessler_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-host-match,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Full pipeline — with OpenACC GPU directives (default):
    python3 examples/kessler/scheme/kessler_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-host-match,generate-meta-kinds,generate-suite-cap,generate-gpu-data,generate-ccpp-cap,generate-gpu-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Full pipeline — with OpenMP target offload directives:
    python3 examples/kessler/scheme/kessler_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p "generate-meta-cap,generate-host-match,generate-meta-kinds,generate-suite-cap,generate-gpu-data,generate-ccpp-cap,generate-gpu-ccpp-cap{directive=omp},generate-kinds,strip-ccpp" \\
        -t ftn

Equivalent driver invocation (OpenACC):
    ccpp_xdsl \\
        --suites   examples/kessler/scheme/kessler_suite.xml \\
        --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta \\
        --host-files   examples/kessler/host_ftn/kessler_host_mod.meta,examples/kessler/host_ftn/kessler_host_sub.meta \\
        --directive acc \\
        -o output/
"""

from xdsl_ccpp.frontend.py_api import (
    ccpp_scheme_from_meta,
    ccpp_host_from_meta,
    ccpp_suite,
    emit_ir,
)

# ---------------------------------------------------------------------------
# Schemes (loaded from .meta files; memory_space = device attributes are
# preserved and drive OpenACC/OpenMP directive generation downstream)
# ---------------------------------------------------------------------------

kessler        = ccpp_scheme_from_meta("examples/kessler/scheme/kessler.meta")
kessler_update = ccpp_scheme_from_meta("examples/kessler/scheme/kessler_update.meta")

# ---------------------------------------------------------------------------
# Host metadata
# ---------------------------------------------------------------------------

host = (
    ccpp_host_from_meta("examples/kessler/host_ftn/kessler_host_mod.meta")
    + ccpp_host_from_meta("examples/kessler/host_ftn/kessler_host_sub.meta")
)

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("kessler_suite", version="1.0")
class kessler_suite:
    physics = [kessler, kessler_update]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(kessler_suite, additional=host)
