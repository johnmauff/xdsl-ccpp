"""Shared CCPP descriptor primitives used by both the frontend parser
(``frontend/ccpp_xml.py``) and the IR-reconstruction path
(``transforms/util/ccpp_descriptors.py``).

Extracted (complexity-audit Tier 2 finding, task #48) after confirming
`CCPPType`, `CCPPItem`, and `CCPPArgument` were three genuinely byte-identical
classes (docstring wording aside) independently defined in both files.
`CCPPTableProperties`/`CCPPArgumentTable` -- which share the same class names
but are NOT duplicates (they serve different pipeline stages: raw
``.meta``-text parsing with kind_spec/dependencies accumulation and
array_layout/language validation, vs. IR-reconstruction with an `arg_tables`
dict) -- were deliberately left alone in each file; consolidating those would
have been wrong.
"""

from enum import StrEnum, auto


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


class CCPPArgument(CCPPItem):
    """Descriptor for a single argument entry within a ``[ccpp-arg-table]`` block.

    Stores the argument's name and any metadata attributes declared in the ``.meta``
    file (e.g. ``standard_name``, ``type``, ``kind``, ``intent``, ``units``).
    """

    def __init__(self, name):
        # The Fortran variable name for this argument
        self.name = name
        super().__init__()
