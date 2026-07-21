from enum import StrEnum, auto

from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.util.visitor import Visitor


def collect_ddt_source_modules(ccpp_mod) -> dict:
    """Return a mapping of DDT type name → Fortran module name.

    Scans the CCPP module IR for DDT ``TablePropertiesOp`` nodes and reads the
    ``source_module`` attribute set by the frontend (the stem of the ``.meta``
    file the DDT was parsed from, which equals the Fortran module name by CCPP
    convention).

    Used by both ``SuiteCAP`` and ``CCPPCAP`` passes to generate correct
    ``use <module>, only: <type>`` statements for DDT types.

    Args:
        ccpp_mod: the named ``builtin.ModuleOp`` with ``sym_name = "ccpp"``.

    Returns:
        dict mapping lowercase DDT table name → source module name string.
    """
    result: dict = {}
    for tbl_op in ccpp_mod.body.ops:
        if not isa(tbl_op, ccpp.TablePropertiesOp):
            continue
        if tbl_op.table_type.data != "ddt":
            continue
        src = tbl_op.attributes.get("source_module")
        if src is not None:
            result[tbl_op.table_name.data] = src.data
    return result


class CCPPType(StrEnum):
    """Enumeration of the CCPP metadata table types.

    Mirrors the ``type`` field in a ``[ccpp-table-properties]`` block:

    - ``SCHEME``  — a physics parameterisation module
    - ``MODULE``  — a host-model data module
    - ``DDT``     — a derived data type definition
    - ``HOST``    — a host-model subroutine cap
    """

    SCHEME = auto()
    MODULE = auto()
    DDT = auto()
    HOST = auto()


class CCPPItem:
    """Generic key/value attribute container used as a base for all CCPP descriptors.

    Stores an arbitrary set of named string attributes in a plain dict.  Subclasses
    may restrict the allowed keys by passing ``allowed_keys`` to `setAttr`, and may
    coerce values to richer types (e.g. converting ``"scheme"`` → `CCPPType.SCHEME`).
    """

    def __init__(self):
        # Dict mapping attribute name → attribute value
        self.attrs = {}

    def setAttr(self, key, value, allowed_keys=None):
        """Store an attribute, optionally validating the key against an allow-list.

        Args:
            key: Attribute name.
            value: Attribute value (string or coerced type).
            allowed_keys: If provided, ``key`` must be a member of this collection.
        """
        if allowed_keys is not None:
            assert key in allowed_keys
        self.attrs[key] = value

    def getAttr(self, key):
        """Return the value of an attribute, asserting it exists."""
        assert key in self.attrs
        return self.attrs[key]

    def hasAttr(self, key):
        """Return True if the named attribute has been set."""
        return key in self.attrs

    def getAttrs(self):
        """Return the full attribute dict."""
        return self.attrs


class CCPPTableProperties(CCPPItem):
    """Descriptor for a ``[ccpp-table-properties]`` metadata block.

    Holds the top-level metadata for one scheme, module, or DDT, plus a mapping
    from argument-table name → `CCPPArgumentTable` for every entry point that
    belongs to this table (e.g. ``_run``, ``_init``, ``_finalize``).

    Allowed attribute keys: ``name``, ``type``, ``dependencies``,
    ``relative_path``, ``language``.
    The ``type`` value is automatically coerced to a `CCPPType` enum member.
    ``language`` is ``"fortran"`` (default, omitted) or ``"c++"``.
    """

    def __init__(self, arg_tables=None):
        super().__init__()
        # Map from argument-table name → CCPPArgumentTable
        if arg_tables is None:
            self.arg_tables = {}
        else:
            self.arg_tables = arg_tables

    def setAttr(self, key, value):
        # Coerce raw string 'type' values into the CCPPType enum
        if key == "type" and isinstance(value, str):
            value = CCPPType(value)
        super().setAttr(key, value, ["name", "type", "dependencies", "relative_path", "language"])

    def setArgTable(self, k, v):
        """Register an argument table under the given key."""
        assert isinstance(v, CCPPArgument)
        self.arg_tables[k] = v

    def getArgTable(self, v):
        """Return the argument table registered under key ``v``."""
        return self.arg_tables[v]


