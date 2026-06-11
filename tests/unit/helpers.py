"""Shared constants and helper functions for xdsl-ccpp unit tests.

Kept separate from conftest.py so test modules can import them directly.
(pytest conftest.py files cannot be imported — fixtures are injected
automatically but explicit imports fail.)
"""

# ── CCPP mandatory arguments ──────────────────────────────────────────────────
# Every scheme argument table must include errmsg and errflg.
# Append this to the end of every [ccpp-arg-table] block in test meta content.

CCPP_MANDATORY_ARGS = """\
[ errmsg ]
  standard_name = ccpp_error_message
  long_name = Error message for error handling in CCPP
  type = character
  kind = len=512
  intent = out
  dimensions = ()
  units = none
[ errflg ]
  standard_name = ccpp_error_code
  long_name = Error flag for error handling in CCPP
  type = integer
  intent = out
  dimensions = ()
  units = 1
"""


def minimal_suite_xml(scheme_name: str, suite_name: str = "test_suite") -> str:
    """Return a minimal suite XML string for a single scheme."""
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="{suite_name}" version="1.0">
  <group name="physics">
    <scheme>{scheme_name}</scheme>
  </group>
</suite>
"""
