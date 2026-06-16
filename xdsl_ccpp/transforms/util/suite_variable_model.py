"""Suite-owned variable classification for CCPP cap generation.

Implements the four-case variable resolution algorithm from capgen-ng
(briefing.md §3.5).  No xDSL/MLIR imports — pure Python analysis.
"""

from dataclasses import dataclass
from enum import Enum

from xdsl_ccpp.util.ccpp_conventions import CCPP_ERROR_STD_NAMES


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class SuiteVarScope(Enum):
    """Result of the four-case variable resolution for one standard_name."""
    SUITE_OWNED   = "suite_owned"    # Case 2: interstitial, module-level
    HOST_RESOLVED = "host_resolved"  # Case 1: matched to host/control metadata


@dataclass
class SuiteVarEntry:
    """Describes one suite-owned framework variable.

    Suite-owned variables are declared at module scope in the suite cap and
    allocated in the suite's *initialize* function with full-domain dimensions.
    Group-cap scheme call sites slice or pass them as needed.
    """

    standard_name: str
    local_name: str            # canonical Fortran name (from the first writer)
    fortran_type: str          # "real", "integer", "character", or DDT type name
    kind: str                  # kind string (e.g. "kind_phys"), "" for non-real
    rank: int                  # 0 = scalar, >0 = array
    alloc_dim_std_names: list  # standard_names for each allocation dimension
    is_ddt: bool               # True for Derived-Data-Type interstitials
    producing_phase: str       # phase postfix in which this var is first written
    producing_group: str       # group name if produced in _run, else ""


# ---------------------------------------------------------------------------
# SuiteVariableModel
# ---------------------------------------------------------------------------

