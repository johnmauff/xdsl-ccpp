"""Composite-scheme version of examples/helloworld/helloworld_py.py.

Same suite, IR and Fortran, written with a package function (hello_package),
a slot (greet), a hook (adjust) and a group function.  Schemes are referenced
by name only, like an XML suite; their metadata (here the !$ccpp-tagged
sources in this directory) and the host metadata come from the command line:

    python3 examples/helloworld_composite/helloworld_composite_py.py \
        --scheme-files=examples/helloworld_composite/hello_scheme.F90,examples/helloworld_composite/temp_adjust.F90 \
        --host-files=examples/helloworld_composite/hello_world_host.meta,examples/helloworld_composite/hello_world_mod.meta \
        [hello_repeats=N]
"""

from xdsl_ccpp.frontend.py_api import (
    ccpp_param,
    ccpp_scheme_ref,
    ccpp_suite,
    export_suite,
)

# ---------------------------------------------------------------------------
# Schemes (by name; metadata supplied on the command line)
# ---------------------------------------------------------------------------

hello_scheme = ccpp_scheme_ref("hello_scheme")
temp_adjust  = ccpp_scheme_ref("temp_adjust")

hello_repeats = ccpp_param("hello_repeats", default=1)

# ---------------------------------------------------------------------------
# Package: schemes composed by an ordinary Python function
# ---------------------------------------------------------------------------


def hello_package(*, adjust, greet=hello_scheme):
    """Greet hello_repeats times (slot ``greet``), then adjust (hook ``adjust``)."""
    for _ in range(hello_repeats):
        greet()
    adjust()


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("hello_world_suite", version="1.0")
class hello_world:
    def physics():
        hello_package(adjust=temp_adjust)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    export_suite(hello_world)
