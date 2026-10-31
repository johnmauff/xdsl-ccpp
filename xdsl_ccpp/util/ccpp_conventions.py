"""CCPP framework conventions — authoritative constants for standard names and mappings.

All strings here are defined by the CCPP specification and shared across the
frontend, transforms, and backend.  Import from here rather than duplicating
literals throughout the codebase.
"""

import contextlib
import re
import sys
from typing import NamedTuple

from xdsl.dialects import builtin

# ── Primitive Fortran types ──────────────────────────────────────────────────
# The set of CCPP "primitive" (non-derived) Fortran types -- anything else is
# a DDT type name. Previously redefined independently in three places
# (suite_variable_model.py twice, cpp_interop.py once) with no shared source
# of truth; consolidated here per the 2026-08-18 codebase complexity audit.
CCPP_PRIMITIVE_TYPES: frozenset = frozenset(
    {"real", "integer", "character", "logical", "complex"}
)

# ── Error handling ──────────────────────────────────────────────────────────
# CCPP framework-defined standard names for error communication.
CCPP_ERROR_MESSAGE = "ccpp_error_message"
CCPP_ERROR_CODE    = "ccpp_error_code"

# Both error standard names as a set — useful for membership tests.
CCPP_ERROR_STD_NAMES: frozenset = frozenset({CCPP_ERROR_MESSAGE, CCPP_ERROR_CODE})

# Local Fortran variable names used in generated caps for error handling.
CCPP_ERRMSG_LOCAL = "errmsg"
CCPP_ERRFLG_LOCAL = "errflg"

# Fixed length (in characters) of the errmsg buffer in all generated caps.
# The CCPP specification mandates 512; schemes declare character(len=512).
CCPP_ERRMSG_LEN = 512

# Fixed length (in characters) of the scheme_name buffer in all generated caps.
CCPP_SCHEME_NAME_LEN = 64

# Sentinel used when a subcycle loop count is a CCPP standard name (a runtime
# variable, not a literal integer). Any value > 1 causes the subcycle loop to
# be emitted; we assume a named loop count always means "loop more than once."
CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT = 2

# ── Framework-internal standard names ──────────────────────────────────────
# Variables managed entirely by the CCPP framework — schemes reference them
# but they are never matched to host model variables.
#
# number_of_ccpp_constituents is legitimately included here: audited every
# real capgen-v1 end-to-end test that uses this standard name (advection,
# advection_auto_clone, constituents_dim, instances_advection) and confirmed
# no host/module table anywhere ever declares it directly -- it is always
# either a dimension name or a scheme's own scalar arg, resolved through the
# framework's dynamic constituent-registration count
# (FRAMEWORK_STD_NAME_TO_CAP_VAR, cap_shared.py). A prior draft of this entry
# special-cased a host-declared occurrence to preserve examples/constadv's
# own such declaration, but that declaration was itself a leftover
# capgen-v0 pattern with no v1 counterpart -- fixed by removing it from
# constadv_host_mod.meta instead (constadv already registers its own
# dyn_const via the real v1 mechanism, so the framework count is correct
# there too), keeping this set simple rather than growing new xdsl_ccpp-side
# accommodation for vocabulary no real capgen-v1 example actually uses.
CCPP_FRAMEWORK_STD_NAMES: frozenset = frozenset({
    "horizontal_loop_extent",         # computed as col_end - col_start + 1
    "ccpp_constituents",              # constituent transport array
    "ccpp_constituent_tendencies",    # constituent tendency array
    "number_of_ccpp_constituents",    # count of registered constituents
})

# CCPP_INTERNAL_STD_NAMES is defined further below, after
# DISPATCH_SCALAR_STD_NAMES (which it now builds on) -- see that section.

# ── Dimension semantic classes ───────────────────────────────────────────────
# Any two dimension names within the same class are considered compatible for
# variable matching purposes, matching capgen-ng's equivalence-class approach.
# Includes compound range forms (ccpp_constant_one:X and begin:end notation)
# exactly as they appear in .meta dimension strings.
CCPP_HORIZONTAL_DIMENSIONS: frozenset = frozenset({
    "horizontal_dimension",
    "horizontal_loop_extent",
    "ccpp_constant_one:horizontal_dimension",
    "ccpp_constant_one:horizontal_loop_extent",
    "horizontal_loop_begin:horizontal_loop_end",
})

