"""ccpp_track_variables — trace a CCPP standard-name variable through a suite.

Usage::

    ccpp_track_variables \
        --suites     path/to/cld_suite.xml \
        --scheme-files path/to/cld_liq.meta,path/to/cld_ice.meta \
        --host-files path/to/host_data.meta \
        --variable   surface_air_pressure

Prints which scheme entry points use the variable, with intent, units, and
whether a unit conversion will be applied.  Exit code 1 when the variable is
not found in any scheme.
"""

import argparse
import os
import sys
from dataclasses import dataclass

from xdsl.dialects import builtin
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import (
    CCPP,
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
    TableTypeKind,
)
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML
from xdsl_ccpp.util.ccpp_conventions import CCPP_DIMENSIONLESS_UNITS, normalize_units


@dataclass
class TrackResult:
    suite_name: str
    group_name: str
    entry_point: str
    local_name: str
    intent: str | None
    scheme_units: str
    host_units: str
    unit_mismatch: bool


def _build_host_unit_map(module: builtin.ModuleOp) -> dict[str, str]:
    """Map standard_name → normalized units for every non-scheme-table argument.

    Host variables may live in tables of type module, ddt, or host — collect
    all of them, mirroring how ccpp_cap.py builds its host variable map.
    """
    host_units: dict[str, str] = {}
    for tbl_op in module.body.ops:
        if not isa(tbl_op, TablePropertiesOp):
            continue
        if tbl_op.table_type.data == TableTypeKind.Scheme:
            continue
        for arg_table_op in tbl_op.body.ops:
            if not isa(arg_table_op, ArgumentTableOp):
                continue
            for arg_op in arg_table_op.body.ops:
                if not isa(arg_op, ArgumentOp):
                    continue
                if arg_op.standard_name is None:
                    continue
                sn = arg_op.standard_name.data.lower()
                host_units[sn] = normalize_units(
                    arg_op.units.data if arg_op.units is not None else None
                )
    return host_units


def _index_scheme_arg_tables(module: builtin.ModuleOp) -> dict[str, ArgumentTableOp]:
    """Index scheme ArgumentTableOps by their full entry-point name (e.g. cld_liq_run).

    Scheme metadata nesting: TablePropertiesOp(name=cld_liq) contains
    ArgumentTableOp(name=cld_liq_run), ArgumentTableOp(name=cld_liq_init), …
    Each ArgumentTableOp holds the actual ArgumentOp entries for that entry point.
    """
    tables: dict[str, ArgumentTableOp] = {}
    for tbl_op in module.body.ops:
        if not isa(tbl_op, TablePropertiesOp):
            continue
        if tbl_op.table_type.data != TableTypeKind.Scheme:
            continue
        for arg_table_op in tbl_op.body.ops:
            if not isa(arg_table_op, ArgumentTableOp):
                continue
            tables[arg_table_op.table_name.data.lower()] = arg_table_op
    return tables


# Keep the old name as an alias so tests that import _index_scheme_tables still work.
_index_scheme_tables = _index_scheme_arg_tables


def _find_variable(
    arg_table: ArgumentTableOp,
    std_name: str,
    host_unit_map: dict[str, str],
) -> "tuple[str, str | None, str, str, bool] | None":
    """Search a scheme ArgumentTableOp for an arg matching std_name.

    Returns (local_name, intent, scheme_units, host_units, unit_mismatch) or None.
    """
    std_name_lower = std_name.lower()
    for arg_op in arg_table.body.ops:
        if not isa(arg_op, ArgumentOp):
            continue
        if arg_op.standard_name is None:
            continue
        if arg_op.standard_name.data.lower() != std_name_lower:
            continue
        local_name = arg_op.arg_name.data
        intent = arg_op.intent.data if arg_op.intent is not None else None
        scheme_u = normalize_units(
            arg_op.units.data if arg_op.units is not None else None
        )
        host_u = host_unit_map.get(std_name_lower, "")
        both_dimensionless = (
            scheme_u in CCPP_DIMENSIONLESS_UNITS
            and host_u in CCPP_DIMENSIONLESS_UNITS
        )
        mismatch = (
            scheme_u != host_u
            and not both_dimensionless
            and scheme_u != ""
            and host_u != ""
        )
        return (local_name, intent, scheme_u, host_u, mismatch)
    return None


def _find_partial_matches(arg_table: ArgumentTableOp, std_name: str) -> list[str]:
    """Return standard names in arg_table that contain std_name as a substring."""
    partial: list[str] = []
    std_name_lower = std_name.lower()
    for arg_op in arg_table.body.ops:
        if not isa(arg_op, ArgumentOp):
            continue
        if arg_op.standard_name is None:
            continue
        sn = arg_op.standard_name.data.lower()
        if std_name_lower in sn and sn != std_name_lower:
            partial.append(sn)
    return partial


