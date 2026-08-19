import argparse
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from enum import Enum

from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr

from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    GroupOp,
    SchemeOp,
    SubcycleOp,
    SuiteOp,
    TablePropertiesOp,
)
from xdsl_ccpp.util.ccpp_conventions import parse_kind_spec_value, set_legacy_mode
from xdsl_ccpp.util.ccpp_item import CCPPArgument, CCPPItem, CCPPType


class MetaData:
    """Base container pairing a table-properties block with its argument tables.

    Args:
        table_properties: The parsed `CCPPTableProperties` for this file.
        arg_tables: List of `CCPPArgumentTable` objects (one per entry point).
    """

    def __init__(self, table_properties, arg_tables):
        self.table_properties = table_properties
        self.arg_tables = arg_tables


class CCPPTableProperties(CCPPItem):
    """Descriptor for a ``[ccpp-table-properties]`` block parsed from a ``.meta`` file.

    Allowed attribute keys: ``name``, ``type``, ``dependencies``, ``dependencies_path``,
    ``source_path``, ``array_layout``, ``language``, ``kind_spec``. The ``type`` value
    is automatically coerced to a `CCPPType` enum member. ``kind_spec`` and
    ``dependencies`` may each be declared more than once (one table can supply
    more than one kind, or split its dependency list across several lines);
    each declaration is parsed and accumulated into ``kind_specs``/``dependencies``
    rather than overwriting a single attribute slot.

    ``dependencies``/``dependencies_path``/``source_path`` mirror real capgen-v1's
    own three-key convention (``metadata/metadata_table.py``'s
    ``MetadataTable.apply_table_props``) verbatim in name and shape, but --
    unlike upstream -- are stored as the raw declared strings, not resolved to
    absolute filesystem paths: no code here yet consumes them for anything
    (see ccpp_cap_refactor_plan.md's "dependencies/source_path tracking" entry
    for why file-path resolution is deliberately out of scope for now).
    """

    def __init__(self):
        super().__init__()
        # List of parsed (kind_name, module, spec) tuples -- see
        # ccpp_conventions.parse_kind_spec_value.
        self.kind_specs: list[tuple[str, str, str]] = []
        # Flat list of raw dependency filenames, in declaration order --
        # accumulated across every "dependencies = ..." line (each of which
        # may itself be a comma-separated list, matching real capgen-v1's own
        # convention), skipping the "none" sentinel (an explicit "no
        # dependencies" declaration, not a literal filename).
        self.dependencies: list[str] = []

    _VALID_ARRAY_LAYOUTS = ("column_major", "row_major")
    _VALID_LANGUAGES = ("fortran", "c++")

    def setAttr(self, key, value):
        # Coerce raw string 'type' values into the CCPPType enum
        if key == "type" and isinstance(value, str):
            value = CCPPType(value)
        if key == "array_layout" and value not in self._VALID_ARRAY_LAYOUTS:
            raise ValueError(
                f"array_layout must be one of {self._VALID_ARRAY_LAYOUTS}, got '{value}'"
            )
        if key == "language" and value not in self._VALID_LANGUAGES:
            raise ValueError(
                f"language must be one of {self._VALID_LANGUAGES}, got '{value}'"
            )
        if key == "kind_spec":
            self.kind_specs.append(parse_kind_spec_value(value))
        if key == "dependencies":
            for entry in value.split(","):
                entry = entry.strip()
                if entry and entry.lower() != "none":
                    self.dependencies.append(entry)
        super().setAttr(key, value, ["name", "type", "dependencies", "dependencies_path",
                                     "source_path", "array_layout", "language", "kind_spec"])


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


# ---------------------------------------------------------------------------
# Suite XML parsing
# ---------------------------------------------------------------------------

#: Max re-scan passes for <nested_suite> expansion before assuming a cycle
#: between mutually-referential suite files -- mirrors capgen-v1's own
#: expand_nested_suites (xml_tools.py), same constant value.
_MAX_NESTED_SUITE_ITERATIONS = 10


def _load_nested_suite_reference(suite_name, group_name, file_attr, default_dir):
    """Load and return the ``<suite>`` or ``<group>`` element a ``<nested_suite>``
    references, mirroring capgen-v1's ``load_suite_by_name`` (xml_tools.py) exactly.

    A relative ``file_attr`` resolves against *default_dir* -- the ORIGINAL
    top-level suite file's own directory, not whichever file this particular
    reference happens to live in (confirmed against upstream source: capgen-v1
    threads one ``default_path`` unchanged through every recursive expansion
    pass, even for a reference that only became reachable because an earlier
    pass spliced its containing file in from somewhere else).
    """
    if not suite_name or not file_attr:
        raise ValueError(
            f"<nested_suite> requires both name= and file= attributes, got "
            f"name={suite_name!r} file={file_attr!r}"
        )
    resolved_path = Path(file_attr)
    if not resolved_path.is_absolute():
        resolved_path = Path(default_dir) / resolved_path
    ref_root = ET.parse(str(resolved_path)).getroot()
    if ref_root.attrib.get("name") == suite_name:
        if group_name:
            for group in ref_root.findall("group"):
                if group.attrib.get("name") == group_name:
                    return group
        else:
            return ref_root
    msg = f"Nested suite '{suite_name}'"
    if group_name:
        msg += f", group '{group_name}',"
    msg += f" not found in file '{resolved_path}'"
    raise ValueError(msg)


