"""module_dependency_resolver — derive a scheme's `dependencies =` field
mechanically from its own `USE` statements, instead of hand-authoring it.

dup-meta-shadow-elim (BACKLOG.md), Phase 3. Confirmed this session:
real `dependencies=` values are relative file paths (e.g.
``../../to_be_ccppized/wv_saturation.F90``, from real
``holtslag_boville_diff_interstitials.meta``), and a scheme's own ``USE``
statements name exactly the modules those paths resolve to, via a clean
module-name-equals-file-stem convention that holds for the overwhelming
majority of real modules (98.3% of the real ``atmospheric_physics``
corpus). ``dependencies=`` is a whole-file/table-level property, not a
per-argument one (Phase 0: no table-level ``!ccpp`` tag syntax is needed
at all for this — it's purely derived), so this scans a file's own `USE`
statements anywhere in it, module-level or inside a subroutine, not
scoped to one entry point.

**root_dir must be explicitly chosen by the caller, not auto-detected.**
The real ``atmospheric_physics`` corpus has almost no module-name
collisions project-wide (2.7%), so a single whole-corpus index works
there. This repo's own ``examples/`` is the opposite: ~20 independent,
self-contained example projects reuse generic names (``data.F90``,
``test_host.F90``) across many directories, so a whole-``examples/``
index would misfire constantly (45.5% "ambiguous" -- confirmed this
session). Scope *root_dir* to the narrowest tree that's actually one
coherent build (a single example directory here; the whole
``atmospheric_physics`` checkout there).
"""

from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass, field

# Framework-provided modules the generator itself unconditionally supplies
# (confirmed this session: real capgen-v1's `utility_paths` in
# ccpp_capgen.py, and xdsl_ccpp's own `_resolve_framework_f90_files()` in
# ccpp_datatable.py) -- never a scheme's own dependency to declare.
FRAMEWORK_MODULES = {
    "ccpp_kinds",
    "ccpp_constituent_prop_mod",
    "ccpp_scheme_utils",
    "ccpp_hashable",
    "ccpp_hash_table",
}

# Fortran-standard/compiler-provided modules -- never a project file at
# all. 'openacc' is real, confirmed usage in
# examples/kessler/scheme/kessler.F90; the rest are the standard
# Fortran 2003+/OpenMP set, included for the same closed-set reason
# _TYPE_MAP hardcodes Fortran's own intrinsic type names.
_INTRINSIC_MODULES = {
    "iso_fortran_env",
    "iso_c_binding",
    "ieee_arithmetic",
    "ieee_exceptions",
    "ieee_features",
    "openacc",
    "omp_lib",
}


# MPI, which a captured scheme must not use (scheme-io-capture-host-module-
# schemes): its replay driver runs as one serial process.
MPI_MODULES = frozenset({"mpi", "mpi_f08"})
MPI_INCLUDE_FILES = frozenset({"mpif.h"})


@dataclass(frozen=True)
class ScopeFacts:
    """The USEs, INCLUDEs and CALLs of one scope of a Fortran file: a
    procedure (*name*), or the specification part of module *module*
    (*name* None, which applies to all the module's procedures).

    For module state (scheme-io-capture-module-state-setup), by name:
    *use_only* is ((module, None | frozenset of (local, remote) names),
    ...) for its USE statements (None: no ONLY list); *declared* the
    entities its type declarations declare; *variables* (a module's
    specification part) those that are not parameters; *refs* the
    identifiers its statements mention (not components after %, not in
    strings); *assigns* the base names of its assignments' and pointer
    assignments' left-hand sides; *passes* those of its CALLs' actual
    arguments (which the callee may set)."""

    name: "str | None"
    module: "str | None"
    uses: frozenset
    includes: frozenset
    calls: frozenset
    use_only: tuple = ()
    declared: frozenset = frozenset()
    variables: frozenset = frozenset()
    refs: frozenset = frozenset()
    assigns: frozenset = frozenset()
    passes: frozenset = frozenset()
    # A module's named constants: ((name, value text), ...).
    parameters: tuple = ()


@dataclass(frozen=True)
class ComponentFacts:
    """One component of a derived type (scheme-io-capture-ddt-args).
    *base* is the declaration's type word ("real", "integer", "logical",
    "character", "complex", "type", "class"); *kind* its kind name (None:
    default); *type_name* the type of a "type"/"class" component; *rank*
    0 for a scalar; *public* its accessibility."""

    name: str
    base: str
    kind: "str | None"
    type_name: "str | None"
    rank: int
    allocatable: bool
    pointer: bool
    public: bool


@dataclass(frozen=True)
class TypeFacts:
    """A derived-type definition: its name, module, parent (EXTENDS) and
    components, in order."""

    name: str
    module: "str | None"
    extends: "str | None"
    components: tuple