CCPP_VERTICAL_DIMENSIONS: frozenset = frozenset({
    "vertical_layer_dimension",
    "vertical_interface_dimension",
    "vertical_layer_index",
    "vertical_interface_index",
    "ccpp_constant_one:vertical_layer_dimension",
    "ccpp_constant_one:vertical_interface_dimension",
})


def is_horizontal_dimension(dim_name: str) -> bool:
    """Return True if dim_name is a recognized CCPP horizontal dimension."""
    return dim_name.lower() in CCPP_HORIZONTAL_DIMENSIONS


def is_vertical_dimension(dim_name: str) -> bool:
    """Return True if dim_name is a recognized CCPP vertical dimension."""
    return dim_name.lower() in CCPP_VERTICAL_DIMENSIONS


def dims_compatible(dim1: str, dim2: str, gfs_dim_aliases: bool = False) -> bool:
    """Return True if two CCPP dimension standard names are semantically compatible.

    Compatibility means both names belong to the same CCPP dimension equivalence
    class (horizontal or vertical), following capgen-ng's semantic equivalence
    model.  Exact equality is also compatible.

    gfs_dim_aliases -- opt-in only (--gfs-dim-aliases), off by default, matching
    capgen-v1's own posture: unlike the always-on classes above, collapsing
    CCPP_GFS_DIM_ALIASES' GFS-specific names to their canonical vertical axis is
    a lossy, physics-specific assumption real capgen-v1 also gates behind an
    explicit flag rather than applying unconditionally. When True, each side is
    canonicalized through CCPP_GFS_DIM_ALIASES before the exact-match/
    equivalence-class checks below, exactly matching capgen-v1's own
    dim_aliases.py: collapsed only for this comparison, never a rename.
    """
    d1, d2 = dim1.lower(), dim2.lower()
    if gfs_dim_aliases:
        d1 = CCPP_GFS_DIM_ALIASES.get(d1, d1)
        d2 = CCPP_GFS_DIM_ALIASES.get(d2, d2)
    if d1 == d2:
        return True
    return (
        (d1 in CCPP_HORIZONTAL_DIMENSIONS and d2 in CCPP_HORIZONTAL_DIMENSIONS)
        or (d1 in CCPP_VERTICAL_DIMENSIONS and d2 in CCPP_VERTICAL_DIMENSIONS)
    )


# ── GFS-physics vertical-axis aliases (opt-in via --gfs-dim-aliases) ────────
# Mirrors real capgen-v1's own metadata/dim_aliases.py _DIM_ALIAS_MAP exactly
# (confirmed against source, capgen_v1_vocabulary.md §4): a handful of GFS
# radiation/chemistry scheme groups declare a vertical-layer-count dimension
# under a differently-spelled standard_name for historical reasons. Unlike
# CCPP_DEPRECATED_STD_NAMES above, this is deliberately NOT a rename -- each
# name also carries meaning as its own standalone control variable elsewhere,
# so dims_compatible() only consults this map at comparison time, never
# rewrites a declaration.
CCPP_GFS_DIM_ALIASES: dict = {
    "adjusted_vertical_layer_dimension_for_radiation": "vertical_layer_dimension",
    "vertical_composition_dimension": "vertical_layer_dimension",
}


# ── Dimension name substitutions (legacy / documentation) ───────────────────
# Kept for reference; host_var_match_pass.py uses dims_compatible() instead.
CCPP_DIM_SUBSTITUTIONS: dict = {
    "horizontal_loop_extent": "horizontal_dimension",
    "horizontal_dimension":   "horizontal_loop_extent",
    "ccpp_constant_one:horizontal_loop_extent": "ccpp_constant_one:horizontal_dimension",
    "ccpp_constant_one:horizontal_dimension":   "ccpp_constant_one:horizontal_loop_extent",
    "vertical_layer_dimension":     "vertical_interface_dimension",
    "vertical_interface_dimension": "vertical_layer_dimension",
}

# ── Loop bound and dimension standard names ────────────────────────────────
# Match by these standard names rather than local variable names (which vary:
# 'ncol', 'foo', 'nbox' all map to horizontal_loop_extent across different schemes).
CCPP_LOOP_EXTENT_STD_NAME = "horizontal_loop_extent"   # column count
CCPP_LOOP_BEGIN_STD_NAME  = "horizontal_loop_begin"    # first column index
CCPP_LOOP_END_STD_NAME    = "horizontal_loop_end"      # last column index
CCPP_HORIZ_DIM_STD_NAME   = "horizontal_dimension"     # size of horizontal dimension
CCPP_VERT_DIM_STD_NAME    = "vertical_layer_dimension" # number of vertical layers

