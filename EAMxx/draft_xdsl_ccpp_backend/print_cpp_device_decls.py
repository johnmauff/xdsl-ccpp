"""Draft of EAMxx-bridge-automation.md's Phase D.3.

A new xdsl-ccpp backend printer that emits *declaration-only*, Kokkos-View-typed
C++ function signatures for CCPP schemes tagged ``cpp_native`` in their ``.meta``
file -- instead of the ``extern "C"`` BIND(C) declarations
``xdsl_ccpp/backend/print_cpp_header.py`` emits for the chost-cap path, and
instead of a Fortran cap at all.

STATUS: draft/exploratory, written 2026-08-25 per the D.3 request in the EAMxx
bridge-automation conversation (see ``EAMxx-bridge-automation.md``). Not wired
into ``xdsl_ccpp/backend/``, not registered with any CLI entry point, not
tested against a real completed IR. Written to sit alongside
``EAMxx/draft_eamxx_files/`` rather than inside the real ``xdsl_ccpp`` package
until the approach is reviewed. Attribute-accessor calls below (``.data``,
``opt_prop_def`` fields) match the real ``xdsl_ccpp.dialects.ccpp`` schema as
read on that date; re-verify against current source before relying on this.

--------------------------------------------------------------------------
Required real-repo integration points this draft anticipates but does NOT
make -- listed so a reviewer can find exactly where ``cpp_native`` would need
to be threaded through, mirroring how ``array_layout``/``language`` already
are (both confirmed by direct reading, not assumed):

1. ``xdsl_ccpp/frontend/ccpp_xml.py``:
   - ``CCPPTableProperties.setAttr`` (its ``array_layout`` validation branch,
     ~line 74) needs a parallel ``cpp_native`` branch validating against
     ``{"pointwise", "column_scan"}``.
   - ``MetaToIR.build_meta_ir`` (~line 665, immediately after the existing
     ``array_layout``/``language`` forwarding block) needs:
         if meta.table_properties.hasAttr("cpp_native"):
             attrs["cpp_native"] = StringAttr(meta.table_properties.getAttr("cpp_native"))

2. ``xdsl_ccpp/frontend/py_api.py`` has its OWN independent copy of this
   forwarding logic:
   - ``scheme_descriptor_from_meta`` (~line 707) only reads ``language`` today.
   - ``ccpp_host_from_meta`` (~line 753) only reads ``array_layout`` today.
   Neither reads the other's property, which is the exact "two
   historically-drifting copies" shape ``EAMxx-bridge-automation.md``'s
   2026-08-25 revision already flagged for ``kind_spec``. ``cpp_native`` would
   need the same two-line addition in *both* functions, or it silently
   vanishes depending which parsing path a given driver script calls.

3. ``xdsl_ccpp/transforms/util/ccpp_descriptors.py``'s ``CCPPTableProperties.setAttr``
   (~line 67) is the IR-side descriptor's OWN allow-list, independent of
   ``ccpp_xml.py``'s frontend-side one above -- and it is currently missing
   ``array_layout`` entirely, despite the frontend already accepting it. This
   is that same drift bug, caught directly while writing this draft (not
   inferred from the doc). Anything relying on this class to validate
   ``cpp_native`` would need it added here too, a fourth edit site.

4. A new CLI-level emission mode (mirroring ``generate-cpp-cap``) that invokes
   ``print_cpp_device_decls`` below, likely named ``generate-cpp-device-decls``.

--------------------------------------------------------------------------
Contract this printer enforces, per an explicit requirement from the person
who requested this draft: the EAMxx AtmosphereProcess printer must never
itself contain a ``Kokkos::parallel_for``/index loop. So every declaration
emitted here takes *whole-array* ``Kokkos::View`` arguments -- never a
per-point scalar -- matching the shape of ``TMSFunctions::compute_tms``, not
``PF::exner_function``'s pointwise form. Whatever loop the implementation
needs lives inside the hand-written D.4 function body (see
``EAMxx/draft_eamxx_files/``), not at any generated call site.
"""

from __future__ import annotations

from typing import IO

from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp

# The only two values `cpp_native` may take. This is a per-SCHEME property
# (set once on the [ccpp-table-properties] block), not per entry-point -- all
# of a scheme's _init/_run/_timestep_*/_finalize arg-tables inherit it, same
# granularity as `array_layout`/`language` today. A scheme this doesn't apply
# to (structurally superseded, genuinely-needs-Fortran) simply omits the
# property, exactly like `language`'s existing "fortran = omit" convention.
POINTWISE = "pointwise"
COLUMN_SCAN = "column_scan"
_VALID_CPP_NATIVE = (POINTWISE, COLUMN_SCAN)

# CCPP `kind` value -> the scalar alias declared in
# EAMxx/draft_eamxx_files/eamxx_ccpp_view_types.hpp. Only kind_phys is mapped;
# anything else falls back to Real, matching kind_phys's own real-world role
# as "the" CCPP real kind in every scheme read during the D.2 triage.
_KIND_TO_SCALAR = {
    "kind_phys": "Real",
}

# CCPP entry points always end in these two error-handling arguments. No
# hand-written EAMxx device function (PF::exner_function,
# TMSFunctions::compute_tms) plumbs them through -- error handling for a pure
# device function is a KOKKOS_ASSERT or simply "can't fail" by construction,
# not a caller-supplied buffer -- so this printer drops them rather than
# forcing every hand-ported body and call site to carry a parameter nothing
# will ever read.
_DROPPED_ARGS = ("errmsg", "errflg")


