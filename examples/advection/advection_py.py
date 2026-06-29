"""Python suite definition for the advection example.

Loads all scheme and host metadata from the existing .meta files, keeping
them as the single source of truth.  Only the suite orchestration is written
in Python.

Run to emit MLIR IR:
    python3 examples/advection/advection_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/advection/advection_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Equivalent XML invocation:
    python3 -m xdsl_ccpp.frontend.ccpp_xml \\
        --suites examples/advection/cld_suite.xml \\
        --scheme-files examples/advection/const_indices.meta,\\
examples/advection/cld_liq.meta,\\
examples/advection/apply_constituent_tendencies.meta,\\
examples/advection/cld_ice.meta \\
        --host-files examples/advection/test_host_data.meta,\\
examples/advection/test_host.meta,\\
examples/advection/test_host_mod.meta \\
        | python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Note: apply_constituent_tendencies appears twice in the suite (once after
cld_liq, once after cld_ice), matching cld_suite.xml.
"""

from xdsl_ccpp.frontend.py_api import (
    ccpp_scheme_from_meta,
    ccpp_host_from_meta,
    ccpp_suite,
    emit_ir,
)

# ---------------------------------------------------------------------------
# Schemes (loaded from .meta files)
# ---------------------------------------------------------------------------

const_indices               = ccpp_scheme_from_meta("examples/advection/const_indices.meta")
cld_liq                     = ccpp_scheme_from_meta("examples/advection/cld_liq.meta")
apply_constituent_tendencies = ccpp_scheme_from_meta("examples/advection/apply_constituent_tendencies.meta")
cld_ice                     = ccpp_scheme_from_meta("examples/advection/cld_ice.meta")

# ---------------------------------------------------------------------------
# Host metadata
# ---------------------------------------------------------------------------

host = (
    ccpp_host_from_meta("examples/advection/test_host_data.meta")
    + ccpp_host_from_meta("examples/advection/test_host.meta")
    + ccpp_host_from_meta("examples/advection/test_host_mod.meta")
)

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("cld_suite", version="1.0")
class cld_suite:
    physics = [const_indices, cld_liq, apply_constituent_tendencies, cld_ice]

    def run():
        const_indices()
        cld_liq()
        apply_constituent_tendencies()   # first application: after cld_liq
        cld_ice()
        apply_constituent_tendencies()   # second application: after cld_ice


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(cld_suite, additional=host)
