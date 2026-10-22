"""Package caps (composite-scheme 2f): generate one Fortran module per
``ccpp.package_cap`` op left by the ``lower-packages`` pass.

Each ``ccpp.segment`` becomes one routine, ``<segment>_<phase>``, generated
by the same code as a suite group's function for that phase (physics mode,
except ``register``, which runs at suite level), but without suite-state
checks. The suite cap calls it as a scheme of the same name. Arguments the
package's schemes share with the outside arrive as dummy arguments;
package-private names are module variables of the package cap.
"""

from __future__ import annotations

from xdsl.dialects import builtin
from xdsl.dialects.builtin import BoolAttr, StringAttr
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import LazyAllocOp
from xdsl_ccpp.transforms.lower_packages import state_create_scheme, state_delete_scheme
from xdsl_ccpp.transforms.package_scope import private_name
from xdsl_ccpp.transforms.suitecap.block_args import _std_key
from xdsl_ccpp.transforms.util.cap_shared import FN_PHASE_ATTR
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildSchemeDescription,
    XMLGroup,
    XMLScheme,
    XMLSuite,
)
from xdsl_ccpp.transforms.util.suite_variable_model import SuiteVariableModel

PACKAGE_CAP_ATTR = "ccpp_package_cap"

# Phases a segment runs in every time step. Package state allocated there is
# sized by extents that can change between calls (e.g. CAM's daylit-column
# count, set outside the package), so it is reallocated when they do.
_REPEATING = {"timestep_init", "run", "timestep_final"}

# Segment phase -> (generator's phase postfix, phase tag of the function).
_PHASES = {
    "register": ("_register", "suite_register"),
    "init": ("_init", "group_init"),
    "timestep_init": ("_timestep_initialize", "timestep_init"),
    "run": ("_run", "run"),
    "timestep_final": ("_timestep_finalize", "timestep_final"),
    "final": ("_finalize", "group_final"),
}


def _segment_group(segment: ccpp.SegmentOp, bsd: BuildSchemeDescription) -> XMLGroup:
    """An in-memory group holding a segment's calls."""
    group = XMLGroup(segment.segment_name.data)
    for op in segment.body.block.ops:
        if isa(op, ccpp.SubcycleOp):
            group.addChild(bsd._build_subcycle(op))
        elif isa(op, ccpp.SchemeOp):
            overrides = {}
            if op.arg_overrides is not None:
                overrides = {k: v.data for k, v in op.arg_overrides.data.items()}
            group.addChild(XMLScheme(op.scheme_name.data, overrides))
    return group


def _package_cap_module(gen, package_cap: ccpp.PackageCapOp) -> builtin.ModuleOp:
    package = package_cap.package_name.data
    bsd = BuildSchemeDescription()
    segments = [s for s in package_cap.body.block.ops if isa(s, ccpp.SegmentOp)]
    groups = [_segment_group(s, bsd) for s in segments]

    package_suite = XMLSuite(f"{package}_package", "1.0")
    for group in groups:
        package_suite.addChild(group)
    suite_model = SuiteVariableModel(package_suite, gen.meta_data, _std_key)
    # Only private names live here; the rest arrive as dummy arguments.
    private_prefix = private_name(package, "")
    suite_model.keep_only(lambda std: std.startswith(private_prefix))

    generated_fns = []
    fn_sigs_by_name: dict = {}
    use_stubs = []
    scheduled_allocs: set = set()
    deferred_warnings: list = []
    # Allocation order in segments follows what their schemes write first
    # (promotion.py, _resolve_alloc_dim_var_refs).
    def state_routine(scheme, target_postfix, generated_postfix, tag):
        """A routine of the package's state schemes: no scheme calls, only
        the allocation of private state (create) or, after the GPU exit
        injection below, its deletion from the device (delete)."""
        state_suite = XMLSuite(scheme, "1.0")
        for group in groups:
            state_suite.addChild(group)
        fn, sigs, stubs = gen.generateSubroutineCall(
            state_suite, target_postfix, generated_postfix,
            state_string=None, check_string=None, physics_mode=False,
            suite_model=suite_model, already_scheduled_allocs=scheduled_allocs,
            deferred_warnings=deferred_warnings, emit_scheme_calls=False,
        )
        fn.attributes[FN_PHASE_ATTR] = StringAttr(tag)
        generated_fns.append(fn)
        use_stubs.extend(stubs)
        for sig in sigs:
            fn_sigs_by_name[sig.sym_name.data] = sig

    gen.generating_package_cap = True
    try:
        # First, so private arrays sized at init are allocated there.
        state_routine(state_create_scheme(package), "_init", "_init", "suite_initialize")
        for segment, group in zip(segments, groups):
            postfix, tag = _PHASES[segment.phase.data]
            segment_suite = XMLSuite(segment.segment_name.data, "1.0")
            segment_suite.addChild(group)
            fn, sigs, stubs = gen.generateSubroutineCall(
                segment_suite, postfix, f"_{segment.phase.data}",
                state_string=None, check_string=None,
                physics_mode=segment.phase.data != "register",
                group_name=segment.segment_name.data, suite_model=suite_model,
                already_scheduled_allocs=scheduled_allocs,
                deferred_warnings=deferred_warnings,
            )
            fn.attributes[FN_PHASE_ATTR] = StringAttr(tag)
            if segment.phase.data in _REPEATING:
                for op in fn.walk():
                    if isa(op, LazyAllocOp) and op.is_run_local is None:
                        op.properties["realloc_on_resize"] = BoolAttr.from_bool(True)
            generated_fns.append(fn)
            use_stubs.extend(stubs)
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
        state_routine(state_delete_scheme(package), "_finalize", "_finalize", "suite_finalize")
    finally:
        gen.generating_package_cap = False

    scheme_entries = gen.getSchemeNames(package_suite)
    fn_sigs = gen._build_fn_signatures(fn_sigs_by_name, scheme_entries, [])
    type_import_globals = gen._build_ddt_use_stubs(scheme_entries)
    allocatable_mod_vars, interstitial_var_names, run_local_entries = (
        gen._build_module_vars(suite_model))
    if allocatable_mod_vars:
        gen._inject_safe_deallocs(generated_fns, allocatable_mod_vars, interstitial_var_names)
    if run_local_entries:
        gen._inject_run_local_var_handling(generated_fns, run_local_entries)
    # Device-resident private state leaves the device in the delete routine.
    gen._inject_suite_owned_gpu_exit(generated_fns, suite_model)

    seen: set = set()
    stubs = []
    for stub in use_stubs:
        module_attr = stub.attributes.get("module")
        key = (stub.sym_name.data, module_attr.data if module_attr else "")
        if key not in seen:
            seen.add(key)
            stubs.append(stub)

    module = builtin.ModuleOp(
        type_import_globals + stubs + allocatable_mod_vars + generated_fns + fn_sigs,
        sym_name=StringAttr(f"{package}_package_cap"),
    )
    module.attributes[PACKAGE_CAP_ATTR] = StringAttr(package)
    return module


def generate_package_caps(gen, top_module: builtin.ModuleOp) -> None:
    """Replace every ``ccpp.package_cap`` op in *top_module* with its
    generated package-cap module.  *gen* is the suite-cap generator (it
    carries the metadata the segments are generated from)."""
    for package_cap in [o for o in top_module.body.block.ops if isa(o, ccpp.PackageCapOp)]:
        module = _package_cap_module(gen, package_cap)
        Rewriter.insert_op(module, InsertPoint.at_start(top_module.body.block))
        Rewriter.erase_op(package_cap)
