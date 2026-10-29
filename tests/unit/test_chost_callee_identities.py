"""The C++ host cap identifies a suite cap function's dummy arguments by the
standard and dimension names the suite cap records on it (suite_arg_attrs),
not by re-deriving them from scheme metadata by local name.

The case that matters: schemes reuse one local name (var_compat's
"scalar_var") for different standard names, and the suite cap names those
dummy arguments after their host variables.
"""

from xdsl_ccpp.transforms.cpp_interop import _chost_callee_identities
from xdsl_ccpp.transforms.util.cap_shared import SUITE_ARG_DIM_NAMES, SUITE_ARG_STD_NAME


def test_renamed_colliding_args_keep_their_own_standard_names():
    hints = ["col_start", "col_end", "scalar_var", "scalar_varA", "effr"]
    attrs = [
        {SUITE_ARG_STD_NAME: "horizontal_loop_begin"},
        {SUITE_ARG_STD_NAME: "horizontal_loop_end"},
        {SUITE_ARG_STD_NAME: "scalar_variable_for_testing"},
        {SUITE_ARG_STD_NAME: "scalar_variable_for_testing_a"},
        {SUITE_ARG_STD_NAME: "effective_radius",
         SUITE_ARG_DIM_NAMES: ["horizontal_loop_extent", "vertical_layer_dimension"]},
    ]
    local_to_std, local_to_dims = _chost_callee_identities(hints, attrs)
    assert local_to_std == {
        "col_start": "horizontal_loop_begin",
        "col_end": "horizontal_loop_end",
        "scalar_var": "scalar_variable_for_testing",
        "scalar_varA": "scalar_variable_for_testing_a",
        "effr": "effective_radius",
    }
    assert local_to_dims == {"effr": ["horizontal_loop_extent", "vertical_layer_dimension"]}


def test_args_without_recorded_names_are_left_to_the_fallback():
    local_to_std, local_to_dims = _chost_callee_identities(["x", None], [{}, {}])
    assert local_to_std == {} and local_to_dims == {}
