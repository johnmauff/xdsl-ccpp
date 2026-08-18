"""CCPP framework conventions — authoritative constants for standard names and mappings.

All strings here are defined by the CCPP specification and shared across the
frontend, transforms, and backend.  Import from here rather than duplicating
literals throughout the codebase.
"""

import re

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

# The full set of names the host variable match pass skips without error.
# Includes both error-handling names and framework-internal names.
CCPP_INTERNAL_STD_NAMES: frozenset = CCPP_ERROR_STD_NAMES | CCPP_FRAMEWORK_STD_NAMES

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


def dims_compatible(dim1: str, dim2: str) -> bool:
    """Return True if two CCPP dimension standard names are semantically compatible.

    Compatibility means both names belong to the same CCPP dimension equivalence
    class (horizontal or vertical), following capgen-ng's semantic equivalence
    model.  Exact equality is also compatible.
    """
    d1, d2 = dim1.lower(), dim2.lower()
    if d1 == d2:
        return True
    return (
        (d1 in CCPP_HORIZONTAL_DIMENSIONS and d2 in CCPP_HORIZONTAL_DIMENSIONS)
        or (d1 in CCPP_VERTICAL_DIMENSIONS and d2 in CCPP_VERTICAL_DIMENSIONS)
    )


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
# see ccpp_cap_refactor_plan.md's vocabulary-resolution redesign, Stage 1.
# This is the classifier later stages use to tell the two apart; nothing
# reads it yet (Stage 1 is classification only, no behavior change).
DISPATCH_SCALAR_STD_NAMES: frozenset = frozenset(
    {CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME} | CCPP_ERROR_STD_NAMES
)


def is_dispatch_scalar_std_name(standard_name: str) -> bool:
    """True if standard_name is one of the fixed CCPP-protocol dispatch
    scalars (loop bounds, error handling) rather than real host state.
    """
    return standard_name.lower() in DISPATCH_SCALAR_STD_NAMES


# ── Deprecated standard names ────────────────────────────────────────────────
# Rejected by default, matching real capgen-v1's own strict posture; still
# fully supported (parsed and handled exactly as before, via suite_cap.py's
# column-chunking synthesis) when --legacy-mode is passed, matching
# capgen-v1's own --legacy-mode flag. Every example in this repo has already
# migrated off these names in favor of the replacement; new metadata should
# use the replacement instead.
CCPP_DEPRECATED_STD_NAMES: dict = {
    CCPP_LOOP_EXTENT_STD_NAME: CCPP_HORIZ_DIM_STD_NAME,
}

# Set once per process (by each frontend's CLI entry point) from --legacy-mode.
# A plain module global rather than a threaded parameter: ArgumentOp is
# constructed from dozens of call sites across three independent frontends
# (ccpp_xml.py, py_api.py, and ccpp_dsl.py's merge_meta_files/merge_meta),
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
        f"(every example in this repo has already migrated)"
    )

# ── Unit conversion table ────────────────────────────────────────────────────
# Maps (scheme_units, host_units) → (to_scheme_expr, to_host_expr).
#
# Each expression is appended to the source variable name to form the RHS of
# a Fortran assignment, e.g. "source_var + 273.15" or "source_var * 100.0".
# An empty string means no conversion expression is emitted (intent=out only).
#
# Units are matched after lowercasing and stripping whitespace.
UNIT_CONVERSIONS: dict = {
    # Temperature
    ("k",    "degc"): ("+ 273.15", "- 273.15"),
    ("degc", "k"):    ("- 273.15", "+ 273.15"),
    # Pressure
    ("pa",   "hpa"):  ("* 100.0",  "* 0.01"),
    ("hpa",  "pa"):   ("* 0.01",   "* 100.0"),
    # Length
    ("m",    "cm"):   ("* 0.01",   "* 100.0"),
    ("cm",   "m"):    ("* 100.0",  "* 0.01"),
    # Mixing ratio
    ("kg kg-1", "g g-1"):  ("* 0.001",  "* 1000.0"),
    ("g g-1",   "kg kg-1"): ("* 1000.0", "* 0.001"),
    # Speed
    ("m s-1",  "cm s-1"): ("* 0.01",  "* 100.0"),
    ("cm s-1", "m s-1"):  ("* 100.0", "* 0.01"),
    # Length (micrometer)
    ("um", "m"): ("* 1.0E6", "* 1.0E-6"),
    ("m", "um"): ("* 1.0E-6", "* 1.0E6"),
    # Length (kilometer)
    ("km", "m"): ("* 0.001", "* 1000.0"),
    ("m", "km"): ("* 1000.0", "* 0.001"),
    # Specific energy — "j kg-1" and "m2 s-2" are dimensionally identical
    # (1 J/kg = 1 (kg m2 s-2) / kg = 1 m2 s-2), so this is a same-magnitude
    # relabeling rather than a real numeric conversion.
    ("m2 s-2", "j kg-1"): ("* 1.0", "* 1.0"),
    ("j kg-1", "m2 s-2"): ("* 1.0", "* 1.0"),
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
