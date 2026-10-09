"""Unit tests for `[ccpp-table-properties]`'s `module_name` override.

Backlog item `table-props-module-name`: real capgen-v1 lets a table's
logical/suite-visible name (e.g. `effr_pre`) differ from the Fortran module
that actually implements it (e.g. `mod_effr_pre`), via a `module_name` key.
xdsl-ccpp's `.meta` parser previously rejected that key and assumed the two
always match -- the gap this fix closes.

`build_meta_ir` already has a `source_module` concept (previously populated
only from the `.meta` filename's own stem); `module_name`, when declared,
now overrides that default. Every downstream consumer (`use` statement
generation, DDT module lookup, `_build_fn_signatures`) already reads
`source_module` generically, so no further plumbing is needed there --
except one real latent bug found along the way: `_build_fn_signatures`
re-looked-up `self.meta_data` (always keyed by *table* name) using the
*resolved module* name, silently missing whenever the two differ and
dropping BIND(C) `language`/`arg_names`/`arg_intents` stamping. See
TestBuildFnSignaturesSharedModule below for the regression this guards.
"""

from io import StringIO

from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

from tests.unit.helpers import CCPP_MANDATORY_ARGS

_SCHEME_META_WITH_OVERRIDE = f"""\
[ccpp-table-properties]
  name = effr_pre
  type = scheme
  module_name = mod_effr_pre
  dependencies =
[ccpp-arg-table]
  name = effr_pre_run
  type = scheme
{CCPP_MANDATORY_ARGS}
"""

_SCHEME_META_WITHOUT_OVERRIDE = f"""\
[ccpp-table-properties]
  name = effr_pre
  type = scheme
  dependencies =
[ccpp-arg-table]
  name = effr_pre_run
  type = scheme
{CCPP_MANDATORY_ARGS}
"""


class TestModuleNameParsing:
    def test_module_name_is_accepted_and_stored(self, tmp_path):
        meta_file = tmp_path / "effr_pre.meta"
        meta_file.write_text(_SCHEME_META_WITH_OVERRIDE)
        tables = parse_meta_file(str(meta_file), True)
        assert len(tables) == 1
        assert tables[0].table_properties.getAttr("module_name") == "mod_effr_pre"

    def test_build_meta_ir_prefers_module_name_override(self, tmp_path):
        meta_file = tmp_path / "effr_pre.meta"
        meta_file.write_text(_SCHEME_META_WITH_OVERRIDE)
        tables = parse_meta_file(str(meta_file), True)
        op = ccppXML().build_meta_ir(
            tables[0], source_module="effr_pre", meta_file_path=str(meta_file),
        )
        assert op.attributes["source_module"].data == "mod_effr_pre"

    def test_build_meta_ir_falls_back_to_filename_stem_without_override(self, tmp_path):
        meta_file = tmp_path / "effr_pre.meta"
        meta_file.write_text(_SCHEME_META_WITHOUT_OVERRIDE)
        tables = parse_meta_file(str(meta_file), True)
        op = ccppXML().build_meta_ir(
            tables[0], source_module="effr_pre", meta_file_path=str(meta_file),
        )
        assert op.attributes["source_module"].data == "effr_pre"


_TWO_SCHEME_SHARED_MODULE_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>scheme_a</scheme>
    <scheme>scheme_b</scheme>
  </group>
</suite>
"""


def _scheme_meta(name: str, *, module_name: str, language: str | None = None) -> str:
    lang_line = f"  language = {language}\n" if language else ""
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
  module_name = {module_name}
{lang_line}[ccpp-arg-table]
  name = {name}_run
  type = scheme
{CCPP_MANDATORY_ARGS}
"""


class TestBuildFnSignaturesSharedModule:
    """Regression test for the _build_fn_signatures lookup bug: two schemes
    sharing one module_name-overridden module, one declaring language = c++.

    Before the fix, `self.meta_data.get(module_name)` (looked up by the
    *resolved module* name) silently missed -- self.meta_data is always
    keyed by table/scheme name -- so the C++ scheme's BIND(C) `language`/
    `arg_names`/`arg_intents` stamping never fired, and print_ftn.py emitted
    a plain `use`, only: statement instead of a BIND(C) interface block.
    """

    def test_cpp_scheme_sharing_module_still_gets_bind_c_interface(
        self, run_host_match, ccpp_context,
    ):
        module = run_host_match(
            scheme_metas=[
                _scheme_meta("scheme_a", module_name="shared_mod", language="c++"),
                _scheme_meta("scheme_b", module_name="shared_mod"),
            ],
            host_metas=[],
            suite_xml=_TWO_SCHEME_SHARED_MODULE_SUITE_XML,
        )
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()

        assert "BIND(C, name='scheme_a_run')" in fortran, fortran
        # The C++ scheme must NOT be emitted as a plain `use` statement --
        # that's the old, buggy fallback this test guards against.
        assert "use shared_mod, only: scheme_a_run" not in fortran, fortran
        # The Fortran-only scheme sharing the same module still gets a
        # normal `use` statement.
        assert "use shared_mod, only: scheme_b_run" in fortran, fortran
