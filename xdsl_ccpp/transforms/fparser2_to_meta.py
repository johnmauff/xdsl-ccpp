"""fparser2_to_meta — Extract CCPP dialect metadata from Fortran source via fparser2.

Uses the pure-Python ``fparser`` library; no external tools required —
``pip install fparser`` is sufficient.

Information extracted:
- Argument names (from dummy argument list)
- Argument types (REAL, INTEGER, CHARACTER, LOGICAL, and derived types via ``TYPE(name)``)
- Array rank (from assumed-shape specs ``(:)`` or ``DIMENSION`` attribute)
- Intent (from INTENT attribute)
- Optional flag (from OPTIONAL attribute)

Information NOT available from Fortran source text:
- ``standard_name`` / ``long_name``
- ``units``
- Kind name (only the kind token as written, not the resolved CCPP kind name)
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field

from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp
from xdsl_ccpp.util.errors import CcppInputError

# Map Fortran intrinsic type names to CCPP type strings
_TYPE_MAP: dict[str, str] = {
    "real": "real",
    "integer": "integer",
    "character": "character",
    "logical": "logical",
    "complex": "complex",
}


def _build_decl_map(scope_node, name_filter: set[str] | None) -> dict[str, dict]:
    """Walk ``Type_Declaration_Stmt`` nodes within *scope_node* and return a
    ``name -> {type, rank, intent, optional, allocatable, kind}`` map.

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
                else:
                    # fparser2's own str() serialization of a Char_Selector
                    # inserts spaces around '=' (e.g. "LEN = 512"/"LEN = *"),
                    # unlike every real .meta file's tight "len=512"/"len=*"
                    # convention. compare_arg_tables already normalizes this
                    # away with the same .replace(" ", "") when comparing
                    # (confirmed this session) -- but nothing downstream of
                    # *extraction* did, so a kind string built here flowed
                    # into real generation (ccpp_generate_meta.py, Phase 4)
                    # with the extra spaces intact. xdsl_ccpp/transforms/
                    # util/typing.py's shape computation does a plain
                    # `"len=" in kind` substring check with no such
                    # normalization, silently falling through to the wrong
                    # (scalar) shape for "len = *" -- confirmed as the exact
                    # cause of a real `memref<i8>` vs `memref<512xi8>`
                    # mismatch building examples/threads_nometa. Normalize
                    # at the source instead of requiring every consumer to
                    # tolerate both spellings.
                    raw_kind = raw_kind.replace(" ", "")
                kind_str = raw_kind.lower() if raw_kind else None

        # Intent/optional/allocatable from attribute list. allocatable
        # mirrors optional exactly -- both are plain Attr_Spec keywords,
        # confirmed directly against fparser2's own parse of a real
        # declaration (examples/advection/cld_liq.F90's `type(...),
        # allocatable, intent(out) :: dyn_const(:)`) -- dup-meta-shadow-elim
        # (BACKLOG.md), Phase 7: a real scheme's allocatable constituent
        # arg needs this to avoid a redundant `!$ccpp ... allocatable =
        # True` tag for something already visible in the declaration
        # itself, matching this project's own "derive what's mechanically
        # derivable, tag only what's genuinely irreducible" philosophy.
        intent_str: str | None = None
        is_optional = False
        is_allocatable = False
        dim_rank_from_attr = 0

        if attr_spec_list:
            for attr in walk(attr_spec_list, f03.Attr_Spec):
                attr_upper = str(attr).upper()
                if attr_upper == "OPTIONAL":
                    is_optional = True
                elif attr_upper == "ALLOCATABLE":
                    is_allocatable = True
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
                "allocatable": is_allocatable,
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


