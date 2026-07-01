"""Minimal suite + host fixture for array_layout filecheck tests.

Emits IR for a single-scheme suite paired with a row_major host module.
Used by tests/filecheck/examples/frontend/array-layout-py.mlir and
tests/filecheck/examples/completed_ir/array-layout-py.mlir.
"""
from xdsl_ccpp.frontend.py_api import Arg, TableDescriptor, ccpp_scheme, ccpp_suite, emit_ir


@ccpp_scheme
class tiny_scheme:
    run = [
        Arg("ncol",   standard_name="horizontal_loop_extent",
            type="integer", units="count",     intent="in"),
        Arg("nz",     standard_name="vertical_layer_dimension",
            type="integer", units="count",     intent="in"),
        Arg("temp",   standard_name="air_temperature",
            type="real",    kind="kind_phys",  units="K",
            dimensions=("horizontal_loop_extent",), intent="inout"),
        Arg("theta",  standard_name="air_potential_temperature",
            type="real",    kind="kind_phys",  units="K",
            dimensions=("horizontal_loop_extent", "vertical_layer_dimension"),
            intent="inout"),
        Arg("errmsg", standard_name="ccpp_error_message",
            type="character", kind="len=512",  units="none", intent="out"),
        Arg("errflg", standard_name="ccpp_error_code",
            type="integer", units="1",         intent="out"),
    ]


@ccpp_suite("tiny_suite", version="1.0")
class tiny_suite:
    physics = [tiny_scheme]


# Host module declared as row_major — the feature under test.
host = TableDescriptor(
    "tiny_host_mod",
    "module",
    {"tiny_host_mod": [
        Arg("ncols",       standard_name="horizontal_dimension",
            type="integer", units="count", intent="in"),
        Arg("nz_total",    standard_name="vertical_layer_dimension",
            type="integer", units="count", intent="in"),
        Arg("temperature", standard_name="air_temperature",
            type="real", kind="kind_phys", units="K",
            dimensions=("horizontal_dimension",), intent="inout"),
        Arg("theta",       standard_name="air_potential_temperature",
            type="real", kind="kind_phys", units="K",
            dimensions=("horizontal_dimension", "vertical_layer_dimension"),
            intent="inout"),
    ]},
    array_layout="row_major",
)


# HOST-type table providing col_start/col_end with standard names so the
# host cap knows their standard names and can use them in RESHAPE dim_exprs.
host_sub = TableDescriptor(
    "tiny_host_sub",
    "host",
    {"tiny_host_sub": [
        Arg("col_start", standard_name="horizontal_loop_begin",
            type="integer", units="count", intent="in"),
        Arg("col_end",   standard_name="horizontal_loop_end",
            type="integer", units="count", intent="in"),
    ]},
)


if __name__ == "__main__":
    emit_ir(tiny_suite, additional=[host, host_sub])
