import argparse
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from enum import Enum, StrEnum, auto

from xdsl.dialects.builtin import IntegerAttr, ModuleOp, StringAttr, i32

from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
)


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


class MetaData:
    """Base container pairing a table-properties block with its argument tables.

    Args:
        table_properties: The parsed `CCPPTableProperties` for this file.
        arg_tables: List of `CCPPArgumentTable` objects (one per entry point).
    """

    def __init__(self, table_properties, arg_tables):
        self.table_properties = table_properties
        self.arg_tables = arg_tables


class SchemeMetaData(MetaData):
    """Metadata parsed from a physics-scheme ``.meta`` file."""

    def __init__(self, table_properties, arg_tables):
        super().__init__(table_properties, arg_tables)


class HostMetaData(MetaData):
    """Metadata parsed from a host-model ``.meta`` file."""

    def __init__(self, table_properties, arg_tables):
        super().__init__(table_properties, arg_tables)


class CCPPItem:
    """Generic key/value attribute container used by the frontend parser.

    Stores an arbitrary set of named string attributes parsed from a ``.meta``
    file.  Subclasses may restrict the allowed keys and coerce values to richer
    types (e.g. ``"scheme"`` → `CCPPType.SCHEME`).
    """

    def __init__(self):
        # Dict mapping attribute name → attribute value
        self.attrs = {}

    def setAttr(self, key, value, allowed_keys=None):
        """Store an attribute, optionally validating the key against an allow-list."""
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
    """Descriptor for a ``[ccpp-table-properties]`` block parsed from a ``.meta`` file.

    Allowed attribute keys: ``name``, ``type``, ``dependencies``, ``relative_path``.
    The ``type`` value is automatically coerced to a `CCPPType` enum member.
    """

    def __init__(self):
        super().__init__()

    _VALID_ARRAY_LAYOUTS = ("column_major", "row_major")

    def setAttr(self, key, value):
        # Coerce raw string 'type' values into the CCPPType enum
        if key == "type" and isinstance(value, str):
            value = CCPPType(value)
        if key == "array_layout" and value not in self._VALID_ARRAY_LAYOUTS:
            raise ValueError(
                f"array_layout must be one of {self._VALID_ARRAY_LAYOUTS}, got '{value}'"
            )
        super().setAttr(key, value, ["name", "type", "dependencies", "relative_path", "array_layout"])


class CCPPArgumentTable(CCPPItem):
    """Descriptor for a ``[ccpp-arg-table]`` block parsed from a ``.meta`` file.

    Represents the argument list for one scheme entry point.
    Allowed attribute keys: ``name``, ``type``.
    """

    def __init__(self):
        super().__init__()
        # Ordered map from argument name → CCPPArgument descriptor
        self.function_arguments = {}

    def setAttr(self, key, value):
        # Silently ignore unrecognised keys (e.g. process)
        if key in ("name", "type"):
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
    """Descriptor for a single argument entry within a ``[ccpp-arg-table]`` block."""

    def __init__(self, name):
        # The Fortran variable name for this argument
        self.name = name
        super().__init__()


# ---------------------------------------------------------------------------
# Suite XML parsing
# ---------------------------------------------------------------------------


class XMLSuiteBase:
    """Base node for the in-memory representation of a parsed suite XML file.

    Each node holds an XML attribute dict and an ordered list of child nodes
    (groups or schemes).
    """

    def __init__(self, xml_node):
        # Preserve the raw XML attributes (e.g. name, version)
        self.attributes = xml_node.attrib
        self.children = []

    def __iter__(self):
        return self.children.__iter__()

    def __next__(self):
        return self.children.__next__()


class XMLScheme(XMLSuiteBase):
    """Leaf node representing a single scheme reference within a group.

    The scheme name is taken from the text content of the ``<scheme>`` element
    (e.g. ``<scheme>hello_scheme</scheme>`` → ``scheme_name = "hello_scheme"``).
    """

    def __init__(self, xml_node):
        assert xml_node.tag == "scheme"
        # Text content of the <scheme> element is the scheme base name
        self.scheme_name = xml_node.text
        super().__init__(xml_node)
        assert len(xml_node) == 0  # scheme elements must be leaf nodes


