"""Composite-scheme version of examples/advection's cld_suite.xml.

Same suite and generated caps, written with a process-update combinator:
``process(scheme)`` runs a process and then applies its constituent
tendencies -- the pattern cld_suite.xml spells out by repeating
``apply_constituent_tendencies``.  The two cloud processes form a package,
``cloud_microphysics``, decorated ``@ccpp_composite`` so the generator's IR
records it as one ``ccpp.composite`` (flattened again before code
generation).  Schemes are referenced by name; their metadata comes from
SCHEMEFILES/HOSTFILES (see CMakeLists.txt), as for an XML suite.
"""

from xdsl_ccpp.frontend.py_api import (ccpp_composite, ccpp_scheme_ref, ccpp_suite,
                                       export_suite)

const_indices                = ccpp_scheme_ref("const_indices")
cld_liq                      = ccpp_scheme_ref("cld_liq")
cld_ice                      = ccpp_scheme_ref("cld_ice")
cld_shadow                   = ccpp_scheme_ref("cld_shadow")
apply_constituent_tendencies = ccpp_scheme_ref("apply_constituent_tendencies")


def process(scheme):
    """Run *scheme*, then apply the constituent tendencies it produced."""
    scheme()
    apply_constituent_tendencies()


@ccpp_composite
def cloud_microphysics(*, liquid=cld_liq, ice=cld_ice):   # SLOTS: liquid, ice
    """Cloud package: liquid then ice processes, each followed by its tendencies."""
    process(liquid)
    process(ice)


@ccpp_suite("cld_suite", version="1.0")
class cld_suite:
    def physics():
        const_indices()
        cloud_microphysics()
        cld_shadow()


if __name__ == "__main__":
    export_suite(cld_suite)