# Real capgen-v1's multi-instance model ("instances/instances_advection"
# entry): a scalar with this standard name,
# threaded as an ordinary caller-supplied dummy argument, selects which
# entry of a HOST-owned array-of-DDT (dimensioned by number_of_instances,
# see cap_shared.py's _build_ddt_resolution_maps) the current call operates
# on. Not a dispatch scalar (DISPATCH_SCALAR_STD_NAMES above) -- it's real
# host state that happens to also serve as an array index, not a fixed
# CCPP-protocol parameter every call has regardless of any scheme's own
# metadata.
CCPP_INSTANCE_NUMBER_STD_NAME = "instance_number"

# Companion to CCPP_INSTANCE_NUMBER_STD_NAME above: the number of model
# instances, also threaded as an ordinary caller-supplied dummy argument
# (real capgen-v1 never use-associates either -- both are genuine runtime
# HOST scalars with no guaranteed backing Fortran module, e.g. a driver-only
# test_host.meta with no test_host.F90 at all). Used to size
# ccpp_suite_state (suite_cap.py's _build_suite_state_lazy_alloc), one entry
# per instance.
CCPP_NUMBER_OF_INSTANCES_STD_NAME = "number_of_instances"

# Real capgen-v1's per-thread analog of instance_number above: a scalar
# with this standard name indexes a HOST-owned per-OpenMP-thread container
# DDT (dimensioned by number_of_threads, see CCPP_SCALAR_INDEX_DIMS below),
# threaded as an ordinary caller-supplied dummy argument exactly like
# instance_number -- never use-associated. Unlike instance_number, real
# capgen-v1's own framework reads no extra per-thread state from this pair
# today (no per-thread equivalent of ccpp_suite_state/lc_instances): it is
# genuinely "substitution-only," confirmed directly against capgen-v1's own
# generator/suite_cap.py and generator/suite_data.py (zero references to
# either name in either file, vs. 22+3 for the instance pair there).
CCPP_THREAD_NUMBER_STD_NAME = "thread_number"

# Companion to CCPP_THREAD_NUMBER_STD_NAME above: the total thread count,
# also threaded as an ordinary caller-supplied dummy argument. Carried for
# symmetry with number_of_instances (real capgen-v1's own
# doc/migration.md §1.7: "kept... so the framework can size per-thread
# state in future"), but not consumed for sizing by anything today.
CCPP_NUMBER_OF_THREADS_STD_NAME = "number_of_threads"

# Real capgen-v1's single-source-of-truth table of "registered scalar-index
# dimensions" (capgen/metadata/registered_dimensions.py's SCALAR_INDEX_DIMS):
# a container DDT-instance variable dimensioned by the KEY standard name gets
# its scalar index substituted from the VALUE standard name at every scheme
# call site that reaches into it (run_dispatch.py's sibling-arg lookup,
# suite_cap.py's _active_expr_ddt_member_indexes). Real capgen-v1 treats
# instance_number/number_of_instances and thread_number/number_of_threads as
# two symmetric entries in this one table; xdsl-ccpp's own
# ccpp_suite_state/constituent-API per-instance machinery is a SEPARATE,
# instance_number-only concern layered on top (see
# CCPP_NUMBER_OF_INSTANCES_STD_NAME's own comment above) -- this table only
# governs the generic container-subscript substitution, nothing else.
CCPP_SCALAR_INDEX_DIMS: dict = {
    CCPP_NUMBER_OF_INSTANCES_STD_NAME: CCPP_INSTANCE_NUMBER_STD_NAME,
    CCPP_NUMBER_OF_THREADS_STD_NAME: CCPP_THREAD_NUMBER_STD_NAME,
}

