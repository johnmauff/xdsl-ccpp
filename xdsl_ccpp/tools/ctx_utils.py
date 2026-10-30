"""Shared xDSL Context factory for xdsl_ccpp's CLI tools.

Register every standard dialect, then load CCPP/CCPPUtils on top -- one
shared factory, so the CLI tools that parse CCPP IR cannot drift apart.
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
