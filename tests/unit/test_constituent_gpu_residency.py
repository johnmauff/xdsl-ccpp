"""initialize_constituents makes the constituent arrays and GPU scratch
arrays device-resident with AccEnterDataOp copyins (raw-fortran-in-ir), not
raw `!$acc` text, so passes see the enter that balances the AccExitDataOp
ccpp_cap.py's _inject_capscratch_gpu_exit emits in ccpp_final. Both sides
reference a multi-instance cap's arrays through lc_instances(instance).
"""

from io import StringIO

import pytest
from xdsl.dialects import builtin, func
from xdsl.dialects.builtin import DYNAMIC_INDEX, ArrayAttr, MemRefType, i8, i32
from xdsl.ir import Block, Region

from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.dialects.ccpp_utils import (
    AccEnterDataOp,
    HostVarRefOp,
)
from xdsl_ccpp.transforms.ccpp_cap import _inject_capscratch_gpu_exit
from xdsl_ccpp.transforms.constituent_cap import _generate_constituent_api
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_VERT_DIM_STD_NAME,
    SUITE_ARG_NAME,
    arg_attr_dict,
)

_RESIDENT = {"lc_constituent_array": True, "lc_const_tend": True}
# (lc_name, rank, alloc_dims, const_std_name, needs_gpu, base)
_SCRATCH = [("lc_scratch", 2, (CCPP_HORIZ_DIM_STD_NAME, CCPP_VERT_DIM_STD_NAME), None, True, None)]


def _init_fn(**kwargs) -> func.FuncOp:
    _, api_op, _ = _generate_constituent_api(
        "TestHost", [], [], scratch_vars=_SCRATCH,
        framework_var_residency=_RESIDENT, needs_const_tend=True, **kwargs,
    )
    return next(
        op for op in api_op.walk()
        if isinstance(op, func.FuncOp)
        and op.sym_name.data.endswith("_ccpp_initialize_constituents")
    )


def _entered(fn) -> list[str]:
    """Names of the arrays the function's AccEnterDataOps copy in."""
    names = []
    for op in fn.walk():
        if isinstance(op, AccEnterDataOp):
            for v in op.copyin_arrays:
                ref = v.owner
                assert isinstance(ref, HostVarRefOp)
                member = ref.attributes.get("member_name")
                names.append(member.data if member is not None else ref.var_name.data)
    return names


def _printed(fn) -> str:
    out = StringIO()
    ftnPrintContext(output=out).print_op(fn)
    return out.getvalue()


def test_residency_is_ops_not_raw_text():
    fn = _init_fn()
    assert _entered(fn) == ["lc_constituent_array", "lc_const_tend", "lc_scratch"]
    assert "!$acc" not in str(fn)  # no directive text in the IR


def test_printed_directives():
    text = _printed(_init_fn())
    for name in ("lc_constituent_array", "lc_const_tend", "lc_scratch"):
        assert f"!$acc enter data copyin({name})" in text
    assert text.count("#ifdef USE_GPU") == 3


def test_multi_instance_directives_reach_the_instance_component():
    fn = _init_fn(instance_local_name="instance", ninstances_local_name="ninstances")
    text = _printed(fn)
    for name in ("lc_constituent_array", "lc_const_tend", "lc_scratch"):
        assert f"!$acc enter data copyin(lc_instances(instance)%{name})" in text


def _final_fn(arg_names: list) -> func.FuncOp:
    types = [MemRefType(i8, [DYNAMIC_INDEX])] + [MemRefType(i32, [])] * (len(arg_names) - 1)
    block = Block(arg_types=types)
    for arg, name in zip(block.args, arg_names):
        arg.name_hint = name
    block.add_op(func.ReturnOp())
    return func.FuncOp(
        "ccpp_final", builtin.FunctionType.from_lists(types, []), Region(block),
        arg_attrs=ArrayAttr([arg_attr_dict({SUITE_ARG_NAME: n}) for n in arg_names]),
    )


def _exits(fn, **kwargs) -> str:
    _inject_capscratch_gpu_exit([fn], "ccpp_final", _RESIDENT, _SCRATCH, **kwargs)
    return _printed(fn)


def test_exit_data_single_instance():
    text = _exits(_final_fn(["suite_name"]))
    for name in ("lc_constituent_array", "lc_const_tend", "lc_scratch"):
        assert f"!$acc exit data delete({name})" in text


def test_exit_data_reaches_the_instance_component():
    text = _exits(_final_fn(["suite_name", "instance", "ninstances"]),
                  instance_local_name="instance")
    for name in ("lc_constituent_array", "lc_const_tend", "lc_scratch"):
        assert f"!$acc exit data delete(lc_instances(instance)%{name})" in text


def test_exit_data_needs_the_instance_argument():
    with pytest.raises(ValueError, match="no 'instance' argument"):
        _exits(_final_fn(["suite_name"]), instance_local_name="instance")