# ── Dispatch-scalar standard names (vocabulary-resolution redesign, Stage 1) ─
# A small, fixed set of CCPP-protocol standard names that behave as generic,
# call-scoped dispatch parameters rather than real host-owned state --
# confirmed by direct inspection of every example's own generic,
# control-derived host table (opt_arg/var_compat/chunked_data/suite_allocate/
# .../test_host.meta): every one of them declares exactly this same 4-name
# set and nothing else; no example's .meta anywhere declares a standard_name
# for thread_num/nthreads/nphys_threads/suite_name/group_name -- those are
# synthesized directly by the code generator, never host-matched. Real
# capgen-v1 threads this same small set as plain scalar arguments (its own
# lb/ub/errmsg/errflg) while resolving every other host-declared variable via
# use-association, regardless of whether xdsl_ccpp would call its owning
# table "host" or "module" type. xdsl_ccpp's own HOST-type table currently
# conflates this set with genuine host state (data.meta's std_arg,
# test_host_mod.meta's phys_state/has_graupel, ...), which is what forces
# every HOST-type reference to be threaded as a block argument today --
# part of the vocabulary-resolution redesign, Stage 1.
# This is the classifier later stages use to tell the two apart. A real
# `CONTROL` table type now exists (type-control-gap) for tables that are
# properly migrated, but this name-based set stays as the authority for
# host_var_match_pass.py's skip-list (see CCPP_INTERNAL_STD_NAMES below) --
# it works correctly regardless of whether a given .meta file's table has
# been migrated to CONTROL yet, a useful defense-in-depth property for an
# only-partially-migrated corpus.
DISPATCH_SCALAR_STD_NAMES: frozenset = frozenset(
    {CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME} | CCPP_ERROR_STD_NAMES
)


def is_dispatch_scalar_std_name(standard_name: str) -> bool:
    """True if standard_name is one of the fixed CCPP-protocol dispatch
    scalars (loop bounds, error handling) rather than real host state.
    """
    return standard_name.lower() in DISPATCH_SCALAR_STD_NAMES


# The full set of names the host variable match pass skips unconditionally,
# before any model_var_index lookup -- error-handling and framework-internal
# names only. Deliberately does NOT include the two loop-bound dispatch
# scalars (horizontal_loop_begin/horizontal_loop_end, see
# DISPATCH_SCALAR_STD_NAMES above): unlike errmsg/errflg, these can
# legitimately be matched via a DDT-member chain (e.g. ddthost/capgen's
# ccpp_info_t bundling pattern) with a real backing Fortran derived-type
# component -- that case must still get the full match+compatibility-check
# treatment. Only a BARE, non-DDT HOST/CONTROL-table declaration of one of
# these two names (no real backing declaration at all) should be skipped --
# see host_var_match_pass.py's own is_ddt check at its match-lookup site,
# which is where that narrower distinction is actually applied
# (type-control-gap).
CCPP_INTERNAL_STD_NAMES: frozenset = CCPP_ERROR_STD_NAMES | CCPP_FRAMEWORK_STD_NAMES

# The subset of DISPATCH_SCALAR_STD_NAMES that can be legitimately matched
# via a DDT-member chain as well as (or instead of) a bare host table scalar
# -- just the two loop-bound names, not the error names (which always skip
# unconditionally above, matching their existing, unaffected behavior).
CCPP_LOOP_BOUND_STD_NAMES: frozenset = frozenset(
    {CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME}
)


# ── Deprecated standard names ────────────────────────────────────────────────
# Rejected by default, matching real capgen-v1's own strict posture; still
# fully supported (parsed and handled exactly as before, via suite_cap.py's
# column-chunking synthesis) when --legacy-mode is passed, matching
# capgen-v1's own --legacy-mode flag. Every example in this repo has already
# migrated off these names in favor of the replacement; new metadata should
# use the replacement instead.
CCPP_DEPRECATED_STD_NAMES: dict = {
    CCPP_LOOP_EXTENT_STD_NAME: CCPP_HORIZ_DIM_STD_NAME,
    # task11-omp-thread item 1: real capgen-v1's own legacy_compat.py maps
    # this the same way, gated behind the identical --legacy-mode shim.
    # Cosmetic only -- xdsl-ccpp's --legacy-mode gate warns-and-accepts a
    # deprecated name but never rewrites it for downstream matching (see
    # CCPP_LOOP_EXTENT_STD_NAME's own case: it only actually resolves
    # because horizontal_loop_extent/horizontal_dimension are ALSO both
    # members of CCPP_HORIZONTAL_DIMENSIONS, consulted separately by
    # dims_compatible()). number_of_openmp_threads/number_of_threads are
    # scalar counts, not dimension names, so there is no equivalent
    # equivalence-class mechanism for this entry to piggyback on -- it
    # only suppresses the reject-unknown-name error under --legacy-mode,
    # it does not make a host declaring the old name actually resolve
    # against a scheme/CCPP_SCALAR_INDEX_DIMS consumer expecting the new
    # one.
    "number_of_openmp_threads": CCPP_NUMBER_OF_THREADS_STD_NAME,
}