class XMLSubcycle(XMLSuiteBase):
    """Intermediate node representing a ``<subcycle loop="N">`` within a group.

    Parses all ``<scheme>`` children and stores them as `XMLScheme` nodes.
    """

    def __init__(self, xml_node):
        assert xml_node.tag == "subcycle"
        super().__init__(xml_node)
        raw = xml_node.attrib.get("loop", "1")
        try:
            int(raw)
            self.is_literal = True
        except ValueError:
            self.is_literal = False
        self.loop_count = raw
        for child in xml_node:
            if child.tag == "scheme":
                self.children.append(XMLScheme(child))


class XMLGroup(XMLSuiteBase):
    """Intermediate node representing a named ``<group>`` within a suite.

    Parses all ``<scheme>`` and ``<subcycle>`` children.
    """

    def __init__(self, xml_node):
        assert xml_node.tag == "group"
        super().__init__(xml_node)

        for child in xml_node:
            if child.tag == "scheme":
                self.children.append(XMLScheme(child))
            elif child.tag == "subcycle":
                self.children.append(XMLSubcycle(child))


class XMLSuite(XMLSuiteBase):
    """Root node representing a complete CCPP suite parsed from an XML file.

    Reads the XML file, asserts the root element is ``<suite>``, and parses all
    ``<group>`` children into `XMLGroup` nodes.
    """

    def __init__(self, xml_name):
        tree = ET.parse(xml_name)
        root = tree.getroot()

        assert root.tag == "suite"
        super().__init__(root)

        # Parse each top-level group element into an XMLGroup node
        for child in root:
            if child.tag == "group":
                self.children.append(XMLGroup(child))


# ---------------------------------------------------------------------------
# .meta file parser (module-level so py_api can import it without pulling in
# the full ccppXML driver class)
# ---------------------------------------------------------------------------


class MetaParseState(Enum):
    """State machine states for the line-oriented ``.meta`` file parser."""

    PROPERTIES = 1  # Inside a [ccpp-table-properties] block
    ARG_TABLE = 2   # Inside a [ccpp-arg-table] header block
    ARG = 3         # Inside a named argument [ arg_name ] block
    NONE = 4        # Not yet inside any block


def parse_meta_file(filename, is_scheme):
    """Parse a ``.meta`` file and return a list of `MetaData` objects.

    A single file may contain multiple ``[ccpp-table-properties]`` blocks
    (e.g. a DDT definition followed by the scheme that uses it).  Each block
    produces a separate entry in the returned list.

    Args:
        filename:  Path to the ``.meta`` file.
        is_scheme: If True, return `SchemeMetaData` instances; otherwise `HostMetaData`.

    Returns:
        A list of `SchemeMetaData` or `HostMetaData` objects, one per
        ``[ccpp-table-properties]`` block found in the file.
    """
    completed = []
    current_table_properties = None
    current_arg_table = None
    parse_state = MetaParseState.NONE
    table_arg_tables = []
    current_arg = None

    def _flush_table_properties():
        nonlocal current_table_properties, table_arg_tables
        if current_table_properties is None:
            return
        cls = SchemeMetaData if is_scheme else HostMetaData
        completed.append(cls(current_table_properties, table_arg_tables))
        current_table_properties = None
        table_arg_tables = []

    with open(filename) as file:
        for line in file:
            sline = line.strip()

            if not sline or sline.startswith("#"):
                continue

            if "[" in sline and "]" in sline:
                token = sline.translate(str.maketrans("", "", "[]"))

                if token in ("ccpp-table-properties", "ccpp-arg-table"):
                    if current_arg is not None:
                        current_arg_table.setFunctionArgument(current_arg)
                        current_arg = None
                    if current_arg_table is not None:
                        table_arg_tables.append(current_arg_table)
                        current_arg_table = None

                if token == "ccpp-table-properties":
                    _flush_table_properties()
                    current_table_properties = CCPPTableProperties()
                    parse_state = MetaParseState.PROPERTIES
                elif token == "ccpp-arg-table":
                    parse_state = MetaParseState.ARG_TABLE
                    current_arg_table = CCPPArgumentTable()
                elif token[0] == " " or token[-1] == " ":
                    if current_arg is not None:
                        current_arg_table.setFunctionArgument(current_arg)
                    parse_state = MetaParseState.ARG
                    current_arg = CCPPArgument(token.strip())
                else:
                    raise AssertionError(
                        f"Unexpected token in arg table: {token!r}"
                    )
            else:
                assert parse_state != MetaParseState.NONE
                for part in sline.split("|"):
                    part = part.strip()
                    if not part:
                        continue
                    assert "=" in part
                    key, value = part.split("=", 1)
                    key, value = key.strip(), value.strip()
                    if parse_state == MetaParseState.PROPERTIES:
                        assert current_table_properties is not None
                        current_table_properties.setAttr(key, value)
                    elif parse_state == MetaParseState.ARG_TABLE:
                        assert current_arg_table is not None
                        current_arg_table.setAttr(key, value)
                    elif parse_state == MetaParseState.ARG:
                        assert current_arg is not None
                        current_arg.setAttr(key, value)

    if current_arg is not None:
        current_arg_table.setFunctionArgument(current_arg)
    if current_arg_table is not None:
        table_arg_tables.append(current_arg_table)
    _flush_table_properties()

    assert completed
    return completed


