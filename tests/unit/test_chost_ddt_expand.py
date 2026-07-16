"""Unit tests for _chost_expand_ddt_arg covering non-vertical array dimensions.

The vmr_type DDT (from the ddthost example) has:
  nvmr       -- integer scalar, standard_name = number_of_chemical_species
  vmr_array  -- real 2-D array, dimensions = (horizontal_dimension, number_of_chemical_species)

The second dimension is NOT a vertical dimension, so the old code left dim_nz=None
and fell back to the global nz_var.  The fix looks up the dimension standard_name in
the DDT's own scalar members to resolve dim_nz = "vmr_nvmr".
"""

import pytest

from xdsl_ccpp.transforms.ccpp_cap import _chost_expand_ddt_arg
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPTableProperties,
    CCPPArgumentTable,
    CCPPArgument,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal meta_data dicts
# ---------------------------------------------------------------------------

def _make_arg(name, **attrs):
    arg = CCPPArgument(name)
    for k, v in attrs.items():
        arg.setAttr(k, v)
    return arg


def _make_arg_table(name, args):
    tbl = CCPPArgumentTable()
    tbl.setAttr("name", name)
    tbl.setAttr("type", "ddt")
    for arg in args:
        tbl.setFunctionArgument(arg)
    return tbl


def _make_vmr_meta_data():
    """Return a minimal meta_data dict for vmr_type (non-vertical second dim)."""
    nvmr = _make_arg(
        "nvmr",
        standard_name="number_of_chemical_species",
        units="count",
        dimensions=0,
        dim_names=[],
        type="integer",
    )
    vmr_array = _make_arg(
        "vmr_array",
        standard_name="array_of_volume_mixing_ratios",
        units="ppmv",
        dimensions=2,
        dim_names=["horizontal_dimension", "number_of_chemical_species"],
        type="real",
        kind="kind_phys",
    )
    arg_table = _make_arg_table("vmr_type", [nvmr, vmr_array])

    props = CCPPTableProperties()
    props.setAttr("name", "vmr_type")
    props.setAttr("type", "ddt")
    props.arg_tables["vmr_type"] = arg_table

    return {"vmr_type": props}


