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
    (*name* None, which applies to all the module's procedures)."""

    name: "str | None"
    module: "str | None"
    uses: frozenset
    includes: frozenset
    calls: frozenset


@dataclass(frozen=True)
class FortranSourceFacts:
    """What one Fortran file declares and needs (lowercased names)."""

    uses: frozenset  # modules USEd anywhere in the file
    modules: frozenset  # modules the file defines
    includes: frozenset  # files named by Fortran INCLUDE lines
    scopes: tuple = ()  # ScopeFacts per procedure and module specification part


class _ScopeBuilder:
    def __init__(self, name, module):
        self.name, self.module = name, module
        self.uses: set = set()
        self.includes: set = set()
        self.calls: set = set()

    def freeze(self) -> ScopeFacts:
        return ScopeFacts(self.name, self.module, frozenset(self.uses),
                          frozenset(self.includes), frozenset(self.calls))


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
        try:
            if first == "use" or lower.startswith("use,"):
                name = str(f03.Use_Stmt(line).children[2]).lower()
                uses.add(name)  # an interface body's too: the file needs it
                if not interface_depth:
                    current().uses.add(name)
            elif first == "include":
                name = str(f03.Include_Stmt(line).children[0]).lower()
                includes.add(name)
                if not interface_depth:
                    current().includes.add(name)
            elif first == "call":
                current().calls.add(_called_name(f03.Call_Stmt(line)))
            elif first == "if" and " call " in f" {lower}":
                for call in walk(f03.If_Stmt(line), f03.Call_Stmt):
                    current().calls.add(_called_name(call))
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
                              tuple(scopes))


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


def source_closure(
    start_files, root_dir: "str | None", provided=frozenset(),
    preproc_defs: "dict[str, str | None] | None" = None,
) -> SourceClosure:
    """Follow the USE statements of *start_files* (and of each file added)
    through the ``.F90`` files under *root_dir*: every module they use that
    is not intrinsic, not MPI and not in *provided* (lowercased names the
    build supplies otherwise) must be defined by a file already in the
    closure, or by exactly one file under *root_dir*, which is added.
    Modules found nowhere, or in several files, are *unresolved*; MPI use
    (MPI_MODULES, MPI_INCLUDE_FILES) is listed in *mpi*. The index of
    *root_dir* is built only when a module is not defined by the files at
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
    index = None
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
                if index is None:
                    index = module_definitions(root_dir) if root_dir else {}
                found = index.get(name, [])
                if len(found) == 1:
                    target = os.path.abspath(found[0])
                    defined[name] = target
                    if target not in seen:
                        seen.add(target)
                        queue.append(target)
                elif found:
                    result.unresolved[name] = (
                        f"used by {base}; defined in {len(found)} files under {root_dir}"
                    )
                else:
                    result.unresolved[name] = f"used by {base}"
            for name in sorted(facts[path].includes):
                if name in MPI_INCLUDE_FILES:
                    result.mpi.append((path, f"include '{name}'"))
    result.sources = list(queue)
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
