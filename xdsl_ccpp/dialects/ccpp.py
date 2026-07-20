from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum, auto
from typing import ClassVar

from xdsl.dialects.builtin import (
    BoolAttr,
    DictionaryAttr,
    IntAttr,
    StringAttr,
    UnitAttr,
)
from xdsl.ir import (
    Block,
    Dialect,
    EnumAttribute,
    Operation,
    Region,
    SpacedOpaqueSyntaxAttribute,
    VerifyException,
)
from xdsl.irdl import (
    IRDLOperation,
    irdl_attr_definition,
    irdl_op_definition,
    opt_prop_def,
    prop_def,
    region_def,
    traits_def,
)
from xdsl.traits import NoTerminator
from xdsl.utils.hints import isa


class TableTypeKind(StrEnum):
    Scheme = auto()
    Module = auto()
    DDT = auto()
    Host = auto()


@irdl_attr_definition
class TableTypeKindAttr(EnumAttribute[TableTypeKind], SpacedOpaqueSyntaxAttribute):
    name = "ccpp.table_type_kind"


@irdl_op_definition
class SuiteOp(IRDLOperation):
    name = "ccpp.suite"

    suite_name = prop_def(StringAttr)
    version = opt_prop_def(StringAttr)

    body = region_def("single_block")

    traits = traits_def(
        NoTerminator(),
    )

    def __init__(
        self,
        suite_name: str | StringAttr,
        body: Region | Sequence[Operation] | Sequence[Block],
        version: str | StringAttr | None = None,
    ):

        if isa(suite_name, str):
            suite_name = StringAttr(suite_name)

        properties = {"suite_name": suite_name}

        if version is not None:
            if isa(version, str):
                version = StringAttr(version)
            properties["version"] = version

        super().__init__(regions=[body], properties=properties)


@irdl_op_definition
class GroupOp(IRDLOperation):
    name = "ccpp.group"

    group_name = prop_def(StringAttr)

    body = region_def("single_block")

    traits = traits_def(
        NoTerminator(),
    )

    def __init__(
        self,
        group_name: str | StringAttr,
        body: Region | Sequence[Operation] | Sequence[Block],
    ):

        if isa(group_name, str):
            group_name = StringAttr(group_name)

        properties = {"group_name": group_name}

        super().__init__(regions=[body], properties=properties)


@irdl_op_definition
class SchemeOp(IRDLOperation):
    name = "ccpp.scheme"

    scheme_name = prop_def(StringAttr)
    # Compile-time keyword argument overrides: {arg_name → literal_value_str}.
    # Present only when the Python frontend specifies per-call overrides.
    arg_overrides = opt_prop_def(DictionaryAttr)

    def __init__(
        self,
        scheme_name: str | StringAttr,
        overrides: dict[str, str] | None = None,
    ):
        if isa(scheme_name, str):
            scheme_name = StringAttr(scheme_name)

        properties: dict = {"scheme_name": scheme_name}
        if overrides:
            properties["arg_overrides"] = DictionaryAttr(
                {k: StringAttr(str(v)) for k, v in overrides.items()}
            )

        super().__init__(properties=properties)


@irdl_op_definition
class SubcycleOp(IRDLOperation):
    """A block of scheme calls that execute inside a Fortran do loop.

    Corresponds to ``<subcycle loop="N">`` in a suite XML file.
    ``loop_count == "1"`` means the schemes run once (no do loop emitted).
    ``loop_count`` may also be a CCPP standard name resolved at runtime;
    ``is_literal`` distinguishes the two cases so consumers need not guess.
    """

    name = "ccpp.subcycle"

    loop_count = prop_def(StringAttr)
    is_literal = prop_def(BoolAttr)

    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        loop_count: "int | str",
        body: "Region | Sequence[Operation] | Sequence[Block]",
        is_literal: bool = True,
    ):
        if not isinstance(body, Region):
            body = Region([Block(list(body))])
        super().__init__(
            regions=[body],
            properties={
                "loop_count": StringAttr(str(loop_count)),
                "is_literal": BoolAttr.from_bool(is_literal),
            },
        )