# Set once per process (by each frontend's CLI entry point) from --legacy-mode.
# A plain module global rather than a threaded parameter: ArgumentOp is
# constructed from dozens of call sites across three independent frontends
# (ccpp_xml.py, py_api.py, and ccpp_dsl.py's merge_meta_files),
# and only one of those (ccpp_xml.py) even runs in-process with the CLI that
# parses the flag -- the others would need it threaded through unrelated
# constructor signatures for no benefit.
_LEGACY_MODE_ENABLED = False


def set_legacy_mode(enabled: bool) -> None:
    """Enable or disable acceptance of deprecated standard names for this process."""
    global _LEGACY_MODE_ENABLED
    _LEGACY_MODE_ENABLED = bool(enabled)


def is_legacy_mode() -> bool:
    """Return True if --legacy-mode was set for this process."""
    return _LEGACY_MODE_ENABLED


def deprecated_std_name_warning(std_name: str) -> str | None:
    """Return a warning message if std_name is deprecated, else None.

    Case-insensitive; matches capgen.py's ArgumentOp handling of standard
    names and dimension names alike. Used for both the --legacy-mode warning
    text and the default-mode rejection text (see ArgumentOp.__init__).
    """
    replacement = CCPP_DEPRECATED_STD_NAMES.get(std_name.lower())
    if replacement is None:
        return None
    return (
        f"standard_name '{std_name}' is deprecated -- use '{replacement}' instead "
    )


# Verbosity of generator messages for this process: 0 quiet, 1 normal (the
# default), 2 detailed. Set by each frontend's entry point from --verbose,
# like set_legacy_mode.
_VERBOSITY = 1


def set_verbosity(level: int) -> None:
    """Set this process's message verbosity (0, 1 or 2)."""
    global _VERBOSITY
    _VERBOSITY = int(level)


def verbosity() -> int:
    """This process's message verbosity (0 quiet, 1 normal, 2 detailed)."""
    return _VERBOSITY


# Deprecated standard names accepted under --legacy-mode, recorded where each
# ArgumentOp is built (one per argument, per standard or dimension name) and
# printed once per process by report_deprecated_uses, so the list can be
# summarised. Each record: (deprecated name, .meta file, argument name).
_DEPRECATED_USES: list[tuple[str, str, str]] = []
_DEPRECATION_SOURCE = ""


@contextlib.contextmanager
def deprecation_source(path: str):
    """Attribute the deprecated names recorded in this block to *path*."""
    global _DEPRECATION_SOURCE
    previous, _DEPRECATION_SOURCE = _DEPRECATION_SOURCE, path
    try:
        yield
    finally:
        _DEPRECATION_SOURCE = previous


@contextlib.contextmanager
def deprecation_records_discarded():
    """Drop the deprecated names recorded in this block, for code that builds
    ArgumentOps from .meta files another step already reports (the
    Fortran-vs-.meta check)."""
    kept = len(_DEPRECATED_USES)
    try:
        yield
    finally:
        del _DEPRECATED_USES[kept:]


def record_deprecated_use(arg_name: str, std_name: str) -> None:
    """Record that *arg_name* uses the deprecated *std_name* (--legacy-mode)."""
    _DEPRECATED_USES.append((std_name.lower(), _DEPRECATION_SOURCE, arg_name))


def deprecated_use_report(level: int) -> list[str]:
    """The lines report_deprecated_uses prints at *level*: none at 0; one
    line per deprecated name at 1; at 2, that line followed by the arguments
    grouped by .meta file."""
    if level <= 0:
        return []
    lines = []
    for name in dict.fromkeys(n for n, _, _ in _DEPRECATED_USES):
        uses = [(src, arg) for n, src, arg in _DEPRECATED_USES if n == name]
        files = list(dict.fromkeys(src for src, _ in uses))
        where = f"{len(uses)} uses in {len(files)} .meta files"
        hint = "" if level >= 2 else "; --verbose 2 lists them"
        lines.append(
            f"Warning(LEGACY): {deprecated_std_name_warning(name).strip()} "
            f"({where}{hint})"
        )
        if level >= 2:
            for src in files:
                args = [arg for s, arg in uses if s == src]
                counts = {a: args.count(a) for a in dict.fromkeys(args)}
                listed = ", ".join(a if c == 1 else f"{a} (x{c})" for a, c in counts.items())
                lines.append(f"  {src or '<unknown file>'}: {listed}")
    return lines