@dataclass(frozen=True)
class FortranSourceFacts:
    """What one Fortran file declares and needs (lowercased names)."""

    uses: frozenset  # modules USEd anywhere in the file
    modules: frozenset  # modules the file defines
    includes: frozenset  # files named by Fortran INCLUDE lines
    scopes: tuple = ()  # ScopeFacts per procedure and module specification part
    types: tuple = ()  # TypeFacts per derived-type definition


class _ScopeBuilder:
    def __init__(self, name, module):
        self.name, self.module = name, module
        self.uses: set = set()
        self.includes: set = set()
        self.calls: set = set()
        self.use_only: list = []
        self.declared: set = set()
        self.variables: set = set()
        self.refs: set = set()
        self.assigns: set = set()
        self.passes: set = set()
        self.parameters: list = []

    def freeze(self) -> ScopeFacts:
        return ScopeFacts(self.name, self.module, frozenset(self.uses),
                          frozenset(self.includes), frozenset(self.calls),
                          tuple(self.use_only), frozenset(self.declared),
                          frozenset(self.variables), frozenset(self.refs),
                          frozenset(self.assigns), frozenset(self.passes),
                          tuple(self.parameters))


# Type declaration statements start with one of these words.
_DECLARATION_WORDS = frozenset({
    "real", "integer", "logical", "character", "complex", "double", "type", "class",
})
_STRING_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_COMPONENT_RE = re.compile(r"%\s*[a-z]\w*")
# An identifier: a letter not preceded by a word character or a "."
# (kind suffixes such as 1.0_kind_phys, operators such as .and.).
_IDENTIFIER_RE = re.compile(r"(?<![\w.])[a-z][a-z0-9_]*")


def _identifiers(lower: str) -> set:
    """The identifiers a (lower-case) statement mentions, without the
    components after % and the contents of strings."""
    text = _COMPONENT_RE.sub(" ", _STRING_RE.sub(" ", lower))
    return set(_IDENTIFIER_RE.findall(text))


def _skip_parens(text: str, pos: int) -> int:
    """The position after the parenthesized group starting at *pos*."""
    depth = 0
    for at in range(pos, len(text)):
        depth += text[at] == "("
        depth -= text[at] == ")"
        if depth == 0:
            return at + 1
    return len(text)


def _assigned_name(lower: str) -> "str | None":
    """The base name a (lower-case) assignment or pointer assignment
    statement assigns -- ``x = ``, ``x(i)%y = ``, ``p => `` -- after an
    optional one-line ``if (...)``; None for any other statement
    (``do k = ...``, declarations, comparisons)."""
    text = _STRING_RE.sub("''", lower).strip()
    if re.match(r"if\s*\(", text):
        text = text[_skip_parens(text, text.index("(")):].strip()
    match = re.match(r"[a-z]\w*", text)
    if match is None:
        return None
    pos = match.end()
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
        elif text[pos] == "(":
            pos = _skip_parens(text, pos)
        elif text[pos] == "%":
            component = re.match(r"%\s*[a-z]\w*", text[pos:])
            if component is None:
                return None
            pos += component.end()
        else:
            break
    if text.startswith("=>", pos) or (text.startswith("=", pos)
                                      and not text.startswith("==", pos)):
        return match.group(0)
    return None


def _base_name(node) -> "str | None":
    """The variable an actual argument or designator starts with."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    if isinstance(node, f03.Actual_Arg_Spec):
        node = node.children[1]
    if isinstance(node, f03.Name):
        return str(node).lower()
    if isinstance(node, (f03.Part_Ref, f03.Data_Ref)):
        names = walk(node, f03.Name)
        return str(names[0]).lower() if names else None
    return None


def _call_arguments(call) -> set:
    """Base names of a Call_Stmt's actual arguments (it may set them)."""
    import fparser.two.Fortran2003 as f03

    args = call.children[1]
    items = args.children if isinstance(args, f03.Actual_Arg_Spec_List) else (
        [args] if args is not None else [])
    return {name for name in map(_base_name, items) if name}


