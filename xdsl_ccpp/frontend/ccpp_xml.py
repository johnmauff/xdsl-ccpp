import argparse
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from enum import Enum, StrEnum, auto

from xdsl.dialects.builtin import ModuleOp, StringAttr

from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
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

    def setAttr(self, key, value):
        # Coerce raw string 'type' values into the CCPPType enum
        if key == "type" and isinstance(value, str):
            value = CCPPType(value)
        super().setAttr(key, value, ["name", "type", "dependencies", "relative_path"])


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


class XMLGroup(XMLSuiteBase):
    """Intermediate node representing a named ``<group>`` within a suite.

    Parses all ``<scheme>`` children and stores them as `XMLScheme` nodes.
    """

    def __init__(self, xml_node):
        assert xml_node.tag == "group"
        super().__init__(xml_node)

        # Parse each child scheme element into an XMLScheme node
        for child in xml_node:
            if child.tag == "scheme":
                self.children.append(XMLScheme(child))


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

    class MetaParseState(Enum):
        """State machine states for the line-oriented ``.meta`` file parser."""

        PROPERTIES = 1  # Inside a [ccpp-table-properties] block
        ARG_TABLE = 2  # Inside a [ccpp-arg-table] header block
        ARG = 3  # Inside a named argument [ arg_name ] block
        NONE = 4  # Not yet inside any block

    def initialise_argument_parser(self):
        """Create and return an `argparse.ArgumentParser` for the frontend CLI."""
        parser = argparse.ArgumentParser(description="CCPP XML")
        self.set_parser_arguments(parser)
        return parser

    def set_parser_arguments(self, parser):
        """Register the ``--scheme-files``, ``--host-files``, and ``--suites`` CLI args."""
        parser.add_argument(
            "--scheme-files",
        )

        parser.add_argument(
            "--host-files",
        )

        parser.add_argument(
            "--suites",
        )

    def build_options_db_from_args(self, args):
        """Normalise parsed CLI args into a plain dict with list values.

        Each multi-value argument (``--scheme-files``, ``--host-files``,
        ``--suites``) accepts a comma-separated string on the command line and
        is split into a Python list here.  Missing arguments default to ``[]``.

        Returns:
            A dict with keys ``scheme_files``, ``host_files``, ``suites``, each
            holding a (possibly empty) list of file path strings.
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
        """Parse a ``.meta`` file and return a list of `MetaData` objects.

        ``.meta`` files use a Fortran-style ini format with three kinds of
        section headers:

        - ``[ccpp-table-properties]`` — top-level properties for the scheme/module
        - ``[ccpp-arg-table]``         — introduces an argument table for one entry point
        - ``[ arg_name ]``             — introduces the attributes for one argument
          (identified by at least one space inside the brackets on either side)

        Lines outside headers are ``key = value`` pairs.  Multiple attributes
        may appear on one line separated by ``|``
        (e.g. ``type = real | kind = kind_phys``).  Blank lines are ignored.

        A single file may contain multiple ``[ccpp-table-properties]`` blocks
        (e.g. a DDT definition followed by the scheme that uses it).  Each block
        produces a separate `MetaData` entry in the returned list.

        Args:
            filename: Path to the ``.meta`` file.
            isScheme: If True, return `SchemeMetaData` instances; otherwise `HostMetaData`.

        Returns:
            A list of `SchemeMetaData` or `HostMetaData` objects, one per
            ``[ccpp-table-properties]`` block found in the file.
        """
        completed = []
        current_table_properties = None
        current_arg_table = None
        parse_state = ccppXML.MetaParseState.NONE
        table_arg_tables = []
        current_arg = None

        def _flush_table_properties():
            nonlocal current_table_properties, table_arg_tables
            if current_table_properties is None:
                return
            cls = SchemeMetaData if isScheme else HostMetaData
            completed.append(cls(current_table_properties, table_arg_tables))
            current_table_properties = None
            table_arg_tables = []

        with open(filename) as file:
            for line in file:
                sline = line.strip()

                # Ignore blank lines and comment lines
                if not sline or sline.startswith("#"):
                    continue

                if "[" in sline and "]" in sline:
                    # Strip brackets to get the section token
                    token = sline.translate(str.maketrans("", "", "[]"))

                    # Starting a new top-level section: flush any in-progress arg/table
                    if token == "ccpp-table-properties" or token == "ccpp-arg-table":
                        if current_arg is not None:
                            current_arg_table.setFunctionArgument(current_arg)
                            current_arg = None
                        if current_arg_table is not None:
                            table_arg_tables.append(current_arg_table)
                            current_arg_table = None

                    if token == "ccpp-table-properties":
                        # Flush the previous block (if any) before starting a new one
                        _flush_table_properties()
                        current_table_properties = CCPPTableProperties()
                        parse_state = ccppXML.MetaParseState.PROPERTIES
                    elif token == "ccpp-arg-table":
                        # Begin a new argument-table header block
                        parse_state = ccppXML.MetaParseState.ARG_TABLE
                        current_arg_table = CCPPArgumentTable()
                    elif token[0] == " " or token[-1] == " ":
                        # Argument block — token is the variable name; spaces may appear
                        # on one or both sides (e.g. '[ ncols]' or '[ temp_level ]')
                        if current_arg is not None:
                            current_arg_table.setFunctionArgument(current_arg)
                        parse_state = ccppXML.MetaParseState.ARG
                        current_arg = CCPPArgument(token.strip())
                    else:
                        raise AssertionError(
                            f"Unexpected token in arg table: {token!r}"
                        )
                else:
                    # Attribute line — one or more key = value pairs separated by '|'
                    # e.g. 'type = real | kind = kind_phys' or 'kind = len=512'
                    assert parse_state != ccppXML.MetaParseState.NONE
                    for part in sline.split("|"):
                        part = part.strip()
                        if not part:
                            continue
                        assert "=" in part
                        # Split on the first '=' only to preserve values like 'len=512'
                        key, value = part.split("=", 1)
                        key, value = key.strip(), value.strip()
                        if parse_state == ccppXML.MetaParseState.PROPERTIES:
                            assert current_table_properties is not None
                            current_table_properties.setAttr(key, value)
                        elif parse_state == ccppXML.MetaParseState.ARG_TABLE:
                            assert current_arg_table is not None
                            current_arg_table.setAttr(key, value)
                        elif parse_state == ccppXML.MetaParseState.ARG:
                            assert current_arg is not None
                            current_arg.setAttr(key, value)

        # Flush any in-progress argument or argument table at end-of-file
        if current_arg is not None:
            current_arg_table.setFunctionArgument(current_arg)
        if current_arg_table is not None:
            table_arg_tables.append(current_arg_table)
        _flush_table_properties()

        assert completed
        return completed

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
            schemes = []
            # Build a SchemeOp for each scheme in the group
            for scheme in grp:
                schemes.append(SchemeOp(scheme.scheme_name))
            groups.append(GroupOp(grp.attributes["name"], schemes))
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
        op = TablePropertiesOp(
            meta.table_properties.getAttr("name"),
            str(meta.table_properties.getAttr("type")),
            tables,
        )
        if source_module:
            op.attributes["source_module"] = StringAttr(source_module)
        return op

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

        print(ModuleOp(ir_ops))


def main():
    ccppXML().run()


if __name__ == "__main__":
    ccppXML().run()