def _join_comment_continuations(
    source_lines: list[str], span: tuple[int, int] | None, sentinels: tuple[str, ...]
) -> list[tuple[int, list[str]]]:
    """Scan *source_lines* (1-indexed, inclusive *span*) for comment lines
    whose stripped, lowercased text starts with one of *sentinels*, chaining
    a line ending in ``&`` with the next matching-sentinel line, matching
    real ``!$acc``/``!$omp`` continuation convention (confirmed in
    ``examples/kessler/scheme/kessler.F90``: ``!$acc parallel loop gang
    vector &`` / ``!$acc present(...) ...``).

    Shared by ``_extract_ccpp_tags`` (sentinel ``!$ccpp``) and
    ``_classify_acc_residency`` (sentinel ``!$acc``) --
    the chain-detection mechanics (trailing ``&``, repeated sentinel) are
    identical regardless of which sentinel is in play. What each chained
    line *means*, though, differs by caller, so this returns each
    sentinel-stripped line **unjoined** -- the caller decides:
    ``_classify_acc_residency`` wants one logical directive's whole
    clause-list as a single blob (``" ".join(...)``), since a real
    ``!$acc`` directive's own clauses genuinely span the continuation as
    one unit. ``_extract_ccpp_tags`` wants each chained line kept
    separate: a ``!$ccpp`` continuation line is a *complete, independent*
    ``key = value`` pair for the same bracketed name established on the
    chain's first line, not a fragment of one value's text -- confirmed
    directly against a real build failure this session (concatenating
    `` standard_name = x`` with a following ``long_name = y`` as one
    blob produced `` standard_name = "x long_name = y"``, corrupting the
    very name the generator relies on to recognize `errmsg` as a
    framework-reserved variable).

    fparser2 strips all comments from its own parse tree, so this is the
    only way to recover them at all -- confirmed empirically this session.
    A sentinel is checked at the very start of the stripped line, so e.g.
    ``!!$acc``/``!!$ccpp`` (a second ``!`` -- a human comment *about* a
    directive, not a real compiler sentinel) is never mistaken for an
    active one, with no special-casing needed (confirmed real case:
    ``examples/kessler/scheme/kessler_update.F90``).

    Returns a list of ``(first_line_no, [remainder, ...])`` -- one entry
    per complete, possibly multi-line, chain; *first_line_no* is the
    1-indexed source line the chain *started* on (useful for error
    messages).
    """
    if span is None:
        return []
    start, end = span

    chains: list[tuple[int, list[str]]] = []
    pending: list[str] | None = None
    pending_line_no: int | None = None

    def _flush():
        nonlocal pending, pending_line_no
        if pending is not None:
            chains.append((pending_line_no, pending))
            pending = None
            pending_line_no = None

    for offset, line in enumerate(source_lines[start - 1:end]):
        line_no = start + offset
        stripped = line.strip()
        lowered = stripped.lower()
        sentinel = next((s for s in sentinels if lowered.startswith(s)), None)
        if sentinel is None:
            _flush()
            continue

        body = stripped[len(sentinel):].strip()
        is_continued = body.endswith("&")
        if is_continued:
            body = body[:-1].strip()
        if pending is not None and body.startswith("&"):
            # A continuation line may repeat the "&" right after the
            # sentinel ("!$acc&  x, y" or "!$acc &  x"); without this the
            # first name read as "& x" and was silently dropped.
            body = body[1:].strip()

        if pending is None:
            pending = [body]
            pending_line_no = line_no
        else:
            pending.append(body)

        if not is_continued:
            chains.append((pending_line_no, pending))
            pending = None
            pending_line_no = None
    _flush()

    return chains


_CCPP_TAG_SENTINELS = ("!$ccpp",)


def _extract_ccpp_tags(
    source_lines: list[str], span: tuple[int, int] | None, filename: str = "<source>"
) -> dict[str, dict[str, str]]:
    """Scan *source_lines* (1-indexed, inclusive *span* = ``(start, end)``)
    for ``!$ccpp [name] key = value`` tag comments.

    Tags are matched by bracketed name, not line position, so they may
    appear anywhere within *span* -- not necessarily adjacent to the
    declaration they describe. Several ``key = value`` pairs for the same
    name may be chained with a trailing ``&``, matching ``!$acc``/``!$omp``
    continuation convention (see ``_join_comment_continuations``) -- each
    chained line is a **complete, independent assignment**, not a
    fragment of one value's text, so a continuation line doesn't repeat
    ``[name]`` (it's implied, from the chain's first line), e.g.::

        !$ccpp [qv] standard_name = water_vapor_mixing_ratio &
        !$ccpp      units = kg kg-1 &
        !$ccpp      long_name = a long description

    is exactly equivalent to three separate, unchained ``!$ccpp [qv] ...``
    lines. This is *not* a mechanism for wrapping one long value across
    lines -- concatenating chained lines into a single value was tried
    first and is exactly what produced a real build failure (see
    ``_join_comment_continuations``'s own docstring).

    Hand-written, line-oriented parser -- matching this codebase's own
    established convention for text-to-IR frontends
    (``xdsl_ccpp/frontend/ccpp_xml.py``'s ``parse_meta_file``) rather than a
    single packed regex -- so malformed input gets the same kind of clear,
    actionable ``filename:line_no`` error that parser already gives, instead
    of an opaque "didn't match" from a failed regex.

    Returns ``{var_name: {key: value}}``, both lowercased; value stripped of
    only leading/trailing whitespace, not altered further.
    """
    tags: dict[str, dict[str, str]] = {}

    for line_no, remainders in _join_comment_continuations(source_lines, span, _CCPP_TAG_SENTINELS):
        first = remainders[0]
        if not first.startswith("["):
            raise CcppInputError(
                f"{filename}:{line_no}: '!$ccpp' tag missing '[name]': {first!r}"
            )
        close = first.find("]")
        if close == -1:
            raise CcppInputError(
                f"{filename}:{line_no}: '!$ccpp' tag has an unterminated "
                f"'[name]': {first!r}"
            )
        var_name = first[1:close].strip().lower()
        if not var_name:
            raise CcppInputError(
                f"{filename}:{line_no}: '!$ccpp' tag has an empty '[name]'"
            )

        # The first chained line's own assignment (after its bracket),
        # plus every subsequent chained line verbatim -- each is its own
        # independent key = value pair for this same var_name.
        segments = [first[close + 1:].strip()] + remainders[1:]
        for seg in segments:
            if "=" not in seg:
                raise CcppInputError(
                    f"{filename}:{line_no}: '!$ccpp [{var_name}]' tag is "
                    f"missing 'key = value': {seg!r}"
                )
            key, value = seg.split("=", 1)
            key = key.strip().lower()
            if not key:
                raise CcppInputError(
                    f"{filename}:{line_no}: '!$ccpp [{var_name}]' tag has an "
                    "empty key"
                )
            tags.setdefault(var_name, {})[key] = value.strip()

    return tags


