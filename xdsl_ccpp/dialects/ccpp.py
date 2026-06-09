from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum, auto

from xdsl.dialects.builtin import (
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
    ):

        if isa(table_name, str):
            table_name = StringAttr(table_name)

        if isa(table_type, str):
            table_type = TableTypeKindAttr(TableTypeKind(table_type))

        if not isinstance(body, Region):
            body = Region([Block(body)])

        super().__init__(
            regions=[body], properties={"name": table_name, "type": table_type}
        )


@irdl_op_definition
class TablePropertiesOp(TableBaseOp):
    name = "ccpp.table_properties"


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
    optional = opt_prop_def(UnitAttr)

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

        known_props = ["standard_name", "long_name", "kind", "intent", "units"]
        for prop in known_props:
            if prop in attributes:
                properties[prop] = StringAttr(attributes[prop])
                prop_keys.remove(prop)

        if "optional" in attributes:
            if attributes["optional"]:
                properties["optional"] = UnitAttr()
                prop_keys.remove("optional")

        # Silently ignore unrecognised keys (e.g. state_variable, allocatable)

        super().__init__(properties=properties)


CCPP = Dialect(
    "ccpp",
    [
        SuiteOp,
        GroupOp,
        SchemeOp,
        KindOp,
        KindsOp,
        TablePropertiesOp,
        ArgumentTableOp,
        ArgumentOp,
    ],
    [
        TableTypeKindAttr,
    ],
)
