"""Package scope analysis (composite-scheme Stage 2, S2-2 and S2-3).

Works out, for each package in an unflattened suite (``ccpp.composite`` ops
tagged ``package``; see py_api.ccpp_package), which standard names are
private to it.  A standard name is private to package P when

1. it is not supplied from outside the suites: not declared (as a variable
   or as a variable's dimension) in a host, module, control or DDT table,
   not managed by the CCPP framework, not a constituent;
2. every scheme that touches it -- as an argument or as an array dimension,
   in any phase -- is called as P's own code: from P's entry points, but not
   through one of their hooks (hook code belongs to the host);
3. at least one of P's schemes writes it (intent out or inout).  A name P
   only reads is an input someone outside P must supply.

Everything else P touches is public, with the reason recorded.  The public
names P shares with host code (adapter or hook schemes) are P's inferred
interface, classified by who writes them:

- output: P writes, host code only reads;
- input: host code writes, P only reads;
- shared state: both write -- a leak across the package boundary.  Each must
  be declared in ``ccpp_package(..., shared_state=[...])``; an undeclared one
  is an error, a declared one that is no longer shared state a warning, so
  the list only ever shrinks towards zero.

`package_scopes` is the analysis (``ccpp_dsl --list-package-scope``).  The
``scope-packages`` pass (`ScopePackages`) acts on it before
``flatten-composites`` erases the package boundaries: each private name is
renamed ``<package>__<name>``, so after flattening nothing outside the
package -- another scheme, the host -- can resolve to it, and its arguments
are marked suite-owned, with or without host metadata.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp, StringAttr, UnitAttr
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind
from xdsl_ccpp.transforms.util.cap_shared import iter_arg_tables
from xdsl_ccpp.util.ccpp_conventions import CCPP_INTERNAL_STD_NAMES

SUITE = "<suite>"  # owner of scheme calls outside every package

HOST = "host"
FRAMEWORK = "framework"
CONSTITUENT = "constituent"
SHARED = "shared"
INPUT = "input"

# Directions of a SHARED name (PackageScope.direction).
OUTPUT = "output"
FROM_HOST = "input"
SHARED_STATE = "shared state"


@dataclass(frozen=True)
class CallSite:
    """Where a scheme is called: the package owning the call (or SUITE) and,
    for host code run through a hook, the hook's entry point and name."""

    scheme: str
    owner: str
    hook: tuple[str, str] | None = None

    def describe(self) -> str:
        if self.hook is not None:
            return f"{self.scheme} [hook {self.hook[0]}.{self.hook[1]}]"
        if self.owner == SUITE:
            return f"{self.scheme} [suite]"
        return f"{self.scheme} [package {self.owner}]"


@dataclass
class PackageScope:
    """The standard names one package touches, split into private and public.

    ``private`` maps each private name to the local names its schemes use
    for it; ``public`` maps each public name to its reason (HOST, FRAMEWORK,
    CONSTITUENT, SHARED or INPUT); ``shared_with`` lists, for SHARED names,
    the call sites outside the package that touch them, and ``direction``
    their interface direction (OUTPUT, FROM_HOST or SHARED_STATE).
    ``declared_shared_state`` is the package's own ``shared_state`` list.
    """

    name: str
    private: dict[str, set[str]] = field(default_factory=dict)
    public: dict[str, str] = field(default_factory=dict)
    shared_with: dict[str, set[CallSite]] = field(default_factory=dict)
    direction: dict[str, str] = field(default_factory=dict)
    declared_shared_state: list[str] = field(default_factory=list)

    def interface_problems(self) -> tuple[list[str], list[str]]:
        """(errors, warnings) from checking the declared shared state against
        the inferred one."""
        actual = {std for std, d in self.direction.items() if d == SHARED_STATE}
        declared = set(self.declared_shared_state)
        errors = [
            f"Package '{self.name}': '{std}' is written both by the package and "
            f"by host code ({', '.join(sorted(s.describe() for s in self.shared_with[std]))}) "
            f"but is not declared in its shared_state."
            for std in sorted(actual - declared)]
        warnings = [
            f"Package '{self.name}': shared_state lists '{std}', which is not "
            f"shared state ({self._what(std)}); remove it from the list."
            for std in sorted(declared - actual)]
        return errors, warnings

    def _what(self, std: str) -> str:
        if std in self.private:
            return "it is private"
        if std in self.direction:
            return f"it is an {self.direction[std]}"
        if std in self.public:
            return f"it is public: {self.public[std]}"
        return "the package does not touch it"