# acc-derive-memory-space (BACKLOG.md): what a scheme entry point's own
# OpenACC says about each of its dummy arguments.
#
# "device": the scheme requires the argument on the device -- named in a
# present/deviceptr clause, in an `update self/host/device` or `host_data
# use_device`, or an array referenced inside a compute construct with
# default(present).
# "either": present-or-copy -- named in a copy-family clause, or an array
# referenced inside a compute construct with no clause for it (OpenACC's
# implicit present-or-copy). The scheme works with host data (it copies the
# data itself) and with data already on the device (it then uses that copy).
#
# Derived-type arguments, and components named in clauses
# (`copyin(sources%sources%lay_source)`), are never classified: the scheme
# moves its own derived-type data (gpu-ddt-deep-copy-residency, not planned).
#
# OpenMP target offload (omp-derive-memory-space), read when the language
# is "omp": "device" for a `map` with the `present` modifier,
# `is_device_ptr`/`has_device_addr`/`use_device_ptr`/`use_device_addr`,
# `target update to/from`, and arrays in a target region with
# `defaultmap(present)`; "either" for any other `map` and arrays in a
# target region with no `map` for them (implicitly tofrom). nvfortran 25.9
# supports neither present form, so a kernel-style OpenMP port is all
# "either" (derive_memory_space treats that as device for --directive omp).
#
# "host" (acc-copy-residency): an "either" array the entry point also
# references in host code -- outside every compute construct, other than as
# the argument of an inquiry intrinsic (size, lbound, present, ...). A
# present-or-copy clause finds resident data present and copies nothing, so
# host code inside the scheme would see a stale host copy (or its writes
# would never reach the device). The cap cannot sync inside a call, so such
# an argument stays on the host: the variable can still be device data
# elsewhere, and the cap syncs it around this call as for any CPU scheme.
#
# "synced" (gpu-diagnostics-conditional-sync): named only in an `update`
# with `if_present` -- the scheme copies the data between host and device
# itself where it is present, and otherwise uses the host copy (a
# diagnostics scheme pulling a field before history_out_field, only if
# that field is output). Like "either" the scheme works either way, but it
# never anchors residency: such an argument becomes device only where the
# variable is device data elsewhere (derive_memory_space, then
# resolve-constituent-residency after copy-clause promotion), so a field
# no ported scheme uses is not made device data just to be copied back.
# Its host references are the scheme's own business (no ACC_HOST).
ACC_DEVICE = "device"
ACC_EITHER = "either"
ACC_HOST = "host"
ACC_SYNCED = "synced"

# AccResidency.note: the stronger of two uses of one argument by the
# entry point's own directives.
_NOTE_RANK = {ACC_SYNCED: 0, ACC_EITHER: 1, ACC_DEVICE: 2}

# Inquiry intrinsics: an array named as their first argument is not read.
_INQUIRY_INTRINSICS = frozenset({
    "size", "lbound", "ubound", "shape", "present", "allocated",
    "associated", "is_contiguous", "kind", "len", "rank",
})

_ACC_DEVICE_CLAUSES = frozenset({"present", "deviceptr"})
_ACC_EITHER_CLAUSES = frozenset({
    "copy", "copyin", "copyout", "create", "no_create",
    "pcopy", "pcopyin", "pcopyout", "pcreate",
    "present_or_copy", "present_or_copyin", "present_or_copyout",
    "present_or_create",
})
# Clauses of `update` and `host_data` whose variables must be present.
_ACC_UPDATE_CLAUSES = frozenset({"self", "host", "device"})
_ACC_HOST_DATA_CLAUSES = frozenset({"use_device"})
_ACC_COMPUTE_KINDS = ("parallel", "kernels", "serial")

_OMP_DEVICE_CLAUSES = frozenset({
    "is_device_ptr", "has_device_addr", "use_device_ptr", "use_device_addr",
})
# map types that end a mapping rather than use the data.
_OMP_UNMAP_TYPES = frozenset({"release", "delete"})
# Words of a combined target construct that make it a loop construct.
_OMP_LOOP_WORDS = frozenset({"do", "loop", "simd", "distribute"})
_OMP_TARGET_DATA_WORDS = frozenset({"data", "enter", "exit", "update"})

LANGUAGES = ("acc", "omp")


def _split_modifiers(arg_text: str) -> tuple[list[str], str]:
    """Split a clause argument at its top-level ':' (OpenMP `map(present,
    to: a, b)`, `to(present: x)`): ([modifier words], variable list). No
    top-level ':' (a subscript's ':' is inside parentheses): ([], text)."""
    depth = 0
    for i, c in enumerate(arg_text):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == ":" and depth == 0:
            return [m.strip() for m in arg_text[:i].split(",") if m.strip()], arg_text[i + 1:]
    return [], arg_text


def _acc_directive(words, clauses):
    """OpenACC: the clauses that name variables, [(category, how, variable
    list)], and the compute construct, (is a loop construct, matches its
    end directive's words, default(present)) or None."""
    kind = words[0]
    named = []
    for clause, arg_text in clauses:
        if clause in _ACC_DEVICE_CLAUSES:
            named.append((ACC_DEVICE, clause, arg_text))
        elif clause in _ACC_EITHER_CLAUSES:
            named.append((ACC_EITHER, clause, arg_text))
        elif kind == "update" and clause in _ACC_UPDATE_CLAUSES:
            if "if_present" in words:
                named.append((ACC_SYNCED, f"update {clause} if_present", arg_text))
            else:
                named.append((ACC_DEVICE, clause, arg_text))
        elif kind == "host_data" and clause in _ACC_HOST_DATA_CLAUSES:
            named.append((ACC_DEVICE, clause, arg_text))
    if kind not in _ACC_COMPUTE_KINDS:
        return named, None
    default_present = any(c == "default" and a.strip() == "present" for c, a in clauses)
    return named, (
        len(words) > 1 and words[1] == "loop",
        lambda end_words: end_words[:2] == ["end", kind],
        default_present,
    )