def report_deprecated_uses() -> None:
    """Print the deprecated names recorded so far (at this process's
    verbosity) to stderr, and forget them."""
    for line in deprecated_use_report(_VERBOSITY):
        print(line, file=sys.stderr)
    _DEPRECATED_USES.clear()

# ── Unit conversion table ────────────────────────────────────────────────────
# Maps (scheme_units, host_units) → (to_scheme, to_host), each an
# (operation, factor) pair for UnitConvertOp/UnitWriteBackOp: the value is
# converted by "add", "sub" or "mul" with the factor, a real literal kept as
# written (e.g. "1.0E6").
#
# Units are matched after lowercasing and stripping whitespace.
UNIT_CONVERSIONS: dict = {
    # Temperature
    ("k",    "degc"): (("add", "273.15"), ("sub", "273.15")),
    ("degc", "k"):    (("sub", "273.15"), ("add", "273.15")),
    # Pressure
    ("pa",   "hpa"):  (("mul", "100.0"), ("mul", "0.01")),
    ("hpa",  "pa"):   (("mul", "0.01"), ("mul", "100.0")),
    # Length
    ("m",    "cm"):   (("mul", "0.01"), ("mul", "100.0")),
    ("cm",   "m"):    (("mul", "100.0"), ("mul", "0.01")),
    # Mixing ratio
    ("kg kg-1", "g g-1"):  (("mul", "0.001"), ("mul", "1000.0")),
    ("g g-1",   "kg kg-1"): (("mul", "1000.0"), ("mul", "0.001")),
    # Speed
    ("m s-1",  "cm s-1"): (("mul", "0.01"), ("mul", "100.0")),
    ("cm s-1", "m s-1"):  (("mul", "100.0"), ("mul", "0.01")),
    # Length (micrometer)
    ("um", "m"): (("mul", "1.0E6"), ("mul", "1.0E-6")),
    ("m", "um"): (("mul", "1.0E-6"), ("mul", "1.0E6")),
    # Length (kilometer)
    ("km", "m"): (("mul", "0.001"), ("mul", "1000.0")),
    ("m", "km"): (("mul", "1000.0"), ("mul", "0.001")),
    # Specific energy — "j kg-1" and "m2 s-2" are dimensionally identical
    # (1 J/kg = 1 (kg m2 s-2) / kg = 1 m2 s-2), so this is a same-magnitude
    # relabeling rather than a real numeric conversion.
    ("m2 s-2", "j kg-1"): (("mul", "1.0"), ("mul", "1.0")),
    ("j kg-1", "m2 s-2"): (("mul", "1.0"), ("mul", "1.0")),
}

# Unit strings that are all considered dimensionless — mutually compatible.
CCPP_DIMENSIONLESS_UNITS: frozenset = frozenset(
    {"1", "none", "count", "frac", "nondimensional", "fraction", ""}
)

def normalize_units(units: str | None) -> str:
    """Return a canonical lowercase-stripped unit string for comparison.

    Also drops an explicit "+" sign on a positive exponent (e.g. "m+2 s-2"
    -> "m2 s-2") -- some CCPP metadata spells positive exponents out
    symmetrically with negative ones ("s-1"), but this is a notation
    variant of the identical unit, not a distinct one.
    """
    if units is None:
        return ""
    normalized = units.strip().lower()
    return re.sub(r"(?<=[a-z])\+(?=\d)", "", normalized)

# ── Kind (precision) mappings ───────────────────────────────────────────────
# Maps CCPP kind names to ISO_FORTRAN_ENV named constants.
CCPP_KIND_TO_ISO: dict = {
    "kind_phys": "REAL64",
}


def real_kind_width(kind: str) -> "int | None":
    """Return 4 or 8 if `kind` is a bare numeric Fortran KIND literal for
    one of the two supported IEEE widths (single/double precision), else
    None -- a named/symbolic kind like "kind_phys", or an unsupported
    numeric literal (e.g. "16", quad precision -- TypeConversions.convert
    only maps to Float32Type/Float64Type, so any other digit string must
    NOT be classified here or it would be silently misclassified as
    double precision instead of staying on the symbolic RealKindType
    path; Copilot PR #115 review).

    A bare digit is already valid, self-contained Fortran (`real(kind=8)`)
    with no portable kind-name meaning to preserve -- unlike a named kind,
    whose own symbolic name must stay intact in the generated declaration
    (see RealKindType's own docstring). This is intentionally separate
    from suite_kinds.py's own `isdigit()` check, which answers a different
    question (whether a kind needs a `public ::` export), not a width.
    """
    if kind in ("4", "8"):
        return int(kind)
    return None

