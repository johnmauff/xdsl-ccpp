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


def _build_decl_map(scope_node, name_filter: set[str] | None) -> dict[str, dict]:
    """Walk ``Type_Declaration_Stmt`` nodes within *scope_node* and return a
    ``name -> {type, rank, intent, optional, kind}`` map.

    *name_filter*, if given, restricts the result to those names
    (case-insensitive, already lowercased); pass ``None`` to keep every
    declared name found in scope. Shared by ``_extract_subroutines`` (filtered
    to a subroutine's own dummy-argument names) and ``extract_program_locals``
    (filtered to the caller's requested names, or unfiltered).
    """
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    decl_map: dict[str, dict] = {}

    for decl in walk(scope_node, f03.Type_Declaration_Stmt):
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
                    + len(walk(attr, f03.Deferred_Shape_Spec))
                    + len(walk(attr, f03.Assumed_Size_Spec))
                )

        # Entities: name + optional inline array spec
        for entity in walk(entity_decl_list, f03.Entity_Decl):
            name = str(entity.children[0]).lower()
            if name_filter is not None and name not in name_filter:
                continue
            array_spec = entity.children[1]
            entity_rank = (
                len(walk(array_spec, f03.Assumed_Shape_Spec))
                + len(walk(array_spec, f03.Explicit_Shape_Spec))
                + len(walk(array_spec, f03.Deferred_Shape_Spec))
                + len(walk(array_spec, f03.Assumed_Size_Spec))
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

    return decl_map


def _extract_subroutines(
    f90_source: str,
    filename: str = "<source>",
    preproc_defs: dict | None = None,
) -> list[tuple[str, str, list[dict]]]:
    """Parse *f90_source* and return a list of (module_name, proc_name, args).

    Each element of *args* is a dict with keys:
    ``name``, ``type``, ``rank``, ``intent`` (or None), ``optional`` (bool),
    ``kind`` (str or None, for CHARACTER only: the length string).

    ``preproc_defs``, when truthy, is applied to *f90_source* via
    ``fortran_preprocess.preprocess_fortran_source`` before fparser2 ever
    sees it -- fparser has no CPP-evaluation capability of its own (it only
    tokenizes ``#if``/``#ifdef``/etc. as opaque directive nodes), so
    conditional-compilation regions must already be resolved by this point.
    """
    import fparser.two.Fortran2003 as f03
    from fparser.two.parser import ParserFactory
    from fparser.two.utils import walk
    from fparser.common.readfortran import FortranStringReader

    if preproc_defs:
        from xdsl_ccpp.transforms.fortran_preprocess import preprocess_fortran_source
        f90_source = preprocess_fortran_source(f90_source, filename, preproc_defs)

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

            decl_map = _build_decl_map(sub, dummy_names)

            # Return args in dummy-argument order
            args = []
            for a in dummy_arg_list.items:
                name = str(a).lower()
                if name in decl_map:
                    args.append({"name": name, **decl_map[name]})

            results.append((module_name, proc_name, args))

    return results


def extract_program_locals(
    f90_source: str,
    filename: str = "<source>",
    preproc_defs: dict | None = None,
    names: set[str] | None = None,
) -> list[tuple[str, list[dict]]]:
    """Parse *f90_source* and return a list of (program_name, args) -- one
    entry per top-level ``program ... end program`` block found.

    Unlike ``_extract_subroutines`` (a subroutine's own dummy arguments),
    this extracts a *driver program's* own local variable declarations,
    scoped strictly to the program's own top-level specification part (never
    an internal ``CONTAINS``-ed subprogram's locals, and never a `module`'s
    declarations -- a program and a module are different fparser2 node
    types; this function only ever walks ``Main_Program``).

    *names*, if given (e.g. ``{"errmsg", "errflg"}``), restricts extraction
    to those variable names (case-insensitive); pass ``None`` to extract
    every declared local in the program's top-level scope.

    ``preproc_defs`` behaves exactly as in ``_extract_subroutines``.

    Each element of the returned *args* list is a dict shaped like
    ``_extract_subroutines``'s own arg dicts (``name``/``type``/``rank``/
    ``intent``/``optional``/``kind``), so it composes with the same
    ArgumentOp-construction code already used for scheme/module extraction.
    """
    import fparser.two.Fortran2003 as f03
    from fparser.two.parser import ParserFactory
    from fparser.two.utils import walk
    from fparser.common.readfortran import FortranStringReader

    if preproc_defs:
        from xdsl_ccpp.transforms.fortran_preprocess import preprocess_fortran_source
        f90_source = preprocess_fortran_source(f90_source, filename, preproc_defs)

    ParserFactory().create(std="f2003")
    reader = FortranStringReader(f90_source)
    tree = f03.Program(reader)

    results = []

    for main_program in walk(tree, f03.Main_Program):
        program_stmt = main_program.children[0]
        program_name = str(program_stmt.children[1]).lower()

        # children[1] is the top-level Specification_Part for every
        # Main_Program that declares one (confirmed directly against
        # fparser2's own Main_Program.match shape: Program_Stmt,
        # [Specification_Part, Execution_Part, Internal_Subprogram_Part],
        # End_Program_Stmt -- optional blocks are omitted from children
        # entirely rather than replaced with None, so an empty program with
        # no declarations at all has no Specification_Part in children[1]).
        # Scoping to this node specifically, not the whole Main_Program
        # subtree, is what keeps an internal CONTAINS-ed subprogram's own
        # locals from being misattributed as program-level.
        spec_part = main_program.children[1] if len(main_program.children) > 1 else None
        if not isinstance(spec_part, f03.Specification_Part):
            results.append((program_name, []))
            continue

        decl_map = _build_decl_map(spec_part, names)
        args = [{"name": name, **attrs} for name, attrs in decl_map.items()]
        results.append((program_name, args))

    return results


def build_meta_module_from_source(
    f90_source: str,
    filename: str = "<source>",
    preproc_defs: dict | None = None,
) -> builtin.ModuleOp:
    """Parse *f90_source* and return a ``builtin.ModuleOp`` containing
    ``ccpp.table_properties`` / ``ccpp.arg_table`` / ``ccpp.arg`` ops.

    ``preproc_defs``, when truthy, resolves ``#ifdef``/``#if`` conditional
    compilation in *f90_source* before parsing -- see ``_extract_subroutines``.

    Raises ``ImportError`` if fparser is not installed.
    """
    subroutines = _extract_subroutines(f90_source, filename, preproc_defs)

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


def build_meta_module_from_file(
    f90_path: str, preproc_defs: dict | None = None
) -> builtin.ModuleOp:
    """Read *f90_path* and return CCPP metadata IR extracted via fparser2.

    ``preproc_defs``, when truthy, resolves ``#ifdef``/``#if`` conditional
    compilation before parsing -- see ``build_meta_module_from_source``.
    """
    with open(f90_path) as f:
        source = f.read()
    return build_meta_module_from_source(source, f90_path, preproc_defs)
