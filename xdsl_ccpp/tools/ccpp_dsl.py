import argparse
import dataclasses
import json
import os
import shlex
import subprocess
import sys

from xdsl.dialects import builtin
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
from xdsl_ccpp.util.ccpp_conventions import set_legacy_mode
from xdsl_ccpp.util.options_db import coerce_list_option


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
            "--meta-file",
            default=None,
            help="Optional metadata MLIR file (e.g. from fir2meta) whose "
            "ccpp.table_properties are merged into the ccpp module before "
            "the optimizer runs",
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
            "--cam-host",
            action="store_true",
            default=False,
            help="Generate CAM-SIMA-specific cam_ccpp_physics_* lifecycle wrapper "
                 "subroutines in the ccpp_cap module.  These wrappers read "
                 "errmsg/errcode from the physics_types module and col_start/col_end "
                 "from physics_grid (CAM-SIMA module-level variables) rather than "
                 "receiving them as dummy arguments.  Off by default so non-CAM "
                 "builds are not required to provide those modules.",
        )
        parser.add_argument(
            "--framework-src-dir",
            default="",
            metavar="DIR",
            help="Path to the real ccpp_framework/src directory.  When --cam-host "
                 "is set, the real framework F90 files (ccpp_hashable.F90, "
                 "ccpp_hash_table.F90, ccpp_constituent_prop_mod.F90, "
                 "ccpp_scheme_utils.F90) from this directory are listed in the "
                 "datatable utility files instead of the bundled xdsl_ccpp stubs.",
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
        if options_db.get("py"):
            # --py mode: --suites and --scheme-files are not required
            if options_db.get("suites"):
                raise ValueError("--py and --suites are mutually exclusive")
        else:
            if not options_db.get("suites"):
                raise ValueError("--suites is required (or use --py)")
            if not options_db.get("scheme_files") and not options_db.get("meta_file"):
                raise ValueError("--scheme-files is required (or provide --meta-file)")

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

        all_inputs = (
            options_db["suites"] + options_db["scheme_files"] + options_db["host_files"]
        )
        if options_db.get("py"):
            all_inputs.append(options_db["py"])
        if options_db.get("meta_file"):
            all_inputs.append(options_db["meta_file"])
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
        the pattern ccpp_validate_source.py/fir2meta.py/flang_utils.py already
        use elsewhere in this same tools/ directory.

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
        self.print_verbose_message(
            label,
            f'{label} with command: {shlex.join(cmd)} > "{out_path}"',
        )
        try:
            with open(out_path, "w") as out_f:
                result = subprocess.run(cmd, stdout=out_f, stderr=None)
        except FileNotFoundError:
            raise CcppDslError(f"could not execute '{cmd[0]}'") from None
        if result.returncode != 0:
            raise CcppDslError(
                f"{label.lower()} failed (exit code {result.returncode})",
                returncode=result.returncode,
            )

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

        self.run_pipeline_stage(cmd, mlir_out, "Running Python frontend")
        self.post_stage_check(mlir_out)
        return mlir_out

    def merge_meta_files(self, mlir_file):
        """Append ``ccpp.table_properties`` from scheme/host .meta files into *mlir_file*.

        Used when ``--py`` is combined with ``--scheme-files`` or ``--host-files``
        to merge additional metadata into the MLIR produced by the Python frontend.
        """
        scheme_files = self.options_db["scheme_files"]
        host_files = self.options_db["host_files"]
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
                prop = frontend.build_meta_ir(meta, meta_file_path=scheme_file)
                ccpp_module.body.block.add_op(prop)
                count += 1
        for host_file in host_files:
            for meta in parse_meta_file(host_file, False):
                prop = frontend.build_meta_ir(meta, meta_file_path=host_file)
                ccpp_module.body.block.add_op(prop)
                count += 1

        with open(mlir_file, "w") as f:
            Printer(stream=f).print_op(ccpp_module)
            f.write("\n")

        self.print_verbose_message(
            f"  -> Merged {count} table_properties block(s)",
        )

    def merge_meta(self, mlir_file):
        """Append ``ccpp.table_properties`` from the ``--meta-file`` into *mlir_file*.

        The metadata file (produced by ``fir2meta``) contains a top-level
        ``builtin.module`` wrapping a ``builtin.module @ccpp_meta`` that holds
        one or more ``ccpp.table_properties`` ops.  This method extracts those
        ops and appends them to the top-level module of *mlir_file* so that
        the subsequent ``generate-meta-cap`` pass sees them alongside the ops
        from the ``.meta`` scheme files.
        """
        meta_path = self.options_db["meta_file"]
        self.print_verbose_message(
            f"Merging metadata from '{meta_path}'",
            f"Merging ccpp.table_properties from '{meta_path}' into '{mlir_file}'",
        )

        ctx = make_ccpp_context()
        with open(mlir_file) as f:
            ccpp_module = Parser(ctx, f.read()).parse_op()

        with open(meta_path) as f:
            meta_module = Parser(make_ccpp_context(), f.read()).parse_op()

        # Extract ccpp.table_properties from the first sub-module in meta_module
        table_props = []
        for child in meta_module.body.block.ops:
            if not isinstance(child, builtin.ModuleOp):
                continue
            for op in list(child.body.block.ops):
                if isinstance(op, TablePropertiesOp):
                    op.detach()
                    table_props.append(op)
            break  # only the first sub-module

        if not table_props:
            self.print_verbose_message(
                f"Warning: no ccpp.table_properties found in '{meta_path}'"
            )
            return

        for prop in table_props:
            ccpp_module.body.block.add_op(prop)

        with open(mlir_file, "w") as f:
            Printer(stream=f).print_op(ccpp_module)
            f.write("\n")

        self.print_verbose_message(
            f"  -> Merged {len(table_props)} table_properties block(s)",
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
        validate_fir.compare_modules.

        Diagnostic only, currently warn-only: mismatches are printed to
        stderr, never raised, and any failure to load or parse a given
        pair is itself just a printed warning. This
        phase is not required for cap generation to succeed, and silently
        does nothing if fparser is not installed.
        """
        try:
            import fparser.two.Fortran2003  # noqa: F401
        except ImportError:
            return

        from xdsl_ccpp.transforms.fortran_preprocess import parse_preproc_defines
        from xdsl_ccpp.transforms.fparser2_to_meta import build_meta_module_from_file
        from xdsl_ccpp.transforms.validate_fir import compare_modules
        from xdsl_ccpp.tools.ccpp_validate_source import _load_meta_file

        preproc_defs = parse_preproc_defines(self.options_db.get("preproc_defs"))

        for meta_path in self.options_db.get("scheme_files") or []:
            stem = os.path.splitext(os.path.basename(meta_path))[0]
            f90_path = os.path.join(
                os.path.dirname(os.path.abspath(meta_path)), f"{stem}.F90"
            )
            if not os.path.isfile(f90_path):
                continue

            meta_module = _load_meta_file(meta_path)
            if meta_module is None:
                continue  # host/module-type .meta, or failed to load (already warned)

            try:
                source_module = build_meta_module_from_file(f90_path, preproc_defs)
            except Exception as exc:
                print(
                    f"Warning: fparser2 failed to parse '{f90_path}' for "
                    f"Fortran-vs-.meta validation: {exc}",
                    file=sys.stderr,
                )
                continue

            for mismatch in compare_modules(meta_module, source_module):
                print(f"Warning: {mismatch}", file=sys.stderr)

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

        ctx = make_ccpp_context()
        with open(mlir_file) as f:
            top_module = Parser(ctx, f.read()).parse_op()

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
        if self.options_db.get("cam_host"):
            cap_opts.append("cam_host=true")
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
        passes = ["generate-meta-cap"]
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
        passes += ["generate-kinds", "strip-ccpp"]
        return ",".join(passes)

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
        ftn_out = os.path.join(tmp_dir, "ccpp.ftn")
        pipeline = self._build_pipeline()
        cmd = [
            sys.executable, "-m", "xdsl_ccpp.tools.ccpp_opt", mlir_in,
            "-p", pipeline, "-t", target,
        ]
        self.run_pipeline_stage(cmd, ftn_out, "Running CCPP optimizer")
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

    def _run_datatable(self, mlir_file: str, caps_dir: str, datatable_path: str) -> None:
        """Generate datatable.xml (and optionally HTML) from *mlir_file*."""
        from pathlib import Path

        from xdsl_ccpp.tools.ccpp_datatable import (
            build_datatable,
            write_datatable,
            write_html,
        )

        self.print_verbose_message(
            f"Generating datatable: {datatable_path}",
            f"Generating datatable from '{mlir_file}' → '{datatable_path}'",
        )

        with open(mlir_file) as f:
            mlir_text = f.read()

        cap_files = [str(p) for p in Path(caps_dir).glob("*.F90")]
        host_name = self.options_db.get("host_name") or ""
        root_el = build_datatable(
            mlir_text, cap_files, host_name=host_name,
            cam_host=bool(self.options_db.get("cam_host")),
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

        # Set once, before any ArgumentOp is constructed (merge_meta_files/
        # merge_meta build ops in-process; run_frontend/run_py_frontend
        # forward the flag to their own subprocess below).
        set_legacy_mode(self.options_db.get("legacy_mode", False))

        tmp_dir = self.options_db["tempdir"]
        out_dir = self.options_db["out"]
        os.makedirs(tmp_dir, exist_ok=True)
        if not self.options_db["stdout"]:
            os.makedirs(out_dir, exist_ok=True)

        if self.options_db.get("py"):
            mlir_file = self.run_py_frontend(tmp_dir)
            self.merge_meta_files(mlir_file)
        else:
            mlir_file = self.run_frontend(tmp_dir)
        if self.options_db.get("meta_file"):
            self.merge_meta(mlir_file)
        self.validate_fortran_sources()
        self._check_memory_space_mismatch(mlir_file)
        wants_cpp = bool(self.options_db.get("bind_c") or self._host_lang_cpp())
        target = "ftn_and_cpp_header" if wants_cpp else "ftn"
        ftn_file = self.run_opt(tmp_dir, mlir_file, target=target)
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
            # run_opt() above already returned, meaning the ccpp_opt
            # subprocess it spawned exited 0 -- and SuiteCAP.apply()
            # (suite_cap.py) unconditionally calls _write_resolved_vars()
            # as the very last thing it does before that process exits,
            # so this file is guaranteed to exist here. No polling/race.
            with open(resolved_vars_path) as f:
                resolved_vars = json.load(f)

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
        ccppMain().run()
    except CcppDslError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