def track(
    module: builtin.ModuleOp,
    variable: str,
    entry_suffixes: list[str] | None = None,
    suite_filter: str | None = None,
) -> tuple[list[TrackResult], list[str]]:
    """Walk the module and return (track_results, partial_match_names).

    Args:
        module: raw CCPP IR module (frontend output, no passes required).
        variable: standard_name to search for (case-insensitive).
        entry_suffixes: entry-point name suffixes to check, e.g. ["run"].
        suite_filter: if set, only report matches within this suite name.
    """
    if entry_suffixes is None:
        entry_suffixes = ["run"]

    host_unit_map = _build_host_unit_map(module)
    scheme_tables = _index_scheme_arg_tables(module)

    results: list[TrackResult] = []
    partial_matches: list[str] = []
    partial_seen: set[str] = set()

    for op in module.body.ops:
        if not isa(op, SuiteOp):
            continue
        suite_name = op.suite_name.data
        if suite_filter and suite_name.lower() != suite_filter.lower():
            continue
        for group_op in op.body.ops:
            if not isa(group_op, GroupOp):
                continue
            group_name = group_op.group_name.data
            for child_op in group_op.body.ops:
                if isa(child_op, SchemeOp):
                    scheme_ops_to_check = [child_op]
                elif isa(child_op, SubcycleOp):
                    scheme_ops_to_check = [
                        s for s in child_op.body.ops if isa(s, SchemeOp)
                    ]
                else:
                    continue
                for scheme_op in scheme_ops_to_check:
                    base = scheme_op.scheme_name.data.lower()
                    for suffix in entry_suffixes:
                        ep = f"{base}_{suffix}"
                        tbl = scheme_tables.get(ep)
                        if tbl is None:
                            continue
                        found = _find_variable(tbl, variable, host_unit_map)
                        if found is not None:
                            local_name, intent, scheme_u, host_u, mismatch = found
                            results.append(TrackResult(
                                suite_name=suite_name,
                                group_name=group_name,
                                entry_point=ep,
                                local_name=local_name,
                                intent=intent,
                                scheme_units=scheme_u,
                                host_units=host_u,
                                unit_mismatch=mismatch,
                            ))
                        else:
                            for pm in _find_partial_matches(tbl, variable):
                                if pm not in partial_seen:
                                    partial_matches.append(pm)
                                    partial_seen.add(pm)

    return results, partial_matches


def _print_report(
    results: list[TrackResult],
    partial_matches: list[str],
    variable: str,
) -> None:
    if not results:
        print(f"Variable '{variable}' not found in any scheme.")
        if partial_matches:
            print("\nPartial matches (standard names containing the query string):")
            for pm in sorted(partial_matches):
                print(f"  {pm}")
        return

    ep_w = max(len(r.entry_point) for r in results)
    ln_w = max(len(r.local_name) for r in results)

    # Group by suite then by group, preserving insertion order
    seen_suite: dict[str, dict[str, list[TrackResult]]] = {}
    for r in results:
        seen_suite.setdefault(r.suite_name, {}).setdefault(r.group_name, []).append(r)

    for suite_name, groups in seen_suite.items():
        print(f"Suite: {suite_name}")
        print(f"Variable: {variable}")
        print()
        for group_name, rows in groups.items():
            print(f"  Group: {group_name}")
            for r in rows:
                intent_str = f"intent={r.intent}" if r.intent else "intent=?"
                units_str = f"units={r.scheme_units}" if r.scheme_units else "units=?"
                host_str = f"host={r.host_units}" if r.host_units else "host=?"
                conv_flag = "  [unit-converted]" if r.unit_mismatch else ""
                print(
                    f"    {r.entry_point:<{ep_w}}  "
                    f"local={r.local_name:<{ln_w}}  "
                    f"{intent_str:<12}  {units_str:<14}  {host_str}{conv_flag}"
                )
        print()


def _load_module(
    suites: list[str],
    scheme_files: list[str],
    host_files: list[str],
) -> builtin.ModuleOp:
    frontend = ccppXML()
    ir_ops = []
    for suite_path in suites:
        ir_ops.append(frontend.build_suite_ir(XMLSuite(suite_path)))
    for path in scheme_files:
        for meta in frontend.parse_metadata_file(path, True):
            ir_ops.append(frontend.build_meta_ir(meta))
    for path in host_files:
        for meta in frontend.parse_metadata_file(path, False):
            ir_ops.append(frontend.build_meta_ir(meta))
    return builtin.ModuleOp(ir_ops)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace a CCPP variable through a suite's call tree"
    )
    parser.add_argument(
        "--suites",
        required=True,
        help="Comma-separated list of suite XML files",
    )
    parser.add_argument(
        "--scheme-files",
        required=True,
        help="Comma-separated list of scheme .meta files",
    )
    parser.add_argument(
        "--host-files",
        default=None,
        help="Comma-separated list of host .meta files",
    )
    parser.add_argument(
        "--variable",
        required=True,
        help="Standard name of the variable to track (case-insensitive)",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help="Restrict output to a single named suite",
    )
    parser.add_argument(
        "--entry-points",
        default="run",
        help="Comma-separated entry-point suffixes to check (default: run)",
    )
    args = parser.parse_args()

    suites = args.suites.split(",")
    scheme_files = args.scheme_files.split(",")
    host_files = args.host_files.split(",") if args.host_files else []
    entry_suffixes = [s.strip() for s in args.entry_points.split(",")]

    for f in suites + scheme_files + host_files:
        if not os.path.exists(f):
            print(f"Error: file not found: '{f}'", file=sys.stderr)
            sys.exit(1)

    module = _load_module(suites, scheme_files, host_files)
    results, partial_matches = track(
        module, args.variable, entry_suffixes, suite_filter=args.suite
    )
    _print_report(results, partial_matches, args.variable)

    if not results:
        sys.exit(1)