class CCPPArgumentTable(CCPPItem):
    """Descriptor for a ``[ccpp-arg-table]`` metadata block.

    Represents the argument list for one scheme entry point (e.g. ``hello_scheme_run``).
    Contains an ordered mapping from argument name → `CCPPArgument`.

    Allowed attribute keys: ``name``, ``type``.
    """

    def __init__(self, function_arguments=None):
        super().__init__()
        # Ordered map from argument name → CCPPArgument descriptor
        if function_arguments is None:
            self.function_arguments = {}
        else:
            self.function_arguments = function_arguments

    def setAttr(self, key, value):
        super().setAttr(key, value, ["name", "type"])

    def setFunctionArgument(self, fn_arg):
        """Add an argument to this table, keyed by its name."""
        assert isinstance(fn_arg, CCPPArgument)
        self.function_arguments[fn_arg.name] = fn_arg

    def getFunctionArgument(self, arg_name):
        """Return the `CCPPArgument` with the given name."""
        return self.function_arguments[arg_name]

    def getFunctionArguments(self):
        """Return all `CCPPArgument` descriptors in declaration order."""
        return self.function_arguments.values()


class CCPPArgument(CCPPItem):
    """Descriptor for a single argument entry within a ``[ccpp-arg-table]`` block.

    Stores the argument's name and any metadata attributes declared in the ``.meta``
    file (e.g. ``standard_name``, ``type``, ``kind``, ``intent``, ``units``).
    """

    def __init__(self, name):
        # The Fortran variable name for this argument
        self.name = name
        super().__init__()


# ---------------------------------------------------------------------------
# IR → descriptor conversion (used in the IR after frontend parsing)
# ---------------------------------------------------------------------------


class XMLSuiteBase:
    """Lightweight node used to represent a suite hierarchy reconstructed from IR.

    Used by `BuildSchemeDescription` to build an in-memory tree matching the
    structure of the original suite XML (suite → groups → schemes) so that
    `GenerateSuiteSubroutine` can iterate over it without reading the XML again.
    """

    def __init__(self, attributes):
        # XML-style attribute dict (e.g. {"name": "hello_world", "version": "1"})
        self.attributes = attributes
        # Ordered list of child nodes (XMLGroup or XMLScheme)
        self.children = []

    def __iter__(self):
        return self.children.__iter__()

    def __next__(self):
        return self.children.__next__()

    def addChild(self, child):
        """Append a child node to this suite/group."""
        self.children.append(child)


class XMLScheme(XMLSuiteBase):
    """Leaf node representing a single scheme within a group."""

    def __init__(self, scheme_name, arg_overrides=None):
        super().__init__({"name": scheme_name, "arg_overrides": arg_overrides or {}})


class XMLSubcycle(XMLSuiteBase):
    """Subcycle node reconstructed from IR: contains schemes and a loop count."""

    def __init__(self, loop_count: "int | str", is_literal: bool = True):
        super().__init__({"loop_count": str(loop_count), "is_literal": is_literal})


class XMLGroup(XMLSuiteBase):
    """Intermediate node representing a named group of schemes within a suite."""

    def __init__(self, group_name):
        super().__init__({"name": group_name})


class XMLSuite(XMLSuiteBase):
    """Root node representing a complete CCPP suite (name + version + groups)."""

    def __init__(self, suite_name, version):
        super().__init__({"name": suite_name, "version": version})


# ---------------------------------------------------------------------------
# Visitor passes that walk CCPP IR and populate descriptor objects
# ---------------------------------------------------------------------------