def _omp_directive(words, clauses):
    """OpenMP target offload: as _acc_directive. Only target constructs
    count: `!$omp parallel do` alone is host threading."""
    if words[0] != "target":
        return [], None
    named = []
    is_update = len(words) > 1 and words[1] == "update"
    for clause, arg_text in clauses:
        if clause == "map":
            modifiers, variables = _split_modifiers(arg_text)
            if any(m in _OMP_UNMAP_TYPES for m in modifiers):
                continue
            if "present" in modifiers:
                named.append((ACC_DEVICE, "map(present)", variables))
            else:
                map_type = next((m for m in modifiers if m in ("to", "from", "tofrom", "alloc")), "tofrom")
                named.append((ACC_EITHER, f"map({map_type})", variables))
        elif clause in _OMP_DEVICE_CLAUSES:
            named.append((ACC_DEVICE, clause, arg_text))
        elif is_update and clause in ("to", "from"):
            named.append((ACC_DEVICE, f"update {clause}", _split_modifiers(arg_text)[1]))
    if len(words) > 1 and words[1] in _OMP_TARGET_DATA_WORDS:
        return named, None
    default_present = any(
        c == "defaultmap" and _split_modifiers(a)[0][:1] == ["present"]
        or c == "defaultmap" and a.strip() == "present"
        for c, a in clauses
    )
    return named, (
        any(w in _OMP_LOOP_WORDS for w in words[1:]),
        lambda end_words: end_words[:2] == ["end", "target"] and end_words[2:3] != ["data"],
        default_present,
    )


@dataclass
class AccArgUse:
    """How one dummy argument is used by the entry point's OpenACC."""

    category: str  # ACC_DEVICE, ACC_EITHER, ACC_HOST or ACC_SYNCED
    line_no: int   # source line of the directive that decided it
    how: str       # e.g. "present", "copyin", "default(present)", "implicit"


@dataclass
class AccResidency:
    """What one entry point's own OpenACC directives say about its dummy
    arguments (see ACC_DEVICE / ACC_EITHER above)."""

    has_acc: bool = False
    args: dict[str, AccArgUse] = field(default_factory=dict)
    # Derived-type dummy arguments its directives name or use, with a line.
    derived_types: dict[str, int] = field(default_factory=dict)
    # Subroutines it calls (lowercased), to spot an entry point with no
    # OpenACC of its own whose callee in the same file has some.
    calls: set[str] = field(default_factory=set)
    # Dummy argument names in order (positional actuals map onto them when
    # this routine is a callee, apply_callee_residency).
    dummies: list[str] = field(default_factory=list)
    # Only for a routine with no directives of its own (apply_callee_residency):
    # each call (callee, (first, last) line span, [(keyword or None, bare
    # actual name or None), ...]), and the execution-part lines referencing
    # each non-derived array dummy.
    call_sites: list[tuple] = field(default_factory=list)
    ref_lines: dict[str, list[int]] = field(default_factory=dict)
    # Callees whose directives classified some of its arguments.
    via_callees: set[str] = field(default_factory=set)

    def note(self, name: str, category: str, line_no: int, how: str) -> None:
        """Record *name*'s use; "device" outranks "either", which outranks
        "synced", and the first use of the winning category is kept."""
        current = self.args.get(name)
        if current is None or _NOTE_RANK.get(category, 0) > _NOTE_RANK.get(current.category, 0):
            self.args[name] = AccArgUse(category, line_no, how)


def _split_directive(
    text: str, where: str = "<source>"
) -> tuple[list[str], list[tuple[str, str]]]:
    """Split one joined, lowercased `!$acc` directive body into its leading
    words (the directive name, e.g. ["parallel", "loop", "gang"]) and its
    clauses with arguments, [(clause, argument text), ...]. A word directly
    followed by `(` is a clause with an argument (balanced parentheses);
    a bare word is part of the directive name or an argument-less clause.
    An unclosed `(` is a CcppInputError naming *where* (file:line)."""
    words: list[str] = []
    clauses: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            word = text[i:j]
            k = j
            while k < n and text[k] == " ":
                k += 1
            if k < n and text[k] == "(":
                depth, m = 0, k
                while m < n:
                    if text[m] == "(":
                        depth += 1
                    elif text[m] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    m += 1
                if m >= n:
                    raise CcppInputError(
                        f"{where}: '!$acc' clause '{word}(' has no closing ')': {text!r}"
                    )
                clauses.append((word, text[k + 1:m]))
                i = m + 1
                continue
            words.append(word)
            i = j
            continue
        i += 1
    return words, clauses