@irdl_op_definition
class CcppHandleOp(IRDLOperation):
    """Records the host model's ccpp_t variable for use by cap-generation passes.

    Emitted by HostVariableMatchPass when it finds a host metadata argument
    with ``type = ccpp_t``.  Cap-generation passes locate this op to thread
    the ccpp_t handle through every generated subroutine signature.

    ``var_name``    — local Fortran variable name (e.g. ``ccpp_data``)
    ``module_name`` — host Fortran module that declares it (e.g. ``data``)
    """

    name = "ccpp.ccpp_handle"

    var_name    = prop_def(StringAttr)
    module_name = prop_def(StringAttr)

    def __init__(self, var_name: str, module_name: str):
        super().__init__(
            properties={
                "var_name":    StringAttr(var_name),
                "module_name": StringAttr(module_name),
            }
        )


class TableBaseOp(IRDLOperation):
    table_name = prop_def(StringAttr, prop_name="name")
    table_type = prop_def(TableTypeKindAttr, prop_name="type")

    body = region_def("single_block")

    traits = traits_def(
        NoTerminator(),
    )

    def __init__(
        self,
        table_name: str | StringAttr,
        table_type: str | TableTypeKindAttr,
        body: Region | Sequence[Operation] | Sequence[Block],
        attributes: dict | None = None,
    ):

        if isa(table_name, str):
            table_name = StringAttr(table_name)

        if isa(table_type, str):
            table_type = TableTypeKindAttr(TableTypeKind(table_type))

        if not isinstance(body, Region):
            body = Region([Block(body)])

        super().__init__(
            regions=[body],
            properties={"name": table_name, "type": table_type},
            attributes=attributes or {},
        )


@irdl_op_definition
class TablePropertiesOp(TableBaseOp):
    name = "ccpp.table_properties"
    # source_module is set dynamically via properties dict (not declared as ClassVar
    # because xDSL requires ClassVar names to be uppercase).
    # It holds the stem of the .meta file = the Fortran module name for this table.


@irdl_op_definition
class ArgumentTableOp(TableBaseOp):
    name = "ccpp.arg_table"


@irdl_op_definition
class KindOp(IRDLOperation):
    """A single named kind entry within a ccpp.kinds block.

    Represents one Fortran kind parameter discovered from the scheme metadata,
    e.g. ``kind_phys``.  The ``name`` property holds the Fortran identifier and
    ``value`` holds its corresponding definition (may be the same string when
    only the name is known from the metadata).
    """

    name = "ccpp.kind"

    kind_name = prop_def(StringAttr, prop_name="name")
    kind_value = prop_def(StringAttr, prop_name="value")

    def __init__(self, kind_name: str | StringAttr, kind_value: str | StringAttr):
        if isa(kind_name, str):
            kind_name = StringAttr(kind_name)
        if isa(kind_value, str):
            kind_value = StringAttr(kind_value)
        super().__init__(properties={"name": kind_name, "value": kind_value})


@irdl_op_definition
class KindsOp(IRDLOperation):
    """Container for all real kind parameters discovered in the scheme metadata.

    Placed at the top of the ``@ccpp`` named module by the ``generate-meta-kinds``
    pass.  Its single-block body holds one `KindOp` per unique kind name found
    across all ``ccpp.arg`` ops whose type is ``real``.  The op is omitted
    entirely when no real kinds are present.
    """

    name = "ccpp.kinds"

    body = region_def("single_block")

    traits = traits_def(
        NoTerminator(),
    )

    def __init__(self, kind_ops: Sequence[Operation]):
        super().__init__(regions=[kind_ops])


class ArgOwnershipKind(StrEnum):
    """Does the cap own this scheme arg, or does its data come from outside?

    Decided once, upfront -- before suite_cap.py builds the suite's own
    subroutine signature -- unlike ArgSourceKind/ResolvedArgOp below, which
    only classifies args that already survived *not* being SuiteOwned (an
    interstitial/advected/allocatable-real arg never becomes a dummy arg at
    all, so it never reaches ResolvedArgOp's world -- there is deliberately
    no SuiteOwned case there). Phase 7 (see ccpp_cap_refactor_plan.md) is
    where suite_cap.py's _is_framework_managed and ccpp_cap.py's
    _build_cap_var_map -- today two independently-computed heuristics for
    this same ownership question -- both migrate to reading this instead.

    SuiteOwned:   interstitial, or advected/allocatable real array -- suite
                  cap owns storage; never a dummy arg on the suite's
                  subroutine signature at all.
    HostMatched:  resolved against host metadata (module var or DDT member --
                  ArgSourceKind's Host/DdtMember split is a finer, later-stage
                  distinction this classification doesn't need).
    CapScratch:   no host match; promoted to a cap-owned module variable
                  (framework array like ccpp_constituents, or scheme-local
                  scratch with no host counterpart). Equivalent to
                  ArgSourceKind.CapVar.
    Block:        genuinely unresolved -- becomes a caller-supplied block
                  argument. Equivalent to ArgSourceKind.Block.
    """

    SuiteOwned = "suite_owned"
    HostMatched = "host_matched"
    CapScratch = "cap_scratch"
    Block = "block"