def _call_sites(module: ModuleOp) -> list[CallSite]:
    """Every scheme call in the module's suites, with its owner."""
    sites = []
    for op in module.walk():
        if not isa(op, ccpp.SchemeOp):
            continue
        # The innermost entry point or hook decides: a scheme inside a hook
        # is host code even though the hook sits inside an entry point.
        owner, hook, hook_name = SUITE, None, None
        parent = op.parent_op()
        while parent is not None and not isa(parent, ccpp.SuiteOp):
            if isa(parent, ccpp.CompositeOp):
                if parent.hook is not None and hook_name is None:
                    hook_name = parent.composite_name.data
                elif parent.package is not None:
                    if hook_name is None:
                        owner = parent.package.data
                    else:
                        hook = (parent.composite_name.data, hook_name)
                    break
            parent = parent.parent_op()
        sites.append(CallSite(op.scheme_name.data, owner, hook))
    return sites


def _dims(arg: ccpp.ArgumentOp) -> list[str]:
    if arg.dim_names is None:
        return []
    return [d.strip().lower() for d in arg.dim_names.data.split(",")
            if d.strip() and d.strip() != ":"]


def package_scopes(module: ModuleOp) -> dict[str, PackageScope]:
    """Analyse *module* -- the frontend's IR before ``flatten-composites``,
    with scheme and host metadata merged in -- and return one PackageScope
    per package, keyed by package name."""
    sites = _call_sites(module)
    packages = sorted({s.owner for s in sites if s.owner != SUITE})
    if not packages:
        return {}
    declared = {op.package_name.data: [n.data for n in op.shared_state]
                for op in module.walk() if isa(op, ccpp.PackageOp)}

    supplied: set[str] = set()
    for _, table in iter_arg_tables(
            module, table_type=(TableTypeKind.Host, TableTypeKind.Module,
                                TableTypeKind.Control, TableTypeKind.DDT)):
        for arg in table.body.ops:
            if isa(arg, ccpp.ArgumentOp) and arg.standard_name is not None:
                supplied.add(arg.standard_name.data.lower())
                supplied.update(_dims(arg))

    # Per scheme: standard name -> (local names, written?), plus constituents.
    touches: dict[str, dict[str, tuple[set[str], bool]]] = {}
    constituents: set[str] = set()
    for props, table in iter_arg_tables(module, table_type=TableTypeKind.Scheme):
        scheme = touches.setdefault(props.table_name.data, {})
        for arg in table.body.ops:
            if not isa(arg, ccpp.ArgumentOp) or arg.standard_name is None:
                continue
            std = arg.standard_name.data.lower()
            if arg.advected is not None or arg.constituent is not None or (
                    arg.allocatable is not None
                    and arg.arg_type.data.lower() == "ccpp_constituent_properties_t"):
                constituents.add(std)
            locals_, written = scheme.get(std, (set(), False))
            locals_.add(arg.arg_name.data)
            intent = arg.intent.data.lower() if arg.intent is not None else "in"
            scheme[std] = (locals_, written or intent in ("out", "inout"))
            for dim in _dims(arg):
                scheme.setdefault(dim, (set(), False))

    # Standard name -> every call site touching it.
    users: dict[str, set[CallSite]] = {}
    for site in sites:
        for std in touches.get(site.scheme, {}):
            users.setdefault(std, set()).add(site)

    scopes = {p: PackageScope(p, declared_shared_state=declared.get(p, []))
              for p in packages}
    for std, std_users in users.items():
        for p in {s.owner for s in std_users if s.owner != SUITE}:
            scope = scopes[p]
            own = [s for s in std_users if s.owner == p]
            outside = {s for s in std_users if s.owner != p}
            if std in CCPP_INTERNAL_STD_NAMES:
                scope.public[std] = FRAMEWORK
            elif std in constituents:
                scope.public[std] = CONSTITUENT
            elif std in supplied:
                scope.public[std] = HOST
            elif outside:
                scope.public[std] = SHARED
                scope.shared_with[std] = outside
                package_writes = any(touches[s.scheme][std][1] for s in own)
                host_writes = any(touches[s.scheme][std][1] for s in outside)
                scope.direction[std] = (SHARED_STATE if package_writes and host_writes
                                        else OUTPUT if package_writes else FROM_HOST)
            elif not any(touches[s.scheme][std][1] for s in own):
                scope.public[std] = INPUT
            else:
                scope.private[std] = set().union(
                    *(touches[s.scheme][std][0] for s in own))
    return scopes


_DIRECTION_TITLES = {
    OUTPUT: "interface outputs (package writes, host code reads)",
    FROM_HOST: "interface inputs (host code writes, package reads)",
    SHARED_STATE: "shared state (package and host code both write)",
}

_REASON_TITLES = {
    INPUT: "public, read but never written by the package (supplied from outside)",
    HOST: "public, declared by the host",
    CONSTITUENT: "public, constituents",
    FRAMEWORK: "public, managed by the CCPP framework",
}


