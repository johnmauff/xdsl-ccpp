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


def _construct_span(construct_node) -> tuple[int, int] | None:
    """Return the 1-indexed, inclusive ``(start_line, end_line)`` source span
    of *construct_node* (e.g. a ``Subroutine_Subprogram``), or ``None`` if it
    can't be determined.

    fparser2 only sets ``.item``/``.item.span`` on leaf statement nodes, not
    on compound block nodes -- confirmed empirically this session, not
    assumed. A block construct's own overall span is recovered from its
    first child's (the opening stmt, e.g. ``Subroutine_Stmt``) start and its
    last child's (the closing stmt, e.g. ``End_Subroutine_Stmt``) end.
    """
    if not construct_node.children:
        return None
    first, last = construct_node.children[0], construct_node.children[-1]
    first_item = getattr(first, "item", None)
    last_item = getattr(last, "item", None)
    if first_item is None or last_item is None:
        return None
    return (first_item.span[0], last_item.span[1])


def _extract_ccpp_tags(
    source_lines: list[str], span: tuple[int, int] | None, filename: str = "<source>"
) -> dict[str, dict[str, str]]:
    """Scan *source_lines* (1-indexed, inclusive *span* = ``(start, end)``)
    for ``!ccpp [name] key = value`` tag comments.

    fparser2 strips all comments from its own parse tree, so these can only
    ever be recovered from the raw source text directly, cross-referenced by
    the enclosing construct's own line span -- confirmed empirically this
    session (comments are gone from the tree; ``.item.span``/``.item.line``
    on real statement nodes are not). Tags are matched by bracketed name,
    not line position, so they may appear anywhere within *span* -- not
    necessarily adjacent to the declaration they describe.

    Hand-written, line-oriented parser -- matching this codebase's own
    established convention for text-to-IR frontends
    (``xdsl_ccpp/frontend/ccpp_xml.py``'s ``parse_meta_file``) rather than a
    single packed regex -- so malformed input gets the same kind of clear,
    actionable ``filename:line_no`` error that parser already gives, instead
    of an opaque "didn't match" from a failed regex.

    Returns ``{var_name: {key: value}}``, both lowercased; value stripped of
    only leading/trailing whitespace, not altered further.
    """
    if span is None:
        return {}
    start, end = span
    tags: dict[str, dict[str, str]] = {}

    for offset, line in enumerate(source_lines[start - 1:end]):
        line_no = start + offset
        stripped = line.strip()
        if not stripped.startswith("!"):
            continue

        # Drop the leading '!' and check for the 'ccpp' marker specifically
        # -- an ordinary comment ("! this computes foo") must never be
        # mistaken for a tag.
        body = stripped[1:].strip()
        if not body.lower().startswith("ccpp"):
            continue
        rest = body[len("ccpp"):].strip()

        if not rest.startswith("["):
            raise ValueError(
                f"{filename}:{line_no}: '!ccpp' tag missing '[name]': {line!r}"
            )
        close = rest.find("]")
        if close == -1:
            raise ValueError(
                f"{filename}:{line_no}: '!ccpp' tag has an unterminated "
                f"'[name]': {line!r}"
            )
        var_name = rest[1:close].strip().lower()
        if not var_name:
            raise ValueError(
                f"{filename}:{line_no}: '!ccpp' tag has an empty '[name]'"
            )

        remainder = rest[close + 1:].strip()
        if "=" not in remainder:
            raise ValueError(
                f"{filename}:{line_no}: '!ccpp [{var_name}]' tag is missing "
                f"'key = value': {line!r}"
            )
        key, value = remainder.split("=", 1)
        key = key.strip().lower()
        if not key:
            raise ValueError(
                f"{filename}:{line_no}: '!ccpp [{var_name}]' tag has an "
                "empty key"
            )

        tags.setdefault(var_name, {})[key] = value.strip()

    return tags


# dup-meta-shadow-elim (BACKLOG.md), Phase 2: clauses that assert a named
# variable's device residency -- confirmed against real usage in this
# repo's own examples/ (kessler.F90, cld_liq.F90, cld_ice.F90). Deliberately
# narrow: `create`/`delete`/`private`/`reduction`/etc. are about a
# variable's own lifecycle or GPU control flow, not whether a *dummy
# argument* is device-resident, so they're left out on purpose.
_DEVICE_RESIDENCY_CLAUSES = ("present", "deviceptr", "copyin", "copyout", "copy")
_ACC_OMP_SENTINELS = ("!$acc", "!$omp")


