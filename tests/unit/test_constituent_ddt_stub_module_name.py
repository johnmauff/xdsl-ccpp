"""Unit tests for `_generate_constituent_api`'s `ddt_source_module` resolution.

Backlog item `constituent-ddt-stub-unify`: `_generate_constituent_api`
hardcoded `use ccpp_constituent_prop_mod, only: <type>` stubs for its 3
constituent DDT types, using a literal module-name constant rather than
consulting the generic `ddt_source_module` mechanism (`collect_ddt_source_modules`,
reflecting a real `.meta` `module_name` override). A full merge isn't
possible -- `ccpp_model_constituents_t` is never a parsed argument type
anywhere, so the generic per-arg-type scan can never discover it, meaning
the 3-type list has to stay regardless. The narrow, safe fix: consult
`ddt_source_module` when available, falling back to the historical
constant otherwise -- fixes a latent (currently dormant) correctness gap
where the hardcoded module name could silently diverge from reality if the
bundled `ccpp_constituent_prop_mod.meta` were ever renamed or overridden.
"""

from xdsl_ccpp.transforms.constituent_cap import _generate_constituent_api
from xdsl_ccpp.transforms.util.cap_shared import _CCPP_CONSTITUENT_MOD

_TYPE_NAMES = (
    "ccpp_constituent_properties_t",
    "ccpp_constituent_prop_ptr_t",
    "ccpp_model_constituents_t",
)


def _stub_modules(ddt_source_module) -> dict[str, str]:
    _, _, global_stubs = _generate_constituent_api(
        "TestHost", [], [], ddt_source_module=ddt_source_module,
    )
    return {stub.sym_name.data: stub.attributes["module"].data for stub in global_stubs}


def test_override_honored_for_matching_type_only():
    modules = _stub_modules({"ccpp_constituent_prop_ptr_t": "custom_mod"})
    assert modules["ccpp_constituent_prop_ptr_t"] == "custom_mod"
    # Types not present in the override dict still fall back to the constant.
    assert modules["ccpp_constituent_properties_t"] == _CCPP_CONSTITUENT_MOD
    assert modules["ccpp_model_constituents_t"] == _CCPP_CONSTITUENT_MOD


def test_default_none_matches_historical_behavior():
    modules = _stub_modules(None)
    for type_name in _TYPE_NAMES:
        assert modules[type_name] == _CCPP_CONSTITUENT_MOD


def test_empty_dict_matches_historical_behavior():
    modules = _stub_modules({})
    for type_name in _TYPE_NAMES:
        assert modules[type_name] == _CCPP_CONSTITUENT_MOD
