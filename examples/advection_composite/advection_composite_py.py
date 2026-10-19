"""Composite-scheme version of examples/advection's cld_suite.xml.

Same suite and generated caps, written with a process-update combinator:
``process(scheme)`` runs a process and then applies its constituent
tendencies -- the pattern cld_suite.xml spells out by repeating
``apply_constituent_tendencies``.  Schemes are referenced by name; their
metadata comes from SCHEMEFILES/HOSTFILES (see CMakeLists.txt), as for
an XML suite.
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_ref, ccpp_suite, export_suite

const_indices                = ccpp_scheme_ref("const_indices")
cld_liq                      = ccpp_scheme_ref("cld_liq")
cld_ice                      = ccpp_scheme_ref("cld_ice")
cld_shadow                   = ccpp_scheme_ref("cld_shadow")
apply_constituent_tendencies = ccpp_scheme_ref("apply_constituent_tendencies")


def process(scheme):
    """Run *scheme*, then apply the constituent tendencies it produced."""
    scheme()
    apply_constituent_tendencies()


@ccpp_suite("cld_suite", version="1.0")
class cld_suite:
    def physics():
        const_indices()
        process(cld_liq)
        process(cld_ice)
        cld_shadow()


if __name__ == "__main__":
    export_suite(cld_suite)
