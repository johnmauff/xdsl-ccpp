"""The transformed IR carries no Fortran or C++ text (fortran-exprs-as-text,
cpp-text-in-ir, active-condition-ir): scan the completed_ir FileCheck
goldens -- the IR every example's pipeline produces before printing -- and
the IR of a C++-host example (constadv; no golden covers the C++ host cap),
and check that the properties naming a variable, member, method or kind
hold plain identifiers, and that the removed text properties are gone.
(VarRefExprOp's and HostVarRefOp's constructors also reject a
non-identifier name; this scan catches the other ops.)
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]

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
    "host_var_ref": ("var_name", "index_expr"),
}

# op -> the list properties whose elements must be identifiers.
_IDENTIFIER_LIST_PROPS = {
    "host_var_ref": ("member_path",),
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
    "cpp_call_statement": ("call_args",),
    "cpp_brace_init_call": ("field_values",),
    "cpp_field_decl": ("cpp_type", "array_suffix", "init_expr"),
    "active_check": ("condition_expr",),
    "host_var_ref": ("member_name",),
}

# C++ ops whose types must be MLIR types, not strings.
_TYPED_PROPS = {
    "cpp_field_decl": ("field_type",),
    "c_function_sig": ("return_type", "param_types"),
    "cpp_constructor": ("param_types",),
    "local_var": ("var_type",),
}

_OP = re.compile(r'"ccpp_utils\.([a-z_]+)"')
# Properties, then (HostVarRefOp's index_expr) the attribute dictionary.
_PROPS = re.compile(r"<\{(.*?)\}>(?: \{(.*?)\})?")
_STRING_PROP = re.compile(r'([A-Za-z_][\w]*) = "((?:[^"\\]|\\.)*)"')


def _ops_with_props(path: Path):
    """(op name, {property: string value}) for each op line in a golden."""
    for line in path.read_text().splitlines():
        op = _OP.search(line)
        props = _PROPS.search(line)
        if op and props:
            text = props.group(1) + ", " + (props.group(2) or "")
            yield op.group(1), dict(_STRING_PROP.findall(text))


def _list_props(line: str, key: str) -> "list[str] | None":
    """The string elements of a list property on an op line, or None."""
    m = re.search(rf"\b{key} = \[([^\]]*)\]", line)
    return None if m is None else re.findall(r'"([^"]*)"', m.group(1))


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
    for line in golden.read_text().splitlines():
        op = _OP.search(line)
        for key in _IDENTIFIER_LIST_PROPS.get(op.group(1) if op else "", ()):
            for value in _list_props(line, key) or ():
                if not _IDENTIFIER.match(value):
                    bad.append(f"{op.group(1)}.{key} element {value!r}")
    assert not bad, f"{golden.name}: expression text in IR names:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("golden", _GOLDENS, ids=lambda p: p.name)
def test_removed_text_properties_are_gone(golden):
    text = golden.read_text()
    bad = [
        f"{op}.{key}"
        for op, keys in _REMOVED_PROPS.items()
        for key in keys
        if re.search(rf'"ccpp_utils\.{op}"[^\n]*\b{key} = ', text)
    ]
    bad += ["bind_c_dim_exprs"] if "bind_c_dim_exprs" in text else []
    assert not bad, f"{golden.name}: removed text properties present: {bad}"


def test_the_scan_sees_the_ops():
    """Guard against a format change silently making the scan vacuous."""
    seen = {op for golden in _GOLDENS for op, _ in _ops_with_props(golden)}
    assert {"var_ref_expr", "member_access_expr", "cap_var_ref", "module_var",
            "ddt_method_call", "allocate", "lazy_alloc", "host_var_ref"} <= seen
    assert any('"ccpp_utils.active_check"' in golden.read_text() for golden in _GOLDENS)
    members = [
        _list_props(line, "member_path") for golden in _GOLDENS
        for line in golden.read_text().splitlines() if '"ccpp_utils.host_var_ref"' in line
    ]
    assert ["fluxSW", "sfc_down_sw"] in members


@pytest.fixture(scope="module")
def chost_ir(tmp_path_factory) -> Path:
    """The transformed IR of examples/constadv with a C++ host."""
    example = _REPO / "examples" / "constadv"
    meta = subprocess.run(
        [sys.executable, "-m", "xdsl_ccpp.frontend.ccpp_xml",
         "--suites", str(example / "constadv_suite.xml"),
         "--scheme-files", str(example / "constadv.meta"),
         "--host-files", ",".join(str(example / "host_cpp" / f) for f in (
             "constadv_host_mod.meta", "constadv_host_sub.meta"))],
        cwd=_REPO, capture_output=True, text=True, check=True,
    ).stdout
    passes = ("generate-meta-cap,generate-meta-kinds,generate-host-match,"
              "generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},"
              "generate-cpp-cap,generate-kinds,strip-ccpp")
    ir = subprocess.run(
        [sys.executable, "-m", "xdsl_ccpp.tools.ccpp_opt", "-p", passes, "-t", "mlir"],
        input=meta, cwd=_REPO, capture_output=True, text=True, check=True,
    ).stdout
    path = tmp_path_factory.mktemp("chost") / "constadv.mlir"
    path.write_text(ir)
    return path


def test_cpp_host_ir_has_no_text(chost_ir):
    seen = {op for op, _ in _ops_with_props(chost_ir)}
    assert {"c_function_sig", "cpp_field_decl", "local_var", "cpp_call_statement"} <= seen
    test_names_are_identifiers(chost_ir)
    test_removed_text_properties_are_gone(chost_ir)
    text = chost_ir.read_text()
    assert '"ccpp_utils.raw_cpp_lines"' not in text
    bad = []
    for line in text.splitlines():
        op = _OP.search(line)
        props = _PROPS.search(line)
        if not (op and props):
            continue
        for key in _TYPED_PROPS.get(op.group(1), ()):
            # A string-valued type, or a string element of a type list (a
            # derived type's quoted name is inside <...>, not an element).
            if re.search(rf'\b{key} = (\[([^\]]*?, )?)?"', props.group(1)):
                bad.append(f"{op.group(1)}.{key}")
    assert not bad, f"C++ types given as text: {bad}"