def _split_top_level(text: str) -> list[str]:
    """Split *text* at the commas not inside parentheses."""
    parts, depth, start = [], 0, 0
    for i, c in enumerate(text):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _clause_variables(arg_text: str) -> list[tuple[str, bool]]:
    """The variables a data clause names: [(base name, is a component
    reference), ...]. Drops a modifier (`readonly:`), subscripts and
    component paths: `x(1:n)` -> ("x", False), `a%b%c` -> ("a", True)."""
    result = []
    for item in _split_top_level(arg_text):
        if ":" in item.split("(", 1)[0]:
            item = item.split(":", 1)[1].strip()
        j = 0
        while j < len(item) and (item[j].isalnum() or item[j] == "_"):
            j += 1
        base = item[:j]
        if base:
            rest = item[j:].lstrip()
            if rest.startswith("("):  # skip a subscript before any %
                depth = 0
                for m, c in enumerate(rest):
                    depth += c == "("
                    depth -= c == ")"
                    if depth == 0:
                        rest = rest[m + 1:].lstrip()
                        break
            result.append((base, rest.startswith("%")))
    return result


def _referenced_names(
    source_lines: list[str], first: int, last: int, skip_inquired: bool = False,
) -> set[str]:
    """Identifiers referenced in Fortran source lines *first*..*last*
    (1-indexed, inclusive), ignoring comments (and so directives), string
    literals and component names (an identifier right after `%`). With
    *skip_inquired*, also the identifier right after `<inquiry intrinsic>(`
    (`size(x, 1)` does not read x)."""
    names: set[str] = set()
    for line in source_lines[first - 1:last]:
        text = line.lower()
        i, n = 0, len(text)
        after_percent = False
        skip_next = False
        while i < n:
            c = text[i]
            if c == "!":
                break
            if c in "'\"":
                end = text.find(c, i + 1)
                i = n if end == -1 else end + 1
                after_percent = False
                continue
            if c.isalpha() or c == "_":
                j = i
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
                word = text[i:j]
                if not after_percent and not skip_next:
                    names.add(word)
                after_percent = False
                skip_next = False
                if skip_inquired and word in _INQUIRY_INTRINSICS:
                    k = j
                    while k < n and text[k] == " ":
                        k += 1
                    if k < n and text[k] == "(":
                        skip_next = True
                        j = k + 1
                i = j
                continue
            if c == "%":
                after_percent = True
            elif c != " ":
                after_percent = False
            i += 1
    return names


def _node_line_span(node) -> tuple[int, int] | None:
    """The 1-indexed, inclusive source span of every statement under *node*
    (fparser2 sets spans on leaf statements only)."""
    from fparser.two.utils import walk

    spans = [
        item.span for item in (getattr(n, "item", None) for n in walk(node))
        if item is not None and getattr(item, "span", None)
    ]
    if not spans:
        return None
    return (min(a for a, _ in spans), max(b for _, b in spans))


def _classify_acc_residency(
    sub, source_lines: list[str], span: tuple[int, int] | None,
    decl_map: dict[str, dict], filename: str = "<source>", language: str = "acc",
) -> AccResidency:
    """Classify the dummy arguments of one entry point (*sub*, a
    Subroutine_Subprogram; *decl_map* its dummy declarations) by its own
    directives in *language* ("acc": `!$acc`, "omp": `!$omp` target
    offload) -- see ACC_DEVICE / ACC_EITHER. Only the routine's own body is
    read, never its callees.

    A compute construct's body is the DO construct after a combined loop
    directive (`parallel loop`, `target teams distribute parallel do`,
    ...), else the lines up to its end directive (`end parallel`, `end
    target`, ...); arrays referenced there are classified ("device" under
    default(present)/defaultmap(present), else "either"). Scalars
    referenced there are firstprivate, not classified.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unknown directive language {language!r}")
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    result = AccResidency()
    result.calls = {
        str(call.children[0]).lower() for call in walk(sub, f03.Call_Stmt)
    }
    if span is None:
        return result
    directives = [
        (line_no, " ".join(remainders).lower())
        for line_no, remainders in _join_comment_continuations(source_lines, span, (f"!${language}",))
    ]
    def is_derived(name: str) -> bool:
        return decl_map[name]["type"] not in _TYPE_MAP

    if not directives:
        _note_calls_and_refs(sub, source_lines, decl_map, result, is_derived)
        return result
    result.has_acc = True

    do_spans = sorted(
        s for s in (
            _construct_span(d)
            for d in walk(sub, (f03.Block_Nonlabel_Do_Construct, f03.Block_Label_Do_Construct))
        ) if s is not None
    )

    interpret = _acc_directive if language == "acc" else _omp_directive
    bodies: list[tuple[int, int]] = []
    # Structured data regions: (first line, last line, the dummies their
    # clauses name), for _note_host_uses.
    data_regions: list[tuple[int, int, set[str]]] = []
    open_regions: list[tuple[int, set[str]]] = []
    for index, (line_no, text) in enumerate(directives):
        words, clauses = _split_directive(text, f"{filename}:{line_no}")
        if _is_data_region_end(words, language):
            if open_regions:
                start, region_names = open_regions.pop()
                data_regions.append((start, line_no, region_names))
            continue
        if not words or words[0] in ("end", "routine", "wait", "atomic", "cache"):
            continue
        named, compute = interpret(words, clauses)
        if _is_data_region_start(words, language):
            open_regions.append((line_no, {
                name for _category, _how, arg_text in named
                for name, is_component in _clause_variables(arg_text)
                if not is_component and name in decl_map
            }))
        for category, how, arg_text in named:
            for name, is_component in _clause_variables(arg_text):
                if name not in decl_map:
                    continue  # a local or module variable
                if is_component or is_derived(name):
                    result.derived_types.setdefault(name, line_no)
                else:
                    result.note(name, category, line_no, how)

        if compute is None:
            continue
        is_loop, is_end, default_present = compute
        body = None
        if is_loop:
            body = next((s for s in do_spans if s[0] > line_no), None)
        else:
            end = next(
                (ln for ln, t in directives[index + 1:]
                 if is_end(_split_directive(t, f"{filename}:{ln}")[0])),
                None,
            )
            if end is not None:
                body = (line_no + 1, end - 1)
        if body is None:
            continue
        bodies.append(body)
        for name in _referenced_names(source_lines, body[0], body[1]):
            if name not in decl_map:
                continue
            if is_derived(name):
                result.derived_types.setdefault(name, line_no)
            elif decl_map[name]["rank"] > 0:
                if default_present:
                    how = "default(present)" if language == "acc" else "defaultmap(present)"
                    result.note(name, ACC_DEVICE, line_no, how)
                else:
                    result.note(name, ACC_EITHER, line_no, "implicit")
    _note_host_uses(sub, source_lines, bodies, data_regions, result)
    return result


def _note_calls_and_refs(sub, source_lines: list[str], decl_map: dict[str, dict],
                         result: AccResidency, is_derived) -> None:
    """For a routine with no directives of its own: record its calls with
    their actual arguments, and where it references each non-derived array
    dummy, so apply_callee_residency can classify its arguments by its
    callees' directives."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    arrays = {
        name for name, decl in decl_map.items()
        if decl["rank"] > 0 and not is_derived(name)
    }
    if not arrays:
        return
    for call in walk(sub, f03.Call_Stmt):
        span = _node_line_span(call)
        if span is None:
            continue
        actual_list = call.children[1]
        actuals = []
        for item in (actual_list.items if actual_list is not None else ()):
            keyword = None
            if isinstance(item, f03.Actual_Arg_Spec):
                keyword, item = str(item.children[0]).lower(), item.children[1]
            name = str(item).lower() if isinstance(item, f03.Name) else None
            actuals.append((keyword, name if name in arrays else None))
        result.call_sites.append((str(call.children[0]).lower(), span, actuals))
    for part in walk(sub, f03.Execution_Part):
        part_span = _node_line_span(part)
        if part_span is None:
            continue
        for line_no in range(part_span[0], part_span[1] + 1):
            for name in _referenced_names(source_lines, line_no, line_no, skip_inquired=True) & arrays:
                result.ref_lines.setdefault(name, []).append(line_no)


