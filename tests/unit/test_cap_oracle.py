"""cam_case.py (a built CAM-SIMA case's generator inputs) and cap_oracle.py
(comparing generated caps between revisions), on synthetic case directories."""

import os

from xdsl_ccpp.tools import cap_oracle
from xdsl_ccpp.tools.cam_case import generator_args, read_case

PHYS = "/cam/src/physics/ncar_ccpp"


def _case(tmp_path, name="case", *, sdfs=(f"{PHYS}/suites/suite_cam4.xml",),
          preproc="UNSET", gpu=False, pkgcap=False):
    case = tmp_path / name
    obj = case / "bld" / "atm" / "obj"
    obj.mkdir(parents=True)
    entries = "".join(f'<SDF file_path="{s}" hash="0"/>' for s in sdfs)
    entries += f'<scheme file_path="{PHYS}/schemes/zm.meta" hash="0"/>'
    entries += '<host file_path="/cam/registry/physics_types.meta" hash="0"/>'
    entries += '<scheme_namelist_meta_file file_path="/bld/zm_namelist.meta" hash="0"/>'
    (obj / "cam_build_cache.xml").write_text(
        f"<cache><CCPP>{entries}<preproc_defs>{preproc}</preproc_defs></CCPP></cache>")
    (case / "env_case.xml").write_text('<entry id="SRCROOT" value="/cam"/>')
    (case / "env_build.xml").write_text(
        f'<entry id="OPENACC_GPU_OFFLOAD" value="{"TRUE" if gpu else "FALSE"}"/>'
        f'<entry id="CCPP_PACKAGE_CAPS" value="{"TRUE" if pkgcap else "FALSE"}"/>')
    return str(case)


def test_read_xml_suite_case(tmp_path):
    case = read_case(_case(tmp_path, preproc="-DSPMD, -DPLON=1"))
    assert case.suite == "cam4" and case.label == "cam4"
    assert case.py_suite is None and case.python_path == ()
    assert case.host_files == ("/cam/registry/physics_types.meta", "/bld/zm_namelist.meta")
    assert case.preproc_defs == ("-DSPMD", "-DPLON=1")
    assert case.framework_src_dir == "/cam/ccpp_framework/src"
    args = generator_args(case, "/out")
    assert args[args.index("--suites") + 1] == f"{PHYS}/suites/suite_cam4.xml"
    assert "--preproc-defs=-DSPMD,-DPLON=1" in args
    assert "--directive" not in args and "--package-caps" not in args
    assert {"--cam-host", "--legacy-mode"} <= set(args)


def test_read_gpu_python_package_cap_case(tmp_path):
    sdfs = (f"{PHYS}/test/test_suites-py/suite_kessler_test.py",
            f"{PHYS}/suites-py/parameterizations/__init__.py")
    case = read_case(_case(tmp_path, sdfs=sdfs, gpu=True, pkgcap=True))
    assert case.suite == "kessler_test" and case.label == "kessler_test-acc-pkgcap"
    assert case.python_path == (f"{PHYS}/suites-py",)
    args = generator_args(case, "/out")
    assert args[args.index("--py") + 1] == sdfs[0] and "--suites" not in args
    assert args[args.index("--directive") + 1] == "acc" and "--package-caps" in args


def test_input_key_groups_identical_inputs(tmp_path):
    a, b = read_case(_case(tmp_path, "a")), read_case(_case(tmp_path, "b"))
    gpu = read_case(_case(tmp_path, "c", gpu=True))
    assert a.input_key == b.input_key != gpu.input_key


