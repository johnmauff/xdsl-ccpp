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

import os

# Framework-provided modules the generator itself unconditionally supplies
# (confirmed this session: real capgen-v1's `utility_paths` in
# ccpp_capgen.py, and xdsl_ccpp's own `_resolve_framework_f90_files()` in
# ccpp_datatable.py) -- never a scheme's own dependency to declare.
_FRAMEWORK_MODULES = {
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


def _parse(f90_path: str):
    import fparser.two.Fortran2003 as f03
    from fparser.two.parser import ParserFactory
    from fparser.common.readfortran import FortranStringReader

    ParserFactory().create(std="f2003")
    with open(f90_path, errors="replace") as f:
        source = f.read()
    return f03.Program(FortranStringReader(source))


def build_module_index(root_dir: str) -> dict[str, str]:
    """Walk every ``.F90`` file under *root_dir* and return a
    ``{module_name_lowercased: file_path}`` index.

    Raises ``ValueError`` if the same module name is defined in more than
    one file within *root_dir* -- a real, actionable ambiguity the caller
    should resolve by narrowing *root_dir*, not something to silently
    pick-one on.
    """
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    index: dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if not fname.lower().endswith(".f90"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                tree = _parse(path)
            except Exception:
                # Not every .F90 under root_dir need parse cleanly (e.g. a
                # file this project doesn't own, like a vendored external
                # library source) -- it simply can't contribute to the
                # index, not a reason to abort the whole scan.
                continue
            for module in walk(tree, f03.Module):
                module_stmt = module.children[0]
                name = str(module_stmt.children[1]).lower()
                if name in index and os.path.abspath(index[name]) != os.path.abspath(path):
                    raise ValueError(
                        f"module '{name}' is defined in more than one file "
                        f"within '{root_dir}': '{index[name]}' and '{path}' "
                        "-- narrow root_dir to resolve the ambiguity"
                    )
                index[name] = path
    return index


def extract_used_modules(f90_path: str) -> set[str]:
    """Return the (lowercased) set of module names *f90_path* itself
    ``USE``s, anywhere in the file."""
    import fparser.two.Fortran2003 as f03
    from fparser.two.utils import walk

    tree = _parse(f90_path)
    return {str(u.children[2]).lower() for u in walk(tree, f03.Use_Stmt)}


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
        if module_name in _FRAMEWORK_MODULES or module_name in _INTRINSIC_MODULES:
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
