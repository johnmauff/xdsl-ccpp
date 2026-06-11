import sys
from dataclasses import dataclass
from typing import ClassVar

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind


@dataclass(frozen=True)
class HostVariableMatchPass(ModulePass):
    """Annotate scheme ccpp.arg ops with their matched host model variable
    and validate that matched pairs are compatible.

    Phase 1 — Matching:
      Builds a standard_name → (local_var_name, module_name, memory_space,
      host_arg_op) index from HOST and MODULE metadata, then walks all SCHEME
      argument tables and sets model_var_name, model_module_name, and
      model_var_memory_space on each arg op whose standard_name appears in
      the index.

    Phase 2 — Compatibility checking:
      For each matched pair, checks:
        - Type (real/integer/logical/character): hard error if mismatched
        - Kind (kind_phys vs kind_dyn etc.): warning; annotates
          model_var_kind_mismatch for the future unit conversion pass
        - Dimension rank: hard error if mismatched, with known valid
          framework substitutions allowed (e.g. horizontal_loop_extent →
          horizontal_dimension)
        - Intent: hard error if scheme requires write access but host
          variable is read-only

      All hard errors are collected before raising so the developer sees
      every problem in one run.

    Naming note: 'model_var_name' and 'model_module_name' refer to the host
    MODEL (the atmospheric model that calls CCPP), not CPU host memory.
    'model_var_memory_space' is used where ambiguity with OpenACC's 'host'
    memory space would otherwise arise.

    Pipeline position: generate-meta-cap → generate-host-match → generate-suite-cap
    """

    name = "generate-host-match"

    # Standard names managed by the CCPP framework itself, or derived/computed
    # by the generated cap rather than provided directly as a named model variable.
    _CCPP_INTERNAL: ClassVar[frozenset] = frozenset([
        "ccpp_error_message",
        "ccpp_error_code",
        # Computed by suite_cap.py as (col_end - col_start + 1) rather than
        # provided directly by the host model as a named variable.
        "horizontal_loop_extent",
    ])

    # Dimension standard names that the framework transforms automatically.
    # Key: scheme-side name, Value: host-side name it maps to.
    # These are valid substitutions, not errors.
    _VALID_DIM_SUBSTITUTIONS: ClassVar[dict] = {
        "horizontal_loop_extent": "horizontal_dimension",
    }

    def _find_ccpp_module(self, ops):
        for op in ops:
            if (
                isa(op, builtin.ModuleOp)
                and op.sym_name is not None
                and op.sym_name.data == "ccpp"
            ):
                return op
        return None

    def _check_compatibility(
        self,
        scheme_arg_op: ccpp.ArgumentOp,
        host_arg_op: ccpp.ArgumentOp,
        scheme_name: str,
    ) -> tuple[list[str], list[str]]:
        """Check type, kind, dimension, and intent compatibility.

        Returns (errors, warnings) as lists of human-readable strings.
        Hard errors (type/rank/intent mismatches) go in errors.
        Soft mismatches (kind) go in warnings and are also annotated on
        the scheme arg op for the future unit conversion pass.
        """
        errors: list[str] = []
        warnings: list[str] = []
        arg_name = scheme_arg_op.arg_name.data
        ctx = f"Scheme '{scheme_name}' arg '{arg_name}'"

        scheme_type = scheme_arg_op.arg_type.data
        host_type   = host_arg_op.arg_type.data

        # ── 1. Type check ──────────────────────────────────────────────────
        if scheme_type != host_type:
            errors.append(
                f"  {ctx}: type mismatch — "
                f"scheme expects '{scheme_type}', host provides '{host_type}'"
            )
            # No point checking kind/dims/intent if types are fundamentally wrong
            return errors, warnings

        # ── 2. Kind check (real variables only) ────────────────────────────
        if scheme_type == "real":
            scheme_kind = (
                scheme_arg_op.kind.data if scheme_arg_op.kind is not None else None
            )
            host_kind = (
                host_arg_op.kind.data if host_arg_op.kind is not None else None
            )
            if scheme_kind != host_kind:
                warnings.append(
                    f"  {ctx}: kind mismatch — "
                    f"scheme expects '{scheme_kind}', host provides '{host_kind}' "
                    f"(kind cast will be needed; annotated for unit conversion pass)"
                )
                # Annotate the scheme arg op so the future conversion pass can act
                scheme_arg_op.properties["model_var_kind_mismatch"] = StringAttr(
                    f"{scheme_kind}:{host_kind}"
                )

        # ── 3. Dimension rank check ─────────────────────────────────────────
        scheme_rank = (
            scheme_arg_op.dimensions.data
            if scheme_arg_op.dimensions is not None
            else 0
        )
        host_rank = (
            host_arg_op.dimensions.data
            if host_arg_op.dimensions is not None
            else 0
        )
        if scheme_rank != host_rank:
            errors.append(
                f"  {ctx}: dimension rank mismatch — "
                f"scheme has {scheme_rank} dimension(s), "
                f"host has {host_rank} dimension(s)"
            )
        elif scheme_rank > 0:
            # Check individual dimension names, allowing known valid substitutions
            scheme_dim_names = [
                d.strip()
                for d in (
                    scheme_arg_op.dim_names.data.split(",")
                    if scheme_arg_op.dim_names is not None
                    else []
                )
            ]
            host_dim_names = [
                d.strip()
                for d in (
                    host_arg_op.dim_names.data.split(",")
                    if host_arg_op.dim_names is not None
                    else []
                )
            ]
            for i, (s_dim, h_dim) in enumerate(
                zip(scheme_dim_names, host_dim_names)
            ):
                if s_dim == h_dim:
                    continue
                # Check if this is a known framework-managed substitution
                if self._VALID_DIM_SUBSTITUTIONS.get(s_dim) == h_dim:
                    continue
                errors.append(
                    f"  {ctx}: dimension {i + 1} name mismatch — "
                    f"scheme uses '{s_dim}', host uses '{h_dim}'"
                )

        # ── 4. Intent check ─────────────────────────────────────────────────
        scheme_intent = (
            scheme_arg_op.intent.data
            if scheme_arg_op.intent is not None
            else "inout"
        )
        host_intent = (
            host_arg_op.intent.data
            if host_arg_op.intent is not None
            else None  # module-level variables with no intent are always accessible
        )
        if host_intent is not None:
            # Determine what access the scheme requires and what the host provides.
            # intent=in  → read access only
            # intent=out → write access only (value uninitialized before call)
            # intent=inout → both read and write access
            scheme_needs_read  = scheme_intent in ("in", "inout")
            scheme_needs_write = scheme_intent in ("out", "inout")
            host_provides_read  = host_intent in ("in", "inout")
            host_provides_write = host_intent in ("out", "inout")

            if scheme_needs_read and not host_provides_read:
                errors.append(
                    f"  {ctx}: intent mismatch — "
                    f"scheme '{scheme_intent}' requires read access but "
                    f"host variable has intent '{host_intent}' "
                    f"(value is uninitialized before the physics call)"
                )
            if scheme_needs_write and not host_provides_write:
                errors.append(
                    f"  {ctx}: intent mismatch — "
                    f"scheme '{scheme_intent}' requires write access but "
                    f"host variable has intent '{host_intent}' "
                    f"(host variable is read-only)"
                )

        return errors, warnings

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = self._find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        # ── Step 1: build model variable index ────────────────────────────
        # standard_name → (local_var_name, module_name, memory_space|None,
        #                   host_arg_op)
        # host_arg_op is stored so compatibility checking can read its
        # type/kind/dimensions/intent without a second IR walk.
        model_var_index: dict = {}

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data not in (
                TableTypeKind.Module, TableTypeKind.Host
            ):
                continue
            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if arg_op.standard_name is not None:
                        memory_space = (
                            arg_op.memory_space.data
                            if arg_op.memory_space is not None
                            else None
                        )
                        model_var_index[arg_op.standard_name.data] = (
                            arg_op.arg_name.data,
                            table_prop_op.table_name.data,
                            memory_space,
                            arg_op,        # host_arg_op for compatibility checking
                        )

        # ── Step 2: match scheme arguments and validate compatibility ──────
        all_errors: list[str] = []

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data != TableTypeKind.Scheme:
                continue
            scheme_name = table_prop_op.table_name.data

            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if arg_op.standard_name is None:
                        continue
                    std_name = arg_op.standard_name.data
                    if std_name in self._CCPP_INTERNAL:
                        continue

                    if std_name in model_var_index:
                        local_name, module_name, model_memory_space, host_arg_op = (
                            model_var_index[std_name]
                        )
                        # Annotate with match information
                        arg_op.properties["model_var_name"]    = StringAttr(local_name)
                        arg_op.properties["model_module_name"] = StringAttr(module_name)
                        if model_memory_space is not None:
                            arg_op.properties["model_var_memory_space"] = StringAttr(
                                model_memory_space
                            )

                        # Validate compatibility — collect errors and warnings
                        errors, warnings = self._check_compatibility(
                            arg_op, host_arg_op, scheme_name
                        )
                        all_errors.extend(errors)
                        for w in warnings:
                            print(f"Warning: {w}", file=sys.stderr)

                    elif arg_op.optional is None:
                        all_errors.append(
                            f"  Scheme '{scheme_name}': argument "
                            f"'{arg_op.arg_name.data}' "
                            f"(standard_name='{std_name}') has no matching "
                            f"host model variable"
                        )

        if all_errors:
            raise ValueError(
                "Host model variable matching/compatibility failed:\n"
                + "\n".join(all_errors)
            )
