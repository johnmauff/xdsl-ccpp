"""CCPP framework conventions — authoritative constants for standard names and mappings.

All strings here are defined by the CCPP specification and shared across the
frontend, transforms, and backend.  Import from here rather than duplicating
literals throughout the codebase.
"""

# ── Error handling ──────────────────────────────────────────────────────────
# CCPP framework-defined standard names for error communication.
CCPP_ERROR_MESSAGE = "ccpp_error_message"
CCPP_ERROR_CODE    = "ccpp_error_code"

# Both error standard names as a set — useful for membership tests.
CCPP_ERROR_STD_NAMES: frozenset = frozenset({CCPP_ERROR_MESSAGE, CCPP_ERROR_CODE})

# Local Fortran variable names used in generated caps for error handling.
CCPP_ERRMSG_LOCAL = "errmsg"
CCPP_ERRFLG_LOCAL = "errflg"

# ── Framework-internal standard names ──────────────────────────────────────
# Variables managed entirely by the CCPP framework — schemes reference them
# but they are never matched to host model variables.
CCPP_FRAMEWORK_STD_NAMES: frozenset = frozenset({
    "horizontal_loop_extent",       # computed as col_end - col_start + 1
    "ccpp_constituents",            # constituent transport array
    "ccpp_constituent_tendencies",  # constituent tendency array
})

# The full set of names the host variable match pass skips without error.
# Includes both error-handling names and framework-internal names.
CCPP_INTERNAL_STD_NAMES: frozenset = CCPP_ERROR_STD_NAMES | CCPP_FRAMEWORK_STD_NAMES

# ── Dimension name substitutions ────────────────────────────────────────────
# Maps a scheme-side dimension standard name to its host-side equivalent.
# Used by HostVariableMatchPass and ccpp_cap.py to validate and classify dims.
CCPP_DIM_SUBSTITUTIONS: dict = {
    "horizontal_loop_extent": "horizontal_dimension",
}

# ── Loop bound and dimension standard names ────────────────────────────────
# Match by these standard names rather than local variable names (which vary:
# 'ncol', 'foo', 'nbox' all map to horizontal_loop_extent across different schemes).
CCPP_LOOP_EXTENT_STD_NAME = "horizontal_loop_extent"   # column count
CCPP_LOOP_BEGIN_STD_NAME  = "horizontal_loop_begin"    # first column index
CCPP_LOOP_END_STD_NAME    = "horizontal_loop_end"      # last column index
CCPP_HORIZ_DIM_STD_NAME   = "horizontal_dimension"     # size of horizontal dimension

# ── Kind (precision) mappings ───────────────────────────────────────────────
# Maps CCPP kind names to ISO_FORTRAN_ENV named constants.
CCPP_KIND_TO_ISO: dict = {
    "kind_phys": "REAL64",
}

# Convenience constant for the primary physics precision kind.
CCPP_KIND_PHYS = "kind_phys"
