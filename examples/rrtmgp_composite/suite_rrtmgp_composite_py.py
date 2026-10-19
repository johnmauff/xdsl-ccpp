"""Composite-scheme version of suite_rrtmgp.xml.

What this file is
-----------------
The suite itself: what a CAM-SIMA physics configuration author writes.  It
calls CAM's radiation adapter (cam_rrtmgp_adapter.py), which calls the
exchangeable RRTMGP package (rrtmgp_package.py).  It produces exactly the
same suite as atmospheric_physics' flat suite_rrtmgp.xml (verified by
comparing the generator's input for both).

How this reduces the complexity CCPP exposes
--------------------------------------------
suite_rrtmgp.xml lists 40 scheme entries and 2 loops; its author must know
every RRTMGP and CAM radiation scheme and their exact order.  Here the suite
author writes two calls and needs to know only that ``cam_rrtmgp()`` means
"CAM's radiation".  The detail still exists, but it is layered: RRTMGP's
internal order lives in the package, CAM's radiation policy in the adapter,
and the physics configuration here.  Each layer is read and changed on its
own, and none of the three contains a file path.

Like an XML suite, this file names schemes only; their metadata comes from
the command line:

    python3 examples/rrtmgp_composite/suite_rrtmgp_composite_py.py --legacy-mode \\
        --scheme-files=<the .meta files under examples/rrtmgp_composite/meta>
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_ref, ccpp_suite, export_suite

from cam_rrtmgp_adapter import cam_rrtmgp

# Test-only scheme from atmospheric_physics' test suite: sets the constituent
# values a standalone radiation test needs.  Part of the suite, not of the
# radiation package or the adapter.
initialize_constituents = ccpp_scheme_ref("initialize_constituents")


@ccpp_suite("rrtmgp", version="1.0")
class rrtmgp:
    def physics_after_coupler():
        initialize_constituents()
        cam_rrtmgp()


if __name__ == "__main__":
    export_suite(rrtmgp)