#: ``kind_spec`` value in a ``[ccpp-table-properties]`` block -- matches real
#: capgen-v1's own syntax (``metadata/metadata_table.py``'s ``_KIND_SPEC_RE``).
#: Two accepted forms:
#:
#:   <module>:<kind_name>=>spec   -- explicit CCPP-visible kind name
#:   <module>:<spec>              -- shorthand; kind_name defaults to spec
#:
#: Captured groups: (module, kind_name_or_None, spec).
_KIND_SPEC_RE = re.compile(
    r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*'
    r'(?:([A-Za-z][A-Za-z0-9_]*)\s*=>\s*)?'
    r'([A-Za-z][A-Za-z0-9_]*)\s*$'
)


def parse_kind_spec_value(value: str) -> tuple[str, str, str]:
    """Parse one ``kind_spec`` value into ``(kind_name, module, spec)``.

    Accepted syntax::

        <module>:<kind_name>=>spec   # explicit CCPP-visible kind name
        <module>:<spec>              # kind_name defaults to spec

    Shared by both `frontend/ccpp_xml.py` (parses ``kind_spec`` out of a
    ``.meta`` file's table properties) and `transforms/suite_kinds.py`
    (decodes the same canonical string back out of IR attributes) -- lives
    here, not in either module, so neither the frontend nor a transform pass
    has to import the other's implementation.

    >>> parse_kind_spec_value('temp_kinds:kind_temp=>temp_r8')
    ('kind_temp', 'temp_kinds', 'temp_r8')
    >>> parse_kind_spec_value('host_kinds:kind_r8')
    ('kind_r8', 'host_kinds', 'kind_r8')
    """
    match = _KIND_SPEC_RE.match(value)
    if match is None:
        raise ValueError(
            f"Malformed kind_spec '{value}': expected "
            "<module>:<kind_name>=>spec or <module>:<spec>"
        )
    module, kind_name, spec = match.group(1), match.group(2), match.group(3)
    if kind_name is None:
        kind_name = spec
    return kind_name, module, spec


# Convenience constant for the primary physics precision kind.
CCPP_KIND_PHYS = "kind_phys"


# Per-argument attributes (func.FuncOp arg_attrs) on generated subroutines:
# what each dummy argument is. Set by the suite cap on suite subroutines
# (suite_arg_attrs) and by the host cap on the functions that pass them
# through; read by later passes and by the printers instead of parsing
# argument names. Names live here too because xDSL rewrites name hints
# (a trailing "_<digits>" is dropped: opt_var_2 -> opt_var).
SUITE_ARG_NAME = "ccpp.name"                # Fortran dummy-argument name
SUITE_ARG_STD_NAME = "ccpp.standard_name"
SUITE_ARG_DIM_NAMES = "ccpp.dim_names"      # dimension standard names
SUITE_ARG_INTENT = "ccpp.intent"            # merged across the schemes sharing it
SUITE_ARG_OPTIONAL = "ccpp.optional"        # UnitAttr
SUITE_ARG_ALLOCATABLE = "ccpp.allocatable"  # UnitAttr
# The intent to declare, as given -- for a generated function whose interface
# is fixed (e.g. ccpp_physics_suite_variables). Without it the printers infer
# intent from how the function uses the argument (classify_arg_intent).
SUITE_ARG_DECLARED_INTENT = "ccpp.declared_intent"
SUITE_ARG_POINTER = "ccpp.pointer"          # UnitAttr; also on allocas (locals, results)
SUITE_ARG_TARGET = "ccpp.target"            # UnitAttr

# Function-level attributes of a generated func.FuncOp.
# FN_RESULT: the function's single returned alloca is a Fortran FUNCTION
# result (printed `function f(...) result(<name>)`), not an intent(out)
# argument.
FN_RESULT = "ccpp.function_result"          # UnitAttr
# FN_USES: modules the function itself USEs, {module: [names]}.
FN_USES = "ccpp.uses"                       # DictionaryAttr[str, ArrayAttr[StringAttr]]
# FN_FIXED_INTERFACE: built by cap_shared.fixed_interface_fn -- its body does
# everything itself (e.g. a BIND(C) routine's own character copies), so the
# printer adds nothing it would infer for other functions.
FN_FIXED_INTERFACE = "ccpp.fixed_interface"  # UnitAttr