# Combining one argument's categories across the callees it is passed to:
# any host use wins, then device, then either, then synced.
_CALLEE_RANK = {ACC_SYNCED: 0, ACC_EITHER: 1, ACC_DEVICE: 2, ACC_HOST: 3}


def apply_callee_residency(acc_residency: dict[str, AccResidency]) -> list[str]:
    """Classify the array arguments of each routine in *acc_residency* that
    has no directives of its own by the directives of the callees it passes
    them to (one call level; callees from the same dict, e.g. the scheme's
    .meta dependencies): micro_pumas_ccpp_run has no OpenACC, but passes its
    arrays to micro_pumas_tend, whose data region and updates make them
    device data. Leaving them host while they are device data elsewhere is
    wrong: the callee's present-or-copy clauses find them present and copy
    nothing back, and the cap's `update device` after the call overwrites
    the device results with the stale host copy (xdsl72gpu pumas T/Q).

    An argument passed bare (`x`, not `x(1:n)`) to a callee dummy the callee
    classifies takes that category (host if any callee says host; device
    outranks either). It becomes ACC_HOST if the routine also references it
    anywhere outside those calls -- its own host code, or a call to a
    callee with no directives. Returns lines for --verbose 2."""
    report: list[str] = []
    for proc, res in acc_residency.items():
        if res.has_acc or not res.call_sites:
            continue
        found: dict[str, AccArgUse] = {}
        classified_spans: dict[str, list[tuple[int, int]]] = {}
        for callee_name, span, actuals in res.call_sites:
            callee = acc_residency.get(callee_name)
            if callee is None or not callee.has_acc:
                continue
            for position, (keyword, actual) in enumerate(actuals):
                if actual is None:
                    continue
                dummy = keyword if keyword is not None else (
                    callee.dummies[position] if position < len(callee.dummies) else None
                )
                use = callee.args.get(dummy) if dummy is not None else None
                if use is None:
                    continue
                res.via_callees.add(callee_name)
                classified_spans.setdefault(actual, []).append(span)
                current = found.get(actual)
                if current is None or _CALLEE_RANK[use.category] > _CALLEE_RANK[current.category]:
                    found[actual] = AccArgUse(use.category, span[0], f"{use.how} in {callee_name}")
        for name, use in found.items():
            spans = classified_spans[name]
            host_line = next(
                (ln for ln in res.ref_lines.get(name, [])
                 if not any(first <= ln <= last for first, last in spans)),
                None,
            )
            if host_line is not None and use.category != ACC_HOST:
                use = AccArgUse(ACC_HOST, host_line, "host use")
            res.args[name] = use
            report.append(f"{proc}: '{name}' {use.category} ({use.how}, line {use.line_no})")
    return report


def _is_data_region_start(words: list[str], language: str) -> bool:
    """A structured data construct's directive: `!$acc data`, `!$omp
    target data` (not `enter`/`exit data`)."""
    if language == "acc":
        return words[:1] == ["data"]
    return words[:2] == ["target", "data"]


def _is_data_region_end(words: list[str], language: str) -> bool:
    """The end directive of a structured data construct."""
    if language == "acc":
        return words[:2] == ["end", "data"]
    return words[:3] == ["end", "target", "data"]


