"""Unit tests for the C++/chost interop fix to PR #73's Copilot review comment:

`ccpp.KindOp.kind_value` is no longer guaranteed to be an ISO_FORTRAN_ENV
constant once metadata `kind_spec` resolves a kind to an arbitrary module
spec (e.g. `temp_r8`). `cpp_interop.py`'s `_real_width_from_iso` and
`print_cpp_header.py`'s `_emit_kinds_header` previously assumed ISO always,
silently defaulting to 64-bit/`double` for anything else -- a real,
silent-wrong-layout risk across the C++/BIND(C) boundary. Both now check
`kind_module` and raise instead of guessing.
"""

from io import StringIO

import pytest
from xdsl.dialects.builtin import ModuleOp

from xdsl_ccpp.backend.print_cpp_header import _emit_kinds_header
from xdsl_ccpp.dialects.ccpp_utils import KindDefOp
from xdsl_ccpp.transforms.cpp_interop import _real_width_from_iso


class TestRealWidthFromIso:
    def test_iso_real32(self):
        assert _real_width_from_iso("kind_dyn", ("REAL32", "iso_fortran_env")) == 32

    def test_iso_real64(self):
        assert _real_width_from_iso("kind_phys", ("REAL64", "iso_fortran_env")) == 64

    def test_unseen_kind_defaults_to_64(self):
        """No entry at all (kind never reached _chost_kind_iso_map) -- same
        fallback as before this fix, unrelated to kind_spec."""
        assert _real_width_from_iso("kind_phys", None) == 64

    def test_kind_spec_resolved_kind_raises(self):
        """A kind resolved via a real host/scheme module (not
        iso_fortran_env) has no derivable width -- must raise, not guess."""
        with pytest.raises(ValueError, match="kind_temp.*temp_kinds:temp_r8"):
            _real_width_from_iso("kind_temp", ("temp_r8", "temp_kinds"))


class TestEmitKindsHeader:
    def test_iso_kind_emits_typedef(self):
        module = ModuleOp([KindDefOp("kind_phys", "REAL64", "iso_fortran_env")])
        out = StringIO()
        _emit_kinds_header(module, out)
        assert "typedef double    kind_phys_t;" in out.getvalue()

    def test_kind_spec_resolved_kind_raises(self):
        module = ModuleOp([KindDefOp("kind_temp", "temp_r8", "temp_kinds")])
        out = StringIO()
        with pytest.raises(ValueError, match="kind_temp.*temp_kinds:temp_r8"):
            _emit_kinds_header(module, out)