def _type_start(stmt) -> "tuple[str, str | None]":
    """(name, parent) of a Derived_Type_Stmt."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    parent = None
    for spec in walk(stmt.children[0], f03.Type_Attr_Spec) if stmt.children[0] else ():
        if str(spec.children[0]).upper() == "EXTENDS":
            parent = str(spec.children[1]).lower()
    return str(stmt.children[1]).lower(), parent


def _components(stmt, default_public: bool) -> list:
    """ComponentFacts of a Data_Component_Def_Stmt."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    spec, attrs, decls = stmt.children[0], stmt.children[1], stmt.children[2]
    base = str(spec.children[0]).lower()
    kind = type_name = None
    if isinstance(spec, f03.Intrinsic_Type_Spec):
        selector = spec.children[1]
        if isinstance(selector, f03.Kind_Selector):
            kind = str(selector.children[1]).lower()
    else:
        type_name = str(spec.children[1]).lower()
    attr_text = str(attrs).upper() if attrs is not None else ""
    allocatable = "ALLOCATABLE" in attr_text
    pointer = "POINTER" in attr_text
    public = default_public
    for access in walk(attrs, f03.Access_Spec) if attrs is not None else ():
        public = str(access).upper() == "PUBLIC"
    dim_rank = 0
    for dim in walk(attrs, f03.Dimension_Component_Attr_Spec) if attrs is not None else ():
        dim_rank = len(dim.children[1].children)
    result = []
    for decl in walk(decls, f03.Component_Decl):
        shape = decl.children[1]
        rank = len(shape.children) if shape is not None else dim_rank
        result.append(ComponentFacts(str(decl.children[0]).lower(), base, kind, type_name,
                                     rank, allocatable, pointer, public))
    return result


def _use_only(use) -> tuple:
    """(module, None | frozenset of (local, remote)) for a Use_Stmt."""
    import fparser.two.Fortran2003 as f03

    module = str(use.children[2]).lower()
    only = use.children[4] if "ONLY" in str(use.children[3] or "").upper() else None
    if only is None:
        return module, None
    pairs = set()
    for item in getattr(only, "children", ()) or ():
        if isinstance(item, f03.Rename):
            pairs.add((str(item.children[1]).lower(), str(item.children[2]).lower()))
        elif isinstance(item, f03.Name):
            pairs.add((str(item).lower(), str(item).lower()))
    return module, frozenset(pairs)