def _mapped_call_arguments(sub, data_regions: list[tuple[int, int, set[str]]],
                           names: set[str]) -> set[tuple[int, str]]:
    """(line, name) for each of *names* passed whole (a bare name) to a
    call inside a structured data region whose clauses name it: the routine
    put it on the device for that callee (PUMAS's micro_pumas_tend passes
    `relvar` to kk2000_liq_autoconversion, whose own kernels use it with
    default(present)), so the reference is not a use on the host."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    exempt: set[tuple[int, str]] = set()
    if not data_regions:
        return exempt
    for call in walk(sub, f03.Call_Stmt):
        span = _node_line_span(call)
        if span is None:
            continue
        mapped = set()
        for first, last, region_names in data_regions:
            if first < span[0] and span[1] < last:
                mapped |= region_names
        if not mapped:
            continue
        actual_list = call.children[1]
        bare = set()
        for item in (actual_list.items if actual_list is not None else ()):
            if isinstance(item, f03.Actual_Arg_Spec):
                item = item.children[1]
            if isinstance(item, f03.Name):
                bare.add(str(item).lower())
        for name in bare & mapped & names:
            exempt.update((line_no, name) for line_no in range(span[0], span[1] + 1))
    return exempt


def _note_host_uses(sub, source_lines: list[str], bodies: list[tuple[int, int]],
                    data_regions: list[tuple[int, int, set[str]]],
                    result: AccResidency) -> None:
    """Turn the "either" arguments that the entry point's execution part
    also references outside every compute construct body (*bodies*) into
    ACC_HOST (see there), at the first such line. A whole array passed to
    a call inside a data region that maps it is not such a reference
    (_mapped_call_arguments)."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    either = {name for name, use in result.args.items() if use.category == ACC_EITHER}
    if not either:
        return
    exempt = _mapped_call_arguments(sub, data_regions, either)
    parts = [_node_line_span(p) for p in walk(sub, f03.Execution_Part)]
    for part in parts:
        if part is None:
            continue
        for line_no in range(part[0], part[1] + 1):
            if any(first <= line_no <= last for first, last in bodies):
                continue
            for name in _referenced_names(source_lines, line_no, line_no, skip_inquired=True) & either:
                if (line_no, name) in exempt:
                    continue
                result.args[name] = AccArgUse(ACC_HOST, line_no, "host use")
                either.discard(name)


def _extract_subroutines(
    f90_source: str,
    filename: str = "<source>",
    preproc_defs: dict | None = None,
    acc_residency: dict | None = None,
    language: str = "acc",
) -> list[tuple[str, str, list[dict]]]:
    """Parse *f90_source* and return a list of (module_name, proc_name, args).

    *acc_residency*, if given, is filled with proc_name -> AccResidency (what
    each subroutine's own directives in *language*, "acc" or "omp", say
    about its dummy arguments, acc-derive-memory-space) from the same parse.

    Each element of *args* is a dict with keys:
    ``name``, ``type``, ``rank``, ``intent`` (or None), ``optional`` (bool),
    ``kind`` (str or None, for CHARACTER only: the length string).

    *f90_source* is always run through
    ``fortran_preprocess.preprocess_fortran_source`` with ``preproc_defs``
    (none if empty) before fparser2 sees it -- fparser has no CPP-evaluation
    capability of its own (it only tokenizes ``#if``/``#ifdef``/etc. as
    opaque directive nodes), so conditional-compilation regions must already
    be resolved by this point.
    """
    import fparser.two.Fortran2003 as f03
    from fparser.two.parser import ParserFactory
    from fparser.two.utils import walk
    from fparser.common.readfortran import FortranStringReader

    # Always, even with no defines: #if/#ifdef regions must be resolved (an
    # undefined name excludes its region, as for the compiler); fparser2 sees
    # the directives as opaque nodes and can fail on disabled code (#if 0).
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
                raise CcppInputError(
                    f"'{filename}': subroutine '{proc_name}' has a !ccpp tag "
                    f"for {unknown_tagged}, which is not one of its own dummy "
                    f"arguments ({sorted(dummy_names)})"
                )
            if dummy_arg_list is None:
                results.append((module_name, proc_name, []))
                continue

            decl_map = _build_decl_map(sub, dummy_names)
            # Directives legitimately also name locals (e.g. kessler.F90's
            # `present(r,rhalf,...)` on its own work arrays); the classifier
            # only records dummy arguments.
            by_language = {
                lang: _classify_acc_residency(sub, source_lines, span, decl_map, filename, lang)
                for lang in LANGUAGES
            }
            if acc_residency is not None:
                by_language[language].dummies = [str(a).lower() for a in dummy_arg_list.items]
                acc_residency[proc_name] = by_language[language]
            # Generated .meta does not know the directive language: an
            # argument either language classifies gets memory_space.
            classified = set(by_language["acc"].args) | set(by_language["omp"].args)

            # Return args in dummy-argument order, enriched with any !ccpp
            # tag content found for that argument's name (standard_name/
            # units/long_name -- the fields fparser2 can never see in plain
            # declaration syntax, regardless of tagging) and, when not
            # already given explicitly by a tag, memory_space = device for
            # every argument the routine's OpenACC classifies, "device" or
            # "either" alike (acc-derive-memory-space stage 1 keeps the
            # earlier clause scanner's behaviour for generated .meta).
            args = []
            for a in dummy_arg_list.items:
                name = str(a).lower()
                if name not in decl_map:
                    continue
                extra = dict(tags.get(name, {}))
                if "memory_space" not in extra and name in classified:
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

    # Always, even with no defines: #if/#ifdef regions must be resolved (an
    # undefined name excludes its region, as for the compiler); fparser2 sees
    # the directives as opaque nodes and can fail on disabled code (#if 0).
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


