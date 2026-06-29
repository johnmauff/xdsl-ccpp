"""Python suite definition for the ddthost example — loads metadata from .meta files.

Covers both suites (ddt_suite and temp_suite) using ccpp_scheme_from_meta and
ccpp_ddt_from_meta, keeping the .meta files as the single source of truth.
For the inline Python equivalent of ddt_suite only, see ddthost_py.py.

Run to emit MLIR IR:
    python3 examples/ddthost/ddthost_meta_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/ddthost/ddthost_meta_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Note: make_ddt.meta contains two [ccpp-table-properties] blocks — the vmr_type
DDT definition and the make_ddt scheme.  ccpp_ddt_from_meta extracts the DDT
and ccpp_scheme_from_meta extracts the scheme from the same file.
host_ccpp_ddt.meta defines the ccpp_info_t DDT used by make_ddt_init.
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
vmr_type           = ccpp_ddt_from_meta("examples/ddthost/make_ddt.meta")
make_ddt           = ccpp_scheme_from_meta("examples/ddthost/make_ddt.meta")

environ_conditions = ccpp_scheme_from_meta("examples/ddthost/environ_conditions.meta")
setup_coeffs       = ccpp_scheme_from_meta("examples/ddthost/setup_coeffs.meta")
temp_set           = ccpp_scheme_from_meta("examples/ddthost/temp_set.meta")
temp_calc_adjust   = ccpp_scheme_from_meta("examples/ddthost/temp_calc_adjust.meta")
temp_adjust        = ccpp_scheme_from_meta("examples/ddthost/temp_adjust.meta")

# ---------------------------------------------------------------------------
# Host metadata (includes ccpp_info_t DDT used by make_ddt_init)
# ---------------------------------------------------------------------------

# host_ccpp_ddt.meta defines the ccpp_info_t DDT referenced by make_ddt_init
ccpp_info_t = ccpp_ddt_from_meta("examples/ddthost/host_ccpp_ddt.meta")

host = (
    ccpp_host_from_meta("examples/ddthost/test_host_data.meta")
    + ccpp_host_from_meta("examples/ddthost/test_host_mod.meta")
    + ccpp_host_from_meta("examples/ddthost/test_host.meta")
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
    # vmr_type and ccpp_info_t DDTs are passed via additional — they are not
    # schemes in any group but must appear in the IR for type resolution.
    emit_ir([ddt_suite, temp_suite], additional=[vmr_type, ccpp_info_t, *host])
