"""--capgen-api (formerly --cam-host): the old flag and the old options_db
key still select it."""

import pytest

from xdsl_ccpp.tools.ccpp_dsl import ccppMain

_H = "examples/helloworld"
_ARGS = ["--suites", f"{_H}/hello_world_suite.xml",
         "--scheme-files", f"{_H}/hello_scheme.meta,{_H}/temp_adjust.meta"]


@pytest.mark.parametrize("flag", ["--capgen-api", "--cam-host"])
def test_flag_and_alias(flag):
    tool = ccppMain()
    args = tool.initialise_argument_parser().parse_args([*_ARGS, flag])
    assert tool.build_options_db_from_args(args)["capgen_api"] is True


def test_former_options_db_key():
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({"suites": [f"{_H}/hello_world_suite.xml"],
                       "scheme_files": [f"{_H}/hello_scheme.meta"], "cam_host": True})
    assert tool._normalize_options_db(dict(options_db))["capgen_api"] is True
