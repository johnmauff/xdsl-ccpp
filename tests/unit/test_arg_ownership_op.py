"""Unit tests for ArgOwnershipOp / ArgOwnershipKind (Phase 7, Stage 1).

These test the op/attribute definitions directly, independent of the
classification logic that will construct them in a later Phase 7 stage.
Stage 1 is "define, don't wire" -- ArgOwnershipOp is not called by any pass
yet; this file covers verify()'s required/forbidden-field rules per
ownership_kind in isolation, the same way test_resolved_arg_op.py covers
ResolvedArgOp/ArgSourceKind (the Phase 3b precedent this mirrors).
"""

import pytest
from xdsl.ir import VerifyException

from xdsl_ccpp.dialects.ccpp import (
    CCPP,
    ArgOwnershipKind,
    ArgOwnershipKindAttr,
    ArgOwnershipOp,
)

# ---------------------------------------------------------------------------
# Dialect registration
# ---------------------------------------------------------------------------

class TestDialectRegistration:
    """ArgOwnershipOp and ArgOwnershipKindAttr are registered on the ccpp dialect."""

    def test_op_registered(self):
        assert ArgOwnershipOp in CCPP.operations

    def test_attr_registered(self):
        assert ArgOwnershipKindAttr in CCPP.attributes


# ---------------------------------------------------------------------------
# Construction + verify() -- one positive case per ownership_kind
# ---------------------------------------------------------------------------

class TestSuiteOwnedConstruction:
    """ownership_kind=SuiteOwned: interstitial, or advected/allocatable real
    array -- never a dummy arg on the suite's own subroutine signature."""

    def test_construct_and_verify(self):
        op = ArgOwnershipOp("to_promote", ArgOwnershipKind.SuiteOwned)
        op.verify()
        assert op.arg_name.data == "to_promote"
        assert op.ownership_kind.data == ArgOwnershipKind.SuiteOwned
        assert op.std_name is None

    def test_construct_from_string_kind(self):
        op = ArgOwnershipOp("to_promote", "suite_owned")
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.SuiteOwned


class TestHostMatchedConstruction:
    """ownership_kind=HostMatched: resolved against host metadata (module var
    or DDT member -- ArgSourceKind's finer Host/DdtMember split isn't needed
    at this ownership layer)."""

    def test_construct_and_verify(self):
        op = ArgOwnershipOp(
            "temp", ArgOwnershipKind.HostMatched, std_name="air_temperature"
        )
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.HostMatched
        assert op.std_name.data == "air_temperature"

    def test_construct_from_string_kind(self):
        op = ArgOwnershipOp("temp", "host_matched", std_name="air_temperature")
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.HostMatched


class TestCapScratchConstruction:
    """ownership_kind=CapScratch: no host match; promoted to a cap-owned
    module variable (framework array or host-less scheme scratch)."""

    def test_construct_and_verify(self):
        op = ArgOwnershipOp(
            "vmr", ArgOwnershipKind.CapScratch, std_name="array_of_volume_mixing_ratios"
        )
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.CapScratch
        assert op.std_name.data == "array_of_volume_mixing_ratios"

    def test_construct_from_string_kind(self):
        op = ArgOwnershipOp(
            "vmr", "cap_scratch", std_name="array_of_volume_mixing_ratios"
        )
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.CapScratch


class TestBlockConstruction:
    """ownership_kind=Block: genuinely unresolved -- becomes a
    caller-supplied block argument."""

    def test_construct_and_verify(self):
        op = ArgOwnershipOp("unmatched_arg", ArgOwnershipKind.Block)
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.Block
        assert op.std_name is None

    def test_construct_from_string_kind(self):
        op = ArgOwnershipOp("unmatched_arg", "block")
        op.verify()
        assert op.ownership_kind.data == ArgOwnershipKind.Block


# ---------------------------------------------------------------------------
# verify() -- negative cases, one per required/forbidden-field violation
# ---------------------------------------------------------------------------

class TestVerifyRejectsInvalidCombinations:
    def test_suite_owned_with_std_name_rejected(self):
        op = ArgOwnershipOp("x", ArgOwnershipKind.SuiteOwned, std_name="s")
        with pytest.raises(VerifyException, match="must not set"):
            op.verify()

    def test_host_matched_missing_std_name(self):
        op = ArgOwnershipOp("x", ArgOwnershipKind.HostMatched)
        with pytest.raises(VerifyException, match="requires std_name"):
            op.verify()

    def test_cap_scratch_missing_std_name(self):
        op = ArgOwnershipOp("x", ArgOwnershipKind.CapScratch)
        with pytest.raises(VerifyException, match="requires std_name"):
            op.verify()

    def test_block_with_std_name_rejected(self):
        op = ArgOwnershipOp("x", ArgOwnershipKind.Block, std_name="s")
        with pytest.raises(VerifyException, match="must not set"):
            op.verify()
