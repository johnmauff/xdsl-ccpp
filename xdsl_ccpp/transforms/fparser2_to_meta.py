"""fparser2_to_meta — Extract CCPP dialect metadata from Fortran source via fparser2.

Parallel to ``fir_to_meta`` but uses the pure-Python ``fparser`` library instead
of Flang.  No external tools required — ``pip install fparser`` is sufficient.

Information extracted:
- Argument names (from dummy argument list)
- Argument types (REAL, INTEGER, CHARACTER, LOGICAL, and derived types via ``TYPE(name)``)
- Array rank (from assumed-shape specs ``(:)`` or ``DIMENSION`` attribute)
- Intent (from INTENT attribute)
- Optional flag (from OPTIONAL attribute)

Information NOT available from Fortran source text (same gaps as fir_to_meta):
- ``standard_name`` / ``long_name``
- ``units``
- Kind name (only the kind token as written, not the resolved CCPP kind name)
"""

from __future__ import annotations

from collections import defaultdict

from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp

# Map Fortran intrinsic type names to CCPP type strings
_TYPE_MAP: dict[str, str] = {
    "real": "real",
    "integer": "integer",
    "character": "character",
    "logical": "logical",
    "complex": "complex",
}


def _fparser_available() -> bool:
    try:
        import fparser.two.Fortran2003  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_subroutines(
    f90_source: str,
) -> list[tuple[str, str, list[dict]]]:
    """Parse *f90_source* and return a list of (module_name, proc_name, args).

    Each element of *args* is a dict with keys:
    ``name``, ``type``, ``rank``, ``intent`` (or None), ``optional`` (bool),
    ``kind`` (str or None, for CHARACTER only: the length string).
    """
    import fparser.two.Fortran2003 as f03
    from fparser.two.parser import ParserFactory
    from fparser.two.utils import walk
    from fparser.common.readfortran import FortranStringReader

    ParserFactory().create(std="f2003")
    reader = FortranStringReader(f90_source)
    tree = f03.Program(reader)

    results = []

    for module in walk(tree, f03.Module):
        module_stmt = module.children[0]
        module_name = str(module_stmt.children[1]).lower()

        for sub in walk(module, f03.Subroutine_Subprogram):
            sub_stmt = sub.children[0]  # Subroutine_Stmt
            proc_name = str(sub_stmt.children[1]).lower()

            dummy_arg_list = sub_stmt.children[2]
            if dummy_arg_list is None:
                results.append((module_name, proc_name, []))
                continue

            # Dummy args are Name nodes inside Dummy_Arg_List, not Dummy_Arg instances
            dummy_names = {str(a).lower() for a in dummy_arg_list.items}

            # Build declaration map: arg_name → {type, rank, intent, optional, kind}
            decl_map: dict[str, dict] = {}

            for decl in walk(sub, f03.Type_Declaration_Stmt):
                type_spec = decl.children[0]
                attr_spec_list = decl.children[1]
                entity_decl_list = decl.children[2]

                # Base type
                base_type = "unknown"
                kind_str = None
                if isinstance(type_spec, f03.Declaration_Type_Spec):
                    # type(derived_type_name) — the CCPP type string IS the Fortran
                    # type name (e.g. type(vmr_type) → "vmr_type")
                    if str(type_spec.children[0]).upper() == "TYPE":
                        base_type = str(type_spec.children[1]).lower().strip()
                elif isinstance(type_spec, f03.Intrinsic_Type_Spec):
                    raw = str(type_spec.children[0]).lower()
                    base_type = _TYPE_MAP.get(raw, raw)
                    sel = type_spec.children[1]
                    if sel is not None:
                        raw_kind = str(sel).strip()
                        # Strip outer parentheses from Kind_Selector / Char_Selector
                        if raw_kind.startswith("(") and raw_kind.endswith(")"):
                            raw_kind = raw_kind[1:-1].strip()
                        if base_type != "character":
                            # For non-character types strip the optional "KIND =" prefix
                            if raw_kind.upper().startswith("KIND"):
                                raw_kind = raw_kind.split("=", 1)[1].strip()
                        kind_str = raw_kind.lower() if raw_kind else None

                # Intent and optional from attribute list
                intent_str: str | None = None
                is_optional = False
                dim_rank_from_attr = 0

                if attr_spec_list:
                    for attr in walk(attr_spec_list, f03.Attr_Spec):
                        if str(attr).upper() == "OPTIONAL":
                            is_optional = True
                    for attr in walk(attr_spec_list, f03.Intent_Attr_Spec):
                        intent_str = str(attr.children[1]).lower()
                    for attr in walk(attr_spec_list, f03.Dimension_Attr_Spec):
                        dim_rank_from_attr = (
                            len(walk(attr, f03.Assumed_Shape_Spec))
                            + len(walk(attr, f03.Explicit_Shape_Spec))
                        )

                # Entities: name + optional inline array spec
                for entity in walk(entity_decl_list, f03.Entity_Decl):
                    name = str(entity.children[0]).lower()
                    if name not in dummy_names:
                        continue
                    array_spec = entity.children[1]
                    entity_rank = (
                        len(walk(array_spec, f03.Assumed_Shape_Spec))
                        + len(walk(array_spec, f03.Explicit_Shape_Spec))
                        if array_spec
                        else 0
                    )
                    rank = entity_rank or dim_rank_from_attr
                    decl_map[name] = {
                        "type": base_type,
                        "rank": rank,
                        "intent": intent_str,
                        "optional": is_optional,
                        "kind": kind_str,
                    }

            # Return args in dummy-argument order
            args = []
            for a in dummy_arg_list.items:
                name = str(a).lower()
                if name in decl_map:
                    args.append({"name": name, **decl_map[name]})

            results.append((module_name, proc_name, args))

    return results


def build_meta_module_from_source(f90_source: str) -> builtin.ModuleOp:
    """Parse *f90_source* and return a ``builtin.ModuleOp`` containing
    ``ccpp.table_properties`` / ``ccpp.arg_table`` / ``ccpp.arg`` ops.

    Raises ``ImportError`` if fparser is not installed.
    """
    subroutines = _extract_subroutines(f90_source)

    # Group by module name → one TablePropertiesOp per module
    by_module: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    for module_name, proc_name, args in subroutines:
        by_module[module_name].append((proc_name, args))

    table_props = []
    for module_name, procs in by_module.items():
        arg_tables = []
        for proc_name, args in procs:
            arg_ops = []
            for arg in args:
                attrs: dict = {"type": arg["type"]}
                if arg["rank"] > 0:
                    dims = ", ".join(f"dim{i + 1}" for i in range(arg["rank"]))
                    attrs["dimensions"] = f"({dims})"
                if arg["intent"]:
                    attrs["intent"] = arg["intent"]
                if arg["optional"]:
                    attrs["optional"] = "True"
                if arg.get("kind"):
                    attrs["kind"] = arg["kind"]
                arg_ops.append(ArgumentOp(arg["name"], arg["type"], attrs))
            arg_tables.append(ArgumentTableOp(proc_name, "scheme", arg_ops))
        table_props.append(TablePropertiesOp(module_name, "scheme", arg_tables))

    return builtin.ModuleOp(table_props)


def build_meta_module_from_file(f90_path: str) -> builtin.ModuleOp:
    """Read *f90_path* and return CCPP metadata IR extracted via fparser2."""
    with open(f90_path) as f:
        source = f.read()
    return build_meta_module_from_source(source)
