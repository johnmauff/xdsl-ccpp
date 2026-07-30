#!/usr/bin/env python3
"""Print the comma-separated list of generated Fortran file paths from an
xdsl_ccpp --emit-datatable XML file, for xdsl_ccpp_capgen.cmake.

xdsl_ccpp's own datatable schema (<datatable><ccpp_files><file path="..."/>)
differs from capgen-v1's <ccpp_datatable> format that ccpp_datafile.py
reads, so this is a small, separate reader rather than an attempt to force
compatibility with that other tool.
"""
import sys
import xml.etree.ElementTree as ET


def main():
    datatable_path = sys.argv[1]
    root = ET.parse(datatable_path).getroot()
    ccpp_files = root.find("ccpp_files")
    if ccpp_files is None:
        print(f"error: no <ccpp_files> section in {datatable_path}", file=sys.stderr)
        sys.exit(1)
    paths = [f.get("path") for f in ccpp_files]
    print(",".join(paths))


if __name__ == "__main__":
    main()