def _extract_device_resident_vars(
    source_lines: list[str], span: tuple[int, int] | None, filename: str = "<source>"
) -> set[str]:
    """Scan *source_lines* (1-indexed, inclusive *span*) for `!$acc`/`!$omp`
    directive lines and return the (lowercased) set of variable names named
    inside a device-residency clause (`present`/`deviceptr`/`copyin`/
    `copyout`/`copy`).

    Hand-written, line-oriented parser, matching this codebase's own
    established convention (see `_extract_ccpp_tags` and
    `ccpp_xml.py`'s `parse_meta_file`) rather than a regex.

    Two real wrinkles confirmed directly against this repo's own examples,
    not assumed:

    - **Continuation lines.** A directive ending in `&` continues onto the
      next line, which repeats the sentinel (e.g.
      `!$acc parallel loop gang vector &` / `!$acc present(...) ...`,
      confirmed in `examples/kessler/scheme/kessler.F90`). Continuation
      lines are joined into one logical line before clause-scanning.
    - **`!!$acc` is not a directive.** A real compiler sentinel is exactly
      `!$acc`/`!$omp` (no second `!` between the comment character and the
      `$`) -- `kessler_update.F90` has a real commented-out
      `!!$acc parallel loop collapse(2) present(...)` sitting right next
      to an active, shorter `!$acc parallel loop collapse(2)` with no
      `present(...)` at all. Checking for the sentinel at the very start
      of the stripped line (after only whitespace) naturally excludes
      `!!$acc`, with no special-casing needed.

    A clause keyword must be immediately followed by `(` and not preceded
    by an identifier character, so `default(present)` (a *different*
    clause, `default`, whose value happens to be the word "present") is
    never mistaken for a `present(...)` clause -- "present" there is
    followed by `)`, not `(`.
    """
    if span is None:
        return set()
    start, end = span

    logical_lines: list[str] = []
    pending: str | None = None

    def _flush():
        nonlocal pending
        if pending is not None:
            logical_lines.append(pending)
            pending = None

    for line in source_lines[start - 1:end]:
        stripped = line.strip()
        lowered = stripped.lower()
        sentinel = next((s for s in _ACC_OMP_SENTINELS if lowered.startswith(s)), None)
        if sentinel is None:
            _flush()
            continue

        body = stripped[len(sentinel):].strip()
        if pending is not None:
            body = pending + " " + body
        if body.endswith("&"):
            pending = body[:-1].strip()
            continue
        logical_lines.append(body)
        pending = None
    _flush()

    var_names: set[str] = set()
    for logical in logical_lines:
        text = logical.lower()
        for keyword in _DEVICE_RESIDENCY_CLAUSES:
            needle = keyword + "("
            pos = text.find(needle)
            while pos != -1:
                is_whole_word = pos == 0 or not (text[pos - 1].isalnum() or text[pos - 1] == "_")
                if is_whole_word:
                    open_paren = pos + len(keyword)
                    close_paren = text.find(")", open_paren)
                    if close_paren == -1:
                        raise ValueError(
                            f"{filename}: '{keyword}(' clause has no closing "
                            f"')': {logical!r}"
                        )
                    inner = text[open_paren + 1:close_paren]
                    for name in inner.split(","):
                        name = name.strip()
                        if name:
                            var_names.add(name)
                pos = text.find(needle, pos + 1)

    return var_names


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
    # Same (possibly preprocessed) source the parser just consumed, so line
    # numbers from fparser2's own .item.span line up exactly -- used only by
    # the !ccpp tag recovery below, which needs the raw text since fparser2
    # strips comments from the parse tree itself.
    source_lines = f90_source.splitlines()

    results = []

    for module in walk(tree, f03.Module):
        module_stmt = module.children[0]
        module_name = str(module_stmt.children[1]).lower()

        for sub in walk(module, f03.Subroutine_Subprogram):
            sub_stmt = sub.children[0]  # Subroutine_Stmt
            proc_name = str(sub_stmt.children[1]).lower()

            dummy_arg_list = sub_stmt.children[2]
            dummy_names = (
                {str(a).lower() for a in dummy_arg_list.items}
                if dummy_arg_list is not None
                else set()
            )

            span = _construct_span(sub)
            tags = _extract_ccpp_tags(source_lines, span, filename)
            unknown_tagged = sorted(set(tags) - dummy_names)
            if unknown_tagged:
                raise ValueError(
                    f"'{filename}': subroutine '{proc_name}' has a !ccpp tag "
                    f"for {unknown_tagged}, which is not one of its own dummy "
                    f"arguments ({sorted(dummy_names)})"
                )
            # Device-residency clauses legitimately also name local/scratch
            # variables with no corresponding dummy argument at all (e.g.
            # kessler.F90's `present(r,rhalf,...)` on its own work arrays) --
            # unlike an unmatched !ccpp tag, that's not an error, it's simply
            # not looked up below.
            device_resident = _extract_device_resident_vars(source_lines, span, filename)

            if dummy_arg_list is None:
                results.append((module_name, proc_name, []))
                continue

            decl_map = _build_decl_map(sub, dummy_names)

            # Return args in dummy-argument order, enriched with any !ccpp
            # tag content found for that argument's name (standard_name/
            # units/long_name -- the fields fparser2 can never see in plain
            # declaration syntax, regardless of tagging) and, when not
            # already given explicitly by a tag, memory_space derived from a
            # real device-residency clause.
            args = []
            for a in dummy_arg_list.items:
                name = str(a).lower()
                if name not in decl_map:
                    continue
                extra = dict(tags.get(name, {}))
                if "memory_space" not in extra and name in device_resident:
                    extra["memory_space"] = "device"
                args.append({"name": name, **decl_map[name], **extra})

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
