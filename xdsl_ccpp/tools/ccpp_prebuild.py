"""ccpp_prebuild — xDSL-CCPP drop-in for ccpp_prebuild.py.

Reads the same host-model ``ccpp_prebuild_config.py`` file used by the
reference CCPP framework and drives the xdsl-ccpp pipeline to generate cap
subroutines.  After generation it writes Makefile/CMake/shell-sourceable
snippets listing the generated caps, mirroring the output of the original
``ccpp_prebuild.py``.

Usage::

    python3 -m xdsl_ccpp.tools.ccpp_prebuild \\
        --config path/to/ccpp_prebuild_config.py \\
        [--suites suite_a,suite_b] \\
        [--builddir /path/to/build] \\
        [--clean] [--verbose]

Config keys read
----------------
The following variables are read from the config module.  All path-valued
keys that contain ``{build_dir}`` are formatted against the resolved build
directory before use.

Required
~~~~~~~~
``HOST_MODEL_IDENTIFIER``
    Short name for the host model (e.g. ``"SCM"``).
``SCHEME_FILES``
    List of Fortran source paths (``.F90``/``.f``/``.F``) for physics
    schemes, relative to basedir.  For each file the corresponding ``.meta``
    file (same directory, same basename) is used as input to xdsl-ccpp.
``CAPS_DIR``
    Directory where generated ``.F90`` cap files are written.
``SUITES_DIR``
    Directory containing suite XML files.
``CAPS_MAKEFILE``, ``CAPS_CMAKEFILE``, ``CAPS_SOURCEFILE``
    Output paths for the generated caps file list.

Optional
~~~~~~~~
``VARIABLE_DEFINITION_FILES``
    Host-model Fortran source paths whose companion ``.meta`` files are
    passed as ``--host-files`` to xdsl-ccpp.
``SCHEME_META_FILES``
    Override: explicit list of ``.meta`` paths for scheme metadata.
    If absent the tool derives them from ``SCHEME_FILES``.
``HOST_META_FILES``
    Override: explicit list of ``.meta`` paths for host model metadata.
    If absent the tool derives them from ``VARIABLE_DEFINITION_FILES``.
``SCHEMES_MAKEFILE``, ``SCHEMES_CMAKEFILE``, ``SCHEMES_SOURCEFILE``
    Output paths for the scheme source file list.
``DEFAULT_BUILD_DIR``
    Fallback build directory when ``--builddir`` is not given on the
    command line (default: ``"build"``).
"""

from __future__ import annotations

import argparse
import glob
import importlib
import os
import sys

from xdsl_ccpp.tools.ccpp_dsl import ccppMain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(value: str, build_dir: str) -> str:
    return value.format(build_dir=build_dir)


def _meta_for(f90_path: str, basedir: str, verbose: bool) -> str | None:
    """Return the .meta companion for a Fortran source file, or None."""
    abs_path = os.path.join(basedir, f90_path)
    base = os.path.splitext(abs_path)[0]
    meta = base + ".meta"
    if os.path.exists(meta):
        return meta
    if verbose:
        print(f"  [skip] no .meta found for {f90_path}")
    return None


