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
        Arg("temp",   standard_name="air_temperature",
            type="real",    kind="kind_phys",  units="K",
            dimensions=("horizontal_loop_extent",), intent="inout"),
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
        Arg("temperature", standard_name="air_temperature",
            type="real", kind="kind_phys", units="K",
            dimensions=("horizontal_dimension",), intent="inout"),
    ]},
    array_layout="row_major",
)


if __name__ == "__main__":
    emit_ir(tiny_suite, additional=[host])
