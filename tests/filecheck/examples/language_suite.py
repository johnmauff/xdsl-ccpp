"""Minimal suite fixture for scheme language filecheck tests.

Emits IR for a two-scheme suite where one scheme is Fortran (default) and
the other is C++.  Used by tests/filecheck/examples/frontend/language-py.mlir
and tests/filecheck/examples/completed_ir/language-py.mlir.
"""
from xdsl_ccpp.frontend.py_api import Arg, SchemeDescriptor, ccpp_suite, emit_ir


fortran_scheme = SchemeDescriptor(
    "tiny_fortran_scheme",
    {
        "run": [
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
    },
)

cxx_scheme = SchemeDescriptor(
    "tiny_cxx_scheme",
    {
        "run": [
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
    },
    language="c++",
)


@ccpp_suite("tiny_suite", version="1.0")
class tiny_suite:
    physics = [fortran_scheme, cxx_scheme]


if __name__ == "__main__":
    emit_ir(tiny_suite)