def _make_tiny_state_meta_data():
    """Return a minimal meta_data dict for tiny_state_t (vertical second dim)."""
    nz_arg = _make_arg(
        "nz",
        standard_name="vertical_layer_dimension",
        units="count",
        dimensions=0,
        dim_names=[],
        type="integer",
    )
    temp = _make_arg(
        "temp",
        standard_name="air_temperature",
        units="K",
        dimensions=2,
        dim_names=["horizontal_dimension", "vertical_layer_dimension"],
        type="real",
        kind="kind_phys",
    )
    arg_table = _make_arg_table("tiny_state_t", [nz_arg, temp])

    props = CCPPTableProperties()
    props.setAttr("name", "tiny_state_t")
    props.setAttr("type", "ddt")
    props.arg_tables["tiny_state_t"] = arg_table

    return {"tiny_state_t": props}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChostExpandDDTNonVertical:
    """_chost_expand_ddt_arg with a non-vertical second dimension (vmr_type)."""

    def _expand(self, **kwargs):
        meta_data = _make_vmr_meta_data()
        defaults = dict(
            prefix="vmr",
            ddt_type_name="vmr_type",
            meta_data=meta_data,
            local_to_std={},
            std_to_host={},
            kind_iso_map={"kind_phys": "REAL64"},
            ncol_var="ncol",
            nz_var="nz",
        )
        defaults.update(kwargs)
        return _chost_expand_ddt_arg(**defaults)

    def test_vmr_array_dim_nz_resolved_to_flat_scalar(self):
        """vmr_vmr_array must have dim_nz='vmr_nvmr', not None or the global nz_var."""
        member_ais, _ = self._expand()
        arr = next(ai for ai in member_ais if ai["bare"] == "vmr_vmr_array")
        assert arr["dim_nz"] == "vmr_nvmr"

    def test_vmr_nvmr_is_not_is_nz(self):
        """nvmr is not a vertical dimension — is_nz must remain False."""
        member_ais, _ = self._expand()
        nvmr = next(ai for ai in member_ais if ai["bare"] == "vmr_nvmr")
        assert nvmr["is_nz"] is False

    def test_vmr_nvmr_is_dim_scalar(self):
        """nvmr dimensions vmr_array so it must be flagged is_dim_scalar."""
        member_ais, _ = self._expand()
        nvmr = next(ai for ai in member_ais if ai["bare"] == "vmr_nvmr")
        assert nvmr["is_dim_scalar"] is True

    def test_vmr_array_is_not_dim_scalar(self):
        """The array member itself must not be flagged is_dim_scalar."""
        member_ais, _ = self._expand()
        arr = next(ai for ai in member_ais if ai["bare"] == "vmr_vmr_array")
        assert not arr.get("is_dim_scalar")

    def test_vmr_nvmr_intent_in(self):
        """Scalar integer DDT members must have intent='in'."""
        member_ais, _ = self._expand()
        nvmr = next(ai for ai in member_ais if ai["bare"] == "vmr_nvmr")
        assert nvmr["intent"] == "in"

    def test_vmr_array_intent_inout(self):
        """Array members inherit the original_intent of the DDT arg."""
        member_ais, _ = self._expand(original_intent="inout")
        arr = next(ai for ai in member_ais if ai["bare"] == "vmr_vmr_array")
        assert arr["intent"] == "inout"

    def test_vmr_array_intent_in(self):
        """intent=in DDTs produce array members with intent='in'."""
        member_ais, _ = self._expand(original_intent="in")
        arr = next(ai for ai in member_ais if ai["bare"] == "vmr_vmr_array")
        assert arr["intent"] == "in"

    def test_dim_nz_not_global_nz_var(self):
        """dim_nz must not fall back to the global nz_var."""
        member_ais, _ = self._expand()
        arr = next(ai for ai in member_ais if ai["bare"] == "vmr_vmr_array")
        assert arr["dim_nz"] != "nz"


class TestChostExpandDDTVertical:
    """_chost_expand_ddt_arg with a standard vertical second dimension (tiny_state_t)."""

    def _expand(self, **kwargs):
        meta_data = _make_tiny_state_meta_data()
        defaults = dict(
            prefix="state",
            ddt_type_name="tiny_state_t",
            meta_data=meta_data,
            local_to_std={},
            std_to_host={},
            kind_iso_map={"kind_phys": "REAL64"},
            ncol_var="ncol",
            nz_var="nz",
        )
        defaults.update(kwargs)
        return _chost_expand_ddt_arg(**defaults)

    def test_temp_dim_nz_resolved_to_flat_nz(self):
        """Vertical arrays must have dim_nz resolved to the flattened nz name."""
        member_ais, _ = self._expand()
        arr = next(ai for ai in member_ais if ai["bare"] == "state_temp")
        assert arr["dim_nz"] == "state_nz"

    def test_nz_is_nz(self):
        """The vertical dimension scalar must have is_nz=True."""
        member_ais, _ = self._expand()
        nz = next(ai for ai in member_ais if ai["bare"] == "state_nz")
        assert nz["is_nz"] is True

    def test_nz_is_not_dim_scalar(self):
        """A vertical dimension scalar must not be flagged is_dim_scalar."""
        member_ais, _ = self._expand()
        nz = next(ai for ai in member_ais if ai["bare"] == "state_nz")
        assert not nz.get("is_dim_scalar")

    def test_temp_is_not_dim_scalar(self):
        """Array members must never be flagged is_dim_scalar."""
        member_ais, _ = self._expand()
        arr = next(ai for ai in member_ais if ai["bare"] == "state_temp")
        assert not arr.get("is_dim_scalar")