# ---------------------------------------------------------------------------
# Frontend driver
# ---------------------------------------------------------------------------


class ccppXML:
    """Frontend that parses CCPP suite XML and ``.meta`` files and emits MLIR IR.

    Reads one suite XML file and any number of scheme/host ``.meta`` files, builds
    an in-memory representation using the descriptor classes above, then emits a
    top-level `ModuleOp` containing `SuiteOp`, `TablePropertiesOp`, and their
    children using the CCPP dialect.

    The resulting MLIR is printed to stdout and is intended to be piped into
    ``ccpp_opt`` for further transformation.

    Typical invocation::

        python3 -m xdsl_ccpp.frontend.ccpp_xml \\
            --suites examples/helloworld/hello_world_suite.xml \\
            --scheme-files examples/helloworld/hello_scheme.meta
    """

    def initialise_argument_parser(self):
        """Create and return an `argparse.ArgumentParser` for the frontend CLI."""
        parser = argparse.ArgumentParser(description="CCPP XML")
        self.set_parser_arguments(parser)
        return parser

    def set_parser_arguments(self, parser):
        """Register the ``--scheme-files``, ``--host-files``, ``--suites``, and ``--num-instances`` CLI args."""
        parser.add_argument(
            "--scheme-files",
        )

        parser.add_argument(
            "--host-files",
        )

        parser.add_argument(
            "--suites",
        )

        parser.add_argument(
            "--num-instances",
            type=int,
            default=None,
            metavar="N",
            help=(
                "Maximum number of simultaneous CCPP instances (ensemble members). "
                "When set, the suite cap generates ccpp_suite_state as a per-instance "
                "array of length N instead of the compiled-in default."
            ),
        )

    def build_options_db_from_args(self, args):
        """Normalise parsed CLI args into a plain dict with list values.

        Each multi-value argument (``--scheme-files``, ``--host-files``,
        ``--suites``) accepts a comma-separated string on the command line and
        is split into a Python list here.  Missing arguments default to ``[]``.

        Returns:
            A dict with keys ``scheme_files``, ``host_files``, ``suites``, and
            optionally ``num_instances`` (int or None).
        """
        options_db = args.__dict__

        # Split comma-separated scheme file paths into a list
        if "scheme_files" in options_db and options_db["scheme_files"] is not None:
            options_db["scheme_files"] = options_db["scheme_files"].split(",")
        else:
            options_db["scheme_files"] = []

        # Split comma-separated host file paths into a list
        if "host_files" in options_db and options_db["host_files"] is not None:
            options_db["host_files"] = options_db["host_files"].split(",")
        else:
            options_db["host_files"] = []

        # Split comma-separated suite XML paths into a list
        if "suites" in options_db and options_db["suites"] is not None:
            options_db["suites"] = options_db["suites"].split(",")
        else:
            options_db["suites"] = []

        return options_db

    def parse_metadata_file(self, filename, isScheme):
        """Parse a ``.meta`` file; delegates to the module-level :func:`parse_meta_file`."""
        return parse_meta_file(filename, isScheme)

    def build_suite_ir(self, suite):
        """Convert a parsed `XMLSuite` tree into CCPP dialect IR ops.

        Walks the suite → group → scheme hierarchy and creates the corresponding
        `SuiteOp` (containing `GroupOp`s containing `SchemeOp`s).

        Returns:
            A `SuiteOp` representing the complete suite.
        """
        groups = []
        # Build a GroupOp for each group in the suite
        for grp in suite:
            group_ops = []
            for child in grp:
                if isinstance(child, XMLSubcycle):
                    scheme_ops = [SchemeOp(s.scheme_name) for s in child]
                    group_ops.append(SubcycleOp(child.loop_count, scheme_ops,
                                                is_literal=child.is_literal))
                else:
                    group_ops.append(SchemeOp(child.scheme_name))
            groups.append(GroupOp(grp.attributes["name"], group_ops))
        return SuiteOp(
            suite.attributes["name"],
            groups,
            suite.attributes["version"] if "version" in suite.attributes else None,
        )

    def build_meta_ir(self, meta, source_module: str = ""):
        """Convert parsed `MetaData` into CCPP dialect IR ops.

        Walks the arg-tables and their arguments, creating `ArgumentOp`s inside
        `ArgumentTableOp`s, all wrapped in a `TablePropertiesOp`.

        Returns:
            A `TablePropertiesOp` representing the complete metadata for one scheme.
        """
        tables = []
        # Build an ArgumentTableOp for each entry point in the metadata file
        for table in meta.arg_tables:
            args = []
            # Build an ArgumentOp for each argument in this entry point
            for fn_arg in table.getFunctionArguments():
                unknown = set(fn_arg.getAttrs().keys()) - ArgumentOp.KNOWN_PROPS
                if unknown:
                    print(
                        f"Warning: argument '{fn_arg.name}' in "
                        f"'{table.getAttr('name')}' has unrecognised keys: "
                        f"{sorted(unknown)}",
                        file=sys.stderr,
                    )
                args.append(
                    ArgumentOp(fn_arg.name, fn_arg.getAttr("type"), fn_arg.getAttrs())
                )
            tables.append(
                ArgumentTableOp(table.getAttr("name"), str(table.getAttr("type")), args)
            )
        attrs = {"source_module": StringAttr(source_module)} if source_module else {}
        if meta.table_properties.hasAttr("array_layout"):
            attrs["array_layout"] = StringAttr(meta.table_properties.getAttr("array_layout"))
        return TablePropertiesOp(
            meta.table_properties.getAttr("name"),
            str(meta.table_properties.getAttr("type")),
            tables,
            attributes=attrs,
        )

    def run(self):
        """Parse all inputs and emit MLIR to stdout.

        1. Parse the suite XML into a `SuiteOp`.
        2. Parse each scheme ``.meta`` file into a `TablePropertiesOp`.
        3. Parse each host ``.meta`` file into a `TablePropertiesOp`.
        4. Wrap all ops in a top-level `ModuleOp` and print it.
        """
        ir_ops = []
        parser = self.initialise_argument_parser()
        args = parser.parse_args()
        self.options_db = self.build_options_db_from_args(args)

        for suite_file in self.options_db["suites"]:
            ir_ops.append(self.build_suite_ir(XMLSuite(suite_file)))

        # Parse each scheme metadata file and emit a TablePropertiesOp.
        # The file stem is the Fortran module name and is stored as source_module.
        schemes = {}
        for scheme_file in self.options_db["scheme_files"]:
            stem = Path(scheme_file).stem
            for c in self.parse_metadata_file(scheme_file, True):
                schemes[c.table_properties.getAttr("name")] = c
                ir_ops.append(self.build_meta_ir(c, source_module=stem))

        # Parse each host metadata file and emit a TablePropertiesOp.
        hosts = {}
        for host_file in self.options_db["host_files"]:
            stem = Path(host_file).stem
            for c in self.parse_metadata_file(host_file, False):
                hosts[c.table_properties.getAttr("name")] = c
                ir_ops.append(self.build_meta_ir(c, source_module=stem))

        module = ModuleOp(ir_ops)

        # Embed --num-instances as an IR attribute so downstream passes can read it.
        num_instances = self.options_db.get("num_instances")
        if num_instances is not None:
            module.attributes["ccpp.num_instances"] = IntegerAttr(num_instances, i32)

        print(module)


def main():
    ccppXML().run()


if __name__ == "__main__":
    ccppXML().run()
