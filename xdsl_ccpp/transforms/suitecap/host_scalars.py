"""Host dispatch scalars synthesised into suite subroutine signatures: dynamic loop counts, instance and thread arguments, suite state."""

from __future__ import annotations



from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.dialects.ccpp_utils import (
    LazyAllocOp,
    StringLiteralExprOp,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
)
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_INSTANCE_NUMBER_STD_NAME,
    CCPP_NUMBER_OF_INSTANCES_STD_NAME,
    CCPP_NUMBER_OF_THREADS_STD_NAME,
    CCPP_THREAD_NUMBER_STD_NAME,
)


def _resolve_host_only_std_name(meta_data, std_name: str):
    """Find a host-declared arg with this exact standard_name in any
    non-scheme table (module, host, or ddt).

    Used for host-only scalars no scheme declares as its own arg (e.g. a
    subcycle's dynamic loop count), which never enter all_args through
    ordinary scheme-arg host matching.
    """
    from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
    for tbl_name, props in meta_data.items():
        if props.getAttr("type") == CCPPType.SCHEME:
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if (var.hasAttr("standard_name")
                    and var.getAttr("standard_name").lower() == std_name.lower()):
                return var
    return None


def _synthesize_dynamic_loop_count_args(meta_data, call_sequence, arg_tables, all_args) -> None:
    """Mutate all_args in place: add a HostMatched dummy arg for each
    subcycle's dynamic (non-literal) loop count not already in all_args,
    so the do-loop bound is a declared argument of the suite subroutine.

    arg_tables holds only schemes for the current postfix; a count is added
    only if one of the subcycle's schemes (recursively) is in arg_tables,
    matching _emit_subcycle_items's "if sn in arg_tables" filter. Only
    called for the _run phase, matching _emit_subcycle's own guard, so
    other phases never gain an unused argument.
    """
    def _subcycle_has_active_schemes(items) -> bool:
        for item in items:
            if item[0] == "scheme":
                _, sn, _ = item
                if sn in arg_tables:
                    return True
            else:
                _, _, _, sub_items = item
                if _subcycle_has_active_schemes(sub_items):
                    return True
        return False

    def _collect_dynamic_counts(items) -> set:
        counts: set = set()
        for item in items:
            if item[0] == "subcycle":
                _, loop_count, is_literal, sub_items = item
                if not is_literal and _subcycle_has_active_schemes(sub_items):
                    counts.add(loop_count)
                counts |= _collect_dynamic_counts(sub_items)
        return counts

    for std_name in _collect_dynamic_counts(call_sequence):
        std_key = std_name.lower()
        if std_key in all_args:
            continue
        host_var = _resolve_host_only_std_name(meta_data, std_name)
        if host_var is None:
            continue
        new_arg = CCPPArgument(host_var.name)
        new_arg.setAttr("standard_name", std_name)
        new_arg.setAttr("type", host_var.getAttr("type"))
        new_arg.setAttr("intent", "in")
        if host_var.hasAttr("kind"):
            new_arg.setAttr("kind", host_var.getAttr("kind"))
        new_arg.setAttr("dimensions", 0)
        new_arg.setAttr("ownership_kind", ArgOwnershipKind.HostMatched)
        all_args[std_key] = new_arg


def _is_multi_scalar_index_host(meta_data, scalar_std_name: str, count_std_name: str) -> bool:
    """True only when the host declares BOTH members of a registered
    scalar-index pair (see CCPP_SCALAR_INDEX_DIMS), e.g. instance_number
    and number_of_instances. The pair is one contract, not two optionals.
    """
    return (
        _resolve_host_only_std_name(meta_data, scalar_std_name) is not None
        and _resolve_host_only_std_name(meta_data, count_std_name) is not None
    )


def _is_multi_instance_host(meta_data) -> bool:
    """True only when the host declares BOTH instance_number and
    number_of_instances.

    Every multi-instance codepath (ccpp_suite_state allocation, the
    constituent-API lc_instances(:) bundle, the synthesis functions below)
    assumes both are present; keep in sync with the analogous pairing in
    ccpp_cap.py/constituent_cap.py/lifecycle_cap.py.
    """
    return _is_multi_scalar_index_host(
        meta_data, CCPP_INSTANCE_NUMBER_STD_NAME, CCPP_NUMBER_OF_INSTANCES_STD_NAME
    )


def _synthesize_host_scalar_arg(
    meta_data, all_args, std_name_const: str, scalar_std_name: str, count_std_name: str
) -> None:
    """Mutate all_args in place: synthesize a HostMatched CCPPArgument for a
    host-declared scalar identified by std_name_const, if not already present.

    A no-op unless the host declares BOTH members of the pair
    (scalar_std_name, count_std_name); std_name_const is one of them.
    """
    std_key = std_name_const.lower()
    if std_key in all_args:
        return
    if not _is_multi_scalar_index_host(meta_data, scalar_std_name, count_std_name):
        return
    host_var = _resolve_host_only_std_name(meta_data, std_name_const)
    new_arg = CCPPArgument(host_var.name)
    new_arg.setAttr("standard_name", std_name_const)
    new_arg.setAttr("type", host_var.getAttr("type"))
    new_arg.setAttr("intent", "in")
    if host_var.hasAttr("kind"):
        new_arg.setAttr("kind", host_var.getAttr("kind"))
    new_arg.setAttr("dimensions", 0)
    new_arg.setAttr("ownership_kind", ArgOwnershipKind.HostMatched)
    all_args[std_key] = new_arg


