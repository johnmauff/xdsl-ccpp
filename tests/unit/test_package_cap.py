"""Package caps (composite-scheme 2f, step 2f-2): ``ccpp_dsl --package-caps``
generates one ``<package>_package_cap`` module per package; the suite cap
calls its segment routines (transforms/lower_packages.py,
transforms/suitecap/package_cap.py)."""

import re

from xdsl_ccpp.tools.ccpp_dsl import ccppMain

H = "examples/helloworld"
_ERR = """[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character
  kind = len=512
  intent = out
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""


def _scheme(name, args, column_count="horizontal_dimension"):
    arrays = "".join(f"""[ {local} ]
  standard_name = {std}
  units = K
  dimensions = ({column_count}, vertical_layer_dimension)
  type = real | kind = kind_phys
  intent = {intent}
""" for local, std, intent in args)
    return f"""[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ ncol ]
  standard_name = {column_count}
  units = count
  dimensions = ()
  type = integer
  intent = in
[ nlev ]
  standard_name = vertical_layer_dimension
  units = count
  dimensions = ()
  type = integer
  intent = in
{arrays}{_ERR}"""


_SUITE = """\
from xdsl_ccpp.frontend.py_api import ccpp_package, ccpp_scheme_ref, ccpp_suite, export_suite

producer = ccpp_scheme_ref("producer")
consumer = ccpp_scheme_ref("consumer")
diag = ccpp_scheme_ref("diag")
pkg = ccpp_package("pkg")

@pkg.entry_point
def step(*, hook):
    producer()
    hook()
    consumer()

@ccpp_suite("pkg_suite", version="1.0")
class PkgSuite:
    def physics():
        step(hook=diag)

if __name__ == "__main__":
    export_suite(PkgSuite)
"""


def _setup(tmp_path, column_count="horizontal_dimension"):
    # flux: first written by the package, read by the hook -- shared, so
    # suite-owned in the suite cap and a dummy argument of the segment.
    schemes = {
        "producer": [("temp", "potential_temperature", "in"), ("work", "work_array", "out"),
                     ("flux", "flux_array", "out")],
        "diag": [("temp", "potential_temperature", "in"), ("flux", "flux_array", "in")],
        "consumer": [("work", "work_array", "in"), ("temp", "potential_temperature", "inout")],
    }
    paths = []
    for name, args in schemes.items():
        path = tmp_path / f"{name}.meta"
        path.write_text(_scheme(name, args, column_count))
        paths.append(str(path))
    (tmp_path / "pkg_suite.py").write_text(_SUITE)
    return paths


def _options(tmp_path, schemes, label, **extra):
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": [], "py": str(tmp_path / "pkg_suite.py"), "scheme_files": schemes,
        "host_files": [f"{H}/hello_world_host.meta", f"{H}/hello_world_mod.meta"],
        "kind_map": ["kind_dyn:REAL32"], "out": str(tmp_path / label / "out"),
        "tempdir": str(tmp_path / label / "tmp"), "verbose": 0, **extra})
    return tool, options_db


def _generate(tmp_path, schemes, label, **extra):
    tool, options_db = _options(tmp_path, schemes, label, **extra)
    result = tool.run(options_db)
    out = options_db["out"]
    return {p: open(f"{out}/{p}").read() for p in result.written if p.endswith(".F90")}


def _calls(src):
    return re.findall(r"call (\w+)\(", src)


def test_package_cap_holds_segments_and_private_state(tmp_path):
    schemes = _setup(tmp_path)
    flat = _generate(tmp_path, schemes, "flat")
    caps = _generate(tmp_path, schemes, "caps", package_caps=True)

    assert "pkg_package_cap.F90" not in flat
    assert _calls(flat["pkg_suite_cap.F90"]).count("producer_run") == 1

    cap = caps["pkg_package_cap.F90"]
    suite = caps["pkg_suite_cap.F90"]
    # The private work array lives in the package cap only.
    assert re.search(r"allocatable :: work\(:, :\)", cap)
    assert "work" not in re.sub(r"!.*", "", suite)
    # A shared array the package writes first stays in the suite cap only.
    assert not re.search(r"allocatable :: flux", cap)
    assert re.search(r"subroutine step_1_run\(.*\bflux\b", cap)
    assert re.search(r"allocatable :: flux\(:, :\)", suite)
    # Two segments around the hook; the suite calls them and the hook.
    assert re.findall(r"subroutine (step_\d_run)\(", cap) == ["step_1_run", "step_2_run"]
    assert _calls(cap) == ["producer_run", "consumer_run"]
    assert {"step_1_run", "step_2_run"} <= set(
        re.findall(r"use pkg_package_cap, only: (\w+)", suite))
    physics = suite.split("subroutine pkg_suite_physics(")[1].split("end subroutine")[0]
    assert _calls(physics) == ["step_1_run", "diag_run", "step_2_run"]


def test_segments_take_the_column_range(tmp_path, legacy_mode):
    """Schemes taking the loop extent: segments are generated like group
    functions, so they take col_start/col_end, which the suite cap passes."""
    schemes = _setup(tmp_path, column_count="horizontal_loop_extent")
    caps = _generate(tmp_path, schemes, "caps", package_caps=True, legacy_mode=True)
    cap = caps["pkg_package_cap.F90"]
    assert re.search(r"subroutine step_1_run\(col_start, col_end,", cap)
    physics = caps["pkg_suite_cap.F90"].split("subroutine pkg_suite_physics(")[1]
    assert re.search(r"call step_1_run\(col_start=col_start, col_end=col_end,", physics)


def test_list_outputs_predicts_the_package_cap(tmp_path):
    schemes = _setup(tmp_path)
    for extra, expected in (({}, False), ({"package_caps": True}, True)):
        tool, options_db = _options(tmp_path, schemes, "list", list_outputs=True, **extra)
        assert ("pkg_package_cap.F90" in tool.run(options_db).written) is expected


def test_assumed_length_character_stays_assumed_length():
    """A segment's len=* character dummy takes the caller's length; a fixed
    512 would read past a shorter host string (s25b: 256-character file
    names arrived as garbage)."""
    from xdsl_ccpp.transforms.suitecap.block_args import _block_arg_type
    from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPArgument

    def arg(kind, dims=0, mismatch=None):
        a = CCPPArgument("fname")
        a.setAttr("type", "character")
        a.setAttr("kind", kind)
        a.setAttr("dimensions", dims)
        if mismatch:
            a.setAttr("model_var_kind_mismatch", mismatch)
        return a

    assert str(_block_arg_type(arg("len=*"))) == "memref<?xi8>"
    assert str(_block_arg_type(arg("len=*", dims=1))) == "memref<?x?xi8>"
    assert str(_block_arg_type(arg("len=64"))) == "memref<64xi8>"
    # Host-matched with a different length: the host's length, as before.
    assert str(_block_arg_type(arg("len=*", mismatch="len=*:len=256"))) == "memref<256xi8>"


_HOST_ERRORS_META = """\
[ccpp-table-properties]
  name = host_errors
  type = module
