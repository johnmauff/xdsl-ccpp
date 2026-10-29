"""The transformed IR carries no Fortran expression text (fortran-exprs-as-text):
scan the completed_ir FileCheck goldens -- the IR every example's pipeline
produces before printing -- and check that the properties naming a variable,
member, method or kind hold plain identifiers, and that the removed text
properties are gone.

Two known exceptions, tracked in BACKLOG.md as active-condition-ir:
ActiveCheckOp.condition_expr and HostVarRefOp.member_name, both expressions
copied from .meta files. VarRefExprOp's own constructor can't enforce an
identifier yet: the C++ cap still passes '&errflg' (cpp-text-in-ir).
"""

import re
from pathlib import Path

import pytest

_GOLDENS = sorted(
    (Path(__file__).parents[1] / "filecheck" / "examples" / "completed_ir").glob("*.mlir")
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INTEGER = re.compile(r"^[0-9]+$")

# op -> the properties that must be identifiers.
_IDENTIFIER_PROPS = {
    "var_ref_expr": ("var_name",),
    "member_access_expr": ("member",),
    "method_call_expr": ("method",),
    "ddt_method_call": ("method",),
    "cap_var_ref": ("var_name",),
    "allocate": ("var_name", "stat_var"),
    "safe_dealloc": ("var_name",),
    "nullify_pointer": ("var_name",),
    "zero_fill": ("var_name",),
    "pointer_assign": ("ptr_name",),
    "call_statement": ("callee",),
    "cam_direct_call": ("callee",),
    "do_loop": ("loop_var",),
    "lazy_alloc": ("var_name",),
    "module_var": ("var_name", "kind"),
    "ddt_component_decl": ("var_name", "kind"),
}

# Text-form properties this item removed; none may come back.
_REMOVED_PROPS = {
    "assign": ("lhs_expr", "rhs_expr"),
    "call_statement": ("call_args",),
    "ddt_method_call": ("obj_expr", "args", "kwargs"),
    "error_guard": ("condition",),
    "allocate": ("dims",),
    "pointer_assign": ("rhs_expr",),
    "cam_direct_call": ("call_args",),
    "cam_suite_dispatch": ("call_args_template",),
    "unit_convert": ("to_scheme_expr",),
    "unit_write_back": ("to_host_expr",),
    "lazy_alloc": ("kind_name", "init_value"),
    "module_var": ("init_value",),
    "ddt_component_decl": ("init_value",),
}

_OP = re.compile(r'"ccpp_utils\.([a-z_]+)"')
_PROPS = re.compile(r"<\{(.*?)\}>")
_STRING_PROP = re.compile(r'([A-Za-z_][\w]*) = "((?:[^"\\]|\\.)*)"')


def _ops_with_props(path: Path):
    """(op name, {property: string value}) for each op line in a golden."""
    for line in path.read_text().splitlines():
        op = _OP.search(line)
        props = _PROPS.search(line)
        if op and props:
            yield op.group(1), dict(_STRING_PROP.findall(props.group(1)))


@pytest.mark.parametrize("golden", _GOLDENS, ids=lambda p: p.name)
def test_names_are_identifiers(golden):
    bad = []
    for op, props in _ops_with_props(golden):
        for key in _IDENTIFIER_PROPS.get(op, ()):
            value = props.get(key)
            if value is None or _IDENTIFIER.match(value):
                continue
            if key == "kind" and _INTEGER.match(value) and op != "ddt_component_decl":
                continue  # an integer kind, e.g. real(kind=8)
            bad.append(f"{op}.{key} = {value!r}")
    assert not bad, f"{golden.name}: expression text in IR names:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("golden", _GOLDENS, ids=lambda p: p.name)
def test_removed_text_properties_are_gone(golden):
    text = golden.read_text()
    bad = [
        f"{op}.{key}"
        for op, keys in _REMOVED_PROPS.items()
        for key in keys
        if re.search(rf'"ccpp_utils\.{op}".*<\{{[^}}]*\b{key} = ', text)
    ]
    bad += ["bind_c_dim_exprs"] if "bind_c_dim_exprs" in text else []
    assert not bad, f"{golden.name}: removed text properties present: {bad}"


def test_the_scan_sees_the_ops():
    """Guard against a format change silently making the scan vacuous."""
    seen = {op for golden in _GOLDENS for op, _ in _ops_with_props(golden)}
    assert {"var_ref_expr", "member_access_expr", "cap_var_ref", "module_var",
            "ddt_method_call", "allocate", "lazy_alloc"} <= seen