def _replace_nested_suite(parent, nested, default_dir):
    """Replace one ``<nested_suite>`` element with the suite/group content it
    references, mirroring capgen-v1's ``replace_nested_suite`` exactly.

    One non-obvious rule preserved from upstream: a ``<nested_suite>``
    declared directly under ``<suite>`` (not inside a ``<group>``) that also
    names a ``group=`` gets its spliced-in children re-wrapped in a single
    *fresh* ``<group name=group_attr>`` containing ALL of them -- every
    other case (nested inside a ``<group>``, or suite-level with ``group=``
    omitted) splices the referenced content's own children in as-is,
    unwrapped, one per item.
    """
    suite_name = nested.attrib.get("name")
    group_name = nested.attrib.get("group")
    file_attr = nested.attrib.get("file")
    referenced = _load_nested_suite_reference(suite_name, group_name, file_attr, default_dir)

    items = [ET.fromstring(ET.tostring(child)) for child in referenced]
    if parent.tag == "suite" and group_name:
        # One shared wrapper for every referenced child -- not one wrapper
        # per child, which would produce several same-named groups instead
        # of a single group holding everything the reference pulled in.
        wrapper = ET.Element("group", attrib={"name": group_name})
        for item in items:
            wrapper.append(item)
        items = [wrapper]

    idx = list(parent).index(nested)
    for item in items:
        parent.insert(idx, item)
        idx += 1
    parent.remove(nested)
    return suite_name


def _expand_nested_suites(root, default_dir):
    """Recursively expand every ``<nested_suite>`` element inside *root* (a
    ``<suite>`` element), mirroring capgen-v1's ``expand_nested_suites``
    (xml_tools.py) exactly -- a pure XML-tree preprocessing pass, run once,
    entirely before any group/scheme/subcycle object is built. By the time
    this returns, the tree is an ordinary (possibly larger) v1-style suite
    XML with no ``<nested_suite>`` elements left -- nothing downstream
    (`XMLGroup`/`XMLScheme`/`XMLSubcycle`, the IR, suite_cap.py, cap_shared.py,
    suite_variable_model.py) needs to know cross-file composition was ever
    involved.
    """
    expanded_names = []
    for _ in range(_MAX_NESTED_SUITE_ITERATIONS):
        keep_expanding = False
        for group in root.findall("group"):
            for nested in group.findall("nested_suite"):
                expanded_names.append(_replace_nested_suite(group, nested, default_dir))
                keep_expanding = True
        for nested in root.findall("nested_suite"):
            expanded_names.append(_replace_nested_suite(root, nested, default_dir))
            keep_expanding = True
        if not keep_expanding:
            return
    raise ValueError(
        "Exceeded max iterations while expanding <nested_suite> elements -- "
        "check for a cycle between mutually-referential suite files, or "
        f"raise _MAX_NESTED_SUITE_ITERATIONS. Suites expanded so far: {expanded_names}"
    )


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
        # Text content of the <scheme> element is the scheme base name.
        # .strip(): every suite XML in this repo writes the name tight
        # against the tags on one line, but XML preserves indentation
        # whitespace/newlines verbatim in element text -- an indented
        # "<scheme>\n  x\n</scheme>" would otherwise silently produce a
        # scheme_name that never matches anything in scheme metadata, with
        # no clear error pointing at whitespace as the cause.
        self.scheme_name = xml_node.text.strip() if xml_node.text else xml_node.text
        super().__init__(xml_node)
        assert len(xml_node) == 0  # scheme elements must be leaf nodes


