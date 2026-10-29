"""Suite-cap module contents: use stubs, state globals, module variables and post-generation fix-ups."""

from __future__ import annotations


from xdsl.dialects import func, llvm, memref
from xdsl.dialects.builtin import (
    StringAttr,
    i8,
)
from xdsl.pattern_rewriter import (
    InsertPoint,
)
from xdsl.rewriter import Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    LazyAllocOp,
    ModuleVarOp,
    SafeDeallocOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _collect_ddt_use_stubs,
    fn_phase,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_KIND_PHYS,
    mark_allocatable_local,
)
from xdsl_ccpp.transforms.suitecap.host_scalars import (
    _is_multi_instance_host,
)


class ModuleAssemblyMixin:
    """Suite-cap module contents: use stubs, state globals, module variables and post-generation fix-ups."""

    def _build_ddt_use_stubs(self, scheme_entries: list) -> list:
        """Return llvm.GlobalOp USE-stubs for each DDT type referenced by scheme args."""
        arg_tables_iterable = (
            arg_table
            for scheme_name, _ in scheme_entries
            if scheme_name in self.meta_data
            for arg_table in self.meta_data[scheme_name].arg_tables.values()
        )
        return _collect_ddt_use_stubs(arg_tables_iterable, self.ddt_source_module)

    def _build_state_globals(self, all_strings_used: set):
        """Return the mutable ccpp_suite_state global and one read-only global per state string.

        For a multi-instance host (_is_multi_instance_host; matches capgen-v1's
        instances model) ccpp_suite_state holds one entry per instance, so it
        is declared allocatable and sized lazily (_build_suite_state_lazy_alloc)
        since number_of_instances is a runtime value.
        """
        ccpp_suite_state_global = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(16, i8),
            "ccpp_suite_state",
            "internal",
            value=StringAttr("uninitialized"),
        )
        if _is_multi_instance_host(self.meta_data):
            ccpp_suite_state_global.attributes["allocatable"] = StringAttr("1")
        string_const_globals = [
            self.generateStringConstantGlobal(s) for s in sorted(all_strings_used)
        ]
        return ccpp_suite_state_global, string_const_globals

    def _build_module_vars(self, suite_model):
        """Return (allocatable_mod_vars, interstitial_var_names, run_local_entries).

        run_local_entries are declared as locals in _run, not at module scope.
        """
        interstitial_var_names: set[str] = set()
        allocatable_mod_vars = []
        run_local_entries = []
        for entry in suite_model.suite_owned_vars():
            if (entry.rank > 0 and not entry.is_ddt
                    and self._is_run_local_var(entry, suite_model)):
                run_local_entries.append(entry)
                continue
            if entry.is_ddt:
                # DDT interstitials are module-scope non-allocatable scalars.
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "type", ddt_name=entry.fortran_type, rank=0)
                )
                interstitial_var_names.add(entry.local_name.lower())
                continue
            if entry.fortran_type == "real":
                kind = entry.kind if entry.kind else CCPP_KIND_PHYS
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "real", kind=kind, rank=entry.rank,
                                needs_device_residency=entry.needs_device_residency)
                )
            elif entry.fortran_type == "integer":
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "integer", rank=entry.rank,
                                needs_device_residency=entry.needs_device_residency)
                )
            elif entry.fortran_type == "character":
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "character",
                                char_len=TypeConversions.char_len(entry.kind), rank=entry.rank,
                                needs_device_residency=entry.needs_device_residency)
                )
            else:
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, entry.fortran_type,
                                kind=entry.kind if entry.kind else None, rank=entry.rank,
                                needs_device_residency=entry.needs_device_residency)
                )
            interstitial_var_names.add(entry.local_name.lower())
        return allocatable_mod_vars, interstitial_var_names, run_local_entries

    @staticmethod
    def _inject_run_local_var_handling(generated_fns, run_local_entries):
        """Inject local allocatable decls and end-of-run SafeDeallocOps for run-local vars.

        Run-local vars are dimensioned by a repeating-phase scalar (e.g. nday
        from a _timestep_init), so each call must see the current size. The
        run FuncOp is found by a LazyAllocOp with is_run_local=True, or by its
        "run" phase tag (for scheme-allocated vars).
        """
        for fn in generated_fns:
            if not isa(fn, func.FuncOp):
                continue
            if not fn.body.blocks:
                continue
            block = fn.body.blocks[0]
            has_run_local_alloc = any(
                isa(bop, LazyAllocOp)
                and bop.is_run_local is not None
                and bool(bop.is_run_local.value.data)
                for bop in block.ops
            )
            # Scheme-allocated vars have no LazyAllocOp; use the phase tag.
            if not (has_run_local_alloc or fn_phase(fn) == "run"):
                continue
            ret_op = next((bop for bop in block.ops if isa(bop, func.ReturnOp)), None)
            if ret_op is None:
                continue
            for entry in run_local_entries:
                full_type = TypeConversions.convert(
                    entry.fortran_type, entry.kind if entry.kind else None, entry.rank
                )
                alloca = memref.AllocaOp.get(
                    full_type.element_type, shape=[0] * entry.rank
                )
                mark_allocatable_local(alloca, entry.local_name)
                Rewriter.insert_op(alloca, InsertPoint.at_start(block))
                Rewriter.insert_op(
                    SafeDeallocOp(entry.local_name), InsertPoint.before(ret_op)
                )

    @staticmethod
    def _inject_safe_deallocs(generated_fns, allocatable_mod_vars, interstitial_var_names):
        """Inject SafeDeallocOps for allocatable arrays before the return of _timestep_final."""
        for fn in generated_fns:
            if not isa(fn, func.FuncOp):
                continue
            if fn_phase(fn) != "timestep_final":
                continue
            if not fn.body.blocks:
                continue
            block = fn.body.blocks[0]
            ret_op = next((bop for bop in block.ops if isa(bop, func.ReturnOp)), None)
            if ret_op is None:
                continue
            for var_decl in allocatable_mod_vars:
                # Arrays only; skip interstitials (persist until _finalize) and
                # POINTER vars (deallocating a non-owning pointer is invalid).
                _is_ptr = bool(var_decl.is_pointer is not None
                               and var_decl.is_pointer.value.data)
                if var_decl.rank.value.data > 0 and not _is_ptr and \
                        var_decl.var_name.data.lower() not in interstitial_var_names:
                    Rewriter.insert_op(SafeDeallocOp(var_decl.var_name.data),
                                       InsertPoint.before(ret_op))