def _write_makefile(path: str, var: str, files: list[str]) -> None:
    """Write a GNU Makefile snippet: VAR = file1 file2 ..."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        if files:
            f.write(f"{var} = \\\n")
            for i, p in enumerate(files):
                sep = " \\" if i < len(files) - 1 else ""
                f.write(f"\t{p}{sep}\n")
        else:
            f.write(f"{var} =\n")


def _write_cmakefile(path: str, var: str, files: list[str]) -> None:
    """Write a CMake snippet: set(VAR file1 file2 ...)"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(f"set({var}\n")
        for p in files:
            f.write(f"    {p}\n")
        f.write(")\n")


def _write_sourcefile(path: str, var: str, files: list[str]) -> None:
    """Write a shell-sourceable snippet: export VAR="file1 file2 ..." """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        joined = " ".join(files)
        f.write(f'export {var}="{joined}"\n')


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _load_config(configfile: str, builddir: str | None) -> dict:
    if not os.path.isfile(configfile):
        print(f"Error: config file not found: '{configfile}'", file=sys.stderr)
        sys.exit(1)

    configpath = os.path.abspath(os.path.dirname(configfile))
    configmodule = os.path.splitext(os.path.basename(configfile))[0]
    sys.path.insert(0, configpath)
    cfg = importlib.import_module(configmodule)

    if not builddir:
        builddir = os.path.join(os.getcwd(), getattr(cfg, "DEFAULT_BUILD_DIR", "build"))

    def f(attr: str, default: str = "") -> str:
        return _fmt(getattr(cfg, attr, default), builddir)

    config: dict = {
        "host_model": getattr(cfg, "HOST_MODEL_IDENTIFIER", "unknown"),
        "builddir": builddir,
        "scheme_files": getattr(cfg, "SCHEME_FILES", []),
        "variable_definition_files": getattr(cfg, "VARIABLE_DEFINITION_FILES", []),
        # Override lists (explicit .meta paths)
        "scheme_meta_files": getattr(cfg, "SCHEME_META_FILES", None),
        "host_meta_files": getattr(cfg, "HOST_META_FILES", None),
        # Directories
        "caps_dir": f("CAPS_DIR"),
        "suites_dir": f("SUITES_DIR", "."),
        # Caps file-list outputs
        "caps_makefile": f("CAPS_MAKEFILE"),
        "caps_cmakefile": f("CAPS_CMAKEFILE"),
        "caps_sourcefile": f("CAPS_SOURCEFILE"),
        # Schemes file-list outputs (optional)
        "schemes_makefile": f("SCHEMES_MAKEFILE"),
        "schemes_cmakefile": f("SCHEMES_CMAKEFILE"),
        "schemes_sourcefile": f("SCHEMES_SOURCEFILE"),
    }
    return config


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def _clean(config: dict) -> None:
    caps_dir = config["caps_dir"]
    removed = []
    if os.path.isdir(caps_dir):
        for f90 in glob.glob(os.path.join(caps_dir, "*.F90")):
            os.remove(f90)
            removed.append(f90)
    for key in (
        "caps_makefile",
        "caps_cmakefile",
        "caps_sourcefile",
        "schemes_makefile",
        "schemes_cmakefile",
        "schemes_sourcefile",
    ):
        path = config.get(key, "")
        if path and os.path.exists(path):
            os.remove(path)
            removed.append(path)
    if removed:
        print("Removed:")
        for p in removed:
            print(f"  {p}")
    else:
        print("Nothing to clean.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="xDSL-CCPP drop-in for ccpp_prebuild.py"
    )
    parser.add_argument(
        "--config", required=True, help="path to ccpp_prebuild_config.py"
    )
    parser.add_argument(
        "--suites",
        default="",
        help="comma-separated suite names (without path or .xml extension)",
    )
    parser.add_argument(
        "--builddir",
        default=None,
        help="build directory (overrides DEFAULT_BUILD_DIR in config)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove previously generated files and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable verbose output",
    )
    args = parser.parse_args()

    basedir = os.getcwd()
    config = _load_config(args.config, args.builddir)
    verbose = args.verbose

    if args.clean:
        _clean(config)
        return

    # ── Resolve suite XML files ───────────────────────────────────────────
    suites_dir = config["suites_dir"]
    if args.suites:
        suite_xmls = [
            os.path.join(suites_dir, f"{name}.xml") for name in args.suites.split(",")
        ]
    else:
        suite_xmls = sorted(glob.glob(os.path.join(suites_dir, "*.xml")))

    missing = [p for p in suite_xmls if not os.path.exists(p)]
    if missing:
        for p in missing:
            print(f"Error: suite file not found: '{p}'", file=sys.stderr)
        sys.exit(1)

    if not suite_xmls:
        print(f"Error: no suite XML files found in '{suites_dir}'", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"Suites: {suite_xmls}")

    # ── Resolve scheme .meta files ────────────────────────────────────────
    if config["scheme_meta_files"] is not None:
        scheme_metas = config["scheme_meta_files"]
    else:
        scheme_metas = []
        for f90 in config["scheme_files"]:
            meta = _meta_for(f90, basedir, verbose)
            if meta:
                scheme_metas.append(meta)

    # ── Resolve host .meta files ──────────────────────────────────────────
    if config["host_meta_files"] is not None:
        host_metas = config["host_meta_files"]
    else:
        host_metas = []
        for f90 in config["variable_definition_files"]:
            meta = _meta_for(f90, basedir, verbose)
            if meta:
                host_metas.append(meta)

    if not scheme_metas:
        print("Warning: no scheme .meta files found", file=sys.stderr)

    # ── Run the xdsl-ccpp pipeline ────────────────────────────────────────
    caps_dir = config["caps_dir"]
    os.makedirs(caps_dir, exist_ok=True)

    tool = ccppMain()
    # Start from ccpp_dsl.py's own CLI defaults (single source of truth --
    # see default_options_db's own docstring for why) and overlay only the
    # keys this config-driven flow actually resolves itself; everything
    # else (--directive, --legacy-mode, --bind-c, etc.) keeps its real CLI
    # default instead of being silently absent from the dict.
    tool.options_db = tool.default_options_db()
    tool.options_db.update({
        "suites": suite_xmls,
        "scheme_files": scheme_metas,
        "host_files": host_metas,
        "out": caps_dir,
        "tempdir": os.path.join(config["builddir"], "tmp"),
        "verbose": 2 if verbose else 1,
    })

    tmp_dir = tool.options_db["tempdir"]
    os.makedirs(tmp_dir, exist_ok=True)

    mlir_file = tool.run_frontend(tmp_dir)
    ftn_file = tool.run_opt(tmp_dir, mlir_file)
    tool.split_fortran_output(ftn_file, caps_dir)
    tool.remove_file_if_exists(mlir_file, ftn_file)
    if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
        os.rmdir(tmp_dir)

    # ── Collect generated cap files ───────────────────────────────────────
    cap_files = sorted(glob.glob(os.path.join(caps_dir, "*.F90")))
    if verbose:
        print(f"Generated caps: {cap_files}")

    # ── Write caps file-list outputs ──────────────────────────────────────
    _write_makefile(config["caps_makefile"], "CCPP_CAPS", cap_files)
    _write_cmakefile(config["caps_cmakefile"], "CCPP_CAPS", cap_files)
    _write_sourcefile(config["caps_sourcefile"], "CCPP_CAPS", cap_files)
    print(f"  -> Written caps lists to '{os.path.dirname(config['caps_makefile'])}'")

    # ── Write schemes file-list outputs (if configured) ───────────────────
    scheme_sources = [os.path.join(basedir, f) for f in config["scheme_files"]]
    if config.get("schemes_makefile"):
        _write_makefile(config["schemes_makefile"], "CCPP_SCHEMES", scheme_sources)
        _write_cmakefile(config["schemes_cmakefile"], "CCPP_SCHEMES", scheme_sources)
        _write_sourcefile(config["schemes_sourcefile"], "CCPP_SCHEMES", scheme_sources)
        print(
            f"  -> Written schemes lists to '{os.path.dirname(config['schemes_makefile'])}'"
        )


if __name__ == "__main__":
    main()
