"""Python suite definition for the capgen example.

Loads all scheme and host metadata from the existing .meta files, keeping
them as the single source of truth.  Only the suite orchestration is written
in Python.  Both suites (ddt_suite and temp_suite) are defined and emitted
together, matching the two-suite XML invocation.

Run to emit MLIR IR:
    python3 examples/capgen/scheme/capgen_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/capgen/scheme/capgen_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Equivalent XML invocation:
    python3 -m xdsl_ccpp.frontend.ccpp_xml \\
        --suites examples/capgen/scheme/ddt_suite.xml,examples/capgen/scheme/temp_suite.xml \\
        --scheme-files examples/capgen/scheme/make_ddt.meta,\\
examples/capgen/scheme/environ_conditions.meta,\\
examples/capgen/scheme/setup_coeffs.meta,\\
examples/capgen/scheme/temp_set.meta,\\
examples/capgen/scheme/temp_calc_adjust.meta,\\
examples/capgen/scheme/temp_adjust.meta \\
        --host-files examples/capgen/host_ftn/test_host_data.meta,\\
examples/capgen/host_ftn/test_host_mod.meta,\\
examples/capgen/host_ftn/test_host.meta \\
        | python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Note: make_ddt.meta contains two [ccpp-table-properties] blocks — the vmr_type
DDT definition and the make_ddt scheme.  ccpp_ddt_from_meta extracts the DDT
and ccpp_scheme_from_meta extracts the scheme from the same file.
"""

from xdsl_ccpp.frontend.py_api import (
    ccpp_ddt_from_meta,
    ccpp_scheme_from_meta,
    ccpp_host_from_meta,
    ccpp_suite,
    emit_ir,
)

# ---------------------------------------------------------------------------
# Schemes and DDTs (loaded from .meta files)
# ---------------------------------------------------------------------------

# make_ddt.meta has two blocks: vmr_type (DDT) then make_ddt (scheme)
vmr_type        = ccpp_ddt_from_meta("examples/capgen/scheme/make_ddt.meta")
make_ddt        = ccpp_scheme_from_meta("examples/capgen/scheme/make_ddt.meta")

environ_conditions = ccpp_scheme_from_meta("examples/capgen/scheme/environ_conditions.meta")
setup_coeffs       = ccpp_scheme_from_meta("examples/capgen/scheme/setup_coeffs.meta")
temp_set           = ccpp_scheme_from_meta("examples/capgen/scheme/temp_set.meta")
temp_calc_adjust   = ccpp_scheme_from_meta("examples/capgen/scheme/temp_calc_adjust.meta")
temp_adjust        = ccpp_scheme_from_meta("examples/capgen/scheme/temp_adjust.meta")

# ---------------------------------------------------------------------------
# Host metadata
# ---------------------------------------------------------------------------

host = (
    ccpp_host_from_meta("examples/capgen/host_ftn/test_host_data.meta")
    + ccpp_host_from_meta("examples/capgen/host_ftn/test_host_mod.meta")
    + ccpp_host_from_meta("examples/capgen/host_ftn/test_host.meta")
)

# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------


@ccpp_suite("ddt_suite", version="1.0")
class ddt_suite:
    data_prep = [make_ddt, environ_conditions]


@ccpp_suite("temp_suite", version="1.0")
class temp_suite:
    physics1 = [setup_coeffs, temp_set]
    physics2 = [temp_calc_adjust, temp_adjust]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # vmr_type DDT is passed via additional — it is not a scheme in any group
    # but must appear in the IR so the optimizer can resolve the type.
    emit_ir([ddt_suite, temp_suite], additional=[vmr_type, *host])