def _called_name(call) -> str:
    """The procedure a Call_Stmt names (a type-bound one: its binding)."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    designator = call.children[0]
    if isinstance(designator, f03.Name):
        return str(designator).lower()
    return str(walk(designator, f03.Name)[-1]).lower()


@functools.lru_cache(maxsize=None)
def _scan_cached(path: str, _stamp, defines_key) -> FortranSourceFacts:
    import fparser.two.Fortran2003 as f03
    from fparser.common.readfortran import FortranStringReader, Line
    from fparser.two.parser import ParserFactory
    from fparser.two.utils import walk

    ParserFactory().create(std="f2003")
    with open(path, errors="replace") as f:
        source = f.read()
    if defines_key is not None:
        from xdsl_ccpp.transforms.fortran_preprocess import preprocess_fortran_source

        source = preprocess_fortran_source(source, path, dict(defines_key))
    uses: set = set()
    modules: set = set()
    includes: set = set()
    scopes: list = []
    module = None
    module_scope = _ScopeBuilder(None, None)
    procedures: list = []  # open procedure scopes, innermost last
    interface_depth = 0  # interface bodies declare, they do not define
    generic = None  # scope of the open named interface: it "calls" its procedures
    type_depth = 0  # inside a derived-type definition: components, not variables
    type_def = None  # the definition being read (see below)
    types: list = []

    def current():
        return procedures[-1] if procedures else module_scope

    def close_procedure():
        if procedures:
            scopes.append(procedures.pop().freeze())

    # Statement by statement (the reader joins continuation lines and drops
    # comments), each matched against fparser's own grammar for that
    # statement: a whole-file parse fails on files that build fine (macros
    # such as coords_1d.F90's USE_CONTIGUOUS, F2008 specifiers), and such a
    # file would hide all its statements. Calls are CALL statements (also
    # in a one-line IF); a function referenced in an expression is not
    # followed.
    for item in FortranStringReader(source, ignore_comments=True):
        if not isinstance(item, Line):
            continue
        line = item.line
        lower = line.lstrip().lower()
        words = lower.replace("(", " ").split()
        first = words[0] if words else ""
        if type_depth:
            # Inside a derived-type definition: its components.
            text = lower.strip()
            if re.match(r"end\s*type\b", text):
                type_depth -= 1
                if type_def is not None:
                    types.append(TypeFacts(type_def[0], module, type_def[1],
                                           tuple(type_def[2])))
                type_def = None
            elif type_def is not None and not type_def[4]:
                if text == "contains":
                    type_def[4] = True  # type-bound procedures follow
                elif text == "private":
                    type_def[3] = False
                elif text != "sequence":
                    try:
                        type_def[2].extend(_components(
                            f03.Data_Component_Def_Stmt(line), type_def[3]))
                    except Exception:  # noqa: BLE001 -- not a component
                        pass
            continue
        if (re.match(r"type\s*(,|::|[a-z])", lower.strip())
                and not re.match(r"type\s+is\b", lower.strip())):
            type_depth += 1  # a derived-type definition ("type, public :: t")
            try:
                name, parent = _type_start(f03.Derived_Type_Stmt(line))
                # [name, parent, components, default public, in contains]
                type_def = [name, parent, [], True, False]
            except Exception:  # noqa: BLE001
                type_def = None
            continue
        if procedures and not interface_depth:
            # Module state (scheme-io-capture-module-state-setup).
            current().refs.update(_identifiers(lower))
            assigned = _assigned_name(lower)
            if assigned:
                current().assigns.add(assigned)
        try:
            if first == "use" or lower.startswith("use,"):
                use = f03.Use_Stmt(line)
                name = str(use.children[2]).lower()
                uses.add(name)  # an interface body's too: the file needs it
                if not interface_depth:
                    current().uses.add(name)
                    current().use_only.append(_use_only(use))
            elif first == "include":
                name = str(f03.Include_Stmt(line).children[0]).lower()
                includes.add(name)
                if not interface_depth:
                    current().includes.add(name)
            elif first == "call":
                call = f03.Call_Stmt(line)
                current().calls.add(_called_name(call))
                current().passes.update(_call_arguments(call))
            elif first == "if" and " call " in f" {lower}":
                for call in walk(f03.If_Stmt(line), f03.Call_Stmt):
                    current().calls.add(_called_name(call))
                    current().passes.update(_call_arguments(call))
            elif first in ("interface", "abstract") and "interface" in words[:2]:
                interface_depth += 1
                names = walk(f03.Interface_Stmt(line), f03.Name)
                if interface_depth == 1 and len(names) == 1:
                    generic = _ScopeBuilder(str(names[0]).lower(), module)
            elif interface_depth and first in ("module", "procedure"):
                if generic is not None:
                    generic.calls.update(
                        str(n).lower() for n in walk(f03.Procedure_Stmt(line), f03.Name))
            elif first == "end" or first.startswith("end"):
                kind = (words[1] if first == "end" and len(words) > 1 else first[3:])
                if kind == "interface":
                    interface_depth = max(0, interface_depth - 1)
                    if not interface_depth and generic is not None:
                        scopes.append(generic.freeze())
                        generic = None
                elif interface_depth:
                    continue
                elif kind in ("subroutine", "function", ""):
                    close_procedure()
                elif kind == "module":
                    while procedures:
                        close_procedure()
                    scopes.append(module_scope.freeze())
                    module, module_scope = None, _ScopeBuilder(None, None)
            elif first == "module" and len(words) == 2:
                # "module procedure ..." is not a Module_Stmt.
                module = str(f03.Module_Stmt(line).children[1]).lower()
                modules.add(module)
                module_scope = _ScopeBuilder(None, module)
            elif (not interface_depth
                    and re.match(r"[a-z]*", first).group(0) in _DECLARATION_WORDS
                    and "function" not in words and "subroutine" not in words):
                decl = f03.Type_Declaration_Stmt(line)
                names = {str(e.children[0]).lower()
                         for e in walk(decl.children[2], f03.Entity_Decl)}
                current().declared.update(names)
                if not procedures and "parameter" not in str(decl.children[1] or "").lower():
                    module_scope.variables.update(names)
                elif not procedures:
                    for entity in walk(decl.children[2], f03.Entity_Decl):
                        init = entity.children[3]
                        if init is not None:
                            module_scope.parameters.append(
                                (str(entity.children[0]).lower(),
                                 str(init).lstrip("= ").strip().lower()))
            elif not interface_depth and ("subroutine" in words or "function" in words):
                stmt_cls = f03.Subroutine_Stmt if "subroutine" in words else f03.Function_Stmt
                name = str(stmt_cls(line).children[1]).lower()
                procedures.append(_ScopeBuilder(name, module))
        except Exception:  # noqa: BLE001 -- not that statement (e.g. "user = 1")
            continue
    while procedures:
        close_procedure()
    if module_scope.module or module_scope.uses or module_scope.includes:
        scopes.append(module_scope.freeze())
    return FortranSourceFacts(frozenset(uses), frozenset(modules), frozenset(includes),
                              tuple(scopes), tuple(types))


def scan_fortran_source(
    f90_path: str, preproc_defs: "dict[str, str | None] | None" = None,
) -> FortranSourceFacts:
    """The modules *f90_path* USEs and defines and the files it INCLUDEs.
    With *preproc_defs* (fortran_preprocess.parse_preproc_defines), code
    the C preprocessor would exclude is left out; without, every branch
    counts. Cached per file (and its modification time) and defines."""
    key = None if preproc_defs is None else tuple(sorted(preproc_defs.items()))
    stat = os.stat(f90_path)
    return _scan_cached(os.path.abspath(f90_path), (stat.st_mtime_ns, stat.st_size), key)


def module_definitions(root_dir: str) -> "dict[str, list[str]]":
    """``{module_name_lowercased: [files defining it]}`` over every ``.F90``
    file under *root_dir* (more than one file: an ambiguity the caller
    decides about)."""
    index: dict = {}
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames.sort()
        for fname in sorted(filenames):
            if not fname.lower().endswith(".f90"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                facts = scan_fortran_source(path)
            except (OSError, ValueError):
                continue
            for name in facts.modules:
                index.setdefault(name, []).append(path)
    return index


def build_module_index(root_dir: str) -> dict[str, str]:
    """Walk every ``.F90`` file under *root_dir* and return a
    ``{module_name_lowercased: file_path}`` index.

    Raises ``ValueError`` if the same module name is defined in more than
    one file within *root_dir* -- a real, actionable ambiguity the caller
    should resolve by narrowing *root_dir*, not something to silently
    pick-one on.
    """
    index: dict[str, str] = {}
    for name, paths in module_definitions(root_dir).items():
        if len(paths) > 1:
            raise ValueError(
                f"module '{name}' is defined in more than one file "
                f"within '{root_dir}': '{paths[0]}' and '{paths[1]}' "
                "-- narrow root_dir to resolve the ambiguity"
            )
        index[name] = paths[0]
    return index


def extract_used_modules(f90_path: str) -> set[str]:
    """Return the (lowercased) set of module names *f90_path* itself
    ``USE``s, anywhere in the file."""
    return set(scan_fortran_source(f90_path).uses)


@dataclass
class SourceClosure:
    """The Fortran sources a set of files needs, found by following USE
    statements through one source tree (source_closure)."""

    sources: list = field(default_factory=list)  # absolute paths, starting files first
    unresolved: dict = field(default_factory=dict)  # module -> reason (who uses it, why missing)
    mpi: list = field(default_factory=list)  # (file, "use mpi" / "include 'mpif.h'")
    # procedure -> how it reaches MPI, e.g. "qneg_final calls
    # qneg_print_summary, which has use mpi (qneg.F90)" (mpi_reach)
    mpi_procedures: dict = field(default_factory=dict)
    # module -> (CPU file, GPU file): a module with a CPU and an OpenACC
    # version (accel_variant_pair), built from one or the other; neither
    # file is in *sources*.
    variants: dict = field(default_factory=dict)


def accel_variant_pair(paths) -> "tuple[str, str] | None":
    """(CPU file, GPU file) when *paths* are exactly two files of the same
    name, the second in an ``accel/`` subdirectory of the first's
    directory -- RTE-RRTMGP's layout for kernels with a CPU and an OpenACC
    version, of which a build compiles one (CAM-SIMA:
    cime_config/cam_autogen.py, _set_rrtmgp_dependencies) -- else None."""
    if len(paths) != 2:
        return None
    first, second = (os.path.abspath(p) for p in paths)
    for cpu, gpu in ((first, second), (second, first)):
        if (os.path.basename(cpu) == os.path.basename(gpu)
                and os.path.dirname(gpu) == os.path.join(os.path.dirname(cpu), "accel")):
            return cpu, gpu
    return None


def source_closure(
    start_files, root_dir: "str | None", provided=frozenset(),
    preproc_defs: "dict[str, str | None] | None" = None,
    listed=frozenset(), extra_roots=(),
) -> SourceClosure:
    """Follow the USE statements of *start_files* (and of each file added)
    through the ``.F90`` files under *root_dir*: every module they use that
    is not intrinsic, not MPI and not in *provided* (lowercased names the
    build supplies otherwise) must be defined by a file already in the
    closure, or by exactly one file under *root_dir*, which is added.
    When several files under *root_dir* define it, only those in *listed*
    count, if any are (absolute paths: the files the build compiles, e.g.
    every table's metadata `dependencies`; other copies, such as a
    library's API, test or example versions, are not built). Two files
    left that are a CPU/OpenACC pair (accel_variant_pair) are both
    followed and become a *variant*; the same holds for such a pair among
    *start_files*. Modules found nowhere, or in several other files, are
    *unresolved*; MPI use (MPI_MODULES, MPI_INCLUDE_FILES) is listed in
    *mpi*. A module defined nowhere under *root_dir* is looked for under
    each of *extra_roots* in turn (other source trees, e.g. CESM share
    code), the first defining it winning, with the same rules. The index
    of a tree is built only when a module is not defined by the files at
    hand."""
    result = SourceClosure()
    seen: set = set()
    queue = []
    for path in start_files:
        path = os.path.abspath(path)
        if path not in seen:
            seen.add(path)
            queue.append(path)
    facts: dict = {}
    defined: dict = {}  # module -> file in the closure
    roots = ([root_dir] if root_dir else []) + list(extra_roots)
    indexes: dict = {}  # root -> module_definitions(root), built on demand

    def candidates(name):
        """(root, files defining *name* under it) for the first root that
        has any; (None, []) when none does."""
        for root in roots:
            if root not in indexes:
                indexes[root] = module_definitions(root)
            if name in indexes[root]:
                return root, indexes[root][name]
        return None, []

    pos = 0
    while pos < len(queue):
        # Scan everything queued so far before resolving, so a module
        # defined by a file already in the closure wins over the index.
        for path in queue[pos:]:
            facts[path] = scan_fortran_source(path, preproc_defs)
            for name in facts[path].modules:
                defined.setdefault(name, path)
        batch, pos = queue[pos:], len(queue)
        for path in batch:
            base = os.path.basename(path)
            for name in sorted(facts[path].uses):
                if name in MPI_MODULES:
                    result.mpi.append((path, f"use {name}"))
                    continue
                if (name in _INTRINSIC_MODULES or name in provided
                        or name in defined or name in result.unresolved):
                    continue
                where, found = candidates(name)
                found = [os.path.abspath(p) for p in found]
                if len(found) > 1:
                    found = [p for p in found if p in listed] or found
                if len(found) == 1 or accel_variant_pair(found):
                    defined[name] = found[0]
                    for target in found:
                        if target not in seen:
                            seen.add(target)
                            queue.append(target)
                elif found:
                    result.unresolved[name] = (
                        f"used by {base}; defined in {len(found)} files under {where}"
                    )
                else:
                    result.unresolved[name] = f"used by {base}"
            for name in sorted(facts[path].includes):
                if name in MPI_INCLUDE_FILES:
                    result.mpi.append((path, f"include '{name}'"))
    # A module defined by several files of the closure (the metadata can
    # list both versions of a kernel): a CPU/OpenACC pair is a variant;
    # anything else cannot be built and is unresolved.
    definers: dict = {}
    for path in queue:
        for name in facts[path].modules:
            definers.setdefault(name, []).append(path)
    variant_files: set = set()
    for name, paths in sorted(definers.items()):
        if len(paths) < 2:
            continue
        pair = accel_variant_pair(paths)
        if pair:
            result.variants[name] = pair
            variant_files.update(pair)
        else:
            result.unresolved[name] = "defined in " + ", ".join(
                os.path.relpath(p, root_dir) if root_dir else p for p in paths
            ) + ", all needed by the scheme"
    result.sources = [p for p in queue if p not in variant_files]
    result.mpi_procedures = mpi_reach([facts[p] for p in queue], list(queue))
    return result


def mpi_reach(file_facts, paths) -> dict:
    """{procedure: how it reaches MPI} over the scopes of *file_facts* (one
    FortranSourceFacts per file of *paths*): a procedure reaches MPI if its
    own scope, or its module's specification part, USEs an MPI module or
    INCLUDEs mpif.h, or it CALLs (through generic interfaces too) a
    procedure that reaches MPI. Procedures are matched by name; one not
    defined in these files (e.g. the host model's) is not followed."""
    by_name: dict = {}
    module_mpi: dict = {}
    for facts, path in zip(file_facts, paths):
        base = os.path.basename(path)
        for scope in facts.scopes:
            direct = sorted(f"use {m}" for m in scope.uses & MPI_MODULES) + sorted(
                f"include '{i}'" for i in scope.includes & MPI_INCLUDE_FILES)
            if scope.name is None:
                if direct and scope.module:
                    module_mpi[scope.module] = f"module {scope.module}, which has {direct[0]} ({base})"
                continue
            by_name.setdefault(scope.name, []).append((scope, direct, base))
    chains: dict = {}  # name -> ([name, callee, ...], what the last one has)
    for name, entries in by_name.items():
        for scope, direct, base in entries:
            if direct:
                chains[name] = ([name], f"has {direct[0]} ({base})")
            elif scope.module in module_mpi:
                chains[name] = ([name], f"is in {module_mpi[scope.module]}")
            if name in chains:
                break
    changed = True
    while changed:
        changed = False
        for name, entries in by_name.items():
            if name in chains:
                continue
            callee = next((c for scope, _d, _b in entries for c in sorted(scope.calls)
                           if c in chains), None)
            if callee is not None:
                path, fact = chains[callee]
                chains[name] = ([name] + path, fact)
                changed = True
    return {name: ", which calls ".join(path).replace(", which calls ", " calls ", 1)
            + (", which " if len(path) > 1 else " ") + fact
            for name, (path, fact) in chains.items()}


def module_state_access(file_facts, entry: str, kind: str = "reads") -> dict:
    """The module variables procedure *entry* and the procedures it reaches
    read (*kind* "reads": mention), assign (*kind* "assigns") or may set
    (*kind* "sets": assign, or pass to a CALL), over the scopes of *file_facts* (one
    FortranSourceFacts per file): {(module, variable): procedure}, the
    first procedure found doing so. Matched by name: a procedure sees its
    own module's variables and those of the modules it, or its module,
    USEs (through an ONLY list's local names); names it declares itself
    hide them. Calls are followed through CALL statements, generic
    interfaces and function references (a defined procedure's name among
    the identifiers). scheme-io-capture-module-state-setup."""
    variables: dict = {}  # module -> its variables
    module_scopes: dict = {}
    by_name: dict = {}
    for facts in file_facts:
        for scope in facts.scopes:
            if scope.name is None:
                if scope.module:
                    module_scopes[scope.module] = scope
                    variables[scope.module] = scope.variables
                continue
            by_name.setdefault(scope.name, []).append(scope)
    found: dict = {}
    seen: set = set()
    queue = [entry.lower()]
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        for scope in by_name.get(name, ()):
            visible: dict = {}
            module_scope = module_scopes.get(scope.module)
            for module, only in scope.use_only + (module_scope.use_only if module_scope else ()):
                module_vars = variables.get(module, frozenset())
                if only is None:
                    for var in module_vars:
                        visible.setdefault(var, (module, var))
                else:
                    for local, remote in only:
                        if remote in module_vars:
                            visible[local] = (module, remote)
            for var in variables.get(scope.module, frozenset()):
                visible[var] = (scope.module, var)
            names = {"reads": scope.refs, "assigns": scope.assigns,
                     "sets": scope.assigns | scope.passes}[kind]
            for local in sorted(names - scope.declared):
                if local in visible:
                    found.setdefault(visible[local], scope.name)
            queue.extend(sorted(scope.calls | (scope.refs & by_name.keys())))
    return found


def resolve_real_kind(kind: "str | None", module: "str | None", file_facts) -> "str | None":
    """"kind_phys" (CCPP's own kind, from the generated ccpp_kinds),
    "double", "single" or None (unknown) for real kind name *kind* as
    module *module* sees it, through its named constants and USE
    renames over *file_facts* (e.g. coords_1d's r8 => shr_kind_r8 =
    selected_real_kind(12)). scheme-io-capture-ddt-args."""
    scopes = {}
    for facts in file_facts:
        for scope in facts.scopes:
            if scope.name is None and scope.module:
                scopes[scope.module] = scope
    name = (kind or "").lower()
    for _ in range(12):
        literal = name.replace(" ", "")
        if literal == "kind_phys":
            return "kind_phys"
        if literal in ("8", "real64", "c_double") or re.fullmatch(r"kind\(1(\.0*)?d0\)", literal):
            return "double"
        if literal in ("4", "real32", "c_float") or re.fullmatch(r"kind\(1(\.0*)?(e0)?\)", literal):
            return "single"
        match = re.fullmatch(r"selected_real_kind\((?:p=)?(\d+)", literal.split(",")[0].rstrip(")"))
        if match:
            return "double" if 7 <= int(match.group(1)) <= 15 else (
                "single" if int(match.group(1)) <= 6 else None)
        scope = scopes.get(module)
        if scope is None:
            return None
        value = dict(scope.parameters).get(name)
        if value is not None:
            name = value
            continue
        for used, only in scope.use_only:
            if only is None:
                other = scopes.get(used)
                if other is not None and name in dict(other.parameters):
                    module = used
                    break
            else:
                remote = dict(only).get(name)
                if remote is not None:
                    module, name = used, remote
                    break
        else:
            return None
    return None


@dataclass(frozen=True)
class CaptureLayout:
    """How the capture records a derived type, component by component
    (scheme-io-capture-ddt-args): its defining module and its components
    as (name, base type, rank, allocatable)."""

    type_name: str
    module: str
    components: tuple


def capture_layout(type_name: str, file_facts) -> "tuple[CaptureLayout | None, str]":
    """(CaptureLayout, "") for derived type *type_name* defined in
    *file_facts* when the capture can record it, else (None, why): every
    component public, not a pointer, integer, logical or real of a
    double-precision kind (kind_phys), rank at most 3; no parent type
    (EXTENDS), no derived-type, character or complex components."""
    type_name = type_name.lower()
    found = next((t for f in file_facts for t in f.types if t.name == type_name), None)
    if found is None:
        return None, f"no definition of type {type_name} in the scheme's sources"
    if found.extends:
        return None, f"type {type_name} extends {found.extends}"
    components = []
    for comp in found.components:
        what = f"component {comp.name} of type {type_name}"
        if not comp.public:
            return None, f"{what} is private"
        if comp.pointer:
            return None, f"{what} is a pointer"
        if comp.base not in ("real", "integer", "logical"):
            return None, f"{what} is {comp.type_name or comp.base}"
        if comp.rank > 3:
            return None, f"{what} has rank {comp.rank}"
        if comp.base == "real":
            if resolve_real_kind(comp.kind, found.module, file_facts) not in ("kind_phys", "double"):
                return None, f"{what} has kind {comp.kind or 'default'}, not kind_phys"
        elif comp.kind is not None:
            return None, f"{what} has kind {comp.kind}"
        components.append((comp.name, comp.base, comp.rank, comp.allocatable))
    if not components:
        return None, f"type {type_name} has no components"
    return CaptureLayout(type_name, found.module, tuple(components)), ""


def _is_ddt_or_host_table(f90_path: str) -> bool:
    """True if *f90_path* has a sibling ``.meta`` declaring a ``DDT`` or
    ``HOST``-type table.

    Confirmed this session, directly against real capgen-v1 source
    (``ccpp_capgen.py``): DDT and host tables "always contribute" to a
    build's dependency closure regardless of which scheme uses them, via
    their own separate, unconditional inclusion path -- not through any
    scheme's own ``dependencies=`` list. Real example confirmed: a scheme
    using a DDT type as one of its own argument types (e.g.
    ``examples/ddthost/scheme/make_ddt.F90``'s ``USE host_ccpp_ddt``, for
    the ``ccpp_info_t`` type of one of its arguments) does NOT list
    ``host_ccpp_ddt.F90`` in its own ``dependencies=`` -- confirmed against
    the real, already-authored ``make_ddt.meta``.

    A module with no sibling ``.meta`` at all (an ordinary plain-Fortran
    utility module, e.g. ``gw_utils.F90``) is never DDT/HOST -- there's
    nothing to classify it as, so it's treated as an ordinary dependency.
    """
    from xdsl_ccpp.frontend.ccpp_xml import parse_meta_file
    from xdsl_ccpp.util.ccpp_item import CCPPType

    meta_path = os.path.splitext(f90_path)[0] + ".meta"
    if not os.path.isfile(meta_path):
        return False
    for entry in parse_meta_file(meta_path, is_scheme=False):
        tp = entry.table_properties
        if tp.hasAttr("type") and tp.getAttr("type") in (CCPPType.DDT, CCPPType.HOST):
            return True
    return False


def resolve_scheme_dependencies(f90_path: str, root_dir: str) -> list[str]:
    """Return the ``dependencies=`` file-path list for the scheme at
    *f90_path*, mechanically derived from its own ``USE`` statements,
    resolved against a module-name index built from every ``.F90`` file
    under *root_dir*.

    Excluded: framework-provided modules, Fortran-intrinsic modules, a
    ``USE``d module that resolves to *f90_path* itself (a file never
    depends on itself), and any ``USE``d module that is itself a DDT/HOST
    table (always included via a separate mechanism -- see
    ``_is_ddt_or_host_table``). Any other ``USE``d module that can't be
    found anywhere under *root_dir* raises ``ValueError`` -- silently
    dropping a real dependency would be worse than failing loudly.

    Returned paths are relative to *f90_path*'s own directory, matching
    real ``.meta`` convention (e.g.
    ``../../to_be_ccppized/wv_saturation.F90``).
    """
    index = build_module_index(root_dir)
    used = extract_used_modules(f90_path)
    own_dir = os.path.dirname(os.path.abspath(f90_path))
    own_abs = os.path.abspath(f90_path)

    deps: list[str] = []
    unresolved: list[str] = []
    for module_name in sorted(used):
        if module_name in FRAMEWORK_MODULES or module_name in _INTRINSIC_MODULES:
            continue
        target = index.get(module_name)
        if target is None:
            unresolved.append(module_name)
            continue
        target_abs = os.path.abspath(target)
        if target_abs == own_abs:
            continue
        if _is_ddt_or_host_table(target):
            continue
        deps.append(os.path.relpath(target_abs, own_dir))

    if unresolved:
        raise ValueError(
            f"'{f90_path}': uses module(s) {sorted(unresolved)}, not found "
            f"anywhere under '{root_dir}' and not a known framework/"
            "intrinsic module -- narrow/widen root_dir, or add to the "
            "exclusion list if this is expected"
        )

    return deps
