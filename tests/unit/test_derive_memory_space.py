"""acc-derive-memory-space stage 2: derive_memory_space.apply_derived_memory_space
(rule (a) for "either" arguments) and its use by ccpp_dsl with --directive acc."""

from xdsl.dialects import builtin

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp
from xdsl_ccpp.transforms.derive_memory_space import apply_derived_memory_space


def _arg(name, std, space=None):
    attrs = {"type": "real", "dimensions": "(horizontal_dimension)", "standard_name": std}
    if space is not None:
        attrs["memory_space"] = space
    return ArgumentOp(name, "real", attrs)


def _module(scheme_tables, host_args=()):
    props = [TablePropertiesOp("s", "scheme", [
        ArgumentTableOp(table, "scheme", args) for table, args in scheme_tables.items()
    ])]
    if host_args:
        props.append(TablePropertiesOp("h", "host", [ArgumentTableOp("h", "host", list(host_args))]))
    return builtin.ModuleOp(props)


def _spaces(module):
    out = {}
    for op in module.walk():
        if isinstance(op, ArgumentTableOp):
            for arg in op.body.block.ops:
                out[(op.table_name.data, arg.arg_name.data)] = (
                    arg.memory_space.data if arg.memory_space is not None else None
                )
    return out


def test_device_is_set_where_meta_is_silent():
    m = _module({"a_run": [_arg("x", "x_std")]})
    report = apply_derived_memory_space(m, {"a_run": {"x": "device"}})
    assert _spaces(m)[("a_run", "x")] == "device"
    assert report == ["a_run: 'x' memory_space = device (its directives require it on the device)"]


def test_explicit_meta_always_wins():
    m = _module({"a_run": [_arg("x", "x_std", "host"), _arg("y", "y_std", "unified")]})
    assert apply_derived_memory_space(m, {"a_run": {"x": "device", "y": "device"}}) == []
    assert _spaces(m) == {("a_run", "x"): "host", ("a_run", "y"): "unified"}


def test_either_stays_host_when_no_one_else_puts_it_on_the_device():
    # RRTMGP's wrappers: copyin of arrays no other scheme keeps on the device.
    m = _module({"a_run": [_arg("p_lay", "p_std")], "b_run": [_arg("p_lay", "p_std")]})
    assert apply_derived_memory_space(m, {"a_run": {"p_lay": "either"}, "b_run": {"p_lay": "either"}}) == []
    assert _spaces(m)[("a_run", "p_lay")] is None


def test_either_becomes_device_when_another_scheme_declares_it():
    # kessler_update_timestep_init's shape: a bare loop on temp_prev, which
    # kessler_update_run uses with present().
    m = _module({
        "u_timestep_init": [_arg("temp_prev", "tp_std")],
        "u_run": [_arg("temp_prev", "tp_std", "device")],
    })
    report = apply_derived_memory_space(m, {"u_timestep_init": {"temp_prev": "either"}})
    assert _spaces(m)[("u_timestep_init", "temp_prev")] == "device"
    assert "the scheme copies it itself, and it is device data elsewhere" in report[0]


def test_either_becomes_device_when_another_scheme_derives_device():
    m = _module({"a_run": [_arg("x", "x_std")], "b_run": [_arg("x", "x_std")]})
    apply_derived_memory_space(m, {"a_run": {"x": "device"}, "b_run": {"x": "either"}})
    assert _spaces(m)[("b_run", "x")] == "device"


def test_either_becomes_device_when_the_host_keeps_it_on_the_device():
    m = _module({"a_run": [_arg("x", "x_std")]}, host_args=[_arg("x_host", "x_std", "device")])
    apply_derived_memory_space(m, {"a_run": {"x": "either"}})
    assert _spaces(m)[("a_run", "x")] == "device"


def test_host_tables_are_never_changed():
    m = _module({}, host_args=[_arg("x", "x_std")])
    assert apply_derived_memory_space(m, {"h": {"x": "device"}}) == []
    assert _spaces(m)[("h", "x")] is None


def test_unclassified_arguments_untouched():
    m = _module({"a_run": [_arg("x", "x_std"), _arg("y", "y_std")]})
    apply_derived_memory_space(m, {"a_run": {"x": "device"}})
    assert _spaces(m)[("a_run", "y")] is None


def test_either_is_device_with_directive_omp():
    # --directive omp: a kernel-style OpenMP port is all "either"; it is
    # device data even where nothing else anchors it.
    m = _module({"a_run": [_arg("x", "x_std")], "b_run": [_arg("y", "y_std", "host")]})
    report = apply_derived_memory_space(
        m, {"a_run": {"x": "either"}, "b_run": {"y": "either"}}, either_is_device=True
    )
    assert _spaces(m) == {("a_run", "x"): "device", ("b_run", "y"): "host"}
    assert report == ["a_run: 'x' memory_space = device "
                      "(the scheme maps it to the device itself; --directive omp)"]