class BuildMetaDataDescriptions(Visitor):
    """Visitor that walks CCPP metadata IR and builds `CCPPTableProperties` descriptors.

    After traversal, `self.meta_data` is a dict mapping scheme/module name →
    `CCPPTableProperties`, where each properties object contains the full set of
    `CCPPArgumentTable` descriptors for that scheme's entry points.

    Typical usage::

        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_module_op)
        descriptions = bmdd.meta_data  # {scheme_name: CCPPTableProperties}
    """

    def __init__(self):
        # Final output: scheme name → CCPPTableProperties
        self.meta_data = {}
        # Transient state used while traversing a single TablePropertiesOp
        self.arg_token = None
        self.arg_table = None

    def traverse_table_properties_op(self, properties_op: ccpp.TablePropertiesOp):
        """Build a `CCPPTableProperties` from one `ccpp.TablePropertiesOp` node.

        Iterates over all child `ArgumentTableOp` nodes, accumulating their
        descriptors, then registers the completed properties object in `self.meta_data`.
        """
        arg_tables = {}
        self.arg_table = None

        # Visit each child ArgumentTableOp; after each visit self.arg_table holds
        # the (name, CCPPArgumentTable) pair for that entry point
        for op in properties_op.body.ops:
            self.traverse(op)
            assert self.arg_table is not None
            k, v = self.arg_table
            arg_tables[k] = v
            self.arg_table = None  # reset for the next sibling

        # Assemble the top-level properties descriptor and store it
        ccpp_prop = CCPPTableProperties(arg_tables)
        ccpp_prop.setAttr("name", properties_op.table_name.data)
        ccpp_prop.setAttr("type", properties_op.table_type.data)
        lang_attr = properties_op.attributes.get("language")
        if lang_attr is not None:
            ccpp_prop.setAttr("language", lang_attr.data)
        self.meta_data[ccpp_prop.getAttr("name")] = ccpp_prop

    def traverse_argument_table_op(self, arg_table_op: ccpp.ArgumentTableOp):
        """Build a `CCPPArgumentTable` from one `ccpp.ArgumentTableOp` node.

        Iterates over all child `ArgumentOp` nodes to collect the individual
        argument descriptors, then stores the result in ``self.arg_table`` for
        the parent traversal method to pick up.
        """
        assert self.arg_table is None
        args = {}
        self.arg_token = None

        # Visit each child ArgumentOp; after each visit self.arg_token holds the
        # CCPPArgument descriptor for that argument
        for op in arg_table_op.body.ops:
            self.traverse(op)
            assert self.arg_token is not None
            args[self.arg_token.name] = self.arg_token
            self.arg_token = None  # reset for the next sibling

        new_arg_table = CCPPArgumentTable(args)
        new_arg_table.setAttr("name", arg_table_op.table_name.data)
        new_arg_table.setAttr("type", arg_table_op.table_type.data)
        # Surface the completed table to the parent traversal via self.arg_table
        self.arg_table = new_arg_table.getAttr("name"), new_arg_table

    def traverse_argument_op(self, arg_op: ccpp.ArgumentOp):
        """Build a `CCPPArgument` from one `ccpp.ArgumentOp` node.

        Copies the standard CCPP metadata properties (``standard_name``,
        ``long_name``, ``kind``, ``intent``, ``units``, ``type``, ``optional``)
        from the op's property dict into the descriptor, then stores the result
        in ``self.arg_token`` for the parent traversal method to pick up.
        """
        assert self.arg_token is None
        arg = CCPPArgument(arg_op.arg_name.data)

        # Copy well-known string properties from the IR op into the descriptor
        known_props = ["standard_name", "long_name", "kind", "intent", "units", "type",
                       "memory_space", "model_var_name", "model_module_name",
                       "model_var_memory_space", "model_var_kind_mismatch",
                       "model_var_unit_mismatch",
                       "default_value", "promoted_dim",
                       # Phase 7, Stage 2's durable ownership classification
                       # (ArgOwnershipKind) -- .data here is the enum member
                       # itself, not a string, same access pattern Stage 3
                       # consumers compare directly against (e.g.
                       # ArgOwnershipKind.SuiteOwned).
                       "ownership_kind"]
        for kp in known_props:
            if kp in arg_op.properties:
                arg.setAttr(kp, arg_op.properties[kp].data)

        # dimensions is stored as an IntAttr (count of dimensions); 0 means scalar
        if "dimensions" in arg_op.properties:
            arg.setAttr("dimensions", arg_op.properties["dimensions"].data)

        # dim_names is a comma-separated StringAttr of dimension standard names
        if "dim_names" in arg_op.properties:
            arg.setAttr("dim_names", arg_op.properties["dim_names"].data.split(","))

        # 'optional' is a flag attribute — store as a boolean rather than a string
        if "optional" in arg_op.properties:
            arg.setAttr("optional", True)

        # 'advected' is a field that points to an existing data-structure
        if "advected" in arg_op.properties:
            arg.setAttr("advected", True)

        # 'allocatable' is an allocated variable managed by CCPP
        if "allocatable" in arg_op.properties:
            arg.setAttr("allocatable", True)

        # 'constituent' marks constituent/tendency variables managed by the framework
        if "constituent" in arg_op.properties:
            arg.setAttr("constituent", True)

        # 'model_var_is_ddt' marks DDT member variables
        if "model_var_is_ddt" in arg_op.properties:
            arg.setAttr("model_var_is_ddt", True)

        # 'model_var_array_layout' is "row_major" when matched host table declares array_layout = row_major
        if "model_var_array_layout" in arg_op.properties:
            arg.setAttr("model_var_array_layout", arg_op.properties["model_var_array_layout"].data)

        # 'is_interstitial' marks variables that flow between lifecycle phases
        if "is_interstitial" in arg_op.properties:
            arg.setAttr("is_interstitial", True)

        # 'is_promoted' marks variables where scheme rank < host rank
        if "is_promoted" in arg_op.properties:
            arg.setAttr("is_promoted", True)

        # Surface the completed argument to the parent traversal via self.arg_token
        self.arg_token = arg