class SuiteVariableModel:
    """Classifies framework variables for a CCPP suite using the four-case
    algorithm from capgen-ng.

    Four cases (applied in processing order across all phases and groups):

    1. Found in host/control metadata (``model_var_name`` set by
       HostVariableMatchPass) → **HOST_RESOLVED** — passed as a block arg
       or DDT member access; not a suite variable.

    2. Not found; first occurrence is ``intent(out)`` → **SUITE_OWNED** —
       add to suite data; declare at module scope; allocate in
       ``initialize`` with full-domain dimensions.

    3. Not found; first occurrence is ``intent(in)`` or ``intent(inout)``
       → **error** — variable consumed before any scheme provides it.

    4. Already in suite data (a prior scheme wrote it in an earlier phase or
       group) → still **SUITE_OWNED**; handled automatically because the
       entry is already in the model.

    Usage::

        model = SuiteVariableModel(suite_description, meta_data, std_key_fn)

        for entry in model.suite_owned_vars():
            print(entry.local_name, entry.rank, entry.alloc_dim_std_names)

        if model.errors():
            for msg in model.errors():
                print("ERROR:", msg)
    """

    # All lifecycle phase postfixes in the order they are processed.
    # "First use" is determined by scanning these in sequence, then within
    # each phase by iterating groups in suite-XML order.
    _PHASE_ORDER = [
        "_register",
        "_init",
        "_timestep_init",
        "_run",
        "_timestep_final",
        "_final",
    ]

    def __init__(self, suite_description, meta_data: dict, std_key_fn):
        """Build the model.

        Parameters
        ----------
        suite_description:
            An ``XMLSuite`` object from ``BuildSchemeDescription`` — iterates
            groups, each of which iterates schemes.
        meta_data:
            Mapping of table-name → ``CCPPTableProperties`` built by
            ``BuildMetaDataDescriptions``.  Keyed by scheme/module name.
        std_key_fn:
            Callable ``(CCPPArgument) → str`` returning the standard_name
            in lowercase (typically ``GenerateSuiteSubroutine._std_key``).
        """
        self._std_key = std_key_fn
        self._suite_owned: dict[str, SuiteVarEntry] = {}
        self._errors: list[str] = []

        # Ordered list of (scheme_name, group_name) pairs across the suite.
        scheme_groups: list[tuple[str, str]] = []
        for group in suite_description:
            gname = group.attributes["name"]
            for scheme in group:
                scheme_groups.append((scheme.attributes["name"], gname))

        self._build(scheme_groups, meta_data)

    # ── Public API ──────────────────────────────────────────────────────────

    def is_suite_owned(self, std_name: str) -> bool:
        """Return True when *std_name* is a suite-owned (module-level) variable."""
        return std_name in self._suite_owned

    def get(self, std_name: str) -> "SuiteVarEntry | None":
        """Return the ``SuiteVarEntry`` for *std_name*, or ``None``."""
        return self._suite_owned.get(std_name)

    def suite_owned_vars(self) -> list:
        """All ``SuiteVarEntry`` objects, in insertion (first-writer) order."""
        return list(self._suite_owned.values())

    def alloc_dims(self, std_name: str) -> list:
        """Dimension standard_names needed to allocate a suite-owned variable.

        Returns an empty list for scalars, DDTs, and non-suite-owned names.
        """
        entry = self._suite_owned.get(std_name)
        return entry.alloc_dim_std_names if entry else []

    def needs_allocation(self, std_name: str) -> bool:
        """True when a suite-owned variable needs an explicit allocate() call.

        Scalars and DDT types do not — they are simply declared.
        """
        entry = self._suite_owned.get(std_name)
        if entry is None:
            return False
        return entry.rank > 0 and not entry.is_ddt

    def errors(self) -> list:
        """Case-3 error messages: variables consumed before any scheme provides them."""
        return list(self._errors)

    def summary(self) -> str:
        """Human-readable summary for debugging."""
        lines = [f"SuiteVariableModel ({len(self._suite_owned)} suite-owned vars):"]
        for e in self._suite_owned.values():
            alloc = (
                f"  alloc({', '.join(e.alloc_dim_std_names)})"
                if e.alloc_dim_std_names else "  (no alloc)"
            )
            lines.append(
                f"  {e.local_name}: {e.fortran_type}"
                f"{'(kind_phys)' if e.kind == 'kind_phys' else ''}"
                f"  rank={e.rank}{alloc}"
                f"  first_written={e.producing_phase}"
                f"{'/' + e.producing_group if e.producing_group else ''}"
            )
        if self._errors:
            lines.append("Errors:")
            lines.extend(f"  {e}" for e in self._errors)
        return "\n".join(lines)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _build(self, scheme_groups: list, meta_data: dict) -> None:
        """Run the four-case algorithm across all phases and groups."""
        for phase_postfix in self._PHASE_ORDER:
            for scheme_name, group_name in scheme_groups:
                if scheme_name not in meta_data:
                    continue
                table_name = scheme_name + phase_postfix
                if table_name not in meta_data[scheme_name].arg_tables:
                    continue
                arg_table = meta_data[scheme_name].getArgTable(table_name)
                self._process_table(
                    arg_table, scheme_name, phase_postfix, group_name
                )

    def _process_table(
        self,
        arg_table,
        scheme_name: str,
        phase: str,
        group_name: str,
    ) -> None:
        """Apply the four-case algorithm to one scheme entry-point table."""
        for arg in arg_table.getFunctionArguments():
            std_name = self._std_key(arg)

            # Skip framework control variables (errmsg, errflg).
            # These are handled by the cap infrastructure, not as suite vars.
            if std_name in CCPP_ERROR_STD_NAMES:
                continue

            # Case 1: host-matched variable — not a suite variable.
            if arg.hasAttr("model_var_name"):
                continue

            intent = (
                arg.getAttr("intent").lower()
                if arg.hasAttr("intent")
                else "in"
            )

            # Case 4: already in suite data from a prior phase/group — no-op.
            if std_name in self._suite_owned:
                continue

            # Framework-managed arrays (advected/allocatable) are always
            # suite-owned — the suite cap allocates them regardless of whether
            # the first scheme entry writes (out) or reads/writes (inout) them.
            if arg.hasAttr("advected") or arg.hasAttr("allocatable"):
                self._suite_owned[std_name] = self._make_entry(
                    arg, std_name, phase, group_name
                )
                continue

            # Case 2: first occurrence is intent(out) → suite-owned.
            if intent == "out":
                self._suite_owned[std_name] = self._make_entry(
                    arg, std_name, phase, group_name
                )
                continue

            # Case 3: first occurrence is intent(in/inout) with no host match
            # and not yet in suite data.
            # Skip if `is_interstitial` is set — the HostVariableMatchPass
            # already detected and flagged this; we avoid double-reporting.
            if intent in ("in", "inout") and not arg.hasAttr("is_interstitial"):
                self._errors.append(
                    f"Scheme '{scheme_name}' ({phase}): argument "
                    f"'{arg.name}' (standard_name='{std_name}') has "
                    f"intent({intent}) but has no host match and no prior "
                    f"suite provider."
                )

    @staticmethod
    def _parse_dim_names(arg) -> list:
        """Extract the dim_names list from a CCPPArgument."""
        if not arg.hasAttr("dim_names"):
            return []
        raw = arg.getAttr("dim_names")
        if isinstance(raw, list):
            return [d.strip() for d in raw if d.strip()]
        return [d.strip() for d in str(raw).split(",") if d.strip()]

    def _make_entry(
        self,
        arg,
        std_name: str,
        phase: str,
        group_name: str,
    ) -> SuiteVarEntry:
        """Construct a SuiteVarEntry from a CCPPArgument."""
        local_name   = arg.name
        arg_type     = arg.getAttr("type") if arg.hasAttr("type") else "real"
        kind         = arg.getAttr("kind") if arg.hasAttr("kind") else ""
        rank         = (
            arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
        )
        dim_names    = self._parse_dim_names(arg)

        # Primitive types vs DDTs.
        primitive_types = {"real", "integer", "character", "logical", "complex"}
        is_ddt = arg_type.lower() not in primitive_types

        return SuiteVarEntry(
            standard_name=std_name,
            local_name=local_name,
            fortran_type=arg_type,
            kind=kind,
            rank=rank,
            alloc_dim_std_names=dim_names,
            is_ddt=is_ddt,
            producing_phase=phase,
            producing_group=group_name,
        )
