import argparse
import contextlib
import dataclasses
import io
import json
import os
import shlex
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

from xdsl.parser import Parser
from xdsl.printer import Printer

from xdsl_ccpp.dialects.ccpp import (
    ArgumentOp,
    ArgumentTableOp,
    TablePropertiesOp,
    TableTypeKind,
)
from xdsl_ccpp.frontend.ccpp_xml import ccppXML, parse_meta_file
from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
from xdsl_ccpp.util.ccpp_conventions import (
    deprecation_records_discarded,
    report_deprecated_uses,
    set_legacy_mode,
    set_verbosity,
)
from xdsl_ccpp.util.errors import report_input_errors
from xdsl_ccpp.util.options_db import coerce_list_option


def _validate_fortran_source(meta_path: str, f90_path: str, preproc_defs) -> str:
    """Compare one scheme's .meta file with its paired .F90 and return what
    that printed to stderr (the mismatch warnings), so the comparisons can
    run in worker processes and still be printed in file order."""
    from xdsl_ccpp.tools.ccpp_validate_source import _load_meta_file
    from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_file
    from xdsl_ccpp.transforms.validate_source import compare_modules

    err = io.StringIO()
    # The frontend reports the .meta files' deprecated standard names.
    with contextlib.redirect_stderr(err), deprecation_records_discarded():
        meta_module = _load_meta_file(meta_path)
        if meta_module is None:
            return err.getvalue()  # host/module-type .meta, or failed to load (already warned)
        try:
            source_module = build_meta_module_from_file(f90_path, preproc_defs)
        except Exception as exc:
            print(
                f"Warning: fparser2 failed to parse '{f90_path}' for "
                f"Fortran-vs-.meta validation: {exc}",
                file=sys.stderr,
            )
            return err.getvalue()
        for mismatch in compare_modules(meta_module, source_module):
            print(f"Warning: {mismatch}", file=sys.stderr)
    return err.getvalue()


class CcppDslError(Exception):
    """Raised for any ccpp_dsl.py pipeline failure. Catchable by an
    in-process caller (e.g. ccppMain().run()); main() is the only place
    that converts this to a printed message and a process exit."""

    def __init__(self, message, returncode=1):
        super().__init__(message)
        self.returncode = returncode


@dataclasses.dataclass(frozen=True)
class CcppDslResult:
    """Return value of `ccppMain.run()` on success.

    written -- list[str], the per-file section names `split_fortran_output`
    produced (its own existing return value, unchanged).

    datatable_path -- str | None, set iff `--emit-datatable`/
    options_db["emit_datatable"] was configured; None otherwise.

    resolved_vars -- dict | None, the exact {"phases": ..., optionally
    "host_vars": ...} dict suite_cap.py's `_write_resolved_vars` already
    serializes to the `--emit-resolved-vars` JSON file, read back
    in-process -- iff emit_resolved_vars was configured; None otherwise.
    Never an empty dict: None unambiguously means "caller didn't ask".
    """

    written: list
    datatable_path: "str | None" = None
    resolved_vars: "dict | None" = None