def format_package_scopes(scopes: dict[str, PackageScope]) -> str:
    """Human-readable report of `package_scopes`' result."""
    if not scopes:
        return "No packages (no @<package>.entry_point composites) in the suites.\n"
    lines = []
    for scope in scopes.values():
        total = len(scope.private) + len(scope.public)
        lines.append(f"package {scope.name}: {total} standard names, "
                     f"{len(scope.private)} private, {len(scope.public)} public")
        lines.append("  private:")
        for std in sorted(scope.private):
            lines.append(f"    {std}  ({', '.join(sorted(scope.private[std]))})")
        for direction, title in _DIRECTION_TITLES.items():
            names = sorted(s for s, d in scope.direction.items() if d == direction)
            if not names:
                continue
            lines.append(f"  public, {title}:")
            for std in names:
                where = ", ".join(sorted(s.describe() for s in scope.shared_with[std]))
                lines.append(f"    {std}  <- {where}")
        for reason, title in _REASON_TITLES.items():
            names = sorted(s for s, r in scope.public.items() if r == reason)
            if not names:
                continue
            lines.append(f"  {title}:")
            for std in names:
                lines.append(f"    {std}")
        errors, warnings = scope.interface_problems()
        for problem in errors:
            lines.append(f"  ERROR: {problem}")
        for problem in warnings:
            lines.append(f"  WARNING: {problem}")
    return "\n".join(lines) + "\n"


# Scheme phases a package init's schemes may have: any other phase would run
# where the generator places the init, not just at initialization.
_INIT_ONLY_PHASES = frozenset({"register", "init", "final"})


def init_problems(module: ModuleOp) -> list[str]:
    """Errors for package inits (``@<package>.init``) that call a scheme
    with a phase other than register, init or final."""
    inits = {(op.package_name.data, op.init.data)
             for op in module.walk() if isa(op, ccpp.PackageOp) and op.init is not None}
    if not inits:
        return []
    phases: dict[str, set[str]] = {}
    for props, table in iter_arg_tables(module, table_type=TableTypeKind.Scheme):
        scheme = props.table_name.data
        phases.setdefault(scheme, set()).add(table.table_name.data[len(scheme) + 1:])
    errors = []
    for op in module.walk():
        if not (isa(op, ccpp.CompositeOp) and op.package is not None
                and (op.package.data, op.composite_name.data) in inits):
            continue
        for scheme_op in op.walk():
            if not isa(scheme_op, ccpp.SchemeOp):
                continue
            scheme = scheme_op.scheme_name.data
            extra = sorted(phases.get(scheme, set()) - _INIT_ONLY_PHASES)
            if extra:
                errors.append(
                    f"Package '{op.package.data}': init '{op.composite_name.data}' "
                    f"calls '{scheme}', which has phase(s) {', '.join(extra)}; a "
                    f"package init may only call schemes with register, init or "
                    f"final phases.")
    return errors


def private_name(package: str, std_name: str) -> str:
    """The standard name a name private to *package* gets after scoping."""
    return f"{package}__{std_name}"


@dataclass(frozen=True)
class ScopePackages(ModulePass):
    """Give every package-private standard name (see `package_scopes`) a
    package-qualified standard name, and mark its arguments suite-owned
    (``is_interstitial``): the package's internal state lives in the suite
    cap whether or not the host is described, and local names shared by
    different private names (RRTMGP's two ``kdist`` objects) are
    disambiguated by the suite cap's usual naming of suite variables.

    First checks each package's declared shared state against the inferred
    one (`PackageScope.interface_problems`) and its init's schemes
    (`init_problems`): errors stop generation, warnings are printed.

    Runs before ``flatten-composites``; a module without packages is left
    unchanged.
    """

    name = "scope-packages"

    def apply(self, ctx: Context, op: ModuleOp) -> None:
        from xdsl_ccpp.transforms.package_segments import multi_instance_problems

        scopes = package_scopes(op)
        errors = init_problems(op) + multi_instance_problems(op)
        for scope in scopes.values():
            scope_errors, warnings = scope.interface_problems()
            errors += scope_errors
            for warning in warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        if errors:
            raise ValueError("Package check failed:\n  " + "\n  ".join(errors))
        renames = {std: private_name(scope.name, std)
                   for scope in scopes.values()
                   for std in scope.private}
        if not renames:
            return
        for _, table in iter_arg_tables(op, table_type=TableTypeKind.Scheme):
            for arg in table.body.ops:
                if not isa(arg, ccpp.ArgumentOp):
                    continue
                if arg.standard_name is not None:
                    new = renames.get(arg.standard_name.data.lower())
                    if new is not None:
                        arg.properties["standard_name"] = StringAttr(new)
                        arg.properties["is_interstitial"] = UnitAttr()
                if arg.dim_names is not None:
                    dims = arg.dim_names.data.split(",")
                    scoped = [renames.get(d.strip().lower(), d) for d in dims]
                    if scoped != dims:
                        arg.properties["dim_names"] = StringAttr(",".join(scoped))
