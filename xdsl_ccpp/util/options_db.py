"""Shared ``options_db`` field-coercion helper.

``ccpp_dsl.py``'s and ``ccpp_xml.py``'s own, independent
``build_options_db_from_args`` implementations each turn a CLI-supplied
comma-joined string (``suites``/``scheme_files``/``host_files``/
``preproc_defs``) into a list via an unconditional ``.split(",")`` --
which crashes with ``AttributeError`` the moment a caller building
``options_db`` programmatically (rather than through argparse) supplies an
already-real Python list, the capgen-v1-native contract for these fields.
``coerce_list_option`` makes both paths safe to call either way.
"""

from __future__ import annotations


def coerce_list_option(value) -> list:
    """Return ``value`` as a ``list[str]``.

    A list/tuple is passed through unchanged (trusting the caller, same as
    ``ccpp_prebuild.py``'s own direct `options_db` list assignment already
    does today); a comma-joined string is split and stripped; a falsy value
    (``None``/``""``) becomes ``[]``.
    """
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [p.strip() for p in value.split(",")]