class ccppMain:
    # (frontend MLIR file, its parsed module), see _parse_frontend.
    _frontend = None

    def initialise_argument_parser(self):
        parser = argparse.ArgumentParser(description="xDSL CCPP DSL compiler flow")
        self.set_parser_arguments(parser)
        return parser

    def default_options_db(self) -> dict:
        """Return this tool's CLI defaults as a plain dict.

        Same key set `build_options_db_from_args` produces, minus its
        required-argument validation and the comma-string -> list
        splitting for `--suites`/`--scheme-files`/`--host-files` (those
        come back as `None` here, not `[]`) -- callers that already have
        real lists for those three (e.g. `ccpp_prebuild.py`, which derives
        them from a host model's `ccpp_prebuild_config.py`) overlay their
        own values on top instead.

        Single source of truth for any tool that drives `ccppMain`
        programmatically rather than through `main()`'s own CLI parsing --
        extracted after a codebase audit found `ccpp_prebuild.py`'s own
        hand-built `options_db` dict was already missing 9 keys this
        parser supports (`py`, `directive`,
        `kind_map`, `emit_datatable`, `no_memory_space_warning`,
        `emit_html`, `emit_resolved_vars`, `bind_c`, `legacy_mode`), with
        nothing to flag it the next time a key is added here. Building
        from this instead means `ccpp_prebuild.py` can no longer silently
        drop a key -- new options just carry their real default forward.
        """
        return vars(self.initialise_argument_parser().parse_args([]))

    def set_parser_arguments(self, parser):
        parser.add_argument(
            "--suites",
            help="Comma-separated list of suite XML files",
        )
        parser.add_argument(
            "--py",
            default=None,
            help="Python frontend file (replaces --suites); executed with python3 to produce MLIR",
        )
        parser.add_argument(
            "--scheme-files",
            help="Comma-separated list of .meta scheme files",
        )
        parser.add_argument(
            "--host-files",
            default=None,
            help="Comma-separated list of .meta host model files",
        )
        parser.add_argument(
            "-o",
            "--out",
            default=".",
            help="Output directory for generated .F90 files (default: current directory)",
        )
        parser.add_argument(
            "--stdout",
            action="store_true",
            help="Write generated Fortran to stdout instead of .F90 files",
        )
        parser.add_argument(
            "--host-name",
            default=None,
            help="Override the CamelCase host name prefix for generated subroutines "
            "(e.g. 'HelloWorld'); derived from the suite name when not set",
        )
        parser.add_argument(
            "-t",
            "--tempdir",
            default="tmp",
            help="Temporary directory for intermediate files (default: 'tmp')",
        )
        parser.add_argument(
            "-d",
            "--debug",
            action="store_true",
            help="Keep temporary files after compilation (do not clean up)",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            type=int,
            choices=[0, 1, 2],
            default=1,
            help="Verbosity level: 0=quiet, 1=normal, 2=detailed (default: 1)",
        )
        parser.add_argument(
            "--directive",
            default=None,
            choices=["acc", "omp"],
            help="GPU directive style: 'acc' for OpenACC, 'omp' for OpenMP "
                 "target offload. When omitted, no GPU data movement directives "
                 "are generated regardless of memory_space attributes.",
        )
        parser.add_argument(
            "--gpu-debug-prints",
            action="store_true",
            default=False,
            help="Instrument every generated GPU data-movement operation "
                 "(update self/device, copyin, copyout) and every module-scope "
                 "scalar with a host-vs-device diagnostic print, to debug "
                 "OpenACC PRESENT/residency failures directly from a run "
                 "instead of reasoning from source alone. Debug-only; has no "
                 "effect unless --directive is also set.",
        )
        parser.add_argument(
            "--gpu-debug-sync",
            action="store_true",
            default=False,
            help="Emit an extra `update self(...)` immediately after every "
                 "scheme call that writes a memory_space=device variable "
                 "(HostMatched, CapScratch, or SuiteOwned), regardless of "
                 "whether that variable's residency treatment otherwise "
                 "needs one. Mirrors host memory to the just-computed "
                 "device value moments after it's produced, so a "
                 "device-blind host-memory debugger reads a live, correct "
                 "value at any breakpoint. Debug-only; has no effect unless "
                 "--directive is also set.",
        )
        parser.add_argument(
            "--capture-scheme",
            action="append",
            default=[],
            metavar="SCHEME[:PHASE]",
            help="Opt-in: instrument every call to SCHEME (optionally restricted "
                 "to one lifecycle PHASE, e.g. 'kessler:run'; omit ':PHASE' to "
                 "capture every phase) with calls into the ccpp_capture_mod "
                 "runtime library, dumping each input/output argument to disk. "
                 "For building data-driven, scheme-level regression tests from "
                 "realistic captured atmospheric states -- not a debugging aid "
                 "and not compared against CAM's own history-file output. May "
                 "be repeated for multiple scheme/phase targets. Deliberately "
                 "skips DDT-typed, errmsg/errflg, and optional arguments (v1 "
                 "scope -- see scheme_io_capture_pass.py).",
        )
        parser.add_argument(
            "--capture-test-driver-dir",
            default=None,
            metavar="DIR",
            help="Only meaningful together with --capture-scheme: for every "
                 "matched scheme call site, additionally write a standalone "
                 "Fortran test-driver program "
                 "(test_<table_name>.F90) into DIR that reads a captured "
                 "fixture back, calls the real scheme subroutine, and "
                 "compares its outputs against the captured 'after' "
                 "snapshot -- for building data-driven, scheme-level "
                 "regression tests. Source only; no CMake/ctest wiring is "
                 "generated.",
        )
        parser.add_argument(
            "--capture-tolerance",
            type=float,
            default=None,
            metavar="VALUE",
            help="Only meaningful together with --capture-scheme: the "
                 "absolute tolerance the generated test driver's real-valued "
                 "comparisons use, overriding the built-in default "
                 "(1.0e-10). Uniform across every real-valued comparison in "
                 "the generated driver -- there is no per-variable override "
                 "in v1. Useful once this is applied beyond a scheme with "
                 "kessler-like deterministic math to a noisier one, where a "
                 "single global default is either too tight (spurious "
                 "FAILs) or too loose (misses a real regression).",
        )
        parser.add_argument(
            "--kind-map",
            action="append",
            default=[],
            metavar="KIND:ISO",
            help="Extra kind-to-ISO mapping, e.g. kind_dyn:REAL32.  "
                 "May be repeated for multiple mappings.  "
                 "Supplements the built-in CCPP_KIND_TO_ISO table for this run only.",
        )
        parser.add_argument(
            "--emit-datatable",
            default=None,
            metavar="FILE",
            help="Write a datatable.xml to this path after generating caps.  "
                 "Records generated .F90 file paths, scheme entry points, "
                 "suite call structure, and variable metadata.",
        )
        parser.add_argument(
            "--no-memory-space-warning",
            action="store_true",
            default=False,
            help="Suppress the warning emitted when memory_space attributes are "
                 "present but --directive is not set.",
        )
        parser.add_argument(
            "--emit-html",
            default=None,
            metavar="DIR",
            help="Write per-entry-point HTML variable tables into this directory "
                 "(requires --emit-datatable).",
        )
        parser.add_argument(
            "--emit-resolved-vars",
            default=None,
            metavar="FILE",
            help="Write a JSON file of the resolved variables required at each "
                 "CCPP lifecycle phase (register/initialize/finalize/"
                 "timestep_initial/timestep_final/run), including host-variable "
                 "binding and dimension info.",
        )
        parser.add_argument(
            "--bind-c",
            action="store_true",
            default=False,
            help="Generate BIND(C) Fortran cap subroutines and matching C++ headers "
                 "(<HostName>_ccpp_cap.h and ccpp_kinds.h). Requires a host file.",
        )
        parser.add_argument(
            "--capgen-api", "--cam-host",
            dest="capgen_api",
            action="store_true",
            default=False,
            help="Also generate original capgen's host API in the ccpp_cap module "
                 "(<host>_ccpp_physics_* and <host>_ccpp_*_constituents, as "
                 "CAM-SIMA calls them), on top of the default capgen-v1 API. The "
                 "wrappers read errmsg/errcode and col_start/col_end from the "
                 "host's module variables rather than receiving them as dummy "
                 "arguments. --cam-host is the former name.",
        )
        parser.add_argument(
            "--framework-src-dir",
            default="",
            metavar="DIR",
            help="Path to a ccpp_framework/src directory (CAM-SIMA's own). When "
                 "given, its framework F90 files (ccpp_hashable.F90, "
                 "ccpp_hash_table.F90, ccpp_constituent_prop_mod.F90, "
                 "ccpp_scheme_utils.F90) are listed in the datatable utility "
                 "files instead of the bundled xdsl_ccpp copies.",
        )
        parser.add_argument(
            "--legacy-mode",
            action="store_true",
            default=False,
            help="Accept deprecated standard names (currently: horizontal_loop_extent) "
                 "with a warning instead of rejecting them. Off by default, matching "
                 "capgen-v1's own --legacy-mode flag. Every example in this repo has "
                 "already migrated off these names; only pass this for host models "
                 "still using the deprecated convention.",
        )
        parser.add_argument(
            "--preproc-defs",
            default=None,
            help="Comma-separated list of C-preprocessor defines (e.g. "
                 "'SPMD,NP=4,_MPI', each entry optionally '-D'-prefixed), "
                 "matching CAM_CONFIG_OPTS-style tokens. Applied only to the "
                 "Fortran-vs-.meta cross-validation phase (see "
                 "validate_fortran_sources): resolves #ifdef/#if conditional "
                 "compilation in each scheme's paired .F90 before comparing "
                 "its real signature against the .meta file, mirroring "
                 "capgen-v1's own check_fortran_against_metadata. Currently "
                 "warn-only -- mismatches are reported, never fatal.",
        )
        parser.add_argument(
            "--jobs",
            type=int,
            default=1,
            help="Number of processes for the Fortran-vs-.meta cross-validation "
                 "(see --preproc-defs), which fparser2-parses every scheme's "
                 ".F90 and is most of the generation time. A build system "
                 "passes its own parallelism (CAM-SIMA: GMAKE_J). Output is "
                 "the same for any value.",
        )
        parser.add_argument(
            "--list-outputs",
            action="store_true",
            default=False,
            help="Print the comma-joined list of output filenames this "
                 "invocation's arguments would produce, then exit -- without "
                 "running suite-cap/ccpp-cap codegen or the Fortran/C++ "
                 "printers. Cheap enough to call once per example at CMake "
                 "configure time (cmake-configure-regen's Part A): a single "
                 "source of truth for the filenames several examples' "
                 "CMakeLists.txt currently predict by hand.",
        )
        parser.add_argument(
            "--list-dependencies",
            action="store_true",
            default=False,
            help="Print the comma-joined list of extra compiled dependency "
                 "files (a scheme/host .meta's own dependencies/"
                 "dependencies_path keys -- e.g. temp_kinds.F90) this "
                 "invocation's arguments declare, then exit -- the same "
                 "list --emit-datatable's own <dependencies> section would "
                 "produce, but without running a real generation. Sibling "
                 "to --list-outputs (cmake-configure-regen's Part B): lets "
                 "CMake predict CCPP_DEPENDENCIES_LIST at configure time "
                 "even once the real generation is deferred to build time.",
        )
        parser.add_argument(
            "--package-caps",
            action="store_true",
            default=False,
            help="Generate one Fortran module per package (<package>_package_cap) "
                 "instead of flattening packages into the suite cap "
                 "(composite-scheme 2f; experimental).",
        )
        parser.add_argument(
            "--list-package-scope",
            action="store_true",
            default=False,
            help="Print, for each package in a --py suite (@<package>.entry_point "
                 "composites), which standard names are private to it and why "
                 "each other name it touches is public, then exit -- without "
                 "generating code (composite-scheme Stage 2; see "
                 "transforms/package_scope.py).",
        )
        parser.add_argument(
            "--gfs-dim-aliases",
            action="store_true",
            default=False,
            help="Treat GFS-physics vertical-axis standard names "
                 "(adjusted_vertical_layer_dimension_for_radiation, "
                 "vertical_composition_dimension) as equivalent to "
                 "vertical_layer_dimension during host/scheme dimension matching "
                 "only -- never a rename, each name still stands alone as its own "
                 "control variable elsewhere. Off by default, matching capgen-v1's "
                 "own --gfs-dim-aliases flag.",
        )
    def build_options_db_from_args(self, args):
        return self._normalize_options_db(args.__dict__)

    def _normalize_options_db(self, options_db):
        """Validate + coerce a raw options_db dict in place and return it.

        Applies the same required-argument validation and list/comma-string
        coercion `build_options_db_from_args` always has, whether the dict
        came from argparse's own `Namespace.__dict__` or a caller-supplied
        dict passed straight to `run(options_db=...)` -- so a programmatic
        caller following the documented default_options_db() + overlay
        pattern gets the exact same normalization (e.g. host_files=None,
        a valid "I have no host files" config, becomes [] here) instead of
        crashing downstream the moment something does `list(...)` on it.
        """
        if "cam_host" in options_db:  # the former name of capgen_api
            options_db["capgen_api"] = (options_db.get("capgen_api")
                                        or options_db.pop("cam_host"))
        if options_db.get("py"):
            # --py mode: --suites and --scheme-files are not required
            if options_db.get("suites"):
                raise ValueError("--py and --suites are mutually exclusive")
        else:
            if not options_db.get("suites"):
                raise ValueError("--suites is required (or use --py)")
            if not options_db.get("scheme_files"):
                raise ValueError("--scheme-files is required")

        # coerce_list_option() accepts either a comma-joined string (the
        # CLI contract -- stripping each entry so a space after a comma,
        # e.g. "a.meta, b.meta", doesn't silently become a path with a
        # leading space, failing to open with a confusing error rather than
        # being tolerated the way most CLI tools handle incidental
        # whitespace) or an already-real Python list (capgen-v1's own
        # contract for these fields, for a caller building options_db
        # programmatically rather than through argparse).
        options_db["suites"] = coerce_list_option(options_db.get("suites"))
        options_db["scheme_files"] = coerce_list_option(options_db["scheme_files"])
        options_db["host_files"] = coerce_list_option(options_db["host_files"])
        options_db["preproc_defs"] = [
            p for p in coerce_list_option(options_db.get("preproc_defs")) if p
        ]
        options_db["jobs"] = int(options_db.get("jobs") or 1)
        if options_db["jobs"] < 1:
            raise ValueError("--jobs must be at least 1")

        all_inputs = (
            options_db["suites"] + options_db["scheme_files"] + options_db["host_files"]
        )
        if options_db.get("py"):
            all_inputs.append(options_db["py"])
        for f in all_inputs:
            if not os.path.exists(f):
                raise FileNotFoundError(f"Input file not found: '{f}'")

        return options_db

    def print_verbose_message(self, *messages):
        level = self.options_db["verbose"]
        if level == 1:
            print(messages[0])
        elif level == 2:
            print(messages[1] if len(messages) > 1 else messages[0])

    def post_stage_check(self, path):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise CcppDslError(f"expected output '{path}' was not created")
        if self.options_db["verbose"] >= 1:
            print(f"  -> Completed, results in '{path}'")

    def remove_file_if_exists(self, *paths):
        for path in paths:
            if os.path.exists(path):
                os.remove(path)

    def run_pipeline_stage(self, cmd, out_path, label):
        """Run one pipeline subprocess, redirecting its stdout to out_path.

        cmd -- an argv list, never a shell string: the pipeline stages
        this backs (run_frontend/run_py_frontend/run_opt -- the latter
        now also covers what used to be a separate generate_cpp_headers
        stage, folded into one combined "ftn_and_cpp_header" pipeline
        target instead of a second subprocess, see cpp-dual-print-
        pipeline) used to build an interpolated shell command string for
        os.system(), which breaks on any path containing quotes or shell
        metacharacters and duplicated the same "build cmd -> verbose-log
        -> execute" shape repeatedly. subprocess.run([...])
        with an explicit stdout redirect closes both gaps at once, matching
        the pattern used elsewhere in this same tools/ directory.

        label -- short, human-readable stage name (e.g. "Running CCPP
        frontend"), matching each call site's own prior print_verbose_message
        short-form text exactly; the long (verbose=2) form is derived from it.

        Only stdout is redirected to out_path (matching each stage's own
        prior `> "{out}"` shell redirection) -- stderr is left to inherit
        this process's own, exactly as it did under os.system(), so a
        subprocess crash's traceback still surfaces directly to the
        caller's terminal instead of being silently captured.

        Exits with a clear CLI error message (no raw Python traceback) if
        the command can't be found, or if it runs but exits non-zero --
        found by Copilot review on PR #91: the first version of this
        helper (from task #62's original os.system -> subprocess.run
        migration) captured neither case, so a failing stage could leave
        out_path holding partial/corrupted content that a downstream
        os.path.getsize(out_path) > 0 check (post_stage_check, or
        apply()'s own "no BIND(C) functions found" check after
        split_fortran_output) would wrongly treat as success, and a
        missing executable would
        surface as an uncaught FileNotFoundError instead -- os.system()
        never raised that, it always went through a shell that printed
        its own "command not found" and returned a status this code
        never checked either, so this failure mode is genuinely new here,
        not merely inherited.

        Does not itself validate out_path's own content beyond the
        command's exit status -- callers that expect out_path to always
        be non-empty on success call self.post_stage_check(out_path)
        afterward. run_opt always does this unconditionally now (for
        either the "ftn" or combined "ftn_and_cpp_header" target): the
        Fortran sections are always present even when there is no
        BIND(C) content, so the combined output is never empty on a
        successful run -- "no BIND(C) functions found" is reported
        separately by apply(), after split_fortran_output, not treated
        as a stage failure here.
        """
        self.finish_pipeline_stage(self.start_pipeline_stage(cmd, out_path, label))

    def start_pipeline_stage(self, cmd, out_path, label):
        """Start run_pipeline_stage's subprocess without waiting for it;
        finish_pipeline_stage (or kill_pipeline_stage) takes the handle."""
        self.print_verbose_message(
            label,
            f'{label} with command: {shlex.join(cmd)} > "{out_path}"',
        )
        out_f = open(out_path, "w")
        try:
            proc = subprocess.Popen(cmd, stdout=out_f, stderr=None)
        except FileNotFoundError:
            out_f.close()
            raise CcppDslError(f"could not execute '{cmd[0]}'") from None
        return proc, out_f, label

    @staticmethod
    def finish_pipeline_stage(stage) -> None:
        """Wait for start_pipeline_stage's subprocess; raise CcppDslError if
        it exited non-zero."""
        proc, out_f, label = stage
        returncode = proc.wait()
        out_f.close()
        if returncode != 0:
            raise CcppDslError(
                f"{label.lower()} failed (exit code {returncode})",
                returncode=returncode,
            )

    @staticmethod
    def kill_pipeline_stage(stage) -> None:
        """Stop start_pipeline_stage's subprocess (run() failed)."""
        proc, out_f, _ = stage
        proc.kill()
        proc.wait()
        out_f.close()

    def run_frontend(self, tmp_dir):
        suites_arg = ",".join(self.options_db["suites"])
        mlir_out = os.path.join(tmp_dir, "ccpp.mlir")

        cmd = [sys.executable, "-m", "xdsl_ccpp.frontend.ccpp_xml", "--suites", suites_arg]
        if self.options_db["scheme_files"]:
            cmd += ["--scheme-files", ",".join(self.options_db["scheme_files"])]
        # Mirror capgen-v1 (ccpp_capgen.py:646): auto-include the bundled
        # ccpp_constituent_prop_mod.meta so callers never have to pass it.
        host_files = list(self.options_db["host_files"])
        _const_meta = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "framework_src",
                         "ccpp_constituent_prop_mod.meta")
        )
        if os.path.isfile(_const_meta) and _const_meta not in host_files:
            host_files.append(_const_meta)
        if host_files:
            cmd += ["--host-files", ",".join(host_files)]
        if self.options_db.get("legacy_mode"):
            cmd.append("--legacy-mode")
        cmd += ["--verbose", str(self.options_db["verbose"])]

        self.run_pipeline_stage(cmd, mlir_out, "Running CCPP frontend")
        self.post_stage_check(mlir_out)
        return mlir_out

    def run_py_frontend(self, tmp_dir):
        py_file = self.options_db["py"]
        mlir_out = os.path.join(tmp_dir, "ccpp.mlir")

        cmd = [sys.executable, py_file]
        if self.options_db.get("legacy_mode"):
            # py_api.py has no argparse of its own (it's the user's own
            # script); it scans sys.argv for this token directly, mirroring
            # ccpp_param()'s existing sys.argv-scanning convention.
            cmd.append("--legacy-mode")
        cmd.append(f"--verbose={self.options_db['verbose']}")

        self.run_pipeline_stage(cmd, mlir_out, "Running Python frontend")
        self.post_stage_check(mlir_out)
        return mlir_out

    def merge_meta_files(self, mlir_file):
        """Append ``ccpp.table_properties`` from scheme/host .meta files into *mlir_file*.

        Used in ``--py`` mode to merge ``--scheme-files``/``--host-files``
        metadata into the MLIR produced by the Python frontend.  Mirrors
        run_frontend()/ccpp_xml.py exactly, so a Python suite given the same
        files generates the same caps as the equivalent XML suite: each table
        records its file stem as ``source_module``, and the bundled
        ccpp_constituent_prop_mod.meta is always included as a host file.
        """
        from pathlib import Path

        scheme_files = self.options_db["scheme_files"]
        host_files = list(self.options_db["host_files"])
        _const_meta = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "framework_src",
                         "ccpp_constituent_prop_mod.meta")
        )
        if os.path.isfile(_const_meta) and _const_meta not in host_files:
            host_files.append(_const_meta)
        if not scheme_files and not host_files:
            return

        self.print_verbose_message(
            "Merging .meta file metadata",
            f"Merging .meta metadata from {len(scheme_files)} scheme + {len(host_files)} host files into '{mlir_file}'",
        )

        ctx = make_ccpp_context()
        with open(mlir_file) as f:
            ccpp_module = Parser(ctx, f.read()).parse_op()

        frontend = ccppXML()
        count = 0
        for scheme_file in scheme_files:
            for meta in parse_meta_file(scheme_file, True):
                prop = frontend.build_meta_ir(meta, source_module=Path(scheme_file).stem,
                                              meta_file_path=scheme_file)
                ccpp_module.body.block.add_op(prop)
                count += 1
        for host_file in host_files:
            for meta in parse_meta_file(host_file, False):
                prop = frontend.build_meta_ir(meta, source_module=Path(host_file).stem,
                                              meta_file_path=host_file)
                ccpp_module.body.block.add_op(prop)
                count += 1

        with open(mlir_file, "w") as f:
            Printer(stream=f).print_op(ccpp_module)
            f.write("\n")
        report_deprecated_uses()

        self.print_verbose_message(
            f"  -> Merged {count} table_properties block(s)",
        )

    def validate_fortran_sources(self) -> None:
        """Cross-validate each scheme's .meta file against its real Fortran
        signature, mirroring capgen-v1's own check_fortran_against_metadata.

        For every --scheme-files entry, look for a paired .F90 (same stem,
        same directory -- the same convention xdsl_ccpp/tools/
        ccpp_validate_source.py already uses), extract its real subroutine
        signatures via fparser2 (fparser2_to_meta.py), applying --preproc-defs
        first (fortran_preprocess.py -- fparser itself has no CPP-evaluation
        capability), and compare against the .meta-declared signature via
        validate_source.compare_modules.

        Diagnostic only, currently warn-only: mismatches are printed to
        stderr, never raised, and any failure to load or parse a given
        pair is itself just a printed warning. This
        phase is not required for cap generation to succeed, and silently
        does nothing if fparser is not installed.

        With --jobs N the pairs are compared in N processes (the fparser2
        parse is most of a generation's time); the warnings are printed in
        file order either way. run() starts the check before the frontend
        and finishes it after ccpp_opt, so with --jobs N it overlaps them.
        """
        self._finish_fortran_check(self._start_fortran_check())

    def _start_fortran_check(self):
        """Start validate_fortran_sources' comparisons; return the handle
        _finish_fortran_check takes: (pool or None, per-pair reports or
        futures). With one job the comparisons run here, serially."""
        try:
            import fparser.two.Fortran2003  # noqa: F401
        except ImportError:
            return None, []

        from xdsl_ccpp.transforms.fortran_preprocess import parse_preproc_defines

        preproc_defs = parse_preproc_defines(self.options_db.get("preproc_defs"))

        pairs = []
        for meta_path in self.options_db.get("scheme_files") or []:
            stem = os.path.splitext(os.path.basename(meta_path))[0]
            f90_path = os.path.join(
                os.path.dirname(os.path.abspath(meta_path)), f"{stem}.F90"
            )
            if os.path.isfile(f90_path):
                pairs.append((meta_path, f90_path))

        jobs = min(self.options_db.get("jobs") or 1, len(pairs))
        if jobs <= 1:
            return None, [_validate_fortran_source(m, f, preproc_defs) for m, f in pairs]
        pool = ProcessPoolExecutor(max_workers=jobs)
        # Largest sources first: the slowest file bounds the wall time.
        order = sorted(range(len(pairs)), key=lambda i: -os.path.getsize(pairs[i][1]))
        futures = {
            i: pool.submit(_validate_fortran_source, *pairs[i], preproc_defs)
            for i in order
        }
        return pool, [futures[i] for i in range(len(pairs))]

    @staticmethod
    def _finish_fortran_check(handle) -> None:
        """Wait for _start_fortran_check's comparisons and print their
        warnings in --scheme-files order."""
        pool, reports = handle
        try:
            for report in reports:
                sys.stderr.write(report if pool is None else report.result())
        finally:
            if pool is not None:
                pool.shutdown(cancel_futures=True)

    @staticmethod
    def _cancel_fortran_check(handle) -> None:
        """Abandon _start_fortran_check's comparisons (run() failed)."""
        pool, _ = handle
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    def _check_memory_space_mismatch(self, mlir_file: str) -> None:
        """Warn when memory_space annotations exist but --directive is not set.

        Before any pass runs, all TablePropertiesOp are flat children of the
        top-level builtin.module.  Walk them to collect args with memory_space
        set and emit a single warning if --directive was omitted.
        """
        if self.options_db.get("directive"):
            return
        if self.options_db.get("no_memory_space_warning"):
            return

        top_module = self._parse_frontend(mlir_file)

        scheme_vars: list[str] = []
        host_vars: list[str] = []

        for op in top_module.body.block.ops:
            if not isinstance(op, TablePropertiesOp):
                continue
            is_scheme = op.table_type.data == TableTypeKind.Scheme
            for arg_table_op in op.body.ops:
                if not isinstance(arg_table_op, ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isinstance(arg_op, ArgumentOp):
                        continue
                    if arg_op.memory_space is None:
                        continue
                    name = (
                        arg_op.standard_name.data
                        if arg_op.standard_name is not None
                        else arg_op.arg_name.data
                    )
                    entry = f"{name} ({arg_op.memory_space.data})"
                    if is_scheme:
                        scheme_vars.append(entry)
                    else:
                        host_vars.append(entry)

        if scheme_vars or host_vars:
            print(
                "Warning: memory_space attributes are set but --directive is not; "
                "GPU data movement directives will not be generated.",
                file=sys.stderr,
            )
            if scheme_vars:
                print(
                    f"  Scheme variables with memory_space: {', '.join(scheme_vars)}",
                    file=sys.stderr,
                )
            if host_vars:
                print(
                    f"  Host variables with memory_space:   {', '.join(host_vars)}",
                    file=sys.stderr,
                )
            print(
                "  Pass --directive acc or --directive omp to generate GPU data movement directives.",
                file=sys.stderr,
            )

    def _host_lang_cpp(self) -> bool:
        """Return True if any host meta file declares ``language = c++``."""
        if not hasattr(self, "_host_lang_cpp_cache"):
            self._host_lang_cpp_cache = self._compute_host_lang_cpp()
        return self._host_lang_cpp_cache

    def _compute_host_lang_cpp(self) -> bool:
        for path in self.options_db.get("host_files") or []:
            try:
                with open(path) as f:
                    in_table_props = False
                    for line in f:
                        stripped = line.strip()
                        if stripped == "[ccpp-table-properties]":
                            in_table_props = True
                        elif stripped.startswith("["):
                            in_table_props = False
                        elif in_table_props:
                            key, _, val = stripped.partition("=")
                            if key.strip() == "language" and val.strip() == "c++":
                                return True
            except OSError:
                pass
        return False

    def _build_pipeline(self) -> str:
        """Build and return the comma-joined pass pipeline string."""
        bind_c = self.options_db.get("bind_c", False) or self._host_lang_cpp()
        ccpp_cap_pass = "generate-ccpp-cap"
        cap_opts: list[str] = []
        if self.options_db.get("host_name"):
            cap_opts.append(f"host_name={self.options_db['host_name']}")
        if bind_c:
            cap_opts.append("bind_c=true")
        if self.options_db.get("capgen_api"):
            cap_opts.append("capgen_api=true")
        if cap_opts:
            ccpp_cap_pass += "{" + " ".join(cap_opts) + "}"
        directive = self.options_db.get("directive")
        meta_kinds_pass = "generate-meta-kinds"
        kind_maps = self.options_db.get("kind_map") or []
        if kind_maps:
            if len(kind_maps) > 1:
                print(
                    "Warning: only the first --kind-map entry is used; "
                    "multiple extra kinds are not yet supported.",
                    file=sys.stderr,
                )
            k, iso = kind_maps[0].split(":", 1)
            meta_kinds_pass += f"{{extra_kind={k.strip()} extra_iso={iso.strip()}}}"
        suite_cap_pass = "generate-suite-cap"
        suite_cap_opts: list[str] = []
        resolved_vars_path = self.options_db.get("emit_resolved_vars")
        if resolved_vars_path:
            # Quoted: xdsl's own pass-pipeline spec lexer
            # (xdsl.utils.parse_pipeline's STRING_LIT token) doesn't accept
            # an unquoted '/' in an arg value, and paths need it. Plain "
            # (not \") is correct now: task #62 moved run_opt()/
            # generate_cpp_headers() from os.system() to subprocess.run()
            # with an argv list, so this whole pipeline string is passed as
            # one opaque argument with no shell re-parsing in between --
            # previously it needed \" specifically because the pipeline
            # string was itself embedded inside a double-quoted shell
            # argument (-p "{pipeline}"), and the shell was relied on to
            # unescape \" into a literal " before ccpp_opt.py's own lexer
            # ever saw it. Passing \" straight through now (no shell to
            # strip it) would reach that lexer as literal backslash-quote,
            # which its own STRING_LIT regex doesn't accept as a delimiter.
            suite_cap_opts.append(f'emit_resolved_vars="{resolved_vars_path}"')
        if self.options_db.get("gpu_debug_sync"):
            suite_cap_opts.append("debug_sync=true")
        if suite_cap_opts:
            suite_cap_pass += "{" + " ".join(suite_cap_opts) + "}"

        has_host = bool(self.options_db.get("host_files"))
        # Packages' private standard names are scoped while the package
        # boundaries are still in the IR (S2-2), then composite schemes
        # (@ccpp_composite / package entry points in the Python frontend) are
        # inlined before any other pass, so everything downstream sees the
        # same flat suite it always has (composite_scheme_plan.md §11, S2-1).
        # Both are no-ops for suites without composites, including every XML
        # suite.
        passes = ["scope-packages"]
        if self.options_db.get("package_caps"):
            passes.append("lower-packages")
        passes += ["flatten-composites", "generate-meta-cap"]
        if has_host:
            host_match_pass = "generate-host-match"
            if self.options_db.get("gfs_dim_aliases"):
                host_match_pass += "{gfs_dim_aliases=true}"
            passes.append(host_match_pass)
        # Ownership classification pass: computes the
        # SuiteOwned/HostMatched/CapScratch/Block ownership classification
        # durably, before any suite's subroutine signature exists. Nothing
        # reads it yet (suite_cap.py/ccpp_cap.py/run_dispatch.py still use
        # their own independent heuristics) -- dual-build only, no observable
        # effect on generated output. Runs unconditionally, even without host
        # metadata: HostMatched simply never triggers in that case, same as
        # generate-host-match's own annotations.
        passes.append("generate-arg-ownership")
        passes.append(meta_kinds_pass)
        passes.append(suite_cap_pass)
        if directive:
            gpu_data_opts = [f"directive={directive}"]
            if self.options_db.get("gpu_debug_sync"):
                gpu_data_opts.append("debug_sync=true")
            passes.append(f"generate-gpu-data{{{' '.join(gpu_data_opts)}}}")
        if has_host:
            passes.append(ccpp_cap_pass)
            # Must run immediately after generate-ccpp-cap and before
            # generate-gpu-ccpp-cap, matching the original behavior where
            # chost generation ran inline at the end of CCPPCAP.apply(),
            # before any subsequent pass could touch the cap module.
            passes.append("generate-cpp-cap")
            if directive:
                passes.append(f"generate-gpu-ccpp-cap{{directive={directive}}}")
        if self.options_db.get("gpu_debug_prints"):
            # Must run after generate-gpu-data/generate-gpu-ccpp-cap above
            # (and generate-suite-cap earlier): it walks the final,
            # fully-resolved set of data-movement ops and module-var
            # declarations, not an intermediate state.
            passes.append("generate-gpu-debug-prints")
        for spec in self.options_db.get("capture_scheme") or []:
            # One pass instance per --capture-scheme entry (not one pass
            # with a packed multi-scheme value): each instance scopes its
            # own call-site walk to its own scheme/phase filter, so
            # multiple entries compose cleanly in sequence, same as how
            # the pipeline already tolerates the same pass name appearing
            # more than once. Must run at the same point
            # generate-gpu-debug-prints does, for the same reason (real
            # KeywordCallOps for every scheme call only exist by here).
            scheme_name, _, phase = spec.partition(":")
            capture_opts = [f"scheme={scheme_name}"]
            if phase:
                capture_opts.append(f"phase={phase}")
            if directive:
                # Needed so the pass knows whether/how to sync a
                # device-resident argument to the host immediately before
                # reading it for capture -- with no --directive, there's
                # no GPU residency to sync in the first place.
                capture_opts.append(f"directive={directive}")
            test_driver_dir = self.options_db.get("capture_test_driver_dir")
            if test_driver_dir:
                # Quoted, not bare: a real path routinely contains "-"/"/"
                # characters the pass-pipeline value lexer's bare IDENT
                # token doesn't accept (confirmed directly -- an
                # unquoted path broke parsing on its first "-"). Escaped
                # per that lexer's own string-literal grammar (only
                # backslash/double-quote need it for a filesystem path).
                escaped = test_driver_dir.replace("\\", "\\\\").replace('"', '\\"')
                capture_opts.append(f'test_driver_dir="{escaped}"')
            tolerance = self.options_db.get("capture_tolerance")
            if tolerance is not None:
                # Quoted, not a bare numeric token: the pass-pipeline
                # value lexer classifies a bare NUMBER token as int vs.
                # float purely by whether "." appears in it -- a value
                # like "1e-08" (no literal ".") would be misparsed as an
                # int() call and crash. A quoted string sidesteps that
                # ambiguity entirely; SchemeIOCapturePass re-parses it
                # with float() on the receiving end, so no precision is
                # lost by round-tripping through str().
                capture_opts.append(f'tolerance="{tolerance}"')
            passes.append(f"generate-scheme-io-capture{{{' '.join(capture_opts)}}}")
        passes += ["generate-kinds", "strip-ccpp"]
        return ",".join(passes)

    def _build_cheap_metadata_module(self):
        """Build the same flat TablePropertiesOp/SuiteOp IR ccpp_xml.py's own
        CLI entry point builds, in-process (no subprocess, no MLIR text
        round-trip) -- the shared starting point for every cheap --list-*
        prediction that needs real IR (as opposed to pure XML/text
        parsing): _predict_kinds_present (needs MetaCAP+MetaKind run on
        top of this) and predict_dependencies (needs nothing further --
        ccpp_datatable.py's own dependency-collection walkers already
        tolerate a bare, pre-MetaCAP module, see predict_dependencies's
        own docstring).

        Always auto-includes the bundled ccpp_constituent_prop_mod.meta,
        mirroring run_frontend()'s own unconditional behavior.
        """
        from pathlib import Path

        from xdsl.dialects import builtin as _builtin

        from xdsl_ccpp.frontend.ccpp_xml import XMLSuite

        if self.options_db.get("py"):
            return self._build_py_metadata_module()

        frontend = ccppXML()
        ir_ops = []
        for suite_file in self.options_db["suites"]:
            ir_ops.append(frontend.build_suite_ir(XMLSuite(suite_file)))
        for scheme_file in self.options_db["scheme_files"]:
            stem = Path(scheme_file).stem
            for meta in parse_meta_file(scheme_file, True):
                ir_ops.append(frontend.build_meta_ir(
                    meta, source_module=stem, meta_file_path=scheme_file))
        host_files = list(self.options_db["host_files"])
        _const_meta = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "framework_src",
                         "ccpp_constituent_prop_mod.meta")
        )
        if os.path.isfile(_const_meta) and _const_meta not in host_files:
            host_files.append(_const_meta)
        for host_file in host_files:
            stem = Path(host_file).stem
            for meta in parse_meta_file(host_file, False):
                ir_ops.append(frontend.build_meta_ir(
                    meta, source_module=stem, meta_file_path=host_file))

        return _builtin.ModuleOp(ir_ops)

    def _build_py_metadata_module(self):
        """``--py`` counterpart of _build_cheap_metadata_module: the exact IR
        real generation starts from (run_py_frontend + merge_meta_files),
        built in a throwaway directory.  The suite script must be executed
        to learn its suites; it does no codegen, so this stays cheap.

        Runs quietly: --list-outputs/--list-dependencies print a
        machine-read list on stdout, which progress messages would corrupt.
        """
        import tempfile

        verbose = self.options_db["verbose"]
        self.options_db["verbose"] = 0
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                mlir_file = self.run_py_frontend(tmp_dir)
                self.merge_meta_files(mlir_file)
                with open(mlir_file) as f:
                    return Parser(make_ccpp_context(), f.read()).parse_op()
        finally:
            self.options_db["verbose"] = verbose

    def _predict_kinds_present(self) -> bool:
        """Return True iff the current --scheme-files/--host-files (plus the
        same bundled ccpp_constituent_prop_mod.meta run_frontend() always
        auto-includes) would cause generate-meta-kinds to emit a ccpp.kinds
        op, i.e. whether ccpp_kinds.F90/.h would be produced.

        Runs the two real passes that decide this (suite_meta.MetaCAP then
        suite_kinds.MetaKind) on top of _build_cheap_metadata_module() --
        reusing their own kind-scanning logic directly rather than a third
        hand-copied mirror of it. Still far cheaper than the full
        pipeline: no generate-suite-cap/generate-ccpp-cap, no Fortran/C++
        printing.
        """
        from xdsl.dialects import builtin as _builtin
        from xdsl.utils.hints import isa

        from xdsl_ccpp.dialects import ccpp
        from xdsl_ccpp.transforms.suite_kinds import MetaKind
        from xdsl_ccpp.transforms.suite_meta import MetaCAP

        module = self._build_cheap_metadata_module()
        ctx = make_ccpp_context()
        MetaCAP().apply(ctx, module)
        MetaKind().apply(ctx, module)

        for sub in module.body.ops:
            if (
                isa(sub, _builtin.ModuleOp)
                and sub.sym_name is not None
                and sub.sym_name.data == "ccpp"
            ):
                return any(isa(op, ccpp.KindsOp) for op in sub.body.ops)
        return False

    def predict_dependencies(self) -> list:
        """Predict --emit-datatable's own <dependencies> section content
        (the exact list CCPP_DEPENDENCIES_LIST in cmake/xdsl_ccpp_capgen.cmake
        is currently built from) cheaply, without a real generation run.
        Powers --list-dependencies.

        ccpp_datatable.py's build_datatable() already tolerates a BARE
        top-level module with no "@ccpp"-named wrapper (confirmed by
        direct read: "if ccpp_mod is None: ccpp_mod = module") -- so
        unlike the ccpp_kinds.F90 gate (which genuinely needs the real
        MetaCAP+MetaKind passes to have run), dependency collection can
        reuse ccpp_datatable.py's own _collect_table_properties/
        _used_scheme_names/_collect_dependencies directly against
        _build_cheap_metadata_module()'s raw, pre-MetaCAP module, with no
        pass execution needed at all for this one.

        Supports --py (via _build_py_metadata_module).
        """
        from xdsl_ccpp.tools.ccpp_datatable import (
            _collect_dependencies,
            _collect_table_properties,
        )

        module = self._build_cheap_metadata_module()
        table_props = _collect_table_properties(module)
        return _collect_dependencies(module, table_props)

    def predict_output_filenames(self) -> list:
        """Predict the list of output filenames this invocation's current
        --suites/--scheme-files/--host-files/--host-name/--bind-c arguments
        would produce, without running suite-cap/ccpp-cap codegen or the
        Fortran/C++ printers. Powers --list-outputs.

        Mirrors, rather than reimplements, each real naming/gating rule:
        - suite cap: suite_cap.py's own "<suite_name>_cap" module-naming
          convention (ModuleOp sym_name -> "<sym_name>.F90",
          print_ftn.py's print_to_ftn), suite_name read directly from each
          suite XML's own <suite name=...> attribute (XMLSuite, no codegen
          needed).
        - host cap: ccpp_cap.py's derive_camel_case_name (shared via
          cap_shared.py) + "_ccpp_cap" -- gated on has_host (--host-files
          non-empty), matching _build_pipeline's own has_host gate around
          generate-ccpp-cap: a valid host-less invocation (suites +
          scheme-files only) produces no host cap at all. Copilot review
          on PR #132 -- no wired-in example exercises a host-less
          invocation, so Part A's own byte-for-byte verification against
          all 24 real generation calls never exercised this path.
        - the main cap's BIND(C) header: emitted whenever bind_c is on
          (--bind-c or _host_lang_cpp()) -- generate-ccpp-cap marks every
          generated lifecycle function bind_c=true unconditionally in that
          case (ccpp_cap.py line ~1485), and a suite always contributes at
          least one.
        - chost cap + header + C++ wrapper: gated purely on
          _host_lang_cpp() (cpp_interop.py's CPPInteropCap.apply has the
          same gate, independent of --bind-c), named via the same
          camel_name + "_ccpp_chost_cap"/"_chost" cpp_interop.py itself
          uses (verified by direct regeneration of examples/capgen's and
          examples/kessler's chost/--bind-c calls: both the .F90 Fortran
          side (print_ftn.py, CCPPCHostCapOp) and the .h/.hpp C++ side
          (print_cpp_header.py) are always produced together once that
          gate is true -- no observed case where the wrapper .hpp is
          independently absent).
        - ccpp_kinds.F90/.h: see _predict_kinds_present -- the one rule
          that genuinely needs real IR + two real passes, not pure text/
          XML parsing, but still no suite-cap/ccpp-cap/codegen/printing.

        --py (python frontend): suite names come from running the suite
        script's frontend only (_build_py_metadata_module) -- no codegen.
        """
        from xdsl.utils.hints import isa

        from xdsl_ccpp.dialects.ccpp import SuiteOp
        from xdsl_ccpp.frontend.ccpp_xml import XMLSuite
        from xdsl_ccpp.transforms.util.cap_shared import derive_camel_case_name

        package_names: list = []
        if self.options_db.get("py"):
            from xdsl_ccpp.dialects.ccpp import PackageOp

            module = self._build_py_metadata_module()
            suite_names = [op.suite_name.data for op in module.walk() if isa(op, SuiteOp)]
            if self.options_db.get("package_caps"):
                package_names = [op.package_name.data for op in module.walk()
                                 if isa(op, PackageOp)]
        else:
            suite_names = [
                XMLSuite(f).attributes["name"] for f in self.options_db["suites"]
            ]
        outputs = [f"{name}_cap.F90" for name in suite_names]
        # --package-caps: one module per package (suitecap/package_cap.py).
        outputs += [f"{name}_package_cap.F90" for name in package_names]

        camel_name = (
            self.options_db.get("host_name")
            or derive_camel_case_name(suite_names[0])
        )
        has_host = bool(self.options_db.get("host_files"))
        if has_host:
            outputs.append(f"{camel_name}_ccpp_cap.F90")

        bind_c = bool(self.options_db.get("bind_c")) or self._host_lang_cpp()
        kinds_present = self._predict_kinds_present()
        if kinds_present:
            outputs.append("ccpp_kinds.F90")
        if has_host and bind_c:
            outputs.append(f"{camel_name}_ccpp_cap.h")
            if kinds_present:
                outputs.append("ccpp_kinds.h")

        if self._host_lang_cpp():
            outputs.append(f"{camel_name}_ccpp_chost_cap.F90")
            outputs.append(f"{camel_name}_ccpp_chost_cap.h")
            outputs.append(f"{camel_name}_chost.hpp")

        return outputs

    def run_opt(self, tmp_dir, mlir_in, target: str = "ftn"):
        """Run the pipeline once and print `target` -- "ftn" (default) or
        "ftn_and_cpp_header" (the combined target that prints both from
        the same already-transformed module in one process, used by
        apply() below instead of a second full independent re-parse+
        re-transform subprocess; see ccpp_opt.py's own
        _output_ftn_and_cpp_header for why this is safe). ccpp_prebuild.py
        calls this with the default "ftn" only -- it never wants C++
        header output, so that caller is intentionally unaffected by the
        combined-target path.

        Do NOT call this with target="cpp_header" alone: this method's
        own post_stage_check below unconditionally requires non-empty
        output, but a cpp_header-only run legitimately produces nothing
        when there's no BIND(C)/CHostCapOp content -- a valid, expected
        outcome, not a failure (the old, now-deleted generate_cpp_headers
        handled that case explicitly; this method doesn't, and nothing
        here actually needs "cpp_header" standalone -- only the FileCheck
        goldens invoke that target directly, via ccpp_opt's own CLI, not
        through this method). Copilot PR #110 review, 2026-10-05.
        """
        return self._finish_opt(self._start_opt(tmp_dir, mlir_in, target))

    def _start_opt(self, tmp_dir, mlir_in, target: str = "ftn"):
        """Start run_opt's ccpp_opt subprocess; _finish_opt takes the handle."""
        ftn_out = os.path.join(tmp_dir, "ccpp.ftn")
        pipeline = self._build_pipeline()
        cmd = [
            sys.executable, "-m", "xdsl_ccpp.tools.ccpp_opt", mlir_in,
            "-p", pipeline, "-t", target, "--verbose", str(self.options_db["verbose"]),
        ]
        return self.start_pipeline_stage(cmd, ftn_out, "Running CCPP optimizer"), ftn_out

    def _finish_opt(self, handle) -> str:
        """Wait for _start_opt's subprocess and check its output; return the
        printer output's path."""
        stage, ftn_out = handle
        self.finish_pipeline_stage(stage)
        self.post_stage_check(ftn_out)
        return ftn_out

    def split_fortran_output(self, ftn_file, out_dir) -> list:
        """Split the combined Fortran/C++-header printer output into
        individual files.

        The printer emits sections separated by '// -----', each preceded by a
        '// FILE: <name>' marker (.F90 for Fortran, .h/.hpp for the
        ftn_and_cpp_header combined target's C++ sections). This method
        writes each section as a separate file in out_dir, or prints to
        stdout when --stdout is set. Returns the list of section
        filenames found either way, so a caller can tell whether any of
        a particular kind (e.g. ".h") was actually produced.
        """
        with open(ftn_file) as f:
            content = f.read()

        written: list = []
        sections = content.split("// -----")
        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.splitlines()
            if not lines[0].startswith("// FILE:"):
                continue
            filename = lines[0][len("// FILE:") :].strip()
            body = "\n".join(lines[1:]).lstrip("\n") + "\n"
            written.append(filename)

            if self.options_db["stdout"]:
                print(body)
            else:
                out_path = os.path.join(out_dir, filename)
                with open(out_path, "w") as out_f:
                    out_f.write(body)
                self.print_verbose_message(
                    f"  -> Written '{out_path}'",
                    f"  -> Written '{out_path}' ({len(body)} bytes)",
                )
        return written

    def _parse_frontend(self, mlir_file: str):
        """The frontend module in *mlir_file*, parsed once per run and shared
        by its read-only consumers (the memory-space check, the datatable);
        ccpp_opt parses its own copy in its subprocess."""
        if self._frontend is None or self._frontend[0] != mlir_file:
            with open(mlir_file) as f:
                self._frontend = (mlir_file, Parser(make_ccpp_context(), f.read()).parse_op())
        return self._frontend[1]

    def _run_datatable(self, mlir_file: str, caps_dir: str, datatable_path: str) -> None:
        """Generate datatable.xml (and optionally HTML) from *mlir_file*."""
        from pathlib import Path

        from xdsl_ccpp.tools.ccpp_datatable import (
            build_datatable_from_module,
            write_datatable,
            write_html,
        )

        self.print_verbose_message(
            f"Generating datatable: {datatable_path}",
            f"Generating datatable from '{mlir_file}' → '{datatable_path}'",
        )

        cap_files = [str(p) for p in Path(caps_dir).glob("*.F90")]
        host_name = self.options_db.get("host_name") or ""
        root_el = build_datatable_from_module(
            self._parse_frontend(mlir_file), cap_files, host_name=host_name,
            framework_src_dir=self.options_db.get("framework_src_dir") or "",
        )
        write_datatable(root_el, datatable_path)
        self.print_verbose_message(f"  -> Wrote datatable: {datatable_path}")

        html_dir = self.options_db.get("emit_html")
        if html_dir:
            written = write_html(root_el, html_dir)
            for path in written:
                self.print_verbose_message(f"  -> Wrote HTML: {path}")

    def run(self, options_db=None):
        """Run the full frontend -> optimizer -> split-output pipeline.

        options_db -- if given (e.g. from default_options_db() plus an
        overlay, matching ccpp_prebuild.py's existing convention), argv is
        never parsed; the dict is still run through the same validation +
        list-coercion normalization build_options_db_from_args() applies to
        a CLI invocation (a copy is normalized, the caller's own dict is
        left untouched). If omitted (main()'s own CLI path), parses
        sys.argv exactly as before.
        """
        try:
            if options_db is not None:
                self.options_db = self._normalize_options_db(dict(options_db))
            else:
                parser = self.initialise_argument_parser()
                args = parser.parse_args()
                self.options_db = self.build_options_db_from_args(args)
        except (ValueError, FileNotFoundError) as e:
            raise CcppDslError(str(e)) from e
        self._frontend = None

        # Set once, before any ArgumentOp is constructed (merge_meta_files
        # builds ops in-process; run_frontend/run_py_frontend
        # forward the flag to their own subprocess below).
        set_legacy_mode(self.options_db.get("legacy_mode", False))
        set_verbosity(self.options_db.get("verbose", 1))

        if self.options_db.get("list_outputs"):
            outputs = self.predict_output_filenames()
            print(",".join(outputs))
            return CcppDslResult(written=outputs)

        if self.options_db.get("list_package_scope"):
            from xdsl_ccpp.transforms.package_scope import (
                format_package_scopes,
                init_problems,
                package_scopes,
            )

            if not self.options_db.get("py"):
                raise CcppDslError("--list-package-scope needs a --py suite")
            from xdsl_ccpp.transforms.package_segments import (
                format_package_segments,
                multi_instance_problems,
                package_segments,
            )

            module = self._build_cheap_metadata_module()
            print(format_package_scopes(package_scopes(module)), end="")
            print(format_package_segments(package_segments(module)), end="")
            for problem in init_problems(module) + multi_instance_problems(module):
                print(f"ERROR: {problem}")
            return CcppDslResult(written=[])

        if self.options_db.get("list_dependencies"):
            deps = self.predict_dependencies()
            print(",".join(deps))
            return CcppDslResult(written=deps)

        tmp_dir = self.options_db["tempdir"]
        out_dir = self.options_db["out"]
        os.makedirs(tmp_dir, exist_ok=True)
        if not self.options_db["stdout"]:
            os.makedirs(out_dir, exist_ok=True)

        # The Fortran-vs-.meta check needs only the scheme files, and the
        # memory-space check and the datatable only read the frontend
        # module, so they run alongside the frontend and ccpp_opt instead of
        # before them (generator-speed step 5); the caps do not change.
        fortran_check = self._start_fortran_check()
        opt = None
        try:
            if self.options_db.get("py"):
                mlir_file = self.run_py_frontend(tmp_dir)
                self.merge_meta_files(mlir_file)
            else:
                mlir_file = self.run_frontend(tmp_dir)
            wants_cpp = bool(self.options_db.get("bind_c") or self._host_lang_cpp())
            target = "ftn_and_cpp_header" if wants_cpp else "ftn"
            opt = self._start_opt(tmp_dir, mlir_file, target=target)
            self._check_memory_space_mismatch(mlir_file)
            if self.options_db.get("emit_datatable"):
                self._parse_frontend(mlir_file)
            ftn_file = self._finish_opt(opt)
        except BaseException:
            if opt is not None and not opt[0][1].closed:
                self.kill_pipeline_stage(opt[0])
            self._cancel_fortran_check(fortran_check)
            raise
        try:
            written = self.split_fortran_output(ftn_file, out_dir)

            if wants_cpp and not any(f.endswith(".h") for f in written):
                self.print_verbose_message(
                    "  -> No BIND(C) functions found; no C++ headers written",
                )

            datatable_path = self.options_db.get("emit_datatable")
            if datatable_path:
                self._run_datatable(mlir_file, out_dir, datatable_path)

            resolved_vars = None
            resolved_vars_path = self.options_db.get("emit_resolved_vars")
            if resolved_vars_path:
                # _finish_opt() above already returned, meaning the ccpp_opt
                # subprocess it spawned exited 0 -- and SuiteCAP.apply()
                # (suite_cap.py) unconditionally calls _write_resolved_vars()
                # as the very last thing it does before that process exits,
                # so this file is guaranteed to exist here. No polling/race.
                with open(resolved_vars_path) as f:
                    resolved_vars = json.load(f)
        except BaseException:
            self._cancel_fortran_check(fortran_check)
            raise
        self._finish_fortran_check(fortran_check)

        if not self.options_db.get("debug"):
            self.remove_file_if_exists(mlir_file, ftn_file)
            if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
                os.rmdir(tmp_dir)

        return CcppDslResult(
            written=written,
            datatable_path=datatable_path,
            resolved_vars=resolved_vars,
        )


def main():
    """CLI entry point: the only place that converts a CcppDslError into a
    printed message and a process exit. An in-process caller should call
    ccppMain().run() directly and catch CcppDslError itself instead."""
    try:
        report_input_errors(ccppMain().run)
    except CcppDslError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