@irdl_attr_definition
class ArgOwnershipKindAttr(EnumAttribute[ArgOwnershipKind], SpacedOpaqueSyntaxAttribute):
    name = "ccpp.arg_ownership_kind"


@irdl_op_definition
class ArgumentOp(IRDLOperation):
    name = "ccpp.arg"

    arg_name = prop_def(StringAttr, prop_name="name")
    arg_type = prop_def(StringAttr, prop_name="type")
    standard_name = opt_prop_def(StringAttr)
    long_name = opt_prop_def(StringAttr)
    # Number of array dimensions (0 = scalar). Stored as IntAttr.
    dimensions = opt_prop_def(IntAttr)
    # Comma-separated dimension standard names, e.g. "horizontal_dimension,vertical_layer_dimension"
    dim_names = opt_prop_def(StringAttr)
    kind = opt_prop_def(StringAttr)
    intent = opt_prop_def(StringAttr)
    units = opt_prop_def(StringAttr)
    memory_space = opt_prop_def(StringAttr)  # values: "host", "device", "unified"
    model_var_name    = opt_prop_def(StringAttr)   # matched host model variable name
    model_module_name = opt_prop_def(StringAttr)   # module containing the host model variable
    model_var_memory_space  = opt_prop_def(StringAttr)  # memory space declared by the host model
    model_var_array_layout  = opt_prop_def(StringAttr)  # "row_major" when host table declares array_layout = row_major
    model_var_kind_mismatch = opt_prop_def(StringAttr)  # set when scheme/host kinds differ: "scheme_kind:host_kind"
    model_var_unit_mismatch = opt_prop_def(StringAttr)  # set when scheme/host units differ: "scheme_units:host_units"
    model_var_is_ddt   = opt_prop_def(UnitAttr)  # set when matched var is a DDT member
    is_interstitial    = opt_prop_def(UnitAttr)   # set when var flows between lifecycle phases
    # Phase 7, Stage 2: durable ownership classification (see ArgOwnershipKind),
    # set by generate-arg-ownership. Reuses this op's own standard_name for the
    # HostMatched/CapScratch payload rather than storing it a second time.
    ownership_kind    = opt_prop_def(ArgOwnershipKindAttr)
    is_promoted        = opt_prop_def(UnitAttr)   # set when scheme rank < host rank (promotion)
    promoted_dim       = opt_prop_def(StringAttr) # standard name of the dimension being promoted over
    allocatable = opt_prop_def(UnitAttr)
    advected    = opt_prop_def(UnitAttr)
    constituent = opt_prop_def(UnitAttr)  # CCPP constituent framework variable
    protected            = opt_prop_def(UnitAttr)    # read-only from the framework's perspective
    state_variable       = opt_prop_def(UnitAttr)    # conserved physics state quantity
    default_value        = opt_prop_def(StringAttr)  # framework initializes to this value if host doesn't provide
    diagnostic_name       = opt_prop_def(StringAttr)  # name used by the diagnostic output system
    diagnostic_name_fixed = opt_prop_def(StringAttr)  # fixed diagnostic name regardless of suite instance
    active                = opt_prop_def(StringAttr)  # Fortran logical expression controlling when variable is active
    optional             = opt_prop_def(UnitAttr)

    # All keys recognised by __init__. Used externally to warn on unrecognised keys.
    KNOWN_PROPS: ClassVar[frozenset] = frozenset([
        "type", "dimensions", "standard_name", "long_name",
        "kind", "intent", "units", "memory_space", "optional",
        "allocatable", "advected", "constituent", "protected", "state_variable",
        "default_value", "diagnostic_name", "diagnostic_name_fixed", "active",
    ])

    def __init__(
        self, arg_name: str | StringAttr, arg_type: str | StringAttr, attributes
    ):
        if isa(arg_name, str):
            arg_name = StringAttr(arg_name)

        if isa(arg_type, str):
            arg_type = StringAttr(arg_type)

        properties = {"name": arg_name, "type": arg_type}
        prop_keys = list(attributes.keys())
        prop_keys.remove("type")

        # Parse the dimensions tuple string, e.g. "(ncol, lev)" → 2 dimensions
        if "dimensions" in prop_keys:
            dim_str = attributes["dimensions"].strip().strip("()")
            dim_parts = (
                [d.strip() for d in dim_str.split(",") if d.strip()]
                if dim_str.strip()
                else []
            )
            ndims = len(dim_parts)
            if ndims > 0:
                properties["dimensions"] = IntAttr(ndims)
                # Store dimension standard names (handle range notation like
                # 'ccpp_constant_one:horizontal_loop_extent' → take upper bound)
                parsed_dims = []
                for d in dim_parts:
                    if ":" in d:
                        d = d.split(":")[1].strip()
                    parsed_dims.append(d)
                properties["dim_names"] = StringAttr(",".join(parsed_dims))
            prop_keys.remove("dimensions")

        known_props = ["standard_name", "long_name", "kind", "intent", "units", "memory_space",
                       "default_value", "diagnostic_name", "diagnostic_name_fixed", "active"]
        for prop in known_props:
            if prop in attributes:
                properties[prop] = StringAttr(attributes[prop])
                prop_keys.remove(prop)

        def _flag_is_true(val) -> bool:
            """Return True for any recognised truthy boolean: True/true/.true."""
            return str(val).strip().lower() in ("true", ".true.")

        for flag in ("optional", "allocatable", "advected", "constituent",
                     "protected", "state_variable"):
            if flag in attributes:
                if _flag_is_true(attributes[flag]):
                    properties[flag] = UnitAttr()
                prop_keys.remove(flag)

        # Silently ignore unrecognised keys

        super().__init__(properties=properties)