# Keys in an `_extract_subroutines` arg dict that are either consumed
# specially above (`rank`/`dim_names` -> the `dimensions` string;
# `intent`/`optional`/`allocatable`/`kind` -> their own attrs entries) or
# not a real ArgumentOp property at all (`name`, passed positionally) --
# never forwarded generically, and never warned about as "unrecognised"
# since they're not attrs keys to begin with.
_ARG_DICT_RESERVED_KEYS = frozenset(
    {"name", "type", "rank", "intent", "optional", "allocatable", "kind", "dim_names"}
)


def build_meta_module_from_source(
    f90_source: str,
    filename: str = "<source>",
    preproc_defs: dict | None = None,
    acc_residency: dict | None = None,
    language: str = "acc",
) -> builtin.ModuleOp:
    """Parse *f90_source* and return a ``builtin.ModuleOp`` containing
    ``ccpp.table_properties`` / ``ccpp.arg_table`` / ``ccpp.arg`` ops.

    ``preproc_defs`` (none if empty) resolves ``#ifdef``/``#if`` conditional
    compilation in *f90_source* before parsing -- see ``_extract_subroutines``.

    Every ``!$ccpp``-tag-derived key found by ``_extract_subroutines``
    (``standard_name``/``units``/``long_name``/``memory_space``/
    ``advected``/... -- whatever a real scheme needs) is forwarded onto
    the ``ArgumentOp`` verbatim, not just a fixed short list -- dup-meta-
    shadow-elim (BACKLOG.md), Phase 4 (and Phase 7's advection migration,
    which is what first needed fields beyond the original four). A key
    ``ArgumentOp`` doesn't recognise at all (``ArgumentOp.KNOWN_PROPS``)
    gets a visible warning instead of being silently dropped, mirroring
    ``ccpp_xml.py``'s own unrecognised-``.meta``-key warning exactly -- a
    typo'd ``!$ccpp`` tag key is the same class of mistake as a typo'd
    ``.meta`` key. Safe to forward unconditionally: confirmed
    ``validate_source.compare_arg_tables`` never compares any tag-derived
    field, so this has no effect on the existing scheme-vs-.meta
    validator even once real files start carrying tags.

    Raises ``ImportError`` if fparser is not installed.
    """
    subroutines = _extract_subroutines(f90_source, filename, preproc_defs, acc_residency, language)

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
                    # dim_names isn't a settable ArgumentOp property on its
                    # own (confirmed: ccpp.py derives it FROM the
                    # `dimensions` string itself) -- a !ccpp [name]
                    # dim_names = ... tag's real names are substituted into
                    # that same string instead of the synthetic
                    # dim1/dim2/... placeholders, not forwarded separately.
                    tag_dim_names = arg.get("dim_names")
                    if tag_dim_names:
                        dim_list = [d.strip() for d in tag_dim_names.split(",") if d.strip()]
                        if len(dim_list) != arg["rank"]:
                            raise CcppInputError(
                                f"'{arg['name']}': !ccpp tag's dim_names has "
                                f"{len(dim_list)} name(s) but the real "
                                f"declaration has rank {arg['rank']}"
                            )
                        dims = ", ".join(dim_list)
                    else:
                        dims = ", ".join(f"dim{i + 1}" for i in range(arg["rank"]))
                    attrs["dimensions"] = f"({dims})"
                if arg["intent"]:
                    attrs["intent"] = arg["intent"]
                if arg["optional"]:
                    attrs["optional"] = "True"
                if arg.get("allocatable"):
                    attrs["allocatable"] = "True"
                if arg.get("kind"):
                    attrs["kind"] = arg["kind"]
                for key, value in arg.items():
                    if key in _ARG_DICT_RESERVED_KEYS or not value:
                        continue
                    attrs[key] = value
                unknown = sorted(set(attrs) - ArgumentOp.KNOWN_PROPS)
                if unknown:
                    print(
                        f"Warning: argument '{arg['name']}' in '{proc_name}' "
                        f"has unrecognised !$ccpp tag key(s): {unknown}",
                        file=sys.stderr,
                    )
                arg_ops.append(ArgumentOp(arg["name"], arg["type"], attrs))
            arg_tables.append(ArgumentTableOp(proc_name, "scheme", arg_ops))
        table_props.append(TablePropertiesOp(module_name, "scheme", arg_tables))

    return builtin.ModuleOp(table_props)


def build_meta_module_from_file(
    f90_path: str, preproc_defs: dict | None = None, acc_residency: dict | None = None,
    language: str = "acc",
) -> builtin.ModuleOp:
    """Read *f90_path* and return CCPP metadata IR extracted via fparser2.

    ``preproc_defs`` (none if empty) resolves ``#ifdef``/``#if`` conditional
    compilation before parsing -- see ``build_meta_module_from_source``.
    ``acc_residency`` as for ``_extract_subroutines``.
    """
    with open(f90_path) as f:
        source = f.read()
    return build_meta_module_from_source(source, f90_path, preproc_defs, acc_residency, language)
