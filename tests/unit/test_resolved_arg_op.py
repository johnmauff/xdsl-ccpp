"""Unit tests for ResolvedArgOp / ArgSourceKind.

These test the op/attribute definitions directly, independent of the
classification logic that constructs them. run_dispatch.py's
_build_per_suite_run_info (see test_run_dispatch.py) is what actually builds
these ops for each callee argument; this file covers verify()'s
required/forbidden-field rules per source_kind in isolation.
"""

import pytest
from xdsl.ir import VerifyException

from xdsl_ccpp.dialects.ccpp import CCPP, ArgSourceKind, ArgSourceKindAttr, ResolvedArgOp


# ---------------------------------------------------------------------------
# Dialect registration
# ---------------------------------------------------------------------------

class TestDialectRegistration:
    """ResolvedArgOp and ArgSourceKindAttr are registered on the ccpp dialect."""

    def test_op_registered(self):
        assert ResolvedArgOp in CCPP.operations

    def test_attr_registered(self):
        assert ArgSourceKindAttr in CCPP.attributes


# ---------------------------------------------------------------------------
# Construction + verify() -- one positive case per source_kind
# ---------------------------------------------------------------------------

class TestHostConstruction:
    """source_kind=Host: a host module variable accessed via USE."""

    def test_construct_and_verify(self):
        op = ResolvedArgOp(
            "temp", ArgSourceKind.Host, var_name="ps", module_name="test_host_mod"
        )
        op.verify()
        assert op.arg_name.data == "temp"
        assert op.source_kind.data == ArgSourceKind.Host
        assert op.var_name.data == "ps"
        assert op.module_name.data == "test_host_mod"
        assert op.member_path is None
        assert op.std_name is None

    def test_construct_from_string_kind(self):
        """source_kind also accepts the raw enum value string ('host')."""
        op = ResolvedArgOp("temp", "host", var_name="ps", module_name="test_host_mod")
        op.verify()
        assert op.source_kind.data == ArgSourceKind.Host


class TestDdtMemberConstruction:
    """source_kind=DdtMember: a member of a module-level DDT instance."""

    def test_construct_and_verify(self):
        op = ResolvedArgOp(
            "rad_temp",
            ArgSourceKind.DdtMember,
            var_name="phys_state",
            module_name="test_host_mod",
            member_path="rad%temp",
        )
        op.verify()
        assert op.source_kind.data == ArgSourceKind.DdtMember
        assert op.var_name.data == "phys_state"
        assert op.module_name.data == "test_host_mod"
        assert op.member_path.data == "rad%temp"
        assert op.std_name is None

    def test_construct_from_string_kind(self):
        """source_kind accepts the exact tag run_dispatch.py's ad hoc tuples
        use today ("ddt_member", not the auto()-squashed "ddtmember") --
        this is what lets Stage 2 convert those tuples without translation.
        """
        op = ResolvedArgOp(
            "rad_temp",
            "ddt_member",
            var_name="phys_state",
            module_name="test_host_mod",
            member_path="rad%temp",
        )
        op.verify()
        assert op.source_kind.data == ArgSourceKind.DdtMember


class TestCapVarConstruction:
    """source_kind=CapVar: a cap-owned module variable (e.g. a constituent)."""

    def test_construct_and_verify(self):
        op = ResolvedArgOp(
            "vmr", ArgSourceKind.CapVar, std_name="array_of_volume_mixing_ratios"
        )
        op.verify()
        assert op.source_kind.data == ArgSourceKind.CapVar
        assert op.std_name.data == "array_of_volume_mixing_ratios"
        assert op.var_name is None
        assert op.module_name is None
        assert op.member_path is None

    def test_construct_from_string_kind(self):
        """source_kind accepts the exact tag run_dispatch.py's ad hoc tuples
        use today ("cap_var", not the auto()-squashed "capvar").
        """
        op = ResolvedArgOp(
            "vmr", "cap_var", std_name="array_of_volume_mixing_ratios"
        )
        op.verify()
        assert op.source_kind.data == ArgSourceKind.CapVar


class TestBlockConstruction:
    """source_kind=Block: unresolved -- becomes a caller-supplied block argument."""

    def test_construct_and_verify(self):
        op = ResolvedArgOp("unmatched_arg", ArgSourceKind.Block)
        op.verify()
        assert op.source_kind.data == ArgSourceKind.Block
        assert op.var_name is None
        assert op.module_name is None
        assert op.member_path is None
        assert op.std_name is None


# ---------------------------------------------------------------------------
# verify() -- negative cases, one per required/forbidden-field violation
# ---------------------------------------------------------------------------

class TestVerifyRejectsInvalidCombinations:
    def test_host_missing_var_name(self):
        op = ResolvedArgOp("x", ArgSourceKind.Host, module_name="m")
        with pytest.raises(VerifyException, match="Host requires"):
            op.verify()

    def test_host_missing_module_name(self):
        op = ResolvedArgOp("x", ArgSourceKind.Host, var_name="v")
        with pytest.raises(VerifyException, match="Host requires"):
            op.verify()

    def test_host_with_member_path_rejected(self):
        """member_path is a DdtMember-only field; Host must not set it."""
        op = ResolvedArgOp(
            "x", ArgSourceKind.Host, var_name="v", module_name="m", member_path="p"
        )
        with pytest.raises(VerifyException, match="must not set"):
            op.verify()

    def test_ddt_member_missing_member_path(self):
        op = ResolvedArgOp(
            "x", ArgSourceKind.DdtMember, var_name="v", module_name="m"
        )
        with pytest.raises(VerifyException, match="DdtMember requires"):
            op.verify()

    def test_ddt_member_with_std_name_rejected(self):
        """std_name is a CapVar-only field; DdtMember must not set it."""
        op = ResolvedArgOp(
            "x", ArgSourceKind.DdtMember,
            var_name="v", module_name="m", member_path="p", std_name="s",
        )
        with pytest.raises(VerifyException, match="must not set"):
            op.verify()

    def test_cap_var_missing_std_name(self):
        op = ResolvedArgOp("x", ArgSourceKind.CapVar)
        with pytest.raises(VerifyException, match="CapVar requires"):
            op.verify()

    def test_cap_var_with_var_name_rejected(self):
        """var_name/module_name are Host/DdtMember-only fields; CapVar must not set them."""
        op = ResolvedArgOp(
            "x", ArgSourceKind.CapVar, std_name="s", var_name="v", module_name="m"
        )
        with pytest.raises(VerifyException, match="must not set"):
            op.verify()

    def test_block_with_any_payload_rejected(self):
        op = ResolvedArgOp("x", ArgSourceKind.Block, std_name="s")
        with pytest.raises(VerifyException, match="must not set"):
            op.verify()