class XMLSubcycle(XMLSuiteBase):
    """Intermediate node representing a ``<subcycle loop="N">`` within a group.

    Parses all ``<scheme>`` children and stores them as `XMLScheme` nodes.
    ``<subcycle>`` children are parsed recursively as nested `XMLSubcycle`
    nodes, to arbitrary depth -- real CCPP suites do this (e.g. NCAR
    ccpp-framework's feature/capgen-v1 end-to-end-tests/var_compat, ported
    into examples/var_compat, nests subcycles three levels deep in one
    branch). This mirrors `XMLGroup`'s own scheme/subcycle dispatch exactly.
    """

    def __init__(self, xml_node):
        assert xml_node.tag == "subcycle"
        super().__init__(xml_node)
        # .strip(): attribute values rarely pick up incidental whitespace
        # (nobody indents inside a quoted attribute), but the same class of
        # bug applies if one ever did -- e.g. loop=" num_subcycles " would
        # otherwise silently fail every downstream standard_name lookup.
        raw = xml_node.attrib.get("loop", "1").strip()
        try:
            int(raw)
            self.is_literal = True
        except ValueError:
            self.is_literal = False
        self.loop_count = raw
        for child in xml_node:
            if child.tag == "scheme":
                self.children.append(XMLScheme(child))
            elif child.tag == "subcycle":
                self.children.append(XMLSubcycle(child))


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

    v2.0 SDF schema: before any of that, expands every ``<nested_suite>``
    cross-file reference in place (see `_expand_nested_suites`) -- a suite
    file may splice in groups/schemes from a *different* suite XML file,
    recursively.  This is a pure XML-tree preprocessing pass; the rest of
    this class (and everything built on top of it) never needs to know
    cross-file composition was involved.

    Also v2.0: a suite may declare a single ``<init>``/``<final>`` scheme
    name as a direct child, called once per suite lifecycle (not per-group)
    -- stored as ``self.init_scheme``/``self.final_scheme`` (``None`` if
    absent).
    """

    def __init__(self, xml_name):
        tree = ET.parse(xml_name)
        root = tree.getroot()

        assert root.tag == "suite"

        # Relative file= paths on any <nested_suite> reached from here
        # resolve against THIS top-level suite file's own directory, not
        # whichever file a given reference happens to live in -- confirmed
        # against capgen-v1's own source, not assumed (see
        # _load_nested_suite_reference's docstring).
        _expand_nested_suites(root, str(Path(xml_name).resolve().parent))

        super().__init__(root)

        # Suite-level lifecycle hooks (v2.0): a single scheme's own init/
        # final phase, called once per suite rather than once per group.
        # .strip(): same reasoning as XMLScheme.scheme_name above -- the
        # text content of these elements is a scheme name used for lookups,
        # not free text.
        self.init_scheme = None
        self.final_scheme = None
        for child in root:
            if child.tag == "init":
                self.init_scheme = child.text.strip() if child.text else child.text
            elif child.tag == "final":
                self.final_scheme = child.text.strip() if child.text else child.text

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
        is_scheme: If True, the file contains scheme metadata; otherwise host metadata.

    Returns:
        A list of `MetaData` objects, one per ``[ccpp-table-properties]`` block
        found in the file.
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
        completed.append(MetaData(current_table_properties, table_arg_tables))
        current_table_properties = None
        table_arg_tables = []

    with open(filename) as file:
        for line_no, line in enumerate(file, start=1):
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
                else:
                    # Anything reaching here is already known not to be one
                    # of the two table/arg-table headers (checked above), and
                    # a .meta file's grammar has no other bracketed construct
                    # -- so it's always an argument name, spaced ("[ name ]",
                    # this project's own writer convention) or tight
                    # ("[name]", capgen-v1's own upstream convention, e.g.
                    # var_compat's effr_calc.meta). .strip() normalizes both
                    # to the same bare name either way.
                    #
                    # Two things a malformed file could do wrong here, both
                    # validated explicitly rather than left to crash
                    # confusingly later (a stray argument bracket goes
                    # unnoticed until the *next* bracket tries to attach it to
                    # a still-nonexistent table; an empty name would silently
                    # propagate as a nameless argument):
                    if current_arg_table is None:
                        raise ValueError(
                            f"{filename}:{line_no}: argument '{token.strip()}' "
                            "declared before any [ccpp-arg-table] header"
                        )
                    arg_name = token.strip()
                    if not arg_name:
                        raise ValueError(
                            f"{filename}:{line_no}: empty argument name '[{token}]'"
                        )
                    if current_arg is not None:
                        current_arg_table.setFunctionArgument(current_arg)
                    parse_state = MetaParseState.ARG
                    current_arg = CCPPArgument(arg_name)
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

        parser.add_argument(
            "--legacy-mode",
            action="store_true",
            default=False,
            help="Accept deprecated standard names (currently: horizontal_loop_extent) "
                 "with a warning instead of rejecting them. Forwarded from ccpp_dsl.py's "
                 "own --legacy-mode flag when this frontend is spawned as a subprocess.",
        )

    def build_options_db_from_args(self, args):
        """Normalise parsed CLI args into a plain dict with list values.

        Each multi-value argument (``--scheme-files``, ``--host-files``,
        ``--suites``) accepts a comma-separated string on the command line and
        is split into a Python list here.  Missing arguments default to ``[]``.

        Returns:
            A dict with keys ``scheme_files``, ``host_files``, and ``suites``.
        """
        options_db = args.__dict__

        # Split comma-separated scheme file paths into a list. .strip() each
        # entry: a space after a comma (e.g. "a.meta, b.meta") would
        # otherwise silently become a path with a leading space, failing to
        # open with a confusing error rather than being tolerated the way
        # most CLI tools handle incidental whitespace.
        if "scheme_files" in options_db and options_db["scheme_files"] is not None:
            options_db["scheme_files"] = [
                p.strip() for p in options_db["scheme_files"].split(",")
            ]
        else:
            options_db["scheme_files"] = []

        # Split comma-separated host file paths into a list
        if "host_files" in options_db and options_db["host_files"] is not None:
            options_db["host_files"] = [
                p.strip() for p in options_db["host_files"].split(",")
            ]
        else:
            options_db["host_files"] = []

        # Split comma-separated suite XML paths into a list
        if "suites" in options_db and options_db["suites"] is not None:
            options_db["suites"] = [p.strip() for p in options_db["suites"].split(",")]
        else:
            options_db["suites"] = []

        return options_db

    def _build_subcycle_op(self, subcycle) -> "SubcycleOp":
        """Recursively build a `SubcycleOp` from an `XMLSubcycle`.

        A child that is itself an `XMLSubcycle` (nested `<subcycle>`) becomes
        a nested `SubcycleOp`, to arbitrary depth -- mirrors `build_suite_ir`'s
        own scheme/subcycle dispatch one level up.
        """
        child_ops = []
        for child in subcycle:
            if isinstance(child, XMLSubcycle):
                child_ops.append(self._build_subcycle_op(child))
            else:
                child_ops.append(SchemeOp(child.scheme_name))
        return SubcycleOp(subcycle.loop_count, child_ops, is_literal=subcycle.is_literal)

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
                    group_ops.append(self._build_subcycle_op(child))
                else:
                    group_ops.append(SchemeOp(child.scheme_name))
            groups.append(GroupOp(grp.attributes["name"], group_ops))
        return SuiteOp(
            suite.attributes["name"],
            groups,
            suite.attributes["version"] if "version" in suite.attributes else None,
            init_scheme=suite.init_scheme,
            final_scheme=suite.final_scheme,
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
        if meta.table_properties.hasAttr("language"):
            lang = meta.table_properties.getAttr("language")
            if lang != "fortran":
                attrs["language"] = StringAttr(lang)
        if meta.table_properties.kind_specs:
            # Re-encoded in the same "<module>:<kind_name>=>spec" canonical form
            # ccpp_conventions.parse_kind_spec_value accepts, so suite_kinds.py's
            # MetaKind pass can decode each entry with that same helper -- one
            # source of truth for the syntax, rather than inventing a second
            # IR-only encoding.
            attrs["kind_specs"] = ArrayAttr([
                StringAttr(f"{module}:{kind_name}=>{spec}")
                for kind_name, module, spec in meta.table_properties.kind_specs
            ])
        if meta.table_properties.hasAttr("source_path"):
            attrs["source_path"] = StringAttr(meta.table_properties.getAttr("source_path"))
        if meta.table_properties.hasAttr("dependencies_path"):
            attrs["dependencies_path"] = StringAttr(
                meta.table_properties.getAttr("dependencies_path")
            )
        if meta.table_properties.dependencies:
            attrs["dependencies"] = ArrayAttr([
                StringAttr(dep) for dep in meta.table_properties.dependencies
            ])
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

        # Set before any ArgumentOp is constructed below.
        set_legacy_mode(self.options_db.get("legacy_mode", False))

        for suite_file in self.options_db["suites"]:
            ir_ops.append(self.build_suite_ir(XMLSuite(suite_file)))

        # Parse each scheme metadata file and emit a TablePropertiesOp.
        # The file stem is the Fortran module name and is stored as source_module.
        schemes = {}
        for scheme_file in self.options_db["scheme_files"]:
            stem = Path(scheme_file).stem
            for c in parse_meta_file(scheme_file, True):
                schemes[c.table_properties.getAttr("name")] = c
                ir_ops.append(self.build_meta_ir(c, source_module=stem))

        # Parse each host metadata file and emit a TablePropertiesOp.
        hosts = {}
        for host_file in self.options_db["host_files"]:
            stem = Path(host_file).stem
            for c in parse_meta_file(host_file, False):
                hosts[c.table_properties.getAttr("name")] = c
                ir_ops.append(self.build_meta_ir(c, source_module=stem))

        module = ModuleOp(ir_ops)

        print(module)


def main():
    ccppXML().run()


if __name__ == "__main__":
    ccppXML().run()