def _view_type(arg: ArgumentOp) -> str:
    """Return the C++ type for one argument -- always a whole-array Kokkos
    view for anything with dimensions > 0, never a bare per-point scalar.

    This is the load-bearing function for the "no loop in the caller"
    contract: whatever this returns is what a generated declaration's
    parameter list contains, and a whole-view parameter is what lets
    D.4's hand-written body own the only Kokkos::parallel_for in the picture.
    """
    ndims = arg.dimensions.data if arg.dimensions is not None else 0
    scalar = _KIND_TO_SCALAR.get(arg.kind.data if arg.kind is not None else "", "Real")

    if ndims == 0:
        if arg.arg_type.data == "integer":
            return "int"
        return scalar  # a real(kind_phys) scalar constant, e.g. Kessler's `dt`/`gravit`

    if ndims == 1:
        return f"VT::view_1d<{scalar}>" if scalar == "int" else f"VT::view_1d<Pack>"
    if ndims == 2:
        return "VT::view_2d<Pack>"
    raise NotImplementedError(
        f"cpp_native device-function printer: no view alias for "
        f"{ndims}-dimensional argument '{arg.arg_name.data}' -- D.1's shared "
        f"header (eamxx_ccpp_view_types.hpp) only defines view_1d/view_2d "
        f"today. A 3-D candidate (e.g. a constituent array) would need that "
        f"header extended before this printer can handle it."
    )


def _is_input_only(arg: ArgumentOp) -> bool:
    return (arg.intent.data if arg.intent is not None else "in") == "in"


def _cpp_param(arg: ArgumentOp) -> str:
    view_t = _view_type(arg)
    name = arg.arg_name.data
    if view_t in ("int", "Real"):
        return f"{view_t} {name}"
    prefix = "const " if _is_input_only(arg) else ""
    return f"{prefix}{view_t}& {name}"


def _collect_cpp_native_schemes(
    prog: ModuleOp,
) -> list[tuple[str, str, TablePropertiesOp]]:
    """Return (scheme_name, cpp_native_mode, table_properties_op) for every
    scheme tagged `cpp_native` anywhere in *prog* -- read off the same
    completed IR xdsl-ccpp's other backends (cpp_interop.py,
    print_cpp_header.py) already consume, not a separate parse pass.
    """
    found: list[tuple[str, str, TablePropertiesOp]] = []
    for op in prog.walk():
        if not isa(op, TablePropertiesOp):
            continue
        mode_attr = op.attributes.get("cpp_native")
        if mode_attr is None:
            continue
        if not isinstance(mode_attr, StringAttr) or mode_attr.data not in _VALID_CPP_NATIVE:
            got = mode_attr.data if isinstance(mode_attr, StringAttr) else mode_attr
            raise ValueError(
                f"Scheme '{op.table_name.data}' has cpp_native = '{got}', "
                f"expected one of {_VALID_CPP_NATIVE}."
            )
        found.append((op.table_name.data, mode_attr.data, op))
    return found


def _entry_point_tables(table_props: TablePropertiesOp):
    """Yield every ArgumentTableOp under one scheme's TablePropertiesOp --
    e.g. kessler_update's _timestep_init/_run/_timestep_final all show up
    here, each becoming its own declaration below.
    """
    for op in table_props.body.block.ops:
        if isa(op, ArgumentTableOp):
            yield op


def print_cpp_device_decls(prog: ModuleOp, output: IO[str]) -> None:
    """Emit declaration-only, Kokkos-View-typed C++ headers for every scheme
    tagged `cpp_native` in its .meta file.

    One ``// FILE:`` section per scheme, named ``<scheme>_device.h``,
    following the same multi-file convention
    ``print_cpp_header.print_to_cpp_headers`` already uses, so the driver's
    existing ``split_fortran_output`` could write these out unchanged.

    Each declaration is a **contract, not an implementation** (Phase D.3): a
    person fills in the body once, by hand, in a matching D.4 header -- see
    ``EAMxx/draft_eamxx_files/`` for the fully-worked Kessler-suite example.
    If the scheme's metadata changes on a later regeneration (a renamed
    standard name, an added argument, a changed kind), this declaration
    changes with it and a stale hand-written body simply fails to compile --
    that compile-time check is the whole point of generating the declaration
    at all, not just documenting it in a comment.
    """
    schemes = _collect_cpp_native_schemes(prog)
    if not schemes:
        return

    wrote = False
    for scheme_name, mode, table_props in schemes:
        if wrote:
            output.write("// -----\n")
        output.write(f"// FILE: {scheme_name}_device.h\n")
        output.write(
            f"// Generated by xdsl-ccpp (DRAFT printer, not yet real). "
            f"cpp_native = {mode}.\n"
            "// Declaration only -- the body is hand-written once in a matching\n"
            "// D.4 header (EAMxx/draft_eamxx_files/). Do not add a\n"
            "// Kokkos::parallel_for at any call site of these functions.\n"
        )
        output.write("#pragma once\n")
        output.write('#include "eamxx_ccpp_view_types.hpp"\n\n')
        output.write("using VT = scream::ccpp::DefaultCCPPViewTypes;\n")
        output.write("using Pack = VT::Pack;\n\n")

        for entry in _entry_point_tables(table_props):
            fn_name = entry.table_name.data
            args = [
                a
                for a in entry.body.block.ops
                if isa(a, ArgumentOp) and a.arg_name.data not in _DROPPED_ARGS
            ]
            params = ", ".join(_cpp_param(a) for a in args)
            output.write("KOKKOS_INLINE_FUNCTION\n")
            output.write(f"static void {fn_name}({params});\n\n")

        wrote = True