def test_compare_dirs_ignores_run_specific_paths(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    base.mkdir(), head.mkdir()
    (base / "ccpp_datatable.xml").write_text(f'<file path="{base}/cam_ccpp_cap.F90"/>\n<file>/old_tree/x.F90</file>\n')
    (head / "ccpp_datatable.xml").write_text(f'<file path="{head}/cam_ccpp_cap.F90"/>\n<file>/new_tree/x.F90</file>\n')
    (base / "cap.F90").write_text("a\nb\n")
    (head / "cap.F90").write_text("a\nc\n")
    (head / "new.F90").write_text("x\n")
    diffs = dict(cap_oracle.compare_dirs(str(base), str(head), "/old_tree", "/new_tree"))
    assert set(diffs) == {"cap.F90", "new.F90"}
    assert "-b\n" in diffs["cap.F90"] and "+c\n" in diffs["cap.F90"]


def test_run_diff_reports(tmp_path, monkeypatch):
    """Identical, different, and failing-both cases; shared inputs generated once."""
    contents = {"base": {"cam4": "x\n", "kessler": "k\n"},
                "head": {"cam4": "y\n", "kessler": "k\n"}}
    calls = []

    def fake_generate(src_tree, case, out_dir):
        calls.append((src_tree, case.suite))
        os.makedirs(out_dir, exist_ok=True)
        if case.suite == "cam7":
            return False, "error: unmatched prec_sh"
        open(os.path.join(out_dir, "cap.F90"), "w").write(contents[src_tree][case.suite])
        return True, ""

    monkeypatch.setattr(cap_oracle, "generate", fake_generate)
    cases = [read_case(_case(tmp_path, n, sdfs=(f"{PHYS}/suites/suite_{s}.xml",)))
             for n, s in (("a", "cam4"), ("b", "kessler"), ("c", "kessler"), ("d", "cam7"))]
    lines = []
    same = cap_oracle.run_diff(cases, "base", "head", str(tmp_path / "out"), report=lines.append)
    assert not same
    text = "\n".join(lines)
    assert "DIFFERENT  cam4: cap.F90 (2 lines)" in text
    assert "IDENTICAL  kessler (+1 cases with the same inputs)" in text
    assert "BOTH FAIL  cam7" in text
    assert calls.count(("base", "kessler")) == 1


def test_input_key_compares_contents_not_paths(tmp_path):
    """Each case has its own copy of the registry metadata: same contents
    under different paths must group together, different contents must not."""
    regs = {}
    for name, text in (("a", "x"), ("b", "x"), ("c", "y")):
        reg = tmp_path / f"{name}_registry.meta"
        reg.write_text(text)
        regs[name] = read_case(_case(tmp_path, name))
        object.__setattr__(regs[name], "host_files", (str(reg),))
    assert regs["a"].input_key == regs["b"].input_key != regs["c"].input_key


def test_run_diff_parallel_keeps_case_order(tmp_path, monkeypatch):
    def fake_generate(src_tree, case, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        open(os.path.join(out_dir, "cap.F90"), "w").write(case.suite)
        return True, ""

    monkeypatch.setattr(cap_oracle, "generate", fake_generate)
    suites = ["s%d" % i for i in range(8)]
    cases = [read_case(_case(tmp_path, s, sdfs=(f"{PHYS}/suites/suite_{s}.xml",))) for s in suites]
    lines = []
    assert cap_oracle.run_diff(cases, "base", "head", str(tmp_path / "out"),
                               report=lines.append, jobs=4)
    assert lines == [f"IDENTICAL  {s}" for s in suites]


# ---- cap_compare: semantic comparison of two generators' caps ----

from xdsl_ccpp.tools.cap_compare import compare  # noqa: E402

_HOST = """\
module cam_ccpp_cap
contains
  subroutine ccpp_physics_run(col_start, col_end)
    integer :: col_start, col_end
    call {suite}_physics_before_coupler(col_start, col_end, {args})
  end subroutine ccpp_physics_run
end module cam_ccpp_cap
"""

_SUITE = """\
module {suite}_cap
contains
  subroutine {suite}_physics_before_coupler(col_start, col_end, {dummies})
    integer :: col_start, col_end
{body}
  end subroutine {suite}_physics_before_coupler
end module {suite}_cap
"""


def _caps(tmp_path, name, host_args, dummies, body, suite="s"):
    d = tmp_path / name
    d.mkdir()
    (d / "cam_ccpp_cap.F90").write_text(_HOST.format(suite=suite, args=host_args))
    (d / f"{suite}_cap.F90").write_text(_SUITE.format(suite=suite, dummies=dummies, body=body))
    return str(d)


def test_compare_resolves_arguments_through_the_host_cap(tmp_path):
    """Different dummy names and suite-cap layouts, same host variables:
    equivalent. A different host variable for one argument: a difference."""
    ref = _caps(tmp_path, "capgen", "trop_top, cf_top", "top_lev1, top_lev_cloudphys",
                "    call cld_run(top_lev=top_lev1)\n    call fice_run(top_lev=top_lev_cloudphys)")
    same = _caps(tmp_path, "xdsl", "cf_top, trop_top", "a, b",
                 "    call cld_run(top_lev=b)\n    call fice_run(top_lev=a)")
    diffs, renames = compare(ref, same, ["physics_before_coupler"])
    assert diffs == [] and renames == []

    wrong = _caps(tmp_path, "xdsl_bad", "cf_top", "a",
                  "    call cld_run(top_lev=a)\n    call fice_run(top_lev=a)")
    diffs, _ = compare(ref, wrong, ["physics_before_coupler"])
    assert diffs == ["run/physics_before_coupler: cld_run#1 top_lev: capgen trop_top | xdsl cf_top"]


def test_compare_reports_call_order_and_loops(tmp_path):
    ref = _caps(tmp_path, "capgen", "x", "x",
                "    call a_run(v=x)\n    do i = 1, 2\n    call b_run(v=x)\n    end do")
    other = _caps(tmp_path, "xdsl", "x", "x", "    call b_run(v=x)\n    call a_run(v=x)")
    diffs, _ = compare(ref, other, ["physics_before_coupler"])
    assert len(diffs) == 1 and "call sequence differs" in diffs[0]
    assert "capgen: a [b]" in diffs[0] and "xdsl:   b a" in diffs[0]


def test_compare_accepts_consistent_renaming_of_cap_variables(tmp_path):
    body = "    real :: {v}(10)\n    call p_run(out={v})\n    call c_run(in={v})"
    ref = _caps(tmp_path, "capgen", "x", "x", body.format(v="work1"))
    other = _caps(tmp_path, "xdsl", "x", "x", body.format(v="tmp_work"))
    diffs, renames = compare(ref, other, ["physics_before_coupler"])
    assert diffs == [] and renames == [("work1", "tmp_work")]


# ---- cap_oracle capgen: outcomes ----

def test_capgen_check_outcomes(tmp_path, monkeypatch):
    """Equivalent, different, capgen rejecting (not a failure), capgen
    erroring and xdsl-ccpp failing (failures); Python and package-cap
    cases skipped."""
    def fake_capgen(case, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        return {"rejected": ("rejected", "Invalid variable property name, 'memory_space'"),
                "broken": ("error", "TypeError: ...")}.get(case.suite, ("ok", ""))

    def fake_generate(src_tree, case, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        return case.suite != "xdslfail", "error"

    def fake_compare(ref, other, groups):
        return (["run: x#1 v: capgen a | xdsl b"], []) if "different" in ref else ([], [])

    monkeypatch.setattr(cap_oracle, "run_capgen", fake_capgen)
    monkeypatch.setattr(cap_oracle, "generate", fake_generate)
    monkeypatch.setattr(cap_oracle, "compare", fake_compare)
    names = ["same", "different", "rejected", "broken", "xdslfail"]
    cases = [read_case(_case(tmp_path, n, sdfs=(f"{PHYS}/suites/suite_{n}.xml",))) for n in names]
    cases.append(read_case(_case(tmp_path, "py", pkgcap=True,
                                 sdfs=(f"{PHYS}/test/test_suites-py/suite_k.py",))))
    lines = []
    assert not cap_oracle.run_capgen_check(cases, "head", str(tmp_path / "out"), report=lines.append)
    text = "\n".join(lines)
    assert "EQUIVALENT same" in text and "DIFFERENT  different: 1 differences" in text
    assert "NO CAPGEN  rejected" in text and "ERROR      broken" in text
    assert "XDSL FAILS xdslfail" in text and "SKIPPED    k-pkgcap" in text

    lines = []
    assert cap_oracle.run_capgen_check(cases[2:3], "head", str(tmp_path / "out2"), report=lines.append)