def arg_attr_values(fn_op) -> list:
    """A function's per-argument attributes as plain values, one dict per
    argument: str for StringAttr, list[str] for ArrayAttr, True for
    UnitAttr; empty dicts when the function has none."""
    n = len(fn_op.body.blocks[0].args) if fn_op.body.blocks else len(fn_op.function_type.inputs)
    if fn_op.arg_attrs is None:
        return [{} for _ in range(n)]
    values = []
    for d in fn_op.arg_attrs.data:
        entry = {}
        for k, v in d.data.items():
            if isinstance(v, builtin.ArrayAttr):
                entry[k] = [x.data for x in v.data]
            elif isinstance(v, builtin.UnitAttr):
                entry[k] = True
            else:
                entry[k] = v.data
        values.append(entry)
    return values


def arg_attr_dict(values: dict) -> builtin.DictionaryAttr:
    """The inverse of arg_attr_values for one argument."""
    out = {}
    for k, v in values.items():
        if v is True:
            out[k] = builtin.UnitAttr()
        elif isinstance(v, list):
            out[k] = builtin.ArrayAttr([builtin.StringAttr(x) for x in v])
        elif v not in (None, False):
            out[k] = builtin.StringAttr(v)
    return builtin.DictionaryAttr(out)


class ArgDecl(NamedTuple):
    """How a printer declares one dummy argument."""
    name: str
    is_alloc: bool  # allocatable (intent(inout))
    is_opt: bool    # optional
    is_in: bool     # an array narrowed to intent(in)
    declared_intent: "str | None" = None  # SUITE_ARG_DECLARED_INTENT, if any
    is_pointer: bool = False
    is_target: bool = False


def arg_decl(attrs: dict, name_hint: "str | None", idx: int) -> ArgDecl:
    """Name and declaration flags of dummy argument *idx*, from its
    arg_attrs (*attrs*, plain values). A function that records no name
    for it (e.g. one built by hand in a test) gets its name hint, or a
    positional name. Allocatable takes precedence over optional, and
    either over intent(in), which narrows only arrays. A declared intent
    (SUITE_ARG_DECLARED_INTENT) overrides all of them."""
    name = attrs.get(SUITE_ARG_NAME) or name_hint or f"arg_{idx}"
    is_alloc = bool(attrs.get(SUITE_ARG_ALLOCATABLE))
    is_opt = not is_alloc and bool(attrs.get(SUITE_ARG_OPTIONAL))
    is_in = (not is_alloc and not is_opt
             and attrs.get(SUITE_ARG_INTENT) == "in"
             and bool(attrs.get(SUITE_ARG_DIM_NAMES)))
    return ArgDecl(
        name, is_alloc, is_opt, is_in, attrs.get(SUITE_ARG_DECLARED_INTENT),
        bool(attrs.get(SUITE_ARG_POINTER)), bool(attrs.get(SUITE_ARG_TARGET)),
    )


def name_local(alloca, name: str) -> None:
    """Name the local variable a memref.AllocaOp declares: the name goes in
    the op's attributes (SUITE_ARG_NAME), where the printer reads it -- the
    name hint is only a hint (xDSL drops a trailing "_<digits>" from it)."""
    alloca.attributes[SUITE_ARG_NAME] = builtin.StringAttr(name)
    alloca.memref.name_hint = name


def mark_allocatable_local(alloca, name: str) -> None:
    """name_local, and make the local allocatable (SUITE_ARG_ALLOCATABLE)."""
    name_local(alloca, name)
    alloca.attributes[SUITE_ARG_ALLOCATABLE] = builtin.UnitAttr()


def mark_pointer_local(alloca, name: str) -> None:
    """name_local, and make the local a POINTER (SUITE_ARG_POINTER); an
    array one is deferred-shape, its rank given by the alloca's shape."""
    name_local(alloca, name)
    alloca.attributes[SUITE_ARG_POINTER] = builtin.UnitAttr()


def is_pointer_local(alloca) -> bool:
    """Whether mark_pointer_local marked a memref.AllocaOp a pointer."""
    return SUITE_ARG_POINTER in alloca.attributes


def local_name(alloca) -> "str | None":
    """The name name_local recorded on a memref.AllocaOp, if any."""
    name = alloca.attributes.get(SUITE_ARG_NAME)
    return name.data if name is not None else None


def is_allocatable_local(alloca) -> bool:
    """Whether mark_allocatable_local marked a memref.AllocaOp allocatable."""
    return SUITE_ARG_ALLOCATABLE in alloca.attributes
