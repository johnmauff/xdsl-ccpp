"""Python equivalent of ddt_suite.xml + make_ddt.meta + environ_conditions.meta.

Run to emit MLIR IR:
    python3 examples/ddthost/ddthost_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/ddthost/ddthost_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn

Note: the vmr_type DDT is passed via ``additional`` to emit_ir, mirroring
how make_ddt.meta contains both the DDT and scheme definitions.
"""

from xdsl_ccpp.frontend.py_api import Arg, ccpp_ddt, ccpp_scheme, ccpp_suite, emit_ir

# ---------------------------------------------------------------------------
# Shared standard arguments
# ---------------------------------------------------------------------------

errmsg = Arg(
    "errmsg",
    standard_name="ccpp_error_message",
    long_name="Error message for error handling in CCPP",
    type="character",
    kind="len=512",
    intent="out",
    units="none",
)

errflg = Arg(
    "errflg",
    standard_name="ccpp_error_code",
    long_name="Error flag for error handling in CCPP",
    type="integer",
    intent="out",
    units="1",
)

# ---------------------------------------------------------------------------
# vmr_type DDT  (from make_ddt.meta, first [ccpp-table-properties] block)
# ---------------------------------------------------------------------------


@ccpp_ddt
class vmr_type:
    vmr_type = [
        Arg(
            "nvmr",
            standard_name="number_of_chemical_species",
            type="integer",
            units="count",
        ),
        Arg(
            "vmr_array",
            standard_name="array_of_volume_mixing_ratios",
            type="real",
            kind="kind_phys",
            units="ppmv",
            dimensions=("horizontal_dimension", "number_of_chemical_species"),
        ),
    ]


# ---------------------------------------------------------------------------
# make_ddt scheme  (from make_ddt.meta, second [ccpp-table-properties] block)
# ---------------------------------------------------------------------------


@ccpp_scheme
class make_ddt:
    run = [
        Arg(
            "cols",
            standard_name="horizontal_loop_begin",
            type="integer",
            units="count",
            intent="in",
        ),
        Arg(
            "cole",
            standard_name="horizontal_loop_end",
            type="integer",
            units="count",
            intent="in",
        ),
        Arg(
            "O3",
            standard_name="ozone",
            type="real",
            kind="kind_phys",
            intent="in",
            units="ppmv",
            dimensions=("horizontal_loop_extent",),
        ),
        Arg(
            "HNO3",
            standard_name="nitric_acid",
            type="real",
            kind="kind_phys",
            intent="in",
            units="ppmv",
            dimensions=("horizontal_loop_extent",),
        ),
        Arg(
            "vmr",
            standard_name="volume_mixing_ratio_ddt",
            type="vmr_type",
            intent="inout",
            units="",
        ),
        errmsg,
        errflg,
    ]
    init = [
        Arg(
            "nbox",
            standard_name="horizontal_dimension",
            type="integer",
            units="count",
            intent="in",
        ),
        Arg(
            "ccpp_info",
            standard_name="host_standard_ccpp_type",
            type="ccpp_info_t",
            intent="in",
            units="",
        ),
        Arg(
            "vmr",
            standard_name="volume_mixing_ratio_ddt",
            type="vmr_type",
            intent="out",
            units="",
        ),
        errmsg,
        errflg,
    ]
    timestep_final = [
        Arg(
            "ncols",
            standard_name="horizontal_dimension",
            type="integer",
            units="count",
            intent="in",
        ),
        Arg(
            "vmr",
            standard_name="volume_mixing_ratio_ddt",
            type="vmr_type",
            intent="in",
            units="",
        ),
        errmsg,
        errflg,
    ]


# ---------------------------------------------------------------------------
# environ_conditions scheme
# ---------------------------------------------------------------------------


@ccpp_scheme
class environ_conditions:
    run = [
        Arg(
            "psurf",
            standard_name="surface_air_pressure",
            type="real",
            kind="kind_phys",
            intent="in",
            units="Pa",
            dimensions=("horizontal_loop_extent",),
        ),
        errmsg,
        errflg,
    ]
    init = [
        Arg(
            "nbox",
            standard_name="horizontal_dimension",
            type="integer",
            units="count",
            intent="in",
        ),
        Arg(
            "o3",
            standard_name="ozone",
            type="real",
            kind="kind_phys",
            intent="out",
            units="ppmv",
            dimensions=("horizontal_dimension",),
        ),
        Arg(
            "hno3",
            standard_name="nitric_acid",
            type="real",
            kind="kind_phys",
            intent="out",
            units="ppmv",
            dimensions=("horizontal_dimension",),
        ),
        Arg(
            "ntimes",
            standard_name="number_of_model_times",
            type="integer",
            units="count",
            intent="out",
        ),
        Arg(
            "model_times",
            standard_name="model_times",
            type="integer",
            intent="out",
            units="seconds",
            dimensions=("number_of_model_times",),
        ),
        errmsg,
        errflg,
    ]
    finalize = [
        Arg(
            "ntimes",
            standard_name="number_of_model_times",
            type="integer",
            units="count",
            intent="in",
        ),
        Arg(
            "model_times",
            standard_name="model_times",
            type="integer",
            intent="in",
            units="seconds",
            dimensions=("number_of_model_times",),
        ),
        errmsg,
        errflg,
    ]


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("ddt_suite", version="1.0")
class ddt_suite:
    data_prep = [make_ddt, environ_conditions]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # vmr_type DDT is passed separately — it is not a scheme in any group but
    # must appear in the IR so the optimizer can resolve the type.
    emit_ir(ddt_suite, additional=[vmr_type])