class BuildSchemeDescription(Visitor):
    """Visitor that walks CCPP suite IR and rebuilds an `XMLSuite` hierarchy.

    After traversal, `self.schemes` is a dict mapping suite name → `XMLSuite`,
    where the tree structure mirrors the original suite XML
    (suite → groups → schemes).  This is consumed by `GenerateSuiteSubroutine`
    during the `generate-suite-cap` pass.

    Typical usage::

        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_module_op)
        suites = bsd.schemes  # {suite_name: XMLSuite}
    """

    def __init__(self):
        # Final output: suite name → XMLSuite tree
        self.schemes = {}
        # Transient state used while building the tree
        self.current_group = None
        self.current_scheme = None

    def traverse_suite_op(self, suite_op: ccpp.SuiteOp):
        """Build an `XMLSuite` from one `ccpp.SuiteOp` node.

        Iterates over all child `GroupOp` nodes, collecting the reconstructed
        `XMLGroup` objects, then registers the completed suite in `self.schemes`.
        """
        current_suite = XMLSuite(suite_op.suite_name.data, suite_op.version.data)

        # Visit each child GroupOp; after each visit self.current_group holds the
        # XMLGroup for that group
        for op in suite_op.body.ops:
            self.traverse(op)
            assert self.current_group is not None
            current_suite.addChild(self.current_group)
            self.current_group = None  # reset for the next sibling

        self.schemes[suite_op.suite_name.data] = current_suite

    def traverse_group_op(self, group_op: ccpp.GroupOp):
        """Build an `XMLGroup` from one `ccpp.GroupOp` node.

        Handles both flat `SchemeOp` children and `SubcycleOp` children.
        Scheme traversal is done directly rather than via the visitor pattern
        so that subcycle children are properly nested.
        """
        self.current_group = XMLGroup(group_op.group_name.data)

        for op in group_op.body.ops:
            if isa(op, ccpp.SubcycleOp):
                subcycle = XMLSubcycle(op.loop_count.data, bool(op.is_literal.value.data))
                for child_op in op.body.ops:
                    if isa(child_op, ccpp.SchemeOp):
                        overrides = {}
                        if child_op.arg_overrides is not None:
                            overrides = {
                                k: v.data
                                for k, v in child_op.arg_overrides.data.items()
                            }
                        subcycle.addChild(XMLScheme(child_op.scheme_name.data, overrides))
                    elif isa(child_op, ccpp.SubcycleOp):
                        # Defense in depth: the frontend XML parser already
                        # rejects nested <subcycle> elements, so this should
                        # be unreachable via the normal XML path. Guards
                        # against a nested SubcycleOp reaching the IR by any
                        # other route (e.g. the Python suite-authoring API)
                        # silently losing every scheme inside it.
                        raise ValueError(
                            "Nested ccpp.subcycle ops are not supported "
                            f"(found one inside subcycle loop_count="
                            f"{op.loop_count.data!r})."
                        )
                self.current_group.addChild(subcycle)
            elif isa(op, ccpp.SchemeOp):
                overrides = {}
                if op.arg_overrides is not None:
                    overrides = {k: v.data for k, v in op.arg_overrides.data.items()}
                self.current_group.addChild(XMLScheme(op.scheme_name.data, overrides))

    def traverse_scheme_op(self, scheme_op: ccpp.SchemeOp):
        """Build an `XMLScheme` leaf from one `ccpp.SchemeOp` node.

        Stores the result in ``self.current_scheme`` for the parent traversal
        method to pick up.  Any ``arg_overrides`` property on the op is
        threaded through as a plain ``{name: literal_str}`` dict.
        """
        overrides = {}
        if scheme_op.arg_overrides is not None:
            overrides = {k: v.data for k, v in scheme_op.arg_overrides.data.items()}
        self.current_scheme = XMLScheme(scheme_op.scheme_name.data, overrides)