class ArgSourceKind(StrEnum):
    """Where a resolved scheme-call argument's data comes from.

    Host:      a host module variable, accessed via a Fortran USE statement.
    DdtMember: a member of a module-level DDT instance (accessed as
               ``instance%path%member``).
    CapVar:    a cap-owned module variable (e.g. a constituent interstitial).
    Block:     unresolved -- the argument becomes a caller-supplied block
               argument instead.
    """

    Host = "host"
    DdtMember = "ddt_member"
    CapVar = "cap_var"
    Block = "block"


@irdl_attr_definition
class ArgSourceKindAttr(EnumAttribute[ArgSourceKind], SpacedOpaqueSyntaxAttribute):
    name = "ccpp.arg_source_kind"


@irdl_op_definition
class ResolvedArgOp(IRDLOperation):
    """Durable record of where one scheme-call argument's data comes from.

    Built directly by run_dispatch.py's _build_per_suite_run_info (one op per
    callee input arg, classifying it as a host module variable, a DDT member,
    a cap-owned variable, or a caller-supplied block argument) and read by
    _build_run_dispatch_chain when constructing the actual SSA reference
    (e.g. ``HostVarRefOp``, which accepts a ``member_name`` for the
    DdtMember case) -- this op makes that resolution decision durable and
    inspectable on its own, independent of that later construction step.

    Required properties by ``source_kind``:
      - Host:      ``var_name``, ``module_name``
      - DdtMember: ``var_name``, ``module_name``, ``member_path``
      - CapVar:    ``std_name``
      - Block:     none of the above
    """

    name = "ccpp.resolved_arg"

    arg_name = prop_def(StringAttr)
    source_kind = prop_def(ArgSourceKindAttr)
    var_name = opt_prop_def(StringAttr)
    module_name = opt_prop_def(StringAttr)
    member_path = opt_prop_def(StringAttr)
    std_name = opt_prop_def(StringAttr)

    def __init__(
        self,
        arg_name: str | StringAttr,
        source_kind: "str | ArgSourceKind | ArgSourceKindAttr",
        var_name: str | StringAttr | None = None,
        module_name: str | StringAttr | None = None,
        member_path: str | StringAttr | None = None,
        std_name: str | StringAttr | None = None,
    ):
        if isa(arg_name, str):
            arg_name = StringAttr(arg_name)
        if isinstance(source_kind, str):
            source_kind = ArgSourceKindAttr(ArgSourceKind(source_kind))
        elif isinstance(source_kind, ArgSourceKind):
            source_kind = ArgSourceKindAttr(source_kind)

        properties: dict = {"arg_name": arg_name, "source_kind": source_kind}
        if var_name is not None:
            properties["var_name"] = StringAttr(var_name) if isa(var_name, str) else var_name
        if module_name is not None:
            properties["module_name"] = StringAttr(module_name) if isa(module_name, str) else module_name
        if member_path is not None:
            properties["member_path"] = StringAttr(member_path) if isa(member_path, str) else member_path
        if std_name is not None:
            properties["std_name"] = StringAttr(std_name) if isa(std_name, str) else std_name

        super().__init__(properties=properties)

    def verify_(self) -> None:
        kind = self.source_kind.data
        has_var = self.var_name is not None
        has_mod = self.module_name is not None
        has_member = self.member_path is not None
        has_std = self.std_name is not None

        if kind == ArgSourceKind.Host:
            if not (has_var and has_mod):
                raise VerifyException(
                    "ResolvedArgOp: source_kind=Host requires var_name and module_name"
                )
            if has_member or has_std:
                raise VerifyException(
                    "ResolvedArgOp: source_kind=Host must not set member_path or std_name"
                )
        elif kind == ArgSourceKind.DdtMember:
            if not (has_var and has_mod and has_member):
                raise VerifyException(
                    "ResolvedArgOp: source_kind=DdtMember requires var_name, "
                    "module_name, and member_path"
                )
            if has_std:
                raise VerifyException(
                    "ResolvedArgOp: source_kind=DdtMember must not set std_name"
                )
        elif kind == ArgSourceKind.CapVar:
            if not has_std:
                raise VerifyException(
                    "ResolvedArgOp: source_kind=CapVar requires std_name"
                )
            if has_var or has_mod or has_member:
                raise VerifyException(
                    "ResolvedArgOp: source_kind=CapVar must not set var_name, "
                    "module_name, or member_path"
                )
        elif kind == ArgSourceKind.Block:
            if has_var or has_mod or has_member or has_std:
                raise VerifyException(
                    "ResolvedArgOp: source_kind=Block must not set any source payload"
                )


