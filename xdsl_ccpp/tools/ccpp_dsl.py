import argparse
import os
import sys

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.parser import Parser
from xdsl.printer import Printer
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP, TablePropertiesOp
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import ccppXML


def _make_ctx() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


class ccppMain:
    def initialise_argument_parser(self):
        parser = argparse.ArgumentParser(description="xDSL CCPP DSL compiler flow")
        self.set_parser_arguments(parser)
        return parser

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
            default="acc",
            choices=["acc", "omp"],
            help="GPU directive backend: 'acc' for OpenACC (default), "
                 "'omp' for OpenMP target offload",
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
            "--emit-html",
            default=None,
            metavar="DIR",
            help="Write per-entry-point HTML variable tables into this directory "
                 "(requires --emit-datatable).",
        )

    def build_options_db_from_args(self, args):
        options_db = args.__dict__

        if options_db.get("py"):
            # --py mode: --suites and --scheme-files are not required
            if options_db.get("suites"):
                raise ValueError("--py and --suites are mutually exclusive")
        else:
            if not options_db.get("suites"):
                raise ValueError("--suites is required (or use --py)")
            if not options_db.get("scheme_files") and not options_db.get("meta_file"):
                raise ValueError("--scheme-files is required (or provide --meta-file)")

        if options_db.get("suites"):
            options_db["suites"] = options_db["suites"].split(",")
        else:
            options_db["suites"] = []
        if options_db["scheme_files"]:
            options_db["scheme_files"] = options_db["scheme_files"].split(",")
        else:
            options_db["scheme_files"] = []
        if options_db["host_files"]:
            options_db["host_files"] = options_db["host_files"].split(",")
        else:
            options_db["host_files"] = []

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
            print(f"Error: expected output '{path}' was not created", file=sys.stderr)
            sys.exit(1)
        if self.options_db["verbose"] >= 1:
            print(f"  -> Completed, results in '{path}'")

    def remove_file_if_exists(self, *paths):
        for path in paths:
            if os.path.exists(path):
                os.remove(path)

    def run_frontend(self, tmp_dir):
        suites_arg = ",".join(self.options_db["suites"])
        mlir_out = os.path.join(tmp_dir, "ccpp.mlir")

        cmd = f'python3 -m xdsl_ccpp.frontend.ccpp_xml --suites "{suites_arg}"'
        if self.options_db["scheme_files"]:
            scheme_files_arg = ",".join(self.options_db["scheme_files"])
            cmd += f' --scheme-files "{scheme_files_arg}"'
        if self.options_db["host_files"]:
            host_files_arg = ",".join(self.options_db["host_files"])
            cmd += f' --host-files "{host_files_arg}"'
        cmd += f' > "{mlir_out}"'

        self.print_verbose_message(
            "Running CCPP frontend",
            f"Running CCPP frontend with command: {cmd}",
        )
        os.system(cmd)
        self.post_stage_check(mlir_out)
        return mlir_out

    def run_py_frontend(self, tmp_dir):
        py_file = self.options_db["py"]
        mlir_out = os.path.join(tmp_dir, "ccpp.mlir")

        cmd = f'python3 "{py_file}" > "{mlir_out}"'

        self.print_verbose_message(
            "Running Python frontend",
            f"Running Python frontend with command: {cmd}",
        )
        os.system(cmd)
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

        ctx = _make_ctx()
        with open(mlir_file) as f:
            ccpp_module = Parser(ctx, f.read()).parse_op()

        frontend = ccppXML()
        count = 0
        for scheme_file in scheme_files:
            for meta in frontend.parse_metadata_file(scheme_file, True):
                prop = frontend.build_meta_ir(meta)
                ccpp_module.body.block.add_op(prop)
                count += 1
        for host_file in host_files:
            for meta in frontend.parse_metadata_file(host_file, False):
                prop = frontend.build_meta_ir(meta)
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

        ctx = _make_ctx()
        with open(mlir_file) as f:
            ccpp_module = Parser(ctx, f.read()).parse_op()

        with open(meta_path) as f:
            meta_module = Parser(_make_ctx(), f.read()).parse_op()

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

    def run_opt(self, tmp_dir, mlir_in):
        ftn_out = os.path.join(tmp_dir, "ccpp.ftn")
        ccpp_cap_pass = "generate-ccpp-cap"
        if self.options_db.get("host_name"):
            ccpp_cap_pass += f"{{host_name={self.options_db['host_name']}}}"
        directive = self.options_db.get("directive", "acc")
        gpu_data_pass      = f"generate-gpu-data{{directive={directive}}}"
        gpu_ccpp_cap_pass  = f"generate-gpu-ccpp-cap{{directive={directive}}}"
        meta_kinds_pass = "generate-meta-kinds"
        kind_maps = self.options_db.get("kind_map") or []
        if kind_maps:
            if len(kind_maps) > 1:
                import sys
                print(
                    "Warning: only the first --kind-map entry is used; "
                    "multiple extra kinds are not yet supported.",
                    file=sys.stderr,
                )
            k, iso = kind_maps[0].split(":", 1)
            meta_kinds_pass += f"{{extra_kind={k.strip()} extra_iso={iso.strip()}}}"
        has_host = bool(self.options_db.get("host_files"))
        host_match_pass = "generate-host-match," if has_host else ""
        ccpp_cap_passes = f",{ccpp_cap_pass},{gpu_ccpp_cap_pass}" if has_host else ""
        pipeline = (
            f"generate-meta-cap,{host_match_pass}{meta_kinds_pass},"
            f"generate-suite-cap,{gpu_data_pass}{ccpp_cap_passes},"
            f"generate-kinds,strip-ccpp"
        )
        cmd = (
            f'python3 -m xdsl_ccpp.tools.ccpp_opt "{mlir_in}"'
            f' -p "{pipeline}"'
            f' -t ftn > "{ftn_out}"'
        )
        self.print_verbose_message(
            "Running CCPP optimizer",
            f"Running CCPP optimizer with command: {cmd}",
        )
        os.system(cmd)
        self.post_stage_check(ftn_out)
        return ftn_out

    def split_fortran_output(self, ftn_file, out_dir):
        """Split the combined Fortran printer output into individual .F90 files.

        The printer emits sections separated by '// -----', each preceded by a
        '// FILE: <name>.F90' marker.  This method writes each section as a
        separate file in out_dir, or prints to stdout when --stdout is set.
        """
        with open(ftn_file) as f:
            content = f.read()

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

    def _run_datatable(self, mlir_file: str, caps_dir: str, datatable_path: str) -> None:
        """Generate datatable.xml (and optionally HTML) from *mlir_file*."""
        from xdsl_ccpp.tools.ccpp_datatable import build_datatable, write_datatable, write_html
        from pathlib import Path

        self.print_verbose_message(
            f"Generating datatable: {datatable_path}",
            f"Generating datatable from '{mlir_file}' → '{datatable_path}'",
        )

        with open(mlir_file) as f:
            mlir_text = f.read()

        cap_files = [str(p) for p in Path(caps_dir).glob("*.F90")]
        host_name = self.options_db.get("host_name") or ""
        root_el = build_datatable(mlir_text, cap_files, host_name=host_name)
        write_datatable(root_el, datatable_path)
        self.print_verbose_message(f"  -> Wrote datatable: {datatable_path}")

        html_dir = self.options_db.get("emit_html")
        if html_dir:
            written = write_html(root_el, html_dir)
            for path in written:
                self.print_verbose_message(f"  -> Wrote HTML: {path}")

    def run(self):
        parser = self.initialise_argument_parser()
        args = parser.parse_args()
        try:
            self.options_db = self.build_options_db_from_args(args)
        except (ValueError, FileNotFoundError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

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
        ftn_file = self.run_opt(tmp_dir, mlir_file)
        self.split_fortran_output(ftn_file, out_dir)

        datatable_path = self.options_db.get("emit_datatable")
        if datatable_path:
            self._run_datatable(mlir_file, out_dir, datatable_path)

        if not self.options_db.get("debug"):
            self.remove_file_if_exists(mlir_file, ftn_file)
            if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
                os.rmdir(tmp_dir)


def main():
    ccppMain().run()


if __name__ == "__main__":
    ccppMain().run()
