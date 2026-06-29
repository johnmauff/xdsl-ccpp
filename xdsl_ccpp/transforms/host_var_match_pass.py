import sys
from dataclasses import dataclass
from typing import ClassVar

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr, UnitAttr
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import CcppHandleOp, TableTypeKind
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_DIMENSIONLESS_UNITS,
    CCPP_INTERNAL_STD_NAMES,
    CCPP_T_TYPE,
    UNIT_CONVERSIONS,
    dims_compatible,
    normalize_units,
)


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

    # Standard names managed by the CCPP framework — see ccpp_conventions.py.
    _CCPP_INTERNAL: ClassVar[frozenset] = CCPP_INTERNAL_STD_NAMES

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

        # ── 2b. Character length check ──────────────────────────────────────
        # When the scheme declares len=* (assumed-length) but the host provides a
        # concrete length, the generated block arg must use the host's length.
        # For arrays this is mandatory (assumed-shape + assumed-length is illegal);
        # for scalars it avoids a length mismatch error at the call site.
        if scheme_type == "character":
            scheme_kind = (
                scheme_arg_op.kind.data if scheme_arg_op.kind is not None else None
            )
            host_kind = (
                host_arg_op.kind.data if host_arg_op.kind is not None else None
            )
            if scheme_kind != host_kind and scheme_kind is not None and host_kind is not None:
                scheme_arg_op.properties["model_var_kind_mismatch"] = StringAttr(
                    f"{scheme_kind}:{host_kind}"
                )

        # ── 2b. Unit check (real variables only) ───────────────────────────
        if scheme_type == "real":
            scheme_units = normalize_units(
                scheme_arg_op.units.data if scheme_arg_op.units is not None else None
            )
            host_units = normalize_units(
                host_arg_op.units.data if host_arg_op.units is not None else None
            )
            both_dimensionless = (
                scheme_units in CCPP_DIMENSIONLESS_UNITS
                and host_units in CCPP_DIMENSIONLESS_UNITS
            )
            if scheme_units != host_units and not both_dimensionless:
                key = (scheme_units, host_units)
                if key in UNIT_CONVERSIONS:
                    scheme_arg_op.properties["model_var_unit_mismatch"] = StringAttr(
                        f"{scheme_units}:{host_units}"
                    )
                else:
                    warnings.append(
                        f"  {ctx}: unit mismatch — "
                        f"scheme expects '{scheme_units}', host provides '{host_units}' "
                        f"(no conversion available; passed as-is)"
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
            if scheme_rank < host_rank and scheme_rank > 0:
                # Possible promotion case: scheme has fewer dimensions than host.
                # Check that the scheme's dimensions form a valid prefix of the
                # host's dimensions (with framework substitutions allowed).
                # The extra host dimensions become the "promoted" dimensions that
                # the suite cap will loop over.
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
                prefix_ok = True
                for s_dim, h_dim in zip(scheme_dim_names, host_dim_names):
                    if dims_compatible(s_dim, h_dim):
                        continue
                    prefix_ok = False
                    break

                if prefix_ok and len(host_dim_names) > len(scheme_dim_names):
                    # Valid promotion — mark the arg and record which dimension(s)
                    # will be looped over in the suite cap.
                    promoted_dims = host_dim_names[len(scheme_dim_names):]
                    scheme_arg_op.properties["is_promoted"] = UnitAttr()
                    # Store the first promoted dimension (vertical loop dimension).
                    # Multiple promoted dims are a future extension.
                    scheme_arg_op.properties["promoted_dim"] = StringAttr(
                        promoted_dims[0]
                    )
                else:
                    errors.append(
                        f"  {ctx}: dimension rank mismatch — "
                        f"scheme has {scheme_rank} dimension(s), "
                        f"host has {host_rank} dimension(s)"
                    )
            else:
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
                if dims_compatible(s_dim, h_dim):
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
        #                   host_arg_op, is_ddt)
        # host_arg_op is stored so compatibility checking can read its
        # type/kind/dimensions/intent without a second IR walk.
        # is_ddt is True when the variable is a member of a DDT type rather
        # than a flat module variable.  DDT members are indexed here so the
        # matching step does not raise "no matching host model variable" errors,
        # but they are flagged so downstream code generation can handle them
        # differently (DDT member access requires instance%member notation).
        model_var_index: dict = {}
        # If the host metadata declares a ccpp_t variable, capture it here
        # so we can emit a CcppHandleOp after the index is fully built.
        _ccpp_handle: "tuple[str, str] | None" = None  # (var_name, module_name)

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data not in (
                TableTypeKind.Module, TableTypeKind.Host, TableTypeKind.DDT
            ):
                continue
            is_ddt = table_prop_op.table_type.data == TableTypeKind.DDT
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
                        # Detect the ccpp_t handle variable — capture it for
                        # CcppHandleOp emission below.  Not added to model_var_index
                        # since no scheme arg carries standard_name = ccpp_t_instance.
                        if arg_op.arg_type.data.lower() == CCPP_T_TYPE:
                            _ccpp_handle = (
                                arg_op.arg_name.data,
                                table_prop_op.table_name.data,
                            )
                            continue
                        # Use lowercase key — CCPP standard names are case-insensitive
                        model_var_index[arg_op.standard_name.data.lower()] = (
                            arg_op.arg_name.data,
                            table_prop_op.table_name.data,
                            memory_space,
                            arg_op,        # host_arg_op for compatibility checking
                            is_ddt,
                        )

        # ── Step 1a: emit CcppHandleOp if a ccpp_t variable was found ─────
        if _ccpp_handle is not None:
            var_name, module_name = _ccpp_handle
            ccpp_mod.body.block.add_op(CcppHandleOp(var_name, module_name))

        # ── Step 1b: build interstitial variable index ────────────────────
        # Collect standard_names that are produced (intent=out or inout) by
        # any scheme's _init or _timestep_init entry point.  Variables that
        # are produced in init and consumed in run, but have no host model
        # match, are interstitial — they flow between lifecycle phases inside
        # the suite cap and are managed by the framework, not the host model.
        #
        # key:   standard_name (lowercase)
        # value: (arg_op, scheme_name, entry_point_name)
        produced_in_init: dict = {}
        # Include _run as a producer suffix: variables produced by one scheme's
        # _run and consumed by another scheme's _run (with no host match) are
        # also interstitial — they flow between scheme calls within the suite.
        _INIT_SUFFIXES = ("_init", "_timestep_init", "_register", "_run")

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data != TableTypeKind.Scheme:
                continue
            scheme_nm = table_prop_op.table_name.data
            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                ep_name = arg_table_op.table_name.data
                if not any(ep_name.endswith(s) for s in _INIT_SUFFIXES):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if arg_op.standard_name is None:
                        continue
                    intent = (
                        arg_op.intent.data if arg_op.intent is not None else None
                    )
                    if intent in ("out", "inout"):
                        sn = arg_op.standard_name.data.lower()
                        produced_in_init[sn] = (arg_op, scheme_nm, ep_name)

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
                    # Normalise to lowercase — CCPP standard names are case-insensitive
                    std_name = arg_op.standard_name.data.lower()
                    if std_name in self._CCPP_INTERNAL:
                        continue
                    # Allocatable variables are dynamically allocated by the
                    # CCPP framework itself — they are not provided by the host
                    # model and do not need a host variable match.
                    if arg_op.allocatable is not None:
                        continue
                    # Advected variables are constituent mixing ratios transported
                    # by the dynamical core.  They live inside the host model's
                    # constituent array and are accessed through the constituent
                    # framework mechanism, not as directly named host variables.
                    if arg_op.advected is not None:
                        continue
                    # Constituent variables (tendencies, diagnostics) are managed
                    # by the CCPP constituent framework, not provided as directly
                    # named host model variables.
                    if arg_op.constituent is not None:
                        continue

                    if std_name in model_var_index:
                        local_name, module_name, model_memory_space, host_arg_op, is_ddt = (
                            model_var_index[std_name]
                        )
                        # Annotate with match information
                        arg_op.properties["model_var_name"]    = StringAttr(local_name)
                        arg_op.properties["model_module_name"] = StringAttr(module_name)
                        if model_memory_space is not None:
                            arg_op.properties["model_var_memory_space"] = StringAttr(
                                model_memory_space
                            )
                        if is_ddt:
                            # Mark as DDT member so code generation can emit
                            # instance%member notation rather than a plain USE.
                            arg_op.properties["model_var_is_ddt"] = UnitAttr()

                        # Validate compatibility — collect errors and warnings
                        errors, warnings = self._check_compatibility(
                            arg_op, host_arg_op, scheme_name
                        )
                        all_errors.extend(errors)
                        for w in warnings:
                            print(f"Warning: {w}", file=sys.stderr)

                    elif arg_op.optional is None and arg_op.default_value is None:
                        # Check if this is an interstitial variable — one that
                        # is produced by a scheme's _init entry point and consumed
                        # by a scheme's _run entry point within the same suite.
                        # These flow between lifecycle phases inside the suite cap
                        # and are managed by the framework rather than the host model.
                        if std_name in produced_in_init:
                            producer_arg, producer_scheme, producer_ep = (
                                produced_in_init[std_name]
                            )
                            # A DDT member cannot be an interstitial: the DDT
                            # instance is host-owned, so its member cannot be
                            # independently managed at suite cap module scope.
                            # This path should be unreachable because DDT members
                            # always have model_var_name set (they have a host match)
                            # and therefore never reach this elif branch.
                            if "model_var_is_ddt" in producer_arg.properties:
                                all_errors.append(
                                    f"  Scheme '{scheme_name}': argument "
                                    f"'{arg_op.arg_name.data}' "
                                    f"(standard_name='{std_name}') is a DDT member "
                                    f"produced by '{producer_scheme}' ({producer_ep}) "
                                    f"and cannot be treated as a suite interstitial — "
                                    f"DDT instance is host-owned."
                                )
                            else:
                                arg_op.properties["is_interstitial"] = UnitAttr()
                        else:
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
