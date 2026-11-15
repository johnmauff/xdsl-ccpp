"""The --capture-ddt-handlers registry (scheme-io-capture-rte-objects):
xdsl_ccpp.util.capture_ddt_handlers.parse_ddt_handlers."""

import pytest

from xdsl_ccpp.util.capture_ddt_handlers import DdtHandler, parse_ddt_handlers
from xdsl_ccpp.util.errors import CcppInputError


def _registry(tmp_path, text: str, sources=("handlers.F90",)) -> str:
    for name in sources:
        (tmp_path / name).write_text("module m\nend module m\n")
    path = tmp_path / "capture_handlers.txt"
    path.write_text(text)
    parse_ddt_handlers.cache_clear()
    return str(path)


def test_handlers_and_sources(tmp_path):
    path = _registry(tmp_path, (
        "# RTE objects\n"
        "handler Ty_Props_CCPP module=cap type_module=props write=w read=r compare=c\n"
        "handler ty_gas_ccpp module=cap type_module=gas write=gw read=gr compare=gc "
        "dims=horizontal_loop_extent,vertical_layer_dimension  # needs sizes\n"
        "\n"
        "source handlers.F90\n"
    ))
    registry = parse_ddt_handlers(path)
    assert registry.handlers["ty_props_ccpp"] == DdtHandler(
        "ty_props_ccpp", "cap", "props", "w", "r", "c")
    assert registry.handlers["ty_gas_ccpp"].dims == (
        "horizontal_loop_extent", "vertical_layer_dimension")
    assert registry.sources == (str(tmp_path / "handlers.F90"),)


def test_driver_sources_are_kept_apart(tmp_path):
    """driver_source: compiled into the test drivers only, so listed apart
    from the sources the model compiles too."""
    path = _registry(tmp_path, (
        "handler t module=m type_module=m write=w read=r compare=c\n"
        "source handlers.F90\n"
        "driver_source reader.F90\n"
    ), sources=("handlers.F90", "reader.F90"))
    registry = parse_ddt_handlers(path)
    assert registry.sources == (str(tmp_path / "handlers.F90"),)
    assert registry.driver_sources == (str(tmp_path / "reader.F90"),)


def test_device_routines(tmp_path):
    path = _registry(tmp_path, (
        "handler t module=m type_module=m write=w read=r compare=c "
        "device_enter=on device_exit=off\n"
        "handler u module=m type_module=m write=w read=r compare=c\n"
    ))
    registry = parse_ddt_handlers(path)
    assert (registry.handlers["t"].device_enter, registry.handlers["t"].device_exit) == ("on", "off")
    assert registry.handlers["u"].device_enter is None


def test_no_registry():
    assert parse_ddt_handlers(None) is None


@pytest.mark.parametrize("line, message", [
    ("handler\n", "handler: missing the type name"),
    ("handler t module=m type_module=m write=w read=r\n", "handler t: missing compare"),
    ("handler t module=m type_module=m write=w read=r compare=c size=3\n",
     "handler t: unknown key 'size'"),
    ("handler t module=m type_module=m write=w read=r compare=c device_enter=on\n",
     "handler t: device_enter and device_exit go together"),
    ("handler t module=m module=n type_module=m write=w read=r compare=c\n",
     "handler t: 'module' given twice"),
    ("handler t module type_module=m write=w read=r compare=c\n",
     "handler t: expected key=value, got 'module'"),
    ("source\n", "source: expected one path"),
    ("source missing.F90\n", "source: no file"),
    ("driver_source\n", "driver_source: expected one path"),
    ("driver_source missing.F90\n", "driver_source: no file"),
    ("type t\n", "unknown keyword 'type'"),
])
def test_malformed_lines_name_the_file_and_line(tmp_path, line, message):
    path = _registry(tmp_path, "# header\n" + line)
    with pytest.raises(CcppInputError) as error:
        parse_ddt_handlers(path)
    assert str(error.value).startswith(f"{path}:2: ")
    assert message in str(error.value)


def test_a_type_listed_twice(tmp_path):
    entry = "handler t module=m type_module=m write=w read=r compare=c\n"
    path = _registry(tmp_path, entry + entry)
    with pytest.raises(CcppInputError, match=r":2: handler t: listed twice"):
        parse_ddt_handlers(path)


def test_a_source_listed_twice(tmp_path):
    path = _registry(tmp_path, "source handlers.F90\ndriver_source handlers.F90\n")
    with pytest.raises(CcppInputError, match=r":2: driver_source: handlers.F90 listed twice"):
        parse_ddt_handlers(path)