def _synthesize_instance_number_arg(meta_data, all_args) -> None:
    """Mutate all_args in place: synthesize the instance_number dummy arg.

    Matches capgen-v1: instance_number is on every lifecycle call, whether
    or not a scheme's entry point for that phase declares it, so each phase
    can index its own ccpp_suite_state entry (see generateStateCheckOps/
    generateStateAssignment). Called for every phase, not just group-scoped ones.
    """
    _synthesize_host_scalar_arg(
        meta_data, all_args, CCPP_INSTANCE_NUMBER_STD_NAME,
        CCPP_INSTANCE_NUMBER_STD_NAME, CCPP_NUMBER_OF_INSTANCES_STD_NAME,
    )


def _synthesize_number_of_instances_arg(meta_data, all_args) -> None:
    """Mutate all_args in place: companion to _synthesize_instance_number_arg,
    for number_of_instances.

    Matches capgen-v1: a caller-supplied dummy argument, never
    use-associated. Its block-arg value sizes ccpp_suite_state's allocation
    (see _build_suite_state_lazy_alloc).
    """
    _synthesize_host_scalar_arg(
        meta_data, all_args, CCPP_NUMBER_OF_INSTANCES_STD_NAME,
        CCPP_INSTANCE_NUMBER_STD_NAME, CCPP_NUMBER_OF_INSTANCES_STD_NAME,
    )


def _is_multi_thread_host(meta_data) -> bool:
    """True only when the host declares BOTH thread_number and
    number_of_threads. Independent of _is_multi_instance_host.
    """
    return _is_multi_scalar_index_host(
        meta_data, CCPP_THREAD_NUMBER_STD_NAME, CCPP_NUMBER_OF_THREADS_STD_NAME
    )


def _synthesize_thread_number_arg(meta_data, all_args) -> None:
    """Mutate all_args in place: synthesize the thread_number dummy arg.

    Mirrors _synthesize_instance_number_arg. No framework state is keyed on
    it; it only lets scheme calls index a host per-thread container DDT
    (see run_dispatch.py's CCPP_SCALAR_INDEX_DIMS lookup).
    """
    _synthesize_host_scalar_arg(
        meta_data, all_args, CCPP_THREAD_NUMBER_STD_NAME,
        CCPP_THREAD_NUMBER_STD_NAME, CCPP_NUMBER_OF_THREADS_STD_NAME,
    )


def _synthesize_number_of_threads_arg(meta_data, all_args) -> None:
    """Mutate all_args in place: companion to _synthesize_thread_number_arg,
    for number_of_threads. Mirrors _synthesize_number_of_instances_arg."""
    _synthesize_host_scalar_arg(
        meta_data, all_args, CCPP_NUMBER_OF_THREADS_STD_NAME,
        CCPP_THREAD_NUMBER_STD_NAME, CCPP_NUMBER_OF_THREADS_STD_NAME,
    )


def _instance_arg_local_name(input_arg_list) -> "str | None":
    """Return the local name of the instance_number arg in input_arg_list,
    or None if absent (a non-multi-instance suite)."""
    std_key = CCPP_INSTANCE_NUMBER_STD_NAME.lower()
    for a in input_arg_list:
        _key = a.getAttr("standard_name").lower() if a.hasAttr("standard_name") else a.name
        if _key == std_key:
            return a.name
    return None


def _number_of_instances_local_name(input_arg_list) -> "str | None":
    """Return the local name of the number_of_instances arg in
    input_arg_list, or None if absent."""
    std_key = CCPP_NUMBER_OF_INSTANCES_STD_NAME.lower()
    for a in input_arg_list:
        _key = a.getAttr("standard_name").lower() if a.hasAttr("standard_name") else a.name
        if _key == std_key:
            return a.name
    return None


def _build_suite_state_lazy_alloc(ninstances_ssa) -> "LazyAllocOp":
    """Return a LazyAllocOp allocating ccpp_suite_state(ninstances_ssa),
    initialized to 'uninitialized', on first use.

    number_of_instances is a runtime host scalar in capgen-v1, so the array
    needs a runtime ALLOCATE; reuses the guarded LazyAllocOp idiom of
    SuiteOwned/framework arrays (see _build_framework_refs).
    """
    return LazyAllocOp(
        var_name="ccpp_suite_state",
        dim_var_refs=[ninstances_ssa],
        init_value_op=StringLiteralExprOp("uninitialized"),
    )