@irdl_op_definition
class ArgOwnershipOp(IRDLOperation):
    """Durable record of one scheme arg's ownership bucket (see
    ArgOwnershipKind).

    Stage 1 of Phase 7 ("define, don't wire") -- not called by any pass yet.
    Future stages compute this early (right after HostVariableMatchPass, before
    generate-suite-cap runs) and migrate suite_cap.py/ccpp_cap.py/run_dispatch.py
    to read it instead of their own independently-computed heuristics.

    Required properties by ``ownership_kind``:
      - SuiteOwned:  none of the below
      - HostMatched: ``std_name``
      - CapScratch:  ``std_name``
      - Block:       none of the below
    """

    name = "ccpp.arg_ownership"

    arg_name = prop_def(StringAttr)
    ownership_kind = prop_def(ArgOwnershipKindAttr)
    std_name = opt_prop_def(StringAttr)

    def __init__(
        self,
        arg_name: str | StringAttr,
        ownership_kind: "str | ArgOwnershipKind | ArgOwnershipKindAttr",
        std_name: str | StringAttr | None = None,
    ):
        if isa(arg_name, str):
            arg_name = StringAttr(arg_name)
        if isinstance(ownership_kind, str):
            ownership_kind = ArgOwnershipKindAttr(ArgOwnershipKind(ownership_kind))
        elif isinstance(ownership_kind, ArgOwnershipKind):
            ownership_kind = ArgOwnershipKindAttr(ownership_kind)

        properties: dict = {"arg_name": arg_name, "ownership_kind": ownership_kind}
        if std_name is not None:
            properties["std_name"] = StringAttr(std_name) if isa(std_name, str) else std_name

        super().__init__(properties=properties)

    def verify_(self) -> None:
        kind = self.ownership_kind.data
        has_std = self.std_name is not None

        if kind in (ArgOwnershipKind.HostMatched, ArgOwnershipKind.CapScratch):
            if not has_std:
                raise VerifyException(
                    f"ArgOwnershipOp: ownership_kind={kind.value} requires std_name"
                )
        else:
            if has_std:
                raise VerifyException(
                    f"ArgOwnershipOp: ownership_kind={kind.value} must not set std_name"
                )


CCPP = Dialect(
    "ccpp",
    [
        SuiteOp,
        GroupOp,
        SchemeOp,
        SubcycleOp,
        CcppHandleOp,
        KindOp,
        KindsOp,
        TablePropertiesOp,
        ArgumentTableOp,
        ArgumentOp,
        ResolvedArgOp,
        ArgOwnershipOp,
    ],
    [
        TableTypeKindAttr,
        ArgSourceKindAttr,
        ArgOwnershipKindAttr,
    ],
)
