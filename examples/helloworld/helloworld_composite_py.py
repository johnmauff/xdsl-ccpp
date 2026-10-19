"""Composite-scheme version of the helloworld Python suite.

Same suite as ``helloworld_py.py`` -- and the same IR and Fortran, checked by
``tests/filecheck/examples/{frontend,end_to_end}/helloworld-composite-py.mlir``
against the exact CHECK lines of the ``helloworld-py`` tests -- but written
with composite-scheme Stage 1 features (see ``composite_scheme_plan.md``):

- ``hello_package`` is an ordinary Python function composing schemes (a
  "package"), called from a group function rather than listed in it;
- ``greet`` is a *slot*: a swappable component with a package default;
- ``adjust`` is a *hook*: a required keyword the caller must supply;
- ``def physics():`` is a group function (no ``physics = [...]`` list, no
  ``run()``).

Run to emit MLIR IR:
    python3 examples/helloworld/helloworld_composite_py.py

CLI override, as for helloworld_py.py:
    python3 examples/helloworld/helloworld_composite_py.py hello_repeats=3
"""

from xdsl_ccpp.frontend.py_api import (
    ccpp_param,
    ccpp_scheme_from_meta,
    ccpp_host_from_meta,
    ccpp_suite,
    emit_ir,
)

# ---------------------------------------------------------------------------
# Schemes and host metadata (identical to helloworld_py.py)
# ---------------------------------------------------------------------------

hello_scheme = ccpp_scheme_from_meta("examples/helloworld/hello_scheme.meta")
temp_adjust  = ccpp_scheme_from_meta("examples/helloworld/temp_adjust.meta")

host = (
    ccpp_host_from_meta("examples/helloworld/hello_world_host.meta")
    + ccpp_host_from_meta("examples/helloworld/hello_world_mod.meta")
)

hello_repeats = ccpp_param("hello_repeats", default=1)

# ---------------------------------------------------------------------------
# Package: schemes composed by an ordinary Python function
# ---------------------------------------------------------------------------


def hello_package(*, adjust, greet=hello_scheme):
    """Greet ``hello_repeats`` times, then adjust.

    ``greet`` is a slot (package default ``hello_scheme``); ``adjust`` is a
    hook the caller must supply.  The ``for`` loop is plain Python, unrolled
    at IR-generation time.
    """
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
    emit_ir(hello_world, additional=host)
