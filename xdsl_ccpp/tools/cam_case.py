"""The generator inputs of a built CAM-SIMA case.

A CAM-SIMA build records what it passed to the cap generator in
``bld/atm/obj/cam_build_cache.xml`` (suite files, scheme and host metadata,
preprocessor definitions); the GPU and package-cap switches are case XML
variables. ``read_case`` collects them, and ``generator_args`` turns them
into the ``ccpp_dsl`` command line CAM-SIMA's ``cam_autogen.py`` uses, so a
case's caps can be regenerated outside a CAM-SIMA build (e.g. with another
xdsl-ccpp revision).
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class CamCase:
    case_dir: str
    suite_files: tuple[str, ...]   # suite definition files, or a Python suite and its helpers
    py_suite: str | None           # the Python suite script, if the case uses one
    scheme_files: tuple[str, ...]
    host_files: tuple[str, ...]    # includes the scheme namelist metadata files
    preproc_defs: tuple[str, ...]
    framework_src_dir: str
    directive: str | None          # "acc" for an OpenACC GPU build
    package_caps: bool
    python_path: tuple[str, ...] = ()  # a Python suite's library (suites-py), put on PYTHONPATH

    @property
    def suite(self) -> str:
        """Suite name, from the suite file name (suite_<name>.xml/.py)."""
        name = os.path.basename(self.py_suite or self.suite_files[0])
        return name[len("suite_"):].rsplit(".", 1)[0] if name.startswith("suite_") else name

    @property
    def label(self) -> str:
        """Short name for reports: suite, plus -acc and -pkgcap."""
        return (self.suite + ("-acc" if self.directive else "")
                + ("-pkgcap" if self.package_caps else ""))

    @property
    def input_key(self) -> str:
        """Equal for cases whose generated caps must be equal: by file
        contents, since each case keeps its own copy of the generated
        registry metadata (bld/atm/obj/cam_registry) under a different path."""
        parts = [*map(_file_digest, (*self.suite_files, *self.scheme_files, *self.host_files)),
                 *self.preproc_defs, _file_digest(self.framework_src_dir),
                 str(self.directive), str(self.package_caps)]
        return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:12]


@functools.cache
def _file_digest(path: str) -> str:
    """A file's content hash; the path itself for a directory or missing file."""
    if not os.path.isfile(path):
        return path
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def _xml_value(path: str, var_id: str) -> str | None:
    match = re.search(rf'id="{var_id}"[^>]*value="([^"]*)"', open(path).read())
    return match.group(1) if match else None


def read_case(case_dir: str) -> CamCase:
    """The generator inputs a built CAM-SIMA case used."""
    cache_path = os.path.join(case_dir, "bld", "atm", "obj", "cam_build_cache.xml")
    if not os.path.isfile(cache_path):
        raise FileNotFoundError(f"{case_dir}: no build cache ({cache_path}); build the case first")
    ccpp = ET.parse(cache_path).getroot().find("CCPP")
    paths = lambda tag: [e.get("file_path") for e in ccpp.iter(tag) if e.get("file_path")]
    suite_files = paths("SDF")
    py_suite = next((f for f in suite_files if os.path.basename(f).startswith("suite_")
                     and f.endswith(".py")), None)
    host_files = paths("host")
    # The scheme namelist .meta files are host files too; the cache stores
    # each path as the element's text (cam_build_cache.py), not file_path.
    namelist_meta = [e.text.strip() for e in ccpp.iter("scheme_namelist_meta_file")
                     if e.text and e.text.strip()]
    host_files += [f for f in namelist_meta if f not in host_files]
    # cam_autogen.py runs a Python suite with its suites-py library first on
    # PYTHONPATH; the build cache lists files from that library.
    library = next((f[:f.index("/suites-py/") + len("/suites-py")]
                    for f in suite_files if "/suites-py/" in f), None) if py_suite else None
    preproc = (ccpp.findtext("preproc_defs") or "UNSET").strip()
    preproc_defs = () if preproc == "UNSET" else tuple(p.strip() for p in preproc.split(","))
    srcroot = _xml_value(os.path.join(case_dir, "env_case.xml"), "SRCROOT")
    env_build = os.path.join(case_dir, "env_build.xml")
    return CamCase(
        case_dir=os.path.abspath(case_dir),
        suite_files=tuple(suite_files),
        py_suite=py_suite,
        scheme_files=tuple(paths("scheme")),
        host_files=tuple(host_files),
        preproc_defs=preproc_defs,
        framework_src_dir=os.path.join(srcroot, "ccpp_framework", "src"),
        directive="acc" if _xml_value(env_build, "OPENACC_GPU_OFFLOAD") == "TRUE" else None,
        package_caps=_xml_value(env_build, "CCPP_PACKAGE_CAPS") == "TRUE",
        python_path=(library,) if library else (),
    )


def suite_groups(case: CamCase) -> list[str]:
    """The group names in the case's suite definition files (empty for a
    Python suite)."""
    groups = []
    for path in case.suite_files:
        if path.endswith(".xml") and os.path.isfile(path):
            groups += [g.get("name") for g in ET.parse(path).getroot().iter("group")]
    return groups


def generator_args(case: CamCase, out_dir: str) -> list[str]:
    """The ccpp_dsl arguments cam_autogen.py passes for this case."""
    suite_args = (["--py", case.py_suite] if case.py_suite
                  else ["--suites", ",".join(case.suite_files)])
    args = [
        "--host-files", ",".join(case.host_files),
        "--scheme-files", ",".join(case.scheme_files),
        *suite_args,
        "--host-name", "cam",
        "-o", out_dir,
        "--tempdir", os.path.join(out_dir, "tmp"),
        "--emit-datatable", os.path.join(out_dir, "ccpp_datatable.xml"),
        "--emit-resolved-vars", os.path.join(out_dir, "resolved_vars.json"),
        "--legacy-mode",
        "--cam-host",
        "--framework-src-dir", case.framework_src_dir,
        "--kind-map", "r8:REAL64",
    ]
    if case.preproc_defs:
        args.append("--preproc-defs=" + ",".join(case.preproc_defs))
    if case.package_caps:
        args.append("--package-caps")
    if case.directive:
        args += ["--directive", case.directive]
    return args


def generator_options(case: CamCase) -> dict:
    """The same inputs as ccppMain options, for in-process use."""
    options = {
        "scheme_files": list(case.scheme_files),
        "host_files": list(case.host_files),
        "host_name": "cam", "capgen_api": True, "legacy_mode": True,
        "framework_src_dir": case.framework_src_dir,
        "kind_map": ["r8:REAL64"], "verbose": 0,
    }
    if case.directive:
        options["directive"] = case.directive
    return options