[ccpp-arg-table]
  name = host_errors
  type = module
[ errmsg ]
  standard_name = ccpp_error_message
  units = none
  dimensions = ()
  type = character | kind = len=512
[ errcode ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
[ col_start ]
  standard_name = horizontal_loop_begin
  units = count
  dimensions = ()
  type = integer
[ col_end ]
  standard_name = horizontal_loop_end
  units = count
  dimensions = ()
  type = integer
"""


def test_active_scheme_list_names_package_schemes(tmp_path):
    """ccpp_physics_suite_schemes lists the package's schemes, not its
    segments: CAM-SIMA reads a scheme's namelist only if it is listed
    (s25c: RRTMGP's file names stayed UNSET)."""
    # --capgen-api's wrappers use-associate the host's errmsg/errcode and
    # column bounds, which a host declares as module variables (CAM-SIMA:
    # physics_types, physics_grid).
    errors = tmp_path / "host_errors.meta"
    errors.write_text(_HOST_ERRORS_META)
    caps = _generate(tmp_path, _setup(tmp_path), "caps", package_caps=True, capgen_api=True,
                     host_files=[f"{H}/hello_world_host.meta", f"{H}/hello_world_mod.meta",
                                 str(errors)])
    body = caps["Pkg_ccpp_cap.F90"].split("subroutine ccpp_physics_suite_schemes")[1]
    body = body.split("end subroutine")[0]
    assert re.findall(r"'(\w+)'", body) == ["pkg_suite", "producer", "diag", "consumer"]


_DIM_META = {
    # sizer returns nwork; diag (the hook) also reads it, so it is a dummy
    # argument of the segment, not package state.
    "sizer": ("""[ nwork ]
  standard_name = number_of_work_levels
  units = count
  dimensions = ()
  type = integer
  intent = out
""", ""),
    "filler": ("""[ ncol ]
  standard_name = horizontal_dimension
  units = count
  dimensions = ()
  type = integer
  intent = in
[ nwork ]
  standard_name = number_of_work_levels
  units = count
  dimensions = ()
  type = integer
  intent = in
[ work ]
  standard_name = work_array
  units = 1
  dimensions = (horizontal_dimension, number_of_work_levels)
  type = real | kind = kind_phys
  intent = out
""", ""),
    "diag": ("""[ nwork ]
  standard_name = number_of_work_levels
  units = count
  dimensions = ()
  type = integer
  intent = in
""", ""),
    "reader": ("""[ ncol ]
  standard_name = horizontal_dimension
  units = count
  dimensions = ()
  type = integer
  intent = in
[ nwork ]
  standard_name = number_of_work_levels
  units = count
  dimensions = ()
  type = integer
  intent = in
[ work ]
  standard_name = work_array
  units = 1
  dimensions = (horizontal_dimension, number_of_work_levels)
  type = real | kind = kind_phys
  intent = in
""", ""),
}

_DIM_SUITE = """\
from xdsl_ccpp.frontend.py_api import ccpp_package, ccpp_scheme_ref, ccpp_suite, export_suite

sizer = ccpp_scheme_ref("sizer")
filler = ccpp_scheme_ref("filler")
reader = ccpp_scheme_ref("reader")
diag = ccpp_scheme_ref("diag")
pkg = ccpp_package("pkg")

@pkg.entry_point
def step(*, hook):
    sizer()
    filler()
    hook()
    reader()

@ccpp_suite("pkg_suite", version="1.0")
class PkgSuite:
    def physics():
        step(hook=diag)

if __name__ == "__main__":
    export_suite(PkgSuite)
"""


def test_private_array_sized_by_segment_output(tmp_path):
    """A private array whose dimension the segment itself returns is
    allocated after the scheme that sets it (s25d: t_rad(columns, nlay) was
    allocated before rrtmgp_inputs_setup_init set nlay), and reallocated
    when its extents change."""
    paths = []
    for name, (args, _) in _DIM_META.items():
        path = tmp_path / f"{name}.meta"
        path.write_text(f"""[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
{args}{_ERR}""")
        paths.append(str(path))
    (tmp_path / "pkg_suite.py").write_text(_DIM_SUITE)
    tool, options_db = _options(tmp_path, paths, "caps", package_caps=True)
    options_db["py"] = str(tmp_path / "pkg_suite.py")
    tool.run(options_db)
    cap = open(f"{options_db['out']}/pkg_package_cap.F90").read()
    step_1 = cap.split("subroutine step_1_run(")[1].split("end subroutine")[0]
    assert re.search(r"integer, intent\((in)?out\) :: nwork", step_1)  # a dummy, not state
    assert step_1.index("call sizer_run(") < step_1.index("allocate(work(")
    # A run segment's extents can change between steps (s25e: nday-sized
    # arrays kept their first size): reallocate when the shape differs.
    assert re.search(r"if \(any\(shape\(work\) /= \[ncol, nwork\]\)\) then\s+deallocate\(work\)",
                     step_1)
    assert step_1.index("any(shape(work)") < step_1.index("if (.not. allocated(work))")


def test_private_device_state_lives_in_the_package_cap(tmp_path):
    """2g-1: a private device-resident array crossing segments (written before
    the hook, read after it) is allocated and created on the device by the
    package's state-create routine, deleted from the device by its
    state-delete routine, and neither allocated nor moved by the run
    segments; the suite cap moves no data and calls the state routines in its
    group init and final."""
    import sys
    sys.path.insert(0, "tests/unit")
    from test_package_scope import _device_scheme_meta

    paths = []
    for name, args in [("producer", [("temp", "potential_temperature", "in"),
                                     ("work", "work_array", "out")]),
                       ("diag", [("temp", "potential_temperature", "in")]),
                       ("consumer", [("work", "work_array", "in"),
                                     ("temp", "potential_temperature", "inout")])]:
        path = tmp_path / f"{name}.meta"
        path.write_text(_device_scheme_meta(name, args))
        paths.append(str(path))
    (tmp_path / "pkg_suite.py").write_text(_SUITE)
    caps = _generate(tmp_path, paths, "caps", package_caps=True, directive="acc")
    cap, suite = caps["pkg_package_cap.F90"], caps["pkg_suite_cap.F90"]

    def routine(src, name):
        return src.split(f"subroutine {name}(")[1].split("end subroutine")[0]

    create = routine(cap, "pkg_state_create_init")
    assert re.search(r"allocate\(work\(", create)
    assert "!$acc enter data create(work)" in create
    assert "!$acc exit data delete(work)" in routine(cap, "pkg_state_delete_finalize")
    for segment in ("step_1_run", "step_2_run"):
        body = routine(cap, segment)
        assert "allocate(" not in body and "!$acc" not in body
    assert "!$acc" not in suite
    assert "call pkg_state_create_init(" in routine(suite, "pkg_suite_init_physics")
    assert "call pkg_state_delete_finalize(" in routine(suite, "pkg_suite_final_physics")


def _mixed_space_caps(tmp_path, suite):
    """producer and diag use their arrays on the device, consumer on the host."""
    import sys
    sys.path.insert(0, "tests/unit")
    from test_package_scope import _device_scheme_meta

    paths = []
    for name, args, device in [
            ("producer", [("temp", "potential_temperature", "inout"),
                          ("work", "work_array", "out")], True),
            ("diag", [("temp", "potential_temperature", "in")], True),
            ("consumer", [("work", "work_array", "in"),
                          ("temp", "potential_temperature", "inout")], False)]:
        path = tmp_path / f"{name}.meta"
        path.write_text((_device_scheme_meta if device else _scheme)(name, args))
        paths.append(str(path))
    (tmp_path / "pkg_suite.py").write_text(suite)
    return _generate(tmp_path, paths, "caps", package_caps=True, directive="acc")


def _routine(src, name):
    return src.split(f"subroutine {name}(")[1].split("end subroutine")[0]


def test_private_state_synced_for_host_use_in_a_later_segment(tmp_path):
    """2g-2: a private array written on the device before the hook and read
    on the host after it is synced around the host use, inside the package
    cap; the device copy stays current between segments."""
    caps = _mixed_space_caps(tmp_path, _SUITE)
    cap = caps["pkg_package_cap.F90"]
    assert "!$acc" not in _routine(cap, "step_1_run")
    step_2 = _routine(cap, "step_2_run")
    assert re.search(r"!\$acc update self\(work\)\s+(#endif\s+)?(#ifdef USE_GPU\s+)?"
                     r"[^!]*call consumer_run\([^)]*\)[^!]*!\$acc update device\(work\)",
                     step_2, re.S), step_2
    assert "update self(work)" not in caps["pkg_suite_cap.F90"]


def test_segment_syncs_host_use_of_a_device_argument(tmp_path):
    """2g-2: a segment using a shared array on the device (producer) and on
    the host (consumer) declares it device-resident, so the suite cap moves
    nothing around it, and syncs the host use inside the package cap."""
    caps = _mixed_space_caps(tmp_path, _SUITE.replace(
        "    producer()\n    hook()\n    consumer()",
        "    producer()\n    consumer()\n    hook()"))
    step_1 = _routine(caps["pkg_package_cap.F90"], "step_1_run")
    produce, consume = step_1.index("call producer_run("), step_1.index("call consumer_run(")
    assert produce < step_1.index("update self(temp)") < consume
    assert consume < step_1.index("update device(temp)")
    assert "!$acc update" not in caps["pkg_suite_cap.F90"]


def test_advected_array_from_the_host_is_a_segment_argument(tmp_path):
    """An advected array (suite-owned in the suite cap) that a hook writes and
    the package updates is a dummy argument of the segment, not package state
    (s27a: Kessler's dry water species)."""
    schemes = {
        "producer": [("temp", "potential_temperature", "in"), ("work", "work_array", "out")],
        "diag": [("temp", "potential_temperature", "in"), ("q", "dry_q", "out")],
        "consumer": [("work", "work_array", "in"), ("q", "dry_q", "inout"),
                     ("temp", "potential_temperature", "inout")],
    }
    paths = []
    for name, args in schemes.items():
        path = tmp_path / f"{name}.meta"
        text = _scheme(name, args)
        path.write_text(re.sub(r"(\[ q \]\n(?:  .*\n)*?  intent = \w+\n)", r"\1  advected = True\n",
                               text))
        paths.append(str(path))
    (tmp_path / "pkg_suite.py").write_text(_SUITE.replace(
        'pkg = ccpp_package("pkg")', 'pkg = ccpp_package("pkg", shared_state=["dry_q"])'))
    caps = _generate(tmp_path, paths, "caps", package_caps=True)
    step_2 = caps["pkg_package_cap.F90"].split("subroutine step_2_run(")[1]
    assert re.match(r"[^)]*\bq\b", step_2), step_2[:200]
    assert re.search(r"intent\(inout\) :: q\(:, :\)", step_2.split("end subroutine")[0])
    assert "allocatable :: q(" not in caps["pkg_package_cap.F90"]


def test_init_segment_does_not_repeat_state_allocation(tmp_path):
    """The init-phase segment calls the package's init schemes only; the
    private arrays are allocated by the state-create routine, which runs
    first (on a GPU, it also creates them on the device)."""
    paths = _setup(tmp_path)
    producer = tmp_path / "producer.meta"
    producer.write_text(producer.read_text() + f"""[ccpp-arg-table]
  name = producer_init
  type = scheme
{_ERR}""")
    caps = _generate(tmp_path, paths, "caps", package_caps=True)
    cap = caps["pkg_package_cap.F90"]
    create = cap.split("subroutine pkg_state_create_init(")[1].split("end subroutine")[0]
    init = cap.split("subroutine step_init_1_init(")[1].split("end subroutine")[0]
    assert "allocate(work(" in create
    assert "call producer_init(" in init
    assert "allocate(" not in init


# Column slicing (BACKLOG chunked-column-slicing): with col_start/col_end
# (legacy horizontal_loop_extent), a suite-owned array with a horizontal first
# dimension is allocated over all columns and passed as the current columns.
_LOOP = "horizontal_loop_extent"


def _slicing_meta(name, phase, body):
    return f"""[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_{phase}
  type = scheme
{body}{_ERR}"""


def _slicing_arg(local, std, intent, dims, extra=""):
    kind = "type = integer" if not dims else "type = real | kind = kind_phys"
    units = "count" if not dims else "1"
    return f"""[ {local} ]
  standard_name = {std}
  units = {units}
  dimensions = ({dims})
  {kind}
  intent = {intent}
{extra}"""


def _slicing_caps(tmp_path, package_caps):
    """setup writes a band count at init; producer writes wk (with interface
    levels, which no scheme takes as an argument) and bw (allocatable, sized
    by the band count); consumer, after the hook, reads both."""
    def run_args(intent):
        return (_slicing_arg("ncol", _LOOP, "in", "")
                + _slicing_arg("wk", "work_at_interfaces", intent,
                               f"{_LOOP}, vertical_interface_dimension")
                + _slicing_arg("nb", "number_of_bands", "in", "")
                + _slicing_arg("bw", "band_work", intent, f"{_LOOP}, number_of_bands",
                               "  allocatable = True\n" if intent == "out" else ""))
    metas = {
        "setup": _slicing_meta("setup", "init", _slicing_arg("nb", "number_of_bands", "out", "")),
        "producer": _slicing_meta("producer", "run", run_args("out")),
        "diag": _slicing_meta("diag", "run", _slicing_arg("ncol", _LOOP, "in", "")),
        "consumer": _slicing_meta("consumer", "run", run_args("in")),
    }
    paths = []
    for name, text in metas.items():
        path = tmp_path / f"{name}.meta"
        path.write_text(text)
        paths.append(str(path))
    (tmp_path / "pkg_suite.py").write_text(_SUITE.replace(
        "@ccpp_suite", 'setup = ccpp_scheme_ref("setup")\n\n@ccpp_suite').replace(
        "        step(hook=diag)", "        setup()\n        step(hook=diag)"))
    caps = _generate(tmp_path, paths, "caps", package_caps=package_caps, legacy_mode=True)
    return {name: src.replace("&\n", " ") for name, src in caps.items()}


def _passed(src, name):
    """How the calls in *src* pass *name*: each keyword argument's value."""
    return set(re.findall(rf"\b{name}=\s*({name}(?:\((?:[^()]|\([^()]*\))*\))?)", src))


def test_suite_owned_arrays_are_sliced_to_the_current_columns(tmp_path):
    caps = _slicing_caps(tmp_path, package_caps=False)
    suite = caps["pkg_suite_cap.F90"]
    assert _passed(suite, "wk") == {"wk(col_start:col_end, 1:size(wk, 2))"}
    assert _passed(suite, "bw") == {"bw(col_start:col_end, 1:nb)"}
    # bw is allocated where it is first written, in the run routine, but
    # over all columns like every other suite-owned array.
    assert re.search(r"allocate\(bw\(ncols, nb\)\)", suite)
    assert not re.search(r"allocate\(\w+\(ncol\b", suite)


def test_package_state_is_sliced_to_the_current_columns(tmp_path):
    caps = _slicing_caps(tmp_path, package_caps=True)
    cap = caps["pkg_package_cap.F90"]
    assert _passed(cap, "wk") == {"wk(col_start:col_end, 1:size(wk, 2))"}
    assert _passed(cap, "bw") == {"bw(col_start:col_end, 1:nb)"}
    assert not re.search(r"allocate\(\w+\(ncol\b", cap)
