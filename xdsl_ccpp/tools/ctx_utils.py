"""Shared xDSL Context factory for xdsl_ccpp's CLI tools.

Extracted (complexity-audit Tier 2 finding, task #44) after the exact same
`_make_ctx()` -- register every standard dialect, then load CCPP/CCPPUtils
on top -- was found duplicated verbatim across 5 CLI tool scripts
(`ccpp_dsl.py`, `ccpp_validate_fir.py`, `ccpp_validate_source.py`,
`fir2meta.py`, `ccpp_datatable.py`). Confirmed identical at every site
(only one carried a docstring); a single shared factory means they can't
independently drift the way `fir2meta.py`'s own Flang invocation once did
(task #37).
"""

from __future__ import annotations

from xdsl.context import Context
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils


def make_ccpp_context() -> Context:
    """Build a Context with all standard + CCPP dialects loaded."""
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx
