#!/usr/bin/env python3
"""Print a comma-separated file-path list from an xdsl_ccpp --emit-datatable
XML file, for xdsl_ccpp_capgen.cmake.

xdsl_ccpp's own datatable schema (<datatable><ccpp_files><file path="..."/>,
<datatable><dependencies><dependency>...</dependency>) differs from
capgen-v1's <ccpp_datatable> format that ccpp_datafile.py reads, so this is
a small, separate reader rather than an attempt to force compatibility with
that other tool.

Usage::

    parse_xdsl_ccpp_datatable.py <datatable.xml>                # ccpp_files (default)
    parse_xdsl_ccpp_datatable.py <datatable.xml> --section ccpp_files
    parse_xdsl_ccpp_datatable.py <datatable.xml> --section dependencies
"""
import argparse
import sys
import xml.etree.ElementTree as ET


def _ccpp_files_paths(root, datatable_path):
    ccpp_files = root.find("ccpp_files")
    if ccpp_files is None:
        print(f"error: no <ccpp_files> section in {datatable_path}", file=sys.stderr)
        sys.exit(1)
    paths = []
    for f in ccpp_files:
        path = f.get("path")
        if path is None:
            # skip subcategory elements (<utilities>, <host_files>, <suite_files>)
            # that capgen-v1's ccpp_datafile.py reads from the same element
            continue
        if not path:
            print(f"error: <file> element with empty path attribute in {datatable_path}",
                  file=sys.stderr)
            sys.exit(1)
        paths.append(path)
    return paths


def _dependencies_paths(root, datatable_path):
    # <dependencies> is a top-level sibling of <ccpp_files>, not a
    # subcategory of it -- confirmed absent entirely (not just empty) for
    # an example that declares no `dependencies = ...` anywhere, so
    # missing is a normal, non-error case (unlike <ccpp_files>, which
    # every example has).
    dependencies = root.find("dependencies")
    if dependencies is None:
        return []
    paths = []
    for dep in dependencies:
        path = dep.text
        if not path:
            print(f"error: <dependency> element with empty text in {datatable_path}",
                  file=sys.stderr)
            sys.exit(1)
        paths.append(path.strip())
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("datatable_path")
    parser.add_argument(
        "--section", choices=("ccpp_files", "dependencies"), default="ccpp_files",
    )
    args = parser.parse_args()
    root = ET.parse(args.datatable_path).getroot()
    if args.section == "ccpp_files":
        paths = _ccpp_files_paths(root, args.datatable_path)
    else:
        paths = _dependencies_paths(root, args.datatable_path)
    print(",".join(paths))


if __name__ == "__main__":
    main()
