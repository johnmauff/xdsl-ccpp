"""Small records shared by the suite-cap generator."""

from __future__ import annotations

from dataclasses import dataclass

from xdsl.dialects import func

from xdsl_ccpp.util.visitor import Visitor


class GatherMetaFunctionSignatures(Visitor):
    """Collects external func.FuncOp declarations (scheme signatures from
    generate-meta-cap), needed when building call sites."""

    def __init__(self):
        self.meta_functions = {}

    def traverse_func_op(self, func_op: func.FuncOp):
        if func_op.is_declaration:
            self.meta_functions[func_op.sym_name.data] = func_op


@dataclass(frozen=True)
class PhaseSpec:
    """One generated phase function of a suite cap or package cap.

    target_postfix    -- the scheme entry points it calls (e.g. "_init");
                         also the phase identity when it calls none.
    generated_postfix -- suffix of the generated function's name.
    phase_tag         -- its FN_PHASE_ATTR value (which module-level
                         injections apply to it).
    column_range      -- group-scoped: col_start/col_end replace the loop
                         extent, horizontal arrays are column-sliced, and
                         promoted schemes loop over the extra dimension.
    emit_scheme_calls -- False for functions that only do framework setup
                         (the suite's flat _init/_finalize, package state
                         routines).
    check_state       -- ccpp_suite_state value checked on entry, or None.
    set_state         -- ccpp_suite_state value set on exit, or None.
    suite_hooks       -- call the suite's <init>/<final> scheme.
    package_scoped    -- a package cap's function: only package-private
                         suite-owned names are module state (the others
                         are dummy arguments), and a dimension's producer
                         is any scheme that writes it before it is read,
                         since a segment returns what its schemes write.
    """

    target_postfix: str
    generated_postfix: str
    phase_tag: str
    column_range: bool
    emit_scheme_calls: bool = True
    check_state: str | None = None
    set_state: str | None = None
    suite_hooks: bool = False
    package_scoped: bool = False


@dataclass
class _ArgTableResult:
    scheme_entries: list
    arg_tables: dict
    scheme_overrides: dict
    actual_postfixes: dict
    all_args: dict
    suite_use_stubs: list
    divergent_std_keys: frozenset


@dataclass
class _ArgClassification:
    framework_vars: dict
    input_arg_list: list
    output_arg_list: list
    ncol_meta: "object | None"


@dataclass
class _BlockSignature:
    new_block: "object"
    input_arg_types: list
    arg_names: list  # each dummy argument's name (see suite_arg_attrs)
    data_ops: dict
    alloc_ops: dict
    kind_cast_ops: list
    unit_convert_ops: list
    writeback_ops: list


@dataclass
class _LifecycleFnsResult:
    generated_fns: list
    fn_sigs_by_name: dict
    suite_host_use_stubs: list
    check_strings_used: set
    state_strings_used: set


@dataclass
class _PendingAlloc:
    """A SuiteOwned var whose allocation dimension is a not-yet-called
    same-phase scheme output; spliced into call_ops by _build_call_ops once
    producer_scheme's call has been emitted."""
    var_name: str
    std_key: str
    alloc_dim_names: list
    init_value: object   # the .meta default_value literal, or None
    needs_device_residency: bool
    producer_scheme: str
    is_run_local: bool = False


@dataclass
class _CallSeqContext:
    """Read-only context shared across _build_call_ops's call-sequence walk."""
    all_args: dict
    data_ops: dict
    framework_ref_ops: list
    suite_use_stubs: list
    actual_postfixes: dict
    tgt_subroutine_postfix: "str | None"
    column_range: bool
    package_scoped: bool
    scheme_overrides: dict
    divergent_std_keys: frozenset
    arg_tables: dict


def _raise_unresolved_pending_allocs_error(pending_allocs, tgt_subroutine_postfix) -> None:
    """Raise for deferred allocations never resolved by the end of the call
    sequence (producer absent, or nested in a promoted-dimension loop)."""
    _unresolved = ", ".join(
        f"{p.var_name!r} (needs {p.producer_scheme!r} to run first)"
        for _plist in pending_allocs.values() for p in _plist
    )
    raise ValueError(
        f"Chained-interstitial allocation could not be resolved for: "
        f"{_unresolved}. This means either the producing scheme's "
        f"call never appears in this suite's call sequence for "
        f"'{tgt_subroutine_postfix}', or it's nested inside a "
        f"promoted-dimension loop body -- not yet supported for a "
        f"same-phase allocation dependency (a subcycle-nested producer IS "
        f"supported, since subcycle bodies route through the same "
        f"call-emission path as the flat case). Give the host/SDF a "
        f"call sequence where the producing scheme runs before "
        f"whatever consumes its output as an allocation dimension, "
        f"outside of any promoted-dimension loop."
    )
