"""Tests that DDT arguments produce a clear error in the chost cap generator.

The C ABI only supports scalar primitives and pointers to them, so derived-type
(DDT) arguments cannot cross a BIND(C) boundary.  The chost generator must
raise an informative ValueError rather than silently producing a corrupt
interface.
"""

import pytest

from xdsl_ccpp.dialects.ccpp_utils import DerivedType
from xdsl_ccpp.transforms.ccpp_cap import _chost_arg_info


class TestChostDDTError:

    def test_derived_type_raises_value_error(self):
        """A DerivedType mtype raises ValueError, not silent corruption."""
        ddt = DerivedType("physics_state_type")
        with pytest.raises(ValueError, match="DDT arguments are not supported"):
            _chost_arg_info("phys_state", ddt, {}, {})

    def test_error_message_names_the_type(self):
        """The error message includes the DDT type name for easy diagnosis."""
        ddt = DerivedType("GFS_statein_type")
        with pytest.raises(ValueError, match="GFS_statein_type"):
            _chost_arg_info("statein", ddt, {}, {})

    def test_error_message_names_the_argument(self):
        """The error message includes the local argument name."""
        ddt = DerivedType("tracer_container")
        with pytest.raises(ValueError, match="tracers"):
            _chost_arg_info("tracers", ddt, {}, {})

    def test_error_message_names_the_standard_name(self):
        """The error message includes the standard_name when known."""
        ddt = DerivedType("physics_state_type")
        local_to_std = {"phys_state": "physics_state_ddt"}
        with pytest.raises(ValueError, match="physics_state_ddt"):
            _chost_arg_info("phys_state", ddt, local_to_std, {})

    def test_primitive_memref_still_works(self):
        """Scalar real args are unaffected by the DDT guard."""
        from xdsl.dialects.builtin import f64, MemRefType
        result = _chost_arg_info("dt", MemRefType(f64, []), {}, {})
        assert result["is_real"] is True
        assert result["rank"] == 0
