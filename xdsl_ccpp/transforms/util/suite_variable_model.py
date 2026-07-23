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
    local_name: str            # canonical Fortran name (from the first writer) --
                                # qualified with producing_scheme if this name
                                # collided with a *different* standard_name's
                                # first-writer name; see _resolve_name_collisions.
    fortran_type: str          # "real", "integer", "character", or DDT type name
    kind: str                  # kind string (e.g. "kind_phys"), "" for non-real
    rank: int                  # 0 = scalar, >0 = array
    alloc_dim_std_names: list  # standard_names for each allocation dimension
    is_ddt: bool               # True for Derived-Data-Type interstitials
    producing_phase: str       # phase postfix in which this var is first written
    producing_group: str       # group name if produced in _run, else ""
    producing_scheme: str      # name of the scheme whose arg first wrote this var
    needs_device_residency: bool = False  # True if ANY occurrence (any scheme/
                                # phase, not just the first writer) declares
                                # memory_space=device -- a simple OR, unlike
                                # HostMatched's present-vs-update split; a
                                # SuiteOwned var's residency need can't
                                # conflict across schemes, only be requested
                                # or not. See _process_table's Case 4 handling.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iter_schemes_duck_typed(node):
    """Recursively yield scheme descriptors from a group/subcycle node.

    Duck-types the subcycle check ("loop_count" in child.attributes) instead
    of `isinstance(child, XMLSubcycle)`, so this module never imports
    cap_shared/xDSL -- see SuiteVariableModel's own comment at its one call
    site for why this can't just be cap_shared._iter_schemes. Descends
    recursively into a (possibly nested) subcycle, mirroring _iter_schemes'
    own recursion.
    """
    for child in node:
        if "loop_count" in child.attributes:
            yield from _iter_schemes_duck_typed(child)
        else:
            yield child


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
        #
        # This duck-types the subcycle check ("loop_count" in child.attributes)
        # instead of `isinstance(child, XMLSubcycle)`, deliberately -- unlike
        # ccpp_cap.py/suite_cap.py's shared cap_shared._iter_schemes, which uses
        # isinstance and is not imported here, since this module's own contract
        # (see the module docstring) is zero xDSL/MLIR imports, and cap_shared
        # transitively imports xdsl.dialects. Not unified with _iter_schemes for
        # that reason; keep both in sync if the subcycle model ever changes --
        # including recursing into a (possibly nested) subcycle, mirroring
        # _iter_schemes' own recursive descent.
        scheme_groups: list[tuple[str, str]] = []
        for group in suite_description:
            gname = group.attributes["name"]
            for scheme in _iter_schemes_duck_typed(group):
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
        self._resolve_name_collisions()

    def _resolve_name_collisions(self) -> None:
        """Qualify local_name for any suite-owned variables that would
        otherwise collide at Fortran module scope.

        Two *different* standard_names can independently pick the same
        local_name (e.g. two schemes each naming their own scalar "tcld") --
        harmless in each scheme's own signature, but suite-owned variables
        are all declared in one shared module scope, so an unqualified
        collision would emit two conflicting declarations of the same
        identifier. Only the colliding subset is touched -- every
        non-colliding name (the overwhelming majority) is emitted exactly as
        the scheme author wrote it, unchanged from today's behavior.

        Processes colliding groups in sorted (local_name, producing_scheme)
        order so the qualified names are a pure function of the suite's own
        standard_names/scheme names -- independent of scheme-file processing
        order, unlike a "first writer keeps the plain name" rule would be.
        """
        by_local_name: dict[str, list[SuiteVarEntry]] = {}
        for entry in self._suite_owned.values():
            by_local_name.setdefault(entry.local_name, []).append(entry)

        for local_name, entries in sorted(by_local_name.items()):
            distinct_std_names = {e.standard_name for e in entries}
            if len(distinct_std_names) <= 1:
                continue
            for entry in sorted(entries, key=lambda e: e.producing_scheme):
                entry.local_name = f"{entry.producing_scheme}_{local_name}"

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

            # Case 4: already in suite data from a prior phase/group. Other
            # attributes stay pinned to the first writer, but a *later*
            # occurrence declaring memory_space=device should still be
            # enough to request GPU residency -- OR it into the existing
            # entry rather than silently dropping it (unlike a full
            # divergence check, there's nothing to reconcile: residency is
            # a simple "does anything ask for it", not a per-scheme clause
            # that could conflict).
            if std_name in self._suite_owned:
                if arg.hasAttr("memory_space") and arg.getAttr("memory_space") == "device":
                    self._suite_owned[std_name].needs_device_residency = True
                continue

            # DDT allocatable arrays (e.g. ccpp_constituent_properties_t from
            # _register) are passed as arguments by the ccpp cap, not owned by
            # the suite cap.  Skip them so no spurious module-level scalar var
            # is emitted in the suite cap.
            _arg_type_str = arg.getAttr("type") if arg.hasAttr("type") else "real"
            _primitive_types = {"real", "integer", "character", "logical", "complex"}
            if (arg.hasAttr("allocatable")
                    and _arg_type_str.lower() not in _primitive_types):
                continue

            # Framework-managed arrays (advected/allocatable) are always
            # suite-owned — the suite cap allocates them regardless of whether
            # the first scheme entry writes (out) or reads/writes (inout) them.
            if arg.hasAttr("advected") or arg.hasAttr("allocatable"):
                self._suite_owned[std_name] = self._make_entry(
                    arg, std_name, phase, group_name, scheme_name
                )
                continue

            # Case 2: first occurrence is intent(out) → suite-owned.
            if intent == "out":
                self._suite_owned[std_name] = self._make_entry(
                    arg, std_name, phase, group_name, scheme_name
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
        scheme_name: str,
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

        needs_device_residency = (
            arg.hasAttr("memory_space") and arg.getAttr("memory_space") == "device"
        )

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
            producing_scheme=scheme_name,
            needs_device_residency=needs_device_residency,
        )
