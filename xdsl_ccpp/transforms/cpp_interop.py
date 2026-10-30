"""C++/BIND(C) host-interop cap generation ("chost").

Extracted from ccpp_cap.py's CCPPCAP pass: this module owns everything
needed to emit a BIND(C) Fortran cap module plus
matching C++ header/wrapper text for a C++ host model, given the already-
generated ccpp_cap module. Runs as its own pass, generate-cpp-cap, right after
generate-ccpp-cap in the pipeline.
"""

from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    Float32Type,
    IndexType,
    IntegerAttr,
    IntegerType,
    MemRefType,
    f32,
    f64,
    i1,
    i8,
    i32,
)
from xdsl.dialects.llvm import LLVMPointerType
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import (
    AddressOfExprOp,
    AllocateOp,
    AssignOp,
    BlankLineOp,
    CallExprOp,
    CallStatementOp,
    CastExprOp,
    CFunctionSigOp,
    CHostCapOp,
    CommentOp,
    ConditionalExprOp,
    CppBraceInitCallOp,
    CppCallStatementOp,
    CppConstructorOp,
    CppFieldDeclOp,
    CppIncludeOp,
    CppNamespaceOp,
    CppStructDefOp,
    CToFortranStringCopyOp,
    DdtComponentDeclOp,
    DdtMethodCallOp,
    DerivedType,
    DerivedTypeDefOp,
    DoLoopOp,
    ExternCGuardOp,
    FortranToCStringCopyOp,
    IndexExprOp,
    LocalVarOp,
    MemberAccessExprOp,
    MethodCallExprOp,
    ModuleVarOp,
    NullPointerExprOp,
    OwnedArrayType,
    OwnedStringType,
    ReadOnlyType,
    RealKindType,
    ReturnStmtOp,
    SliceExprOp,
    StringLiteralExprOp,
    StructLiteralExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.ccpp_cap import _collect_public_suite_functions
from xdsl_ccpp.transforms.util.cap_shared import (
    _CCPP_CONSTITUENT_MOD,
    _CONSTITUENT_DDT_NAME,
    SUITE_ARG_DIM_NAMES,
    SUITE_ARG_STD_NAME,
    SUITE_FN_INFIX,
    _allocated_cond,
    _int_var_cmp,
    _scf_if,
    bind_c_extents_attr,
    fixed_interface_fn,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPType,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_HORIZONTAL_DIMENSIONS,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_PRIMITIVE_TYPES,
    CCPP_SCHEME_NAME_LEN,
    CCPP_VERT_DIM_STD_NAME,
    CCPP_KIND_PHYS,
    CCPP_VERTICAL_DIMENSIONS,
    arg_decl,
    name_local,
    real_kind_width,
)
from xdsl_ccpp.util.cpp_type_table import c_numeric_type

# The C struct the C++ host reads constituent properties into.
_CONSTITUENT_INFO = DerivedType("CcppConstituentInfo")

# Field descriptors for ccpp_constituent_properties_t.
# Each entry: (fortran_field_name, kind, char_len_or_None)
#   kind: "char" | "real" | "logical"
#   char_len: declared len= value (excluding the +1 null terminator)
_CONSTITUENT_STRUCT_FIELDS = [
    ("std_name",         "char",    128),
    ("long_name",        "char",    128),
    ("units",            "char",    32),
    ("default_val",      "real",    None),
    ("min_val",          "real",    None),
    ("is_advected_flag", "logical", None),
    ("is_water",         "logical", None),
    ("mix_ratio_type",   "char",    32),
    ("vert_dim",         "char",    64),
    ("default_val_set",  "logical", None),
    ("molar_mass_val",   "real",    None),
    ("thermo_active",    "logical", None),
]

# Maps each _CONSTITUENT_STRUCT_FIELDS field name to the real bound-procedure
# name on ccpp_constituent_properties_t; the local temp holding its output
# is typed like the struct field. Every field's data is `private` on the real
# module (xdsl_ccpp/framework_src/ccpp_constituent_prop_mod.F90) -- direct
# `%fname` component access (this code's own behavior before this fix)
# does not compile; every accessor is a *subroutine*
# `(this, out_arg, errcode, errmsg)`, not a plain function, so each field
# needs its own call plus a temp var to receive the result before copying
# into the BIND(C) buffer. "mix_ratio_type" has no real 1:1 accessor (the
# real module decomposes it into separate is_mass_mixing_ratio/
# is_volume_mixing_ratio/is_number_concentration/is_dry/is_moist/is_wet
# boolean predicates instead of one combined field) -- its entry here
# (accessor=None) is a sentinel the generator below special-cases,
# deriving the same 'dry'/'wet'/'moist' string the pre-2026-09-07
# simplified stub stored directly, via is_dry/is_wet/is_moist (mutually
# exclusive per ccp_is_dry/ccp_is_wet/ccp_is_moist's own single-enum
# comparison against this%const_water -- confirmed by direct read of
# ccpp_constituent_prop_mod.F90). Reviewed in PR #118 (Copilot): blanking
# this field unconditionally would have silently contradicted
# multilanguage_limitations.md's own documented full-metadata query
# promise, even though neither driver_constprop_chost.cpp nor
# driver_constadv_chost.cpp currently reads it.
_CONSTITUENT_ACCESSORS = {
    "std_name":         "standard_name",
    "long_name":        "long_name",
    "units":            "units",
    "default_val":      "default_value",
    "min_val":          "minimum",
    "is_advected_flag": "is_advected",
    "is_water":         "is_water_species",
    "mix_ratio_type":   None,  # derived, see comment above
    "vert_dim":         "vertical_dimension",
    "default_val_set":  "has_default",
    "molar_mass_val":   "molar_mass",
    "thermo_active":    "is_thermo_active",
}


# _emit_subr_header/_emit_call (hand-rolled column-wrap loops) removed:
# superseded by CallStatementOp, which shares the
# wrap_paren_list helper in print_ftn.py instead of each hand-rolling its
# own copy.


def _chost_kind_iso_map(ccpp_mod) -> dict:
    """Extract kind-name → (value, module) mapping from ccpp.kinds ops in the
    ccpp module. `value` is an ISO_FORTRAN_ENV constant ('REAL32'/'REAL64')
    for the common case, or an arbitrary spec name (e.g. 'temp_r8') when a
    metadata kind_spec resolved this kind instead -- `module` distinguishes
    the two ('iso_fortran_env' vs the real host/scheme module name), see
    _real_width_from_iso.
    """
    kind_iso: dict = {}
    for inner in ccpp_mod.body.ops:
        if not isa(inner, ccpp.KindsOp):
            continue
        for kind_op in inner.body.ops:
            if isa(kind_op, ccpp.KindOp):
                kind_iso[kind_op.kind_name.data] = (
                    kind_op.kind_value.data, kind_op.kind_module.data,
                )
    return kind_iso


def _real_width_from_iso(kind_name: str, kind_entry: "tuple[str, str] | None") -> int:
    """Return 32 or 64 for real kind *kind_name*, given its (value, module)
    entry from _chost_kind_iso_map (None if the kind was never seen there).

    A bare numeric KIND literal (e.g. "4", "8") is never seen in
    _chost_kind_iso_map at all -- suite_kinds.py's MetaKind pass
    deliberately never creates a ccpp.kind entry for one (it's already
    valid, self-contained Fortran with no ccpp_kinds dependency to
    export). kind_entry is None therefore does not mean "unknown width";
    check real_kind_width(kind_name) first (chost-real-width-fallback)
    before falling back to the historical 64-bit default, which would
    otherwise silently mis-widen a real kind_name="4" (single precision)
    to 64-bit. real_kind_width returns a Fortran KIND byte count (4/8),
    not a bit width -- multiply by 8 before returning it here.

    Raises ValueError if the kind was resolved via a metadata kind_spec
    (module != 'iso_fortran_env') rather than the hardcoded ISO_FORTRAN_ENV
    table: kind_spec only names a symbol (e.g. 'temp_r8'), not a width, so
    there is no width to read here at all -- silently guessing 64 would risk
    generating a BIND(C)/C++ struct with the wrong byte size for that field,
    a real, silent correctness bug across the language boundary. chost/C++
    interop for a kind_spec-resolved real kind isn't supported yet; add an
    explicit width mapping here if/when it's actually needed.
    """
    if kind_entry is None:
        byte_width = real_kind_width(kind_name)
        return byte_width * 8 if byte_width is not None else 64
    value, module = kind_entry
    if module != "iso_fortran_env":
        raise ValueError(
            f"chost cap: real kind '{kind_name}' was resolved via a metadata "
            f"kind_spec ('{module}:{value}'), not ISO_FORTRAN_ENV -- its "
            f"width (32- or 64-bit) isn't derivable from that declaration "
            f"alone, and the C++/BIND(C) interop layer needs a definite "
            f"width to lay out matching struct fields correctly. Give this "
            f"kind name an explicit width mapping before using it in a "
            f"C++/chost host."
        )
    return 32 if value == "REAL32" else 64


def _chost_build_maps(meta_data):
    """Build std_to_host (host/module/control-owned naming, global) and a
    HOST/MODULE/DDT/CONTROL-only local_to_std_fallback (used for
    synthesized/non-scheme-sourced bare names like col_start/col_end/ncol/nz)
    from metadata for chost arg classification.

    local_to_std_fallback deliberately EXCLUDES SCHEME tables: a suite
    cap function's dummy arguments are identified by the standard names
    the suite cap records on it (_chost_callee_identities), since one
    local name can mean different standard names in different schemes.
    HOST/MODULE/DDT names are host-owned and scheme-independent (same
    reasoning as std_to_host below), so keeping those flat here is safe.
    """
    std_to_host: dict = {}
    for props in meta_data.values():
        if props.getAttr("type") not in (CCPPType.HOST, CCPPType.MODULE, CCPPType.CONTROL):
            continue
        for atbl in props.arg_tables.values():
            for var in atbl.getFunctionArguments():
                if var.hasAttr("standard_name"):
                    sn = var.getAttr("standard_name").lower()
                    if sn not in std_to_host:
                        std_to_host[sn] = var.name

    local_to_std_fallback: dict = {}
    for props in meta_data.values():
        if props.getAttr("type") == CCPPType.SCHEME:
            continue
        for atbl in props.arg_tables.values():
            for var in atbl.getFunctionArguments():
                if var.hasAttr("standard_name") and var.name not in local_to_std_fallback:
                    local_to_std_fallback[var.name] = var.getAttr("standard_name").lower()

    ncol_var = (std_to_host.get(CCPP_HORIZ_DIM_STD_NAME)
                or std_to_host.get(CCPP_LOOP_EXTENT_STD_NAME) or "ncol")
    nz_var = std_to_host.get(CCPP_VERT_DIM_STD_NAME, "nz")
    return std_to_host, local_to_std_fallback, ncol_var, nz_var


@dataclass
class ChostArgInfo:
    """Arg descriptor for one chost (C++/BIND(C) host-interop) cap argument.

    Union of the fields ever populated across this module's ~7 construction
    sites (_chost_arg_info, _chost_expand_ddt_arg, _chost_out_infos x3,
    _chost_maybe_inject_ncol, _chost_maybe_inject_nz) -- no single site sets
    every field, so each one defaults to whatever the ~100+ existing read
    sites already assumed as a fallback (matching their .get(key, default)
    calls, or plain None/False for keys only ever read via bracket access
    after being unconditionally set at every construction site).

    Implements __getitem__/__setitem__/get() as a drop-in replacement for the
    plain dicts these call sites used to build, so every existing read/mutate
    site (bracket access, .get(), bracket assignment) keeps working unchanged.
    """

    hint: str | None = None
    bare: str = ""
    host: str = ""
    std: str = ""
    is_col_start: bool = False
    is_col_end: bool = False
    is_ncol: bool = False
    is_nz: bool = False
    is_dim_scalar: bool = False
    is_errmsg: bool = False
    is_errflg: bool = False
    is_sname: bool = False
    is_char: bool = False
    is_int: bool = False
    is_real: bool = False
    is_logical: bool = False
    real_width: int = 64
    rank: int = 0
    intent: str | None = None
    dim_nz: str | None = None
    dim_n3: str | None = None
    dim_ncol: str | None = None
    char_len: int | None = None
    _ddt_member: tuple | None = None   # member path, outermost first
    _ddt_local: str | None = None
    _ddt_prefix: str | None = None

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)


def _chost_arg_info(hint, mtype, local_to_std, std_to_host, kind_iso_map=None,
                    local_to_dim_names=None, attrs=None):
    """Return an arg descriptor dict for a single suite cap input argument;
    *attrs* is its suite_arg_attrs, as plain values."""
    bare = hint or ""
    std  = local_to_std.get(bare, "")
    host = std_to_host.get(std, bare)

    is_col_start = (std == CCPP_LOOP_BEGIN_STD_NAME)
    is_col_end   = (std == CCPP_LOOP_END_STD_NAME)
    is_ncol      = std in {CCPP_HORIZ_DIM_STD_NAME, CCPP_LOOP_EXTENT_STD_NAME}
    is_nz        = std in {CCPP_VERT_DIM_STD_NAME}
    is_errmsg    = (std == "ccpp_error_message")
    is_errflg    = (std == "ccpp_error_code")
    is_sname     = (std == "scheme_name" or bare == "scheme_name")
    is_in_only   = arg_decl(attrs or {}, hint, 0).is_in

    rank = 0
    real_width = 64
    is_char = is_int = is_real = False
    _ddt = (mtype if isinstance(mtype, DerivedType)
            else mtype.element_type if isinstance(mtype, MemRefType) and isinstance(mtype.element_type, DerivedType)
            else None)
    if _ddt is not None:
        raise ValueError(
            f"chost cap: argument '{bare}' (standard_name='{std}') has derived "
            f"type '{_ddt.type_name.data}' — DDT arguments are not supported in "
            f"the C-interoperable chost interface by this helper directly. DDT "
            f"flattening is handled one layer up, by _chost_fn_contexts routing "
            f"through _chost_expand_ddt_arg (requires scheme metadata to be "
            f"available — see multilanguage_limitations.md §4, which is fully "
            f"resolved via that path). Reaching this error means a DDT arg "
            f"reached _chost_arg_info directly without going through that routing."
        )
    char_len = None
    if isinstance(mtype, MemRefType):
        elem = mtype.element_type
        if isinstance(elem, IntegerType) and elem.width.data == 8:
            static_dims = [d.data for d in mtype.shape if d.data != DYNAMIC_INDEX]
            dyn_dims    = [d for d in mtype.shape if d.data == DYNAMIC_INDEX]
            if dyn_dims:
                if len(mtype.shape) == 1:
                    raise ValueError(
                        f"chost cap: argument '{bare}' (standard_name='{std}') is an "
                        f"assumed-length character (len=*) — BIND(C) does not permit "
                        f"assumed-length dummy arguments. Change the scheme to use a "
                        f"fixed-length character(len=N) argument instead."
                    )
                raise ValueError(
                    f"chost cap: argument '{bare}' (standard_name='{std}') is a "
                    f"character array — arrays of strings are not supported in the "
                    f"C-interoperable chost interface. Use a fixed-length scalar "
                    f"character(len=N) argument instead."
                )
            is_char  = True
            rank     = -1
            char_len = static_dims[0] if static_dims else CCPP_ERRMSG_LEN
        elif isinstance(elem, IntegerType):
            is_int = True
        else:
            is_real = True
            if isinstance(elem, Float32Type):
                real_width = 32
            elif isinstance(elem, RealKindType) and kind_iso_map:
                real_width = _real_width_from_iso(
                    elem.kind_name.data, kind_iso_map.get(elem.kind_name.data)
                )
            rank = sum(1 for d in mtype.shape if d.data == DYNAMIC_INDEX)

    if is_col_start or is_col_end:
        intent = None
    elif is_errmsg or is_sname or is_errflg:
        intent = "out"
    elif is_ncol or is_nz or is_int or (is_real and rank == 0):
        intent = "in"
    elif is_in_only:
        intent = "in"
    else:
        intent = "inout"

    # Resolve the correct vertical dimension host variable for rank-2 arrays.
    # A 2-D real may use vertical_interface_dimension (e.g. pverP) rather than
    # the default vertical_layer_dimension (pver), so look up the actual
    # dimension standard name rather than falling back to the global nz_var.
    dim_nz = None
    if rank >= 2 and is_real and local_to_dim_names is not None:
        _dim_names = local_to_dim_names.get(bare, [])
        _vert = next(
            (d.lower() for d in _dim_names if d.lower() in CCPP_VERTICAL_DIMENSIONS),
            None,
        )
        if _vert is not None:
            dim_nz = std_to_host.get(_vert)

    dim_n3 = None
    if rank >= 3 and is_real and local_to_dim_names is not None:
        _dim_names = local_to_dim_names.get(bare, [])
        for _d in _dim_names:
            _d_lo = _d.lower()
            if (_d_lo not in CCPP_HORIZONTAL_DIMENSIONS
                    and _d_lo not in CCPP_VERTICAL_DIMENSIONS):
                dim_n3 = std_to_host.get(_d_lo)
                if dim_n3:
                    break

    return ChostArgInfo(
        hint=hint, bare=bare, host=host, std=std,
        is_col_start=is_col_start, is_col_end=is_col_end,
        is_ncol=is_ncol, is_nz=is_nz, is_errmsg=is_errmsg,
        is_errflg=is_errflg, is_sname=is_sname,
        is_char=is_char, is_int=is_int, is_real=is_real, is_logical=False,
        real_width=real_width, rank=rank, intent=intent,
        dim_nz=dim_nz, dim_n3=dim_n3, char_len=char_len,
    )


def _chost_expand_ddt_arg(
    prefix, ddt_type_name, meta_data,
    local_to_std, std_to_host, kind_iso_map, ncol_var, nz_var,
    original_intent="inout",
):
    """Expand a DDT scheme argument into flat C-interoperable arg info dicts.

    For a scheme arg ``state`` of type ``tiny_state_t``, produces one arg dict
    per DDT member (e.g. ``state_nz``, ``state_temp``), plus a ``local_info``
    dict that drives Fortran reconstruction code.

    Returns (member_ais, local_info).
    """
    ddt_props = meta_data.get(ddt_type_name)
    if ddt_props is None:
        for _k, _v in meta_data.items():
            if _k.lower() == ddt_type_name.lower() and _v.getAttr("type") == CCPPType.DDT:
                ddt_props = _v
                break
    if ddt_props is None:
        raise ValueError(
            f"chost DDT expand: type '{ddt_type_name}' not found in metadata"
        )
    ddt_table_name = ddt_props.getAttr("name")
    arg_table = ddt_props.arg_tables.get(ddt_table_name)
    if arg_table is None:
        raise ValueError(
            f"chost DDT expand: DDT '{ddt_type_name}' has no arg table"
        )

    # ── Pass 1: build lookup of scalar integer members by standard_name ─────────
    # Enables resolving non-vertical array dimensions such as
    #   vmr_array(horizontal_dimension, number_of_chemical_species)
    # by finding the DDT scalar member whose standard_name matches the dimension.
    scalar_std_to_flat: dict = {}
    for var in arg_table.getFunctionArguments():
        _vtype = var.getAttr("type").lower() if var.hasAttr("type") else "real"
        _ndim  = int(var.getAttr("dimensions")) if var.hasAttr("dimensions") else 0
        if _vtype == "integer" and _ndim == 0:
            _std = var.getAttr("standard_name").lower() if var.hasAttr("standard_name") else ""
            scalar_std_to_flat[_std] = f"{prefix}_{var.name}"

    # ── Pass 2: build member arg-info dicts ───────────────────────────────────
    member_ais = []
    flat_nz_var = None
    dim_scalars_used: set = set()   # flat names of scalars referenced as dim_nz
    char_member_blanks: list = []   # character member paths — not exposed, init to ' '

    for var in arg_table.getFunctionArguments():
        flat_name = f"{prefix}_{var.name}"
        std = var.getAttr("standard_name").lower() if var.hasAttr("standard_name") else ""
        ndim = int(var.getAttr("dimensions")) if var.hasAttr("dimensions") else 0
        dim_names = var.getAttr("dim_names") if var.hasAttr("dim_names") else []

        is_ncol = std in {CCPP_HORIZ_DIM_STD_NAME, CCPP_LOOP_EXTENT_STD_NAME}
        is_nz   = std in CCPP_VERTICAL_DIMENSIONS
        vtype   = var.getAttr("type").lower() if var.hasAttr("type") else "real"
        is_int     = (vtype == "integer")
        is_real    = (vtype == "real")
        is_logical = (vtype == "logical")

        if vtype not in CCPP_PRIMITIVE_TYPES:
            # Nested DDT member: expand recursively, re-root paths under this local.
            # Option B (direct path): nested members are accessed as
            # outer_local%member%leaf so no separate inner local is declared.
            nested_ais, nested_li = _chost_expand_ddt_arg(
                f"{prefix}_{var.name}", vtype, meta_data,
                local_to_std, std_to_host, kind_iso_map, ncol_var, nz_var,
                original_intent=original_intent,
            )
            for nai in nested_ais:
                nai["_ddt_member"] = (var.name, *nai["_ddt_member"])
                nai["_ddt_local"]  = f"{prefix}_local"
                nai["_ddt_prefix"] = prefix
            member_ais.extend(nested_ais)
            for cmn in nested_li.get("char_member_blanks", []):
                char_member_blanks.append((var.name, *cmn))
            continue

        if vtype == "character":
            # Character members (e.g. ccpp_info_t%errmsg) are not exposed in the
            # C interface; the chost cap initialises them to blank instead.
            char_member_blanks.append((var.name,))
            continue

        real_width = 64
        if is_real and var.hasAttr("kind"):
            real_width = _real_width_from_iso(
                var.getAttr("kind"), kind_iso_map.get(var.getAttr("kind"))
            )

        has_horiz = any(d.lower() in CCPP_HORIZONTAL_DIMENSIONS for d in dim_names)
        has_vert  = any(d.lower() in CCPP_VERTICAL_DIMENSIONS    for d in dim_names)

        dim_ncol = ncol_var if has_horiz else None
        if has_vert:
            dim_nz = "__FLAT_NZ__"
        elif ndim >= 2 and has_horiz:
            # Non-vertical second dimension: find the DDT scalar that provides it.
            dim_nz = None
            for d in dim_names:
                if d.lower() not in CCPP_HORIZONTAL_DIMENSIONS:
                    candidate = scalar_std_to_flat.get(d.lower())
                    if candidate:
                        dim_nz = candidate
                        dim_scalars_used.add(candidate)
                        break
        else:
            dim_nz = None

        if is_nz or is_ncol or (is_int and ndim == 0):
            intent = "in"
        elif ndim == 0 and is_real:
            intent = "in"
        else:
            intent = original_intent

        ai = ChostArgInfo(
            hint=None, bare=flat_name, host=flat_name, std=std,
            is_col_start=False, is_col_end=False,
            is_ncol=is_ncol, is_nz=is_nz, is_dim_scalar=False,
            is_errmsg=False, is_errflg=False, is_sname=False,
            is_char=False, is_int=is_int, is_real=is_real, is_logical=is_logical,
            real_width=real_width, rank=ndim, intent=intent,
            _ddt_member=(var.name,),
            _ddt_local=f"{prefix}_local",
            _ddt_prefix=prefix,
            dim_ncol=dim_ncol,
            dim_nz=dim_nz,
        )
        if is_nz:
            flat_nz_var = flat_name
        member_ais.append(ai)

    for ai in member_ais:
        if ai["dim_nz"] == "__FLAT_NZ__":
            ai["dim_nz"] = flat_nz_var
        # Non-vertical scalars that dimension an array get is_dim_scalar so they
        # appear in the canonical nz group and in the State constructor.
        if ai["host"] in dim_scalars_used:
            ai["is_dim_scalar"] = True

    array_ais = [ai for ai in member_ais if ai["rank"] > 0]
    local_info = dict(
        local_name=f"{prefix}_local",
        ddt_type=ddt_type_name,
        prefix=prefix,
        member_ais=member_ais,
        array_ais=array_ais,
        flat_nz_var=flat_nz_var,
        char_member_blanks=char_member_blanks,
    )
    return member_ais, local_info


def _chost_canonical_order(visible):
    """ncol first, nz second, then other args, then errmsg, then errflg."""
    ncols   = [a for a in visible if a["is_ncol"]]
    nzs     = [a for a in visible if a["is_nz"] or a.get("is_dim_scalar")]
    errmsgs = [a for a in visible if a["is_errmsg"]]
    errflgs = [a for a in visible if a["is_errflg"]]
    others  = [a for a in visible
               if not a["is_ncol"] and not a["is_nz"] and not a.get("is_dim_scalar")
               and not a["is_errmsg"] and not a["is_errflg"]]
    return ncols + nzs + others + errmsgs + errflgs


def _chost_out_infos(pfn_out_types, std_to_host):
    """Build arg descriptors for suite cap output return values (errmsg, errflg, scheme_name)."""
    out_infos = []
    for otype in pfn_out_types:
        if not isinstance(otype, MemRefType):
            continue
        elem = otype.element_type
        if isinstance(elem, IntegerType) and elem.width.data == 8:
            static_dims = [d.data for d in otype.shape if d.data != DYNAMIC_INDEX]
            char_len = static_dims[0] if static_dims else CCPP_ERRMSG_LEN
            if char_len == CCPP_ERRMSG_LEN:
                host = std_to_host.get("ccpp_error_message", "errmsg")
                out_infos.append(ChostArgInfo(
                    hint="errmsg", bare="errmsg", host=host,
                    std="ccpp_error_message",
                    is_col_start=False, is_col_end=False,
                    is_ncol=False, is_nz=False,
                    is_errmsg=True, is_errflg=False, is_sname=False,
                    is_char=True, is_int=False, is_real=False, is_logical=False,
                    rank=-1, intent="out",
                ))
            else:
                host = std_to_host.get("scheme_name", "scheme_name")
                out_infos.append(ChostArgInfo(
                    hint="scheme_name", bare="scheme_name", host=host,
                    std="scheme_name",
                    is_col_start=False, is_col_end=False,
                    is_ncol=False, is_nz=False,
                    is_errmsg=False, is_errflg=False, is_sname=True,
                    is_char=True, is_int=False, is_real=False, is_logical=False,
                    rank=-1, intent="out",
                ))
        elif isinstance(elem, IntegerType):
            host = std_to_host.get("ccpp_error_code", "errflg")
            out_infos.append(ChostArgInfo(
                hint="errflg", bare="errflg", host=host,
                std="ccpp_error_code",
                is_col_start=False, is_col_end=False,
                is_ncol=False, is_nz=False,
                is_errmsg=False, is_errflg=True, is_sname=False,
                is_char=False, is_int=True, is_real=False, is_logical=False,
                rank=0, intent="out",
            ))
    return out_infos


def _chost_maybe_inject_ncol(visible: list, infos: list, ncol_var: str) -> list:
    """Prepend a synthetic ncol arg-descriptor when ncol is needed but absent.

    Triggers when col_end is present (ncol = col_end - col_start + 1 idiom) OR
    when any horizontal array is present (its Fortran declaration needs ncol as
    the explicit dimension size in the BIND(C) interface).

    Returns the (possibly prepended) visible list.
    """
    has_col_end     = any(ai["is_col_end"]                       for ai in infos)
    has_horiz_array = any(ai["is_real"] and ai["rank"] >= 1      for ai in infos)
    ncol_in_visible = any(ai["is_ncol"]                          for ai in visible)
    if (has_col_end or has_horiz_array) and not ncol_in_visible:
        visible = [ChostArgInfo(
            hint=ncol_var, bare=ncol_var, host=ncol_var,
            std=CCPP_HORIZ_DIM_STD_NAME,
            is_col_start=False, is_col_end=False,
            is_ncol=True, is_nz=False, is_errmsg=False,
            is_errflg=False, is_sname=False,
            is_char=False, is_int=True, is_real=False, is_logical=False,
            rank=0, intent="in",
        )] + visible
    return visible


def _chost_maybe_inject_nz(visible: list, infos: list, std_to_host: dict) -> list:
    """Inject vertical dimension scalar args required by rank-2 arrays but not yet visible.

    When a rank-2 real arg has dim_nz pointing to a specific host variable (e.g. pverP
    for vertical_interface_dimension), that scalar must appear as a BIND(C) parameter.
    The canonical injection for the default nz_var is handled elsewhere; this function
    covers non-default vertical dimensions like vertical_interface_dimension.

    Returns the (possibly extended) visible list.
    """
    nz_hosts_present = {ai["host"] for ai in visible if ai["is_nz"] or ai.get("is_dim_scalar")}
    to_inject: dict = {}
    for ai in infos:
        if not (ai["is_real"] and ai["rank"] >= 2):
            continue
        dz = ai.get("dim_nz")
        if not dz or dz in nz_hosts_present:
            continue
        # Find the standard_name whose std_to_host value is dz.
        nz_std = next(
            (std for std, host in std_to_host.items()
             if host == dz and std in CCPP_VERTICAL_DIMENSIONS),
            None,
        )
        if nz_std and dz not in to_inject:
            to_inject[dz] = ChostArgInfo(
                hint=dz, bare=dz, host=dz, std=nz_std,
                is_col_start=False, is_col_end=False,
                is_ncol=False, is_nz=True, is_errmsg=False,
                is_errflg=False, is_sname=False,
                is_char=False, is_int=True, is_real=False, is_logical=False,
                rank=0, intent="in", dim_nz=None,
            )
            nz_hosts_present.add(dz)
    if to_inject:
        visible = list(to_inject.values()) + visible
    return visible


_LIFECYCLE = {
    "ccpp_register":              "register",
    "ccpp_init":                  "initialize",
    "ccpp_final":                 "finalize",
    "ccpp_physics_timestep_init": "timestep_initial",
    "ccpp_physics_timestep_final": "timestep_final",
    "ccpp_physics_run":           "run",
    "ccpp_physics_init":          "physics_initial",
    "ccpp_physics_final":         "physics_final",
}


def _lc_of(fn_name: str):
    """Return the lifecycle name for a bind-C function name, or None if not recognised."""
    for suffix, lc in _LIFECYCLE.items():
        if fn_name.endswith(suffix):
            return lc
    return None


def _chost_fn_name(camel_name: str, lc: str) -> str:
    """Return the chost counterpart name for a lifecycle phase.

    Built from camel_name/lc directly rather than string-munging the plain
    cap's own bind-C function name: since Stage 5 of the vocabulary-
    resolution redesign made the plain cap's own subroutine names bare
    (capgen-v1-style, no host prefix), the plain
    name alone no longer carries camel_name to derive this from. chost's
    own naming is xdsl_ccpp-specific (there's no capgen-v1 equivalent to
    align it with) and is deliberately left unchanged by that redesign --
    still host-prefixed, e.g. "Kessler_chost_physics_run".
    """
    return f"{camel_name}_chost_physics_{lc}"


def _suite_fn_groups_for(lc: str, suite_name: str, suite_descriptions: dict) -> list:
    """Return [(suite_fn_name, group_or_None), ...] for a given lifecycle.

    "run", "timestep_initial"/"timestep_final", and "physics_initial"/
    "physics_final" are all group-scoped -- one suite cap function per
    XML group, named suite_cap.py's own generated_subroutine_posfix
    convention (f"_{group_name}" for run, f"_timestep_init_{group_name}"
    for timestep_initial, f"_timestep_final_{group_name}" for
    timestep_final, f"_init_{group_name}" for physics_initial,
    f"_final_{group_name}" for physics_final). group_or_None is the
    originating XML group node for these -- chost-identity-collision:
    needed so a caller can resolve exactly which schemes feed this one
    suite cap function, instead of a flat, cross-suite, cross-group scan.
    Every other lifecycle stays a single flat function with no single
    originating group at all ("physics_initial"/"physics_final" are
    net-new lifecycles, not a moved "initialize"/"finalize" -- those stay
    flat, unchanged, and no longer emit any scheme calls at all -- see
    suite_cap.py's emit_scheme_calls). This is the same "run is special,
    everything else is flat" assumption already found and fixed in
    gpu_data_pass.py/gpu_ccpp_cap_pass.py.
    """
    groups = suite_descriptions.get(suite_name, [])
    if lc == "run":
        return [
            (f"{suite_name}{SUITE_FN_INFIX}_{grp.attributes['name']}", grp)
            for grp in groups
        ]
    if lc == "timestep_initial":
        return [
            (f"{suite_name}{SUITE_FN_INFIX}_timestep_init_{grp.attributes['name']}", grp)
            for grp in groups
        ]
    if lc == "timestep_final":
        return [
            (f"{suite_name}{SUITE_FN_INFIX}_timestep_final_{grp.attributes['name']}", grp)
            for grp in groups
        ]
    if lc == "physics_initial":
        return [
            (f"{suite_name}{SUITE_FN_INFIX}_init_{grp.attributes['name']}", grp)
            for grp in groups
        ]
    if lc == "physics_final":
        return [
            (f"{suite_name}{SUITE_FN_INFIX}_final_{grp.attributes['name']}", grp)
            for grp in groups
        ]
    return [(f"{suite_name}{SUITE_FN_INFIX}_{lc}", None)]


def _chost_callee_identities(pfn_hints, arg_attrs) -> "tuple[dict, dict]":
    """(local_to_std, local_to_dim_names) for a suite cap function's dummy
    arguments: the standard and dimension names the suite cap records on
    it (suite_arg_attrs), keyed by bare dummy-argument name. Read, not
    re-derived from scheme metadata: several schemes may use one local
    name for different standard names, and the suite cap renames such
    arguments."""
    local_to_std: dict = {}
    local_to_dim_names: dict = {}
    for hint, attrs in zip(pfn_hints, arg_attrs):
        if not hint:
            continue
        bare = hint
        if SUITE_ARG_STD_NAME in attrs:
            local_to_std[bare] = attrs[SUITE_ARG_STD_NAME]
        if SUITE_ARG_DIM_NAMES in attrs:
            local_to_dim_names[bare] = list(attrs[SUITE_ARG_DIM_NAMES])
    return local_to_std, local_to_dim_names


def _chost_arg_type(ai: dict):
    """The C-interop type of a chost arg descriptor (an MLIR type; see
    cpp_type_table.py).

    Numeric (int/real) cases go through the shared `c_numeric_type`
    decision table (`cpp_type_table.py`) that `print_cpp_header.py`'s
    `_c_param_type` also adapts onto (BACKLOG.md's `cpp-type-table-unify`).
    """
    if ai["is_ncol"] or ai["is_nz"]:
        return i32
    if ai["is_int"] and not ai["is_errflg"]:
        # Always rank-0/intent(in) by this call site's own convention --
        # every _chost_arg_info-constructed int arg is scalar (rank is
        # never advanced for is_int there). A DDT-member int ARRAY
        # (rank>0, via _chost_expand_ddt_arg) also reaches this branch
        # and, as today, still renders as plain "int" rather than "int*"
        # -- a pre-existing, unexercised gap this unification pass
        # preserves rather than silently changes.
        return c_numeric_type(kind="int", width=64, rank=0, intent="in")
    if ai["is_real"]:
        # Rank-0 real chost args are always passed by value, intent(in),
        # regardless of the scheme's own declared intent -- an existing
        # Fortran-generator convention, forced here rather than baked
        # into the shared table itself.
        real_intent = "in" if ai["rank"] == 0 else ai["intent"]
        return c_numeric_type(
            kind="real", width=ai.get("real_width", 64), rank=ai["rank"],
            intent=real_intent,
        )
    if ai.get("is_logical"):
        return i1
    buffer = MemRefType(i8, [DYNAMIC_INDEX])   # a character buffer
    if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
        return ReadOnlyType(buffer) if ai.get("intent") == "in" else buffer
    if ai["is_sname"] or ai["is_errmsg"]:
        return buffer
    if ai["is_errflg"]:
        return MemRefType(i32, [])   # by pointer
    return LLVMPointerType()


def _writable(t):
    """``t`` without read-only access (the State struct owns its memory)."""
    return t.inner if isinstance(t, ReadOnlyType) else t


# Map CCPP lifecycle names to scheme entry-point name suffixes.
_LC_TO_ENTRY_SUFFIX = {
    "run":              ("_run",),
    "initialize":       ("_init", "_initialize"),
    "timestep_initial": ("_timestep_initial",),
    "timestep_final":   ("_timestep_final",),
    "finalize":         ("_finalize",),
    "register":         ("_register",),
    # physics_initial/physics_final: the new group-scoped
    # ccpp_physics_init/ccpp_physics_final call schemes via the SAME
    # "_init"/"_finalize" scheme-table postfixes "initialize"/"finalize"
    # above already use (see suite_cap.py's group_phase_specs) -- without
    # these entries, _ddt_arg_intent's lookup below silently falls through
    # to its "not found" default ("inout"), which caused a DDT arg's real
    # intent=out to be lost, dropping it from the chost wrapper entirely
    # (confirmed via a real regression, examples/ddthost-shaped
    # ddt-intent-out-chost-ftn.mlir fixture, while verifying this stage).
    "physics_initial":  ("_init", "_initialize"),
    "physics_final":    ("_finalize",),
}

def _ddt_arg_intent(std_name: str, lc: str, meta_data: dict) -> str:
    """Return the intent of a DDT arg with the given standard_name for lifecycle lc.

    Scans all SCHEME arg tables whose name ends with the entry-point suffix that
    corresponds to ``lc`` (e.g. ``lc="timestep_final"`` → suffix ``"_timestep_final"``).
    If any matching table declares the arg ``intent=inout`` (most permissive), that
    wins immediately.  Returns ``"inout"`` when not found (safe default).
    """
    suffixes = _LC_TO_ENTRY_SUFFIX.get(lc, ())
    found: str | None = None
    for props in meta_data.values():
        if props.getAttr("type") != CCPPType.SCHEME:
            continue
        for tbl_name, atbl in props.arg_tables.items():
            if not any(tbl_name.endswith(s) for s in suffixes):
                continue
            for var in atbl.getFunctionArguments():
                if not (var.hasAttr("standard_name") and var.hasAttr("intent")):
                    continue
                if var.getAttr("standard_name").lower() != std_name:
                    continue
                intent = var.getAttr("intent")
                if intent == "inout":
                    return "inout"
                found = found or intent
    return found or "inout"


def _ddt_out_name(ddt_type_name: str, lc: str, meta_data: dict) -> "str | None":
    """Return the local variable name of an intent=out arg with the given DDT type.

    Scans scheme arg tables for lifecycle ``lc`` looking for an arg whose ``type``
    matches ``ddt_type_name`` and whose ``intent`` is ``"out"``.  Returns None when
    not found (e.g. the DDT appears as intent=inout in the inputs).
    """
    suffixes = _LC_TO_ENTRY_SUFFIX.get(lc, ())
    for props in meta_data.values():
        if props.getAttr("type") != CCPPType.SCHEME:
            continue
        for tbl_name, atbl in props.arg_tables.items():
            if not any(tbl_name.endswith(s) for s in suffixes):
                continue
            for var in atbl.getFunctionArguments():
                if not var.hasAttr("type") or not var.hasAttr("intent"):
                    continue
                if var.getAttr("type").lower() != ddt_type_name.lower():
                    continue
                if var.getAttr("intent") == "out":
                    return var.name
    return None


def _chost_fn_contexts(
    camel_name, bind_c_fns, suite_name, suite_descriptions, public_fns,
    ncol_var, local_to_std_fallback, std_to_host, kind_iso_map,
    meta_data=None, ddt_source_module=None, nz_var="nz",
):
    """Yield per-function context dicts for chost cap generation.

    Each dict contains the computed preamble values for one bind-C function:
    fn, cfn, lc, sfns, suite_fn, infos, out_infos, visible, ddt_locals,
    suite_call_pieces.

    When meta_data is provided, DDT-typed arguments are expanded into flat
    C-compatible args rather than raising an error.  ddt_locals maps each
    original DDT arg bare name to a local_info dict used to generate Fortran
    reconstruction code.  suite_call_pieces is a list parallel to the original
    pfn_hints, recording what to pass in the suite cap call for each arg.

    Functions with no recognised lifecycle or no matching suite cap are skipped.

    local_to_std/local_to_dim_names: for the suite cap function's own
    dummy arguments, the standard and dimension names the suite cap
    recorded on it (_chost_callee_identities); local_to_std_fallback
    (HOST/MODULE/DDT-only, built once in _chost_build_maps) covers the
    other names resolved here, e.g. DDT members.
    """
    # HOST/MODULE/DDT-only dim_names fallback (mirrors local_to_std_fallback's
    # own SCHEME-table exclusion in _chost_build_maps, same reasoning --
    # a scheme-declared bare name's dim_names must come from the
    # per-function scoped pass below, not this flat global scan).
    local_to_dim_names_fallback: dict = {}
    if meta_data is not None:
        for props in meta_data.values():
            if props.getAttr("type") == CCPPType.SCHEME:
                continue
            for atbl in props.arg_tables.values():
                for var in atbl.getFunctionArguments():
                    if var.hasAttr("dim_names") and var.name not in local_to_dim_names_fallback:
                        local_to_dim_names_fallback[var.name] = var.getAttr("dim_names")

    contexts = []
    for fn in bind_c_fns:
        fn_name = fn.sym_name.data
        lc = _lc_of(fn_name)
        if lc is None:
            continue
        sfn_groups = _suite_fn_groups_for(lc, suite_name, suite_descriptions)
        sfns = [name for name, _grp in sfn_groups]
        suite_fn = next((name for name, _grp in sfn_groups if name in public_fns), None)
        if suite_fn is None:
            continue
        _, pfn_out_types, pfn_types, pfn_hints, pfn_attrs = public_fns[suite_fn]
        # The callee's own dummy arguments are identified by what the suite
        # cap recorded; the HOST/MODULE/DDT fallback serves the other names
        # resolved here (DDT members, synthesized dimensions).
        callee_std, callee_dims = _chost_callee_identities(pfn_hints, pfn_attrs)
        local_to_std = {**local_to_std_fallback, **callee_std}
        local_to_dim_names = {**local_to_dim_names_fallback, **callee_dims}

        infos = []
        ddt_locals: dict = {}
        suite_call_pieces: list = []
        constituent_vars: list = []

        for h, t, h_attrs in zip(pfn_hints, pfn_types, pfn_attrs):
            bare = h or ""
            _ddt_type = None
            if isinstance(t, MemRefType) and isinstance(t.element_type, DerivedType):
                _ddt_type = t.element_type.type_name.data
            elif isinstance(t, DerivedType):
                _ddt_type = t.type_name.data

            if _ddt_type == _CONSTITUENT_DDT_NAME and isinstance(t, MemRefType):
                # Constituent DDT array — excluded from C++ function signature.
                # The chost cap owns a module-level allocatable for each one and
                # passes it directly to the suite cap register function.
                constituent_vars.append(bare)
                suite_call_pieces.append({
                    "kind": "constituent_mod_var",
                    "name": f"chost_{bare}",
                })
                continue

            if _ddt_type is not None and meta_data is not None:
                std = local_to_std.get(bare, "")
                original_intent = _ddt_arg_intent(std, lc, meta_data)
                member_ais, local_info = _chost_expand_ddt_arg(
                    bare, _ddt_type, meta_data,
                    local_to_std, std_to_host, kind_iso_map, ncol_var, nz_var,
                    original_intent=original_intent,
                )
                infos.extend(member_ais)
                ddt_locals[bare] = local_info
                suite_call_pieces.append({"kind": "ddt_local", "name": local_info["local_name"]})
            else:
                ai = _chost_arg_info(
                    h, t, local_to_std, std_to_host, kind_iso_map,
                    local_to_dim_names=local_to_dim_names, attrs=h_attrs,
                )
                # Only array args are narrowed to intent(in) (arg_decl), so a
                # scalar char arg's intent defaults to "inout".
                # Look up the actual intent from scheme metadata to get it right.
                if (ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]
                        and ai["intent"] == "inout" and meta_data is not None):
                    actual = _ddt_arg_intent(ai["std"], lc, meta_data)
                    if actual == "in":
                        ai["intent"] = "in"
                infos.append(ai)
                suite_call_pieces.append({"kind": "arg", "ai": ai})

        out_infos = _chost_out_infos(pfn_out_types, std_to_host)

        # ── intent=out DDT outputs (Gap 3) ────────────────────────────────────
        # For intent=out DDTs the MLIR encodes them as function *outputs* (not
        # inputs), so they do not appear in pfn_hints/pfn_types.  Detect them
        # here and expand into flat args just like intent=inout DDTs from inputs,
        # but skip the array allocate+fill in the copy-in phase (the scheme does
        # the allocation internally).
        ddt_out_locals: list = []
        if meta_data is not None:
            for otype in pfn_out_types:
                if not isinstance(otype, MemRefType):
                    continue
                elem = otype.element_type
                if not isinstance(elem, DerivedType):
                    continue
                ddt_type_name = elem.type_name.data
                prefix = _ddt_out_name(ddt_type_name, lc, meta_data)
                if prefix is None or prefix in ddt_locals:
                    continue
                member_ais, local_info = _chost_expand_ddt_arg(
                    prefix, ddt_type_name, meta_data,
                    local_to_std, std_to_host, kind_iso_map, ncol_var, nz_var,
                    original_intent="out",
                )
                infos.extend(member_ais)
                ddt_locals[prefix] = local_info
                ddt_out_locals.append(local_info["local_name"])

        # Resolve rank-3 arrays whose 3rd dimension has no HOST/MODULE-table
        # standard_name -- _chost_arg_info's own dim_n3 resolution only checks
        # std_to_host (chost-rank3-bindc's fix, HOST/MODULE tables only), so a
        # dimension declared ONLY on a SCHEME table (e.g. constadv's `q`'s 3rd
        # dim, number_of_ccpp_constituents, declared solely via the scheme's own
        # `ncnst` arg) is left unresolved there. That dimension's value is still
        # available here, though: a sibling scalar scheme arg in this exact
        # suite call already carries that same standard_name (resolved into
        # `infos` above via the per-function scoped local_to_std) -- reuse ITS
        # host name as the explicit-shape bound instead of falling back to
        # assumed-size, the same rank/class mismatch chost-rank3-bindc fixed
        # for the plain --bind-c path.
        for _ai in infos:
            if _ai["rank"] >= 3 and _ai["is_real"] and not _ai.get("dim_n3"):
                _dim_names = local_to_dim_names.get(_ai["bare"], [])
                for _d in _dim_names:
                    _d_lo = _d.lower()
                    if (_d_lo in CCPP_HORIZONTAL_DIMENSIONS
                            or _d_lo in CCPP_VERTICAL_DIMENSIONS):
                        continue
                    _sibling = next(
                        (s for s in infos
                         if s["is_int"] and s["rank"] == 0 and s["std"] == _d_lo),
                        None,
                    )
                    if _sibling is not None:
                        _ai["dim_n3"] = _sibling["host"]
                        break

        # Mark scalar ints that provide the 3rd dimension of a rank-3 array.
        # Reuses is_dim_scalar so they land in the State constructor automatically.
        _n3_hosts = {ai.get("dim_n3") for ai in infos if ai.get("dim_n3")}
        if _n3_hosts:
            for _ai in infos:
                if _ai["host"] in _n3_hosts and _ai["is_int"] and _ai["rank"] == 0:
                    _ai["is_dim_scalar"] = True

        visible = list(infos) + out_infos
        # Deduplicate by host name: two schemes may map different local names
        # (e.g. cols/col_start) to the same host variable.  Keep first occurrence
        # so the BIND(C) parameter list has no repeated entries.
        _seen: set = set()
        visible = [ai for ai in visible
                   if not (ai["host"] in _seen or _seen.add(ai["host"]))]
        visible = _chost_maybe_inject_ncol(visible, infos, ncol_var)
        visible = _chost_maybe_inject_nz(visible, infos, std_to_host)
        visible = _chost_canonical_order(visible)
        contexts.append({
            "fn": fn,
            "cfn": _chost_fn_name(camel_name, lc),
            "lc": lc,
            "sfns": sfns,
            "suite_fn": suite_fn,
            "infos": infos,
            "out_infos": out_infos,
            "visible": visible,
            "ddt_locals": ddt_locals,
            "suite_call_pieces": suite_call_pieces,
            "ddt_out_locals": ddt_out_locals,
            "constituent_vars": constituent_vars,
        })
    return contexts


class CPPInteropCap(ModulePass):
    """MLIR pass that generates a BIND(C) chost Fortran cap + C++ header/wrapper.

    Runs after generate-ccpp-cap. When any host/module TablePropertiesOp in the
    ccpp module carries language = "c++", builds a CHostCapOp carrying BIND(C)
    Fortran, a C++ header, and a C++ wrapper that delegate to the regular ccpp
    cap module generate-ccpp-cap just produced.

    Re-derives suite_descriptions/meta_data/ddt_source_module from the IR (the
    same way generate-ccpp-cap itself re-derives them from generate-suite-cap's
    output) rather than receiving them as a direct handoff, since passes only
    communicate through the shared IR. Also re-locates the just-generated ccpp
    cap module by name (it is guaranteed to be present in the block, inserted
    by generate-ccpp-cap immediately before this pass runs), and excludes it
    from the public_fns scan so the result matches exactly what generate-ccpp-cap
    itself saw when it originally called this code inline (before the module
    existed in the block).
    """

    name = "generate-cpp-cap"

    def _generate_chost_cap_module(
        self, suite_descriptions, meta_data, cap_mod, ccpp_mod,
        public_fns=None, ddt_source_module=None,
    ):
        """Build a CHostCapOp carrying the BIND(C) chost Fortran module and C++ header.

        The chost cap accepts all physics arrays as explicit pointer arguments so
        that a C++ host model can own the data and call Fortran physics without a
        Fortran host module.  The generated module delegates internally to the
        regular suite cap subroutines.

        Called when the host declares ``language = "c++``.
        """
        # Derive the CamelCase prefix from the regular cap module name.
        # e.g. "Kessler_ccpp_cap" → "Kessler"
        cap_mod_name = cap_mod.sym_name.data
        assert cap_mod_name.endswith("_ccpp_cap"), (
            f"Expected cap module name to end with '_ccpp_cap', got '{cap_mod_name}'"
        )
        camel_name = cap_mod_name[: -len("_ccpp_cap")]
        mod_name = camel_name + "_ccpp_chost_cap"

        # Collect BIND(C) function definitions from the cap module (ordered).
        bind_c_fns = [
            op for op in cap_mod.body.ops
            if isa(op, func.FuncOp)
            and not op.is_declaration
            and "bind_c" in op.attributes
        ]

        # The suite cap module name is the first suite key + "_cap".
        # e.g. "kessler_suite" → "kessler_suite_cap"
        suite_names = list(suite_descriptions.keys())
        suite_cap_mod_name = suite_names[0] + "_cap" if suite_names else ""

        public_fns = public_fns or {}

        # Metadata maps + fn_ctxs computed once and shared across all three
        # builders below -- previously each independently recomputed the
        # same std_to_host/local_to_std/ncol_var/nz_var/kind_iso_map maps
        # and called _chost_fn_contexts on identical inputs.
        std_to_host, local_to_std_fallback, ncol_var, nz_var = _chost_build_maps(meta_data)
        kind_iso_map = _chost_kind_iso_map(ccpp_mod) if ccpp_mod is not None else {}
        suite_name = next(iter(suite_descriptions), "")
        fn_ctxs = _chost_fn_contexts(
            camel_name, bind_c_fns, suite_name, suite_descriptions, public_fns,
            ncol_var, local_to_std_fallback, std_to_host, kind_iso_map,
            meta_data=meta_data, ddt_source_module=ddt_source_module, nz_var=nz_var,
        )

        ftn_body_ops = self._build_chost_ftn_text(
            camel_name, mod_name, suite_cap_mod_name, bind_c_fns,
            public_fns, fn_ctxs, ncol_var, nz_var,
            ddt_source_module=ddt_source_module,
        )
        cpp_body_ops = self._build_chost_cpp_text(mod_name, fn_ctxs)
        wrapper_body_ops = self._build_chost_wrapper_body(
            camel_name, mod_name, fn_ctxs, ncol_var, nz_var,
        )

        return CHostCapOp(ftn_body_ops, cpp_body_ops, mod_name, wrapper_body_ops)

    def _build_chost_ftn_text(
        self, camel_name, mod_name, suite_cap_mod_name, bind_c_fns,
        public_fns, fn_ctxs, ncol_var, nz_var,
        ddt_source_module=None,
    ):
        """Build the complete Fortran BIND(C) chost cap module as typed ops.

        Returns ``CHostCapOp.ftn_body``: one builtin.ModuleOp, printed like
        every other cap module -- USE stubs, the BIND(C) struct type
        (DerivedTypeDefOp), module variables (ModuleVarOp), and one BIND(C)
        func.FuncOp (cap_shared.fixed_interface_fn) per lifecycle routine
        and constituent query, built from statement ops
        (AssignOp/CallStatementOp/CToFortranStringCopyOp/
        FortranToCStringCopyOp/scf.IfOp/DoLoopOp/AllocateOp).

        ``fn_ctxs``/``ncol_var``/``nz_var`` are computed once in
        ``_generate_chost_cap_module`` and shared with
        ``_build_chost_cpp_text``/``_build_chost_wrapper_body`` -- previously
        each of the three builders independently recomputed the same
        metadata maps and called ``_chost_fn_contexts`` on identical inputs.
        """

        _int = MemRefType(i32, [])
        _string = MemRefType(i8, [DYNAMIC_INDEX])

        def ftn_arg(ai):
            """(name, type, intent, flags, explicit extents) of one BIND(C)
            dummy argument; the printer spells the C-interop declaration
            (integer(c_int), value / real(c_double), target / c_char)."""
            host = ai["host"]
            if ai["is_ncol"] or ai["is_nz"] or (ai["is_int"] and not ai["is_errflg"]):
                return (host, _int, "in", (), None)
            if ai["is_real"]:
                real = f32 if ai.get("real_width", 64) == 32 else f64
                rank = ai["rank"]
                if rank == 0:
                    return (host, MemRefType(real, []), "in", (), None)
                _dn = ai.get("dim_ncol") or ncol_var
                _dz = ai.get("dim_nz")   or nz_var
                # rank >= 3: explicit shape for the 3rd dim when known so the
                # array can be passed to assumed-shape (:,:,:) suite cap dummies;
                # else assumed size, ().
                _d3 = ai.get("dim_n3")
                extents = [(_dn,), (_dz,), (_d3,) if _d3 else ()][:rank]
                return (host, MemRefType(real, [DYNAMIC_INDEX] * rank), ai["intent"], (),
                        extents)
            if ai.get("is_logical"):
                return (host, MemRefType(i1, []), ai["intent"], (), None)
            if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
                return (host, _string, ai["intent"], (), None)
            if ai["is_sname"] or ai["is_errmsg"]:
                return (host, _string, "out", (), None)
            if ai["is_errflg"]:
                return (host, _int, "out", (), None)
            raise ValueError(f"chost cap: unclassified argument {host!r}")

        def bind_c_fn(name, args, body, *, locals_=(), result=None):
            """A fixed-interface BIND(C) routine; args as ftn_arg returns."""
            fn = fixed_interface_fn(
                name, [a[:4] for a in args], body, locals_=locals_, result=result,
            )
            fn.attributes["bind_c"] = builtin.UnitAttr()
            fn.attributes["bind_c_extents"] = bind_c_extents_attr([a[4] for a in args])
            return fn

        def local(name, elem, shape=()):
            alloca = memref.AllocaOp.get(elem, shape=list(shape))
            name_local(alloca, name)
            return alloca

        # Expression builders for the routine bodies.
        def var(name: str, result_type=None):
            return VarRefExprOp(name, result_type=result_type)

        def member(base: str, path: tuple):
            """base%path[0]%path[1]..."""
            op = var(base)
            for name in path:
                op = MemberAccessExprOp(op, name)
            return op

        def convert(x_op, kind: str, intrinsic: str = "real"):
            """real(x, kind) / logical(x, kind) / int(x, kind)."""
            return CallExprOp(intrinsic, [x_op, var(kind)], result_type=i32)

        def const(value: int):
            return arith.ConstantOp(IntegerAttr.from_int_and_width(value, 32))

        def assign(lhs_op, rhs_op):
            return AssignOp(lhs_op=lhs_op, rhs_op=rhs_op)

        def call_arg(ai):
            """How the chost routine passes one of its arguments on."""
            if ai["is_col_start"] or ai["is_col_end"]:
                return var(ai["host"])
            if ai["is_real"] and ai["rank"] == 0:
                return convert(var(ai["host"]), "kind_phys")
            if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
                return var(f"{ai['host']}_f")
            return var(ai["host"])

        # ── Collect suite cap functions referenced ──────────────────────────────
        used_suite_fns: list = []
        for ctx in fn_ctxs:
            for sfn in ctx["sfns"]:
                if sfn not in used_suite_fns and sfn in public_fns:
                    used_suite_fns.append(sfn)

        # ── Collect DDT types that need USE statements ──────────────────────────
        ddt_uses: dict = {}  # type_name → module_name
        for ctx in fn_ctxs:
            for li in ctx.get("ddt_locals", {}).values():
                tn = li["ddt_type"]
                if tn not in ddt_uses and ddt_source_module:
                    mod = ddt_source_module.get(tn)
                    if mod:
                        ddt_uses[tn] = mod

        # ── Collect constituent DDT array variables across all lifecycles ───────
        all_constituent_vars: list = []
        _seen_cv: set = set()
        for ctx in fn_ctxs:
            for cv in ctx.get("constituent_vars", []):
                if cv not in _seen_cv:
                    _seen_cv.add(cv)
                    all_constituent_vars.append(cv)

        # ── Module specification part ────────────────────────────────────────
        # A builtin.ModuleOp printed like every other cap module: USE lines
        # from llvm.GlobalOp stubs (plus ccpp_kinds and iso_c_binding, which
        # the printer adds), the BIND(C) struct type, module variables, and
        # a public line per public routine.
        def use_stub(name: str, module: str):
            stub = llvm.GlobalOp(
                llvm.LLVMArrayType.from_size_and_type(1, i8), name, "external",
            )
            stub.attributes["module"] = builtin.StringAttr(module)
            return stub

        module_ops: list = [use_stub(tn, mod) for tn, mod in sorted(ddt_uses.items())]
        if all_constituent_vars:
            module_ops.append(use_stub(_CONSTITUENT_DDT_NAME, _CCPP_CONSTITUENT_MOD))
        module_ops += [use_stub(sfn, suite_cap_mod_name) for sfn in used_suite_fns]
        if all_constituent_vars:
            # BIND(C) struct mirroring CcppConstituentInfo on the C++ side.
            module_ops.append(DerivedTypeDefOp(
                "chost_constituent_info_t",
                [
                    DdtComponentDeclOp(fname, "character", kind="c_char",
                                       fixed_dim=flen + 1) if fkind == "char"
                    else DdtComponentDeclOp(fname, "real", kind="c_double") if fkind == "real"
                    else DdtComponentDeclOp(fname, "logical", kind="c_bool")
                    for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS
                ],
                is_public=True, bind_c=True,
            ))
            module_ops += [
                ModuleVarOp(f"chost_{cv}", "type", ddt_name=_CONSTITUENT_DDT_NAME, rank=1)
                for cv in all_constituent_vars
            ]

        # ── Subroutines ─────────────────────────────────────────────────────────
        for ctx in fn_ctxs:
            cfn, sfns = ctx["cfn"], ctx["sfns"]
            infos, out_infos, visible = ctx["infos"], ctx["out_infos"], ctx["visible"]
            ddt_locals      = ctx.get("ddt_locals", {})
            suite_call_pcs  = ctx.get("suite_call_pieces", [])

            has_errmsg = any(ai["is_errmsg"] for ai in visible)
            has_sname  = any(ai["is_sname"]  for ai in visible)
            plain_char_args = [ai for ai in visible
                               if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]]
            sn = next((ai["host"] for ai in visible if ai["is_sname"]), None)
            em = next((ai["host"] for ai in visible if ai["is_errmsg"]), None)

            # ── Declarations ─────────────────────────────────────────────────
            args = [ftn_arg(ai) for ai in visible]
            locals_: list = []
            if has_errmsg or has_sname or plain_char_args:
                locals_.append(local("i", i32))
            if has_sname:
                locals_.append(local(f"{sn}_f", i8, [CCPP_SCHEME_NAME_LEN]))
            if has_errmsg:
                locals_.append(local(f"{em}_f", i8, [CCPP_ERRMSG_LEN]))
            for ai in plain_char_args:
                cl = ai.get("char_len") or CCPP_ERRMSG_LEN
                locals_.append(local(f"{ai['host']}_f", i8, [cl]))
            for li in ddt_locals.values():
                locals_.append(local(li["local_name"], DerivedType(li["ddt_type"])))

            # ── Body initialization ───────────────────────────────────────────
            body_ops: list = []
            if has_errmsg:
                body_ops.append(assign(var(f"{em}_f"), StringLiteralExprOp(" ")))
            if has_sname:
                body_ops.append(assign(var(f"{sn}_f"), StringLiteralExprOp(" ")))
            if any(ai["is_errflg"] for ai in visible):
                ef = next(ai["host"] for ai in visible if ai["is_errflg"])
                body_ops.append(assign(var(ef), const(0)))
            # C→F copy-in for plain character(len=N) args (intent=in or intent=inout)
            for ai in plain_char_args:
                if ai.get("intent") in ("in", "inout"):
                    h = ai["host"]
                    body_ops.append(CToFortranStringCopyOp(c_var=h, f_var=f"{h}_f"))

            # ── DDT copy-in: scalars assigned, arrays allocated and filled ────
            for li in ddt_locals.values():
                lname = li["local_name"]
                # Character members are not in the C interface; initialise blank.
                for mn in li.get("char_member_blanks", []):
                    body_ops.append(assign(member(lname, mn), StringLiteralExprOp(" ")))
                for ai in li["member_ais"]:
                    mn = ai["_ddt_member"]
                    fn_ = ai["bare"]
                    if ai["rank"] == 0:
                        body_ops.append(assign(member(lname, mn), var(fn_)))
                    else:
                        dims = [ai.get("dim_ncol") or ncol_var, ai.get("dim_nz") or nz_var,
                                ai.get("dim_n3")][:ai["rank"]]
                        if None in dims:
                            raise ValueError(
                                f"chost cap: DDT member {'%'.join((lname, *mn))} has rank "
                                f"{ai['rank']} but no known extent for dimension 3"
                            )
                        if ai["intent"] != "out":
                            # intent=out: scheme allocates internally; skip pre-alloc.
                            body_ops.append(AllocateOp(
                                target_op=member(lname, mn), dim_ops=[var(d) for d in dims],
                            ))
                            body_ops.append(assign(
                                member(lname, mn), convert(var(fn_), "kind_phys"),
                            ))

            # ── Suite cap calls ───────────────────────────────────────────────
            for sfn_i in sfns:
                if sfn_i not in public_fns:
                    continue
                if suite_call_pcs:
                    call_ops = [
                        var(piece["name"]) if piece["kind"] in ("ddt_local", "constituent_mod_var")
                        else call_arg(piece["ai"])
                        for piece in suite_call_pcs
                    ]
                else:
                    call_ops = [call_arg(ai) for ai in infos]
                # intent=out DDT locals come before errmsg/errflg in the call.
                call_ops += [var(n) for n in ctx.get("ddt_out_locals", [])]
                # Output args (suite cap output order: errmsg_f / scheme_name_f / errflg)
                call_ops += [
                    var(f"{oai['host']}_f") if oai["is_errmsg"] or oai["is_sname"]
                    else var(oai["host"])
                    for oai in out_infos
                ]
                body_ops.append(CallStatementOp(sfn_i, arg_ops=call_ops))

            # ── DDT cleanup: writeback inout arrays ───────────────────────────
            # No explicit deallocate here: lname is a local, non-SAVE derived-
            # type variable, and every ultimate allocatable component still
            # allocated when this subroutine returns is deallocated
            # automatically per the Fortran standard's own local-variable
            # cleanup rules -- an explicit deallocate immediately before that
            # already-scheduled cleanup is redundant at best, and confirmed
            # via a real CI runtime failure (capgen_cxx_host: "double free or
            # corruption (out)" inside CapgenChost_chost_physics_physics_initial,
            # the first time an intent=out DDT arg -- allocated inside the
            # callee, not by this wrapper's own copy-in -- went through this
            # exact cleanup path) to risk a genuine double free at worst.
            for li in ddt_locals.values():
                lname = li["local_name"]
                for ai in li["array_ais"]:
                    mn  = ai["_ddt_member"]
                    fn_ = ai["bare"]
                    if ai["intent"] != "in":
                        c_real = "c_float" if ai.get("real_width", 64) == 32 else "c_double"
                        body_ops.append(assign(var(fn_), convert(member(lname, mn), c_real)))

            # ── F→C string copy loops ─────────────────────────────────────────
            if has_sname:
                body_ops.append(FortranToCStringCopyOp(c_var=sn, f_var=f"{sn}_f"))
            if has_errmsg:
                body_ops.append(FortranToCStringCopyOp(c_var=em, f_var=f"{em}_f"))
            for ai in plain_char_args:
                if ai.get("intent") in ("out", "inout"):
                    h = ai["host"]
                    body_ops.append(FortranToCStringCopyOp(c_var=h, f_var=f"{h}_f"))

            module_ops.append(bind_c_fn(cfn, args, body_ops, locals_=locals_))

        # ── Constituent query functions ──────────────────────────────────────────
        # Every local/module variable name built below must NOT start with a
        # leading underscore ("chost_", not "_chost_") -- a bare identifier
        # beginning with "_" is invalid Fortran (names must start with a
        # letter; confirmed directly against gfortran, which rejects it
        # unconditionally as "Invalid character in name", not a style
        # preference or GNU-extension-gated restriction). This constituent-
        # query code is the only place in the whole chost cap generator that
        # ever uses "_chost_"-prefixed names as *bare* identifiers rather
        # than as part of a longer, letter-led name -- confirmed the sole
        # root cause of constadv/constprop's compile failures.
        if all_constituent_vars:
            nc_body: list = [assign(var("n"), const(0))]
            for cv in all_constituent_vars:
                nc_body.extend(_scf_if(
                    _allocated_cond(f"chost_{cv}"),
                    [assign(var("n"), arith.AddiOp(
                        var("n", i32),
                        convert(CallExprOp("size", [var(f"chost_{cv}")]), "c_int", "int"),
                    ))],
                ))
            module_ops.append(bind_c_fn(
                f"{mod_name}_nconstituents", [], nc_body, result=local("n", i32),
            ))

            gci_body: list = [assign(var("chost_idx"), const(0))]
            for cv in all_constituent_vars:
                inner_do_body: list = [
                    assign(var("chost_idx"), arith.AddiOp(var("chost_idx", i32), const(1))),
                    *_scf_if(
                        _int_var_cmp("chost_idx", "n", "sgt"),
                        [ReturnStmtOp()],
                    ),
                ]
                for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS:
                    accessor = _CONSTITUENT_ACCESSORS[fname]
                    src = f"chost_v_{fname}"

                    def dst(fname=fname):
                        """buf(chost_idx)%<field>"""
                        return MemberAccessExprOp(
                            IndexExprOp(var("buf"), [var("chost_idx")]), fname)

                    def element(cv=cv):
                        """chost_<cv>(chost_i)"""
                        return IndexExprOp(var(f"chost_{cv}"), [var("chost_i")])

                    if fname == "mix_ratio_type":
                        # No 1:1 accessor -- derive 'dry'/'wet'/'moist' from
                        # the three mutually-exclusive predicates instead
                        # (see _CONSTITUENT_ACCESSORS' own comment).
                        inner_do_body.append(assign(var(src), StringLiteralExprOp("")))
                        for _pred, _label in (
                            ("is_dry", "dry"), ("is_wet", "wet"), ("is_moist", "moist"),
                        ):
                            inner_do_body.append(DdtMethodCallOp(
                                obj_expr_op=element(), method=_pred,
                                arg_ops=[var("chost_v_mix_pred"), var("chost_errcode"),
                                         var("chost_errmsg")],
                            ))
                            inner_do_body.extend(_scf_if(
                                var("chost_v_mix_pred", i1),
                                [assign(var(src), StringLiteralExprOp(_label))],
                            ))
                    elif accessor is None:
                        inner_do_body.append(assign(var(src), StringLiteralExprOp("")))
                    else:
                        inner_do_body.append(DdtMethodCallOp(
                            obj_expr_op=element(), method=accessor,
                            arg_ops=[var(src), var("chost_errcode"), var("chost_errmsg")],
                        ))
                    if fkind == "char":
                        inner_do_body.append(assign(var("chost_slen"), CallExprOp(
                            "min", [CallExprOp("len_trim", [var(src)]), const(flen)],
                        )))
                        inner_do_body.append(DoLoopOp("chost_j", var("chost_slen"), [assign(
                            IndexExprOp(dst(), [var("chost_j")]),
                            IndexExprOp(var(src), [SliceExprOp(var("chost_j"), var("chost_j"))]),
                        )]))
                        inner_do_body.append(assign(
                            IndexExprOp(dst(), [CallExprOp("min", [
                                arith.AddiOp(var("chost_slen", i32), const(1)), const(flen + 1),
                            ])]),
                            var("c_null_char"),
                        ))
                    elif fkind == "real":
                        inner_do_body.append(assign(dst(), convert(var(src), "c_double")))
                    else:  # logical
                        inner_do_body.append(assign(dst(), convert(var(src), "c_bool", "logical")))
                gci_body.extend(_scf_if(
                    _allocated_cond(f"chost_{cv}"),
                    [DoLoopOp(
                        "chost_i", CallExprOp("size", [var(f"chost_{cv}")]), inner_do_body,
                    )],
                ))
            # One temporary per struct field, typed like the field itself.
            _field_temps = [
                local(f"chost_v_{fname}", *(
                    (i8, [flen]) if fkind == "char"
                    else (RealKindType(CCPP_KIND_PHYS), []) if fkind == "real"
                    else (i1, [])
                ))
                for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS
            ]
            module_ops.append(bind_c_fn(
                f"{mod_name}_get_constituent_info",
                [("buf", MemRefType(DerivedType("chost_constituent_info_t"), [DYNAMIC_INDEX]),
                  "out", (), "n"),
                 ("n", _int, "in", (), "")],
                gci_body,
                locals_=[
                    *(local(n, i32) for n in
                      ("chost_idx", "chost_j", "chost_slen", "chost_i", "chost_errcode")),
                    local("chost_errmsg", i8, [CCPP_ERRMSG_LEN]),
                    local("chost_v_mix_pred", i1),
                    *_field_temps,
                ],
            ))

        return [builtin.ModuleOp(module_ops, sym_name=builtin.StringAttr(mod_name))]

    def _build_chost_cpp_text(self, mod_name, fn_ctxs):
        """Build the complete C++ header for the chost cap as typed ops.
        Returns a list of ops for ``CHostCapOp.cpp_body``.

        The fixed banner/``#pragma once`` preamble is not part of this
        list -- it's identical across every generated header (this one and
        the regular ``<HostName>_ccpp_cap.h``), so ``print_cpp_header.py``
        writes it once itself rather than modeling it as generated content.

        ``fn_ctxs`` is computed once in ``_generate_chost_cap_module`` and
        shared with ``_build_chost_ftn_text``/``_build_chost_wrapper_body``
        -- previously each of the three builders independently recomputed
        the same metadata maps and called ``_chost_fn_contexts`` on
        identical inputs.
        """
        all_constituent_vars_cpp: list = []
        _seen_cv_cpp: set = set()
        for ctx in fn_ctxs:
            for cv in ctx.get("constituent_vars", []):
                if cv not in _seen_cv_cpp:
                    _seen_cv_cpp.add(cv)
                    all_constituent_vars_cpp.append(cv)

        proto_ops: list = []
        for ctx in fn_ctxs:
            cfn, visible = ctx["cfn"], ctx["visible"]
            proto_ops.append(CFunctionSigOp(
                fn_name=cfn,
                param_names=[ai["host"] for ai in visible],
                param_types=[_chost_arg_type(ai) for ai in visible],
                param_comments=["" for _ in visible],
                body_ops=[],
            ))

        body_ops: list = [ExternCGuardOp(body_ops=proto_ops)]

        if all_constituent_vars_cpp:
            field_ops: list = []
            for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS:
                if fkind == "char":
                    field_ops.append(CppFieldDeclOp(fname, MemRefType(i8, [flen + 1])))
                elif fkind == "real":
                    field_ops.append(CppFieldDeclOp(fname, f64))
                else:  # logical
                    field_ops.append(CppFieldDeclOp(fname, i1))
            body_ops.append(CppIncludeOp(header="stdbool.h"))
            body_ops.append(CppStructDefOp(
                struct_name=_CONSTITUENT_INFO.type_name.data, member_ops=field_ops
            ))
            body_ops.append(ExternCGuardOp(body_ops=[
                CFunctionSigOp(
                    fn_name=f"{mod_name}_nconstituents", return_type=i32,
                    param_names=[], param_types=[], param_comments=[], body_ops=[],
                ),
                CFunctionSigOp(
                    fn_name=f"{mod_name}_get_constituent_info",
                    param_names=["buf", "n"],
                    param_types=[MemRefType(_CONSTITUENT_INFO, [DYNAMIC_INDEX]), i32],
                    param_comments=["", ""], body_ops=[],
                ),
            ]))

        return body_ops

    def _build_chost_wrapper_body(self, camel_name, mod_name, fn_ctxs, ncol_var, nz_var):
        """Build the C++ ergonomics wrapper (.hpp) for the chost cap as
        typed ops. Returns a list of ops for ``CHostCapOp.wrapper_body``.

        Produces a header-only wrapper with:
        - A ``Status`` struct carrying an int code and std::string message.
        - Per-lifecycle named arg structs (e.g. ``RunArgs``) — errmsg/errflg/
          scheme_name are excluded and handled internally.
        - ``inline`` free functions inside ``namespace <camel_name>_chost``.
        - A ``State`` struct aggregating fields across all lifecycles, with
          a constructor, a ``std::vector``-backed ``allocate()``, and
          designated-initializer convenience overloads.

        The fixed banner/pragma/includes are not part of this list -- 100%
        derivable from ``mod_name``, ``print_cpp_header.py``'s
        ``_cpp_wrapper_banner`` writes them directly. Everything else
        builds from statement ops (CppStructDefOp/CFunctionSigOp/
        CppCallStatementOp/CppConstructorOp/CppBraceInitCallOp/LocalVarOp/
        ReturnStmtOp/DdtMethodCallOp/AssignOp/scf.if), expression ops,
        and CommentOp/BlankLineOp for layout; no C++ text.

        ``fn_ctxs`` is computed once in ``_generate_chost_cap_module`` and
        shared with ``_build_chost_ftn_text``/``_build_chost_cpp_text`` --
        previously each of the three builders independently recomputed the
        same metadata maps and called ``_chost_fn_contexts`` on identical
        inputs.
        """
        ns_name = f"{camel_name}_chost"

        _CPP_FN_NAME = {"register": "do_register"}  # 'register' is a C++ keyword

        def struct_name(lc):
            return "".join(w.capitalize() for w in lc.split("_")) + "Args"

        # body_ops is the ops list for CppNamespaceOp's body.
        body_ops: list = []
        emit = body_ops.append

        def blank():
            emit(BlankLineOp())

        def banner(title: str):
            """A section banner: // ── title ─────..."""
            emit(CommentOp([f"── {title} " + "─" * max(1, 72 - len(title))]))

        def var(name: str, result_type=None):
            return VarRefExprOp(name, result_type=result_type)

        def const(value: int, result_type=i32):
            return arith.ConstantOp(IntegerAttr(value, result_type))

        blank()
        emit(CppStructDefOp(
            "Status",
            member_ops=[
                CppFieldDeclOp("code", i32, type_width=11),
                CppFieldDeclOp("message", OwnedStringType(), type_width=11),
            ],
            is_pod=False,
            method_ops=[CFunctionSigOp(
                fn_name="ok", return_type=i1, is_const=True,
                param_names=[], param_types=[], param_comments=[],
                body_ops=[ReturnStmtOp(value_op=arith.CmpiOp(var("code", i32), const(0), "eq"))],
            )],
        ))

        # Collect constituent vars across all lifecycles for this wrapper
        all_constituent_vars_hpp: list = []
        _seen_cv_hpp: set = set()
        fn_ctxs_hpp = fn_ctxs
        for ctx in fn_ctxs_hpp:
            for cv in ctx.get("constituent_vars", []):
                if cv not in _seen_cv_hpp:
                    _seen_cv_hpp.add(cv)
                    all_constituent_vars_hpp.append(cv)

        if all_constituent_vars_hpp:
            blank()
            emit(CommentOp([
                "── constituent query " + "─" * 53,
                "CcppConstituentInfo is declared in the included .h file.",
                "Use nconstituents() + get_constituents() after do_register().",
            ]))
            blank()
            emit(CFunctionSigOp(
                fn_name="nconstituents", return_type=i32, is_inline=True,
                param_names=[], param_types=[], param_comments=[],
                body_ops=[ReturnStmtOp(value_op=CallExprOp(f"{mod_name}_nconstituents"))],
            ))
            blank()
            emit(CFunctionSigOp(
                fn_name="get_constituents", return_type=OwnedArrayType(_CONSTITUENT_INFO),
                is_inline=True,
                param_names=[], param_types=[], param_comments=[],
                body_ops=[
                    LocalVarOp("n", i32, init_op=CallExprOp("nconstituents")),
                    LocalVarOp("v", OwnedArrayType(_CONSTITUENT_INFO),
                               size_op=CastExprOp(var("n", i32), IndexType())),
                    *_scf_if(arith.CmpiOp(var("n", i32), const(0), "sgt"), [
                        CppCallStatementOp(f"{mod_name}_get_constituent_info", call_arg_ops=[
                            MethodCallExprOp(var("v"), "data"), var("n"),
                        ]),
                    ]),
                    ReturnStmtOp(value_op=var("v")),
                ],
            ))

        lc_data: list = []   # (cpp_fn, struct_args) per lifecycle, for State generation

        for ctx in fn_ctxs_hpp:
            cfn, lc, visible = ctx["cfn"], ctx["lc"], ctx["visible"]

            has_errmsg  = any(ai["is_errmsg"] for ai in visible)
            has_errflg  = any(ai["is_errflg"] for ai in visible)
            has_sname   = any(ai["is_sname"]  for ai in visible)

            # Physics args go into the struct; output-control args are handled internally.
            struct_args = [
                ai for ai in visible
                if not ai["is_errmsg"] and not ai["is_errflg"] and not ai["is_sname"]
            ]

            cpp_fn = _CPP_FN_NAME.get(lc, lc)
            sn     = struct_name(lc)
            lc_data.append((cpp_fn, struct_args))

            # ── Section header ─────────────────────────────────────────────────
            blank()
            banner(lc)
            blank()

            # ── Arg struct (only if there are physics args) ────────────────────
            if struct_args:
                emit(CppStructDefOp(
                    sn,
                    member_ops=[
                        CppFieldDeclOp(ai["host"], _chost_arg_type(ai), type_width=16)
                        for ai in struct_args
                    ],
                ))
                blank()
                param_names  = ["a"]
                param_types  = [ReadOnlyType(DerivedType(sn))]
            else:
                param_names  = []
                param_types  = []

            # ── Internal buffers ───────────────────────────────────────────────
            # +1 on each: the Fortran side writes a null terminator at
            # len_trim(...)+1, which is one past the end of a buffer sized
            # exactly CCPP_*_LEN when the string fully fills it.
            # Declared as an aligned block (type, name columns).
            fn_body_ops: list = []
            aligned = {"type_width": 6, "name_width": 16}
            if has_sname:
                fn_body_ops.append(LocalVarOp(
                    "scheme_name", MemRefType(i8, [CCPP_SCHEME_NAME_LEN + 1]), zero_init=True,
                    **aligned,
                ))
            if has_errmsg:
                fn_body_ops.append(LocalVarOp(
                    "errmsg", MemRefType(i8, [CCPP_ERRMSG_LEN + 1]), zero_init=True, **aligned,
                ))
            if has_errflg:
                fn_body_ops.append(LocalVarOp("errflg", i32, init_op=const(0), **aligned))

            # ── C function call ────────────────────────────────────────────────
            call_arg_ops = []
            for ai in visible:
                if ai["is_errmsg"]:
                    call_arg_ops.append(VarRefExprOp("errmsg"))
                elif ai["is_errflg"]:
                    # The C function takes the error flag by pointer.
                    call_arg_ops.append(AddressOfExprOp(VarRefExprOp("errflg")))
                elif ai["is_sname"]:
                    call_arg_ops.append(VarRefExprOp("scheme_name"))
                else:
                    call_arg_ops.append(MemberAccessExprOp(VarRefExprOp("a"), ai["host"]))
            fn_body_ops.append(CppCallStatementOp(callee=cfn, call_arg_ops=call_arg_ops))

            # ── Return ─────────────────────────────────────────────────────────
            # A Status: the error flag, and the message if it is set.
            if has_errflg and has_errmsg:
                status = StructLiteralExprOp([
                    var("errflg"),
                    ConditionalExprOp(var("errflg"), var("errmsg"), StringLiteralExprOp("")),
                ])
            else:
                status = StructLiteralExprOp([const(0), StringLiteralExprOp("")])
            fn_body_ops.append(ReturnStmtOp(value_op=status))

            emit(CFunctionSigOp(
                fn_name=cpp_fn, return_type=DerivedType("Status"), is_inline=True,
                param_names=param_names, param_types=param_types,
                param_comments=[""] * len(param_names),
                body_ops=fn_body_ops,
            ))

        # ── State struct + overloads ──────────────────────────────────────────
        # Collect all physics fields across all lifecycles, excluding col_start/col_end
        # (those are loop bounds passed per-call, not persistent state).
        seen_state: set = set()
        state_fields: list = []
        for _cpp_fn, sargs in lc_data:
            for ai in sargs:
                if ai["is_col_start"] or ai["is_col_end"]:
                    continue
                if ai["host"] not in seen_state:
                    seen_state.add(ai["host"])
                    state_fields.append(ai)

        if state_fields:
            blank()
            emit(CommentOp(["── State " + "─" * 69]))
            blank()

            member_ops = []
            for ai in state_fields:
                # Host owns the memory — writable so allocate() and init can write
                field_t = _writable(_chost_arg_type(ai))
                init_op = (
                    NullPointerExprOp() if isinstance(field_t, MemRefType)
                    else arith.ConstantOp(IntegerAttr.from_int_and_width(0, 32))
                )
                member_ops.append(CppFieldDeclOp(
                    ai["host"], field_t, type_width=16, init_expr_op=init_op,
                ))

            # Constructor: initialise ncol and all is_nz scalars; other fields
            # default via their in-class initialisers.  Prevents aggregate-init
            # errors when State has a private: section from allocate().
            ncol_fields = [ai for ai in state_fields if ai["is_ncol"]]
            nz_fields   = [ai for ai in state_fields if ai["is_nz"] or ai.get("is_dim_scalar")]
            dim_scalar_fields = ncol_fields + nz_fields

            # Array fields whose size we can express from their dim_ncol / dim_nz / dim_n3
            alloc_fields = [
                ai for ai in state_fields
                if not ai["is_int"]
                and (
                    ai["rank"] in (1, 2)
                    or (ai["rank"] >= 3 and ai.get("dim_n3"))
                )
            ]

            method_ops = []
            if dim_scalar_fields:
                method_ops.append(CppConstructorOp(
                    param_names=[ai["host"] for ai in dim_scalar_fields],
                    param_types=[i32] * len(dim_scalar_fields),
                    param_default_ops=[
                        arith.ConstantOp(IntegerAttr.from_int_and_width(0, 32))
                        for _ in dim_scalar_fields
                    ],
                    init_members=[ai["host"] for ai in dim_scalar_fields],
                    init_expr_ops=[VarRefExprOp(ai["host"]) for ai in dim_scalar_fields],
                    body_ops=[],
                ))

            private_member_ops = []
            if alloc_fields:
                allocate_body_ops = []
                for ai in alloc_fields:
                    # Element count: ncol [* nz [* n3]], as a std::size_t.
                    extents = [ai.get("dim_ncol") or ncol_var, ai.get("dim_nz") or nz_var,
                               ai.get("dim_n3")][:ai["rank"]]
                    size_op = CastExprOp(var(extents[0], i32), IndexType())
                    for extent in extents[1:]:
                        size_op = arith.MuliOp(size_op, var(extent, IndexType()))
                    storage = f"_{ai['host']}"
                    allocate_body_ops += [
                        DdtMethodCallOp(obj_expr_op=var(storage), method="assign",
                                        arg_ops=[size_op, const(0)]),
                        AssignOp(lhs_op=var(ai["host"]),
                                 rhs_op=MethodCallExprOp(var(storage), "data")),
                    ]
                method_ops += [
                    BlankLineOp(),
                    CommentOp([
                        "Allocate all array fields from internal storage.",
                        "Set ncol (and nz/ncnst for higher-rank arrays) before calling.",
                    ]),
                ]
                method_ops.append(CFunctionSigOp(
                    fn_name="allocate",
                    param_names=[], param_types=[], param_comments=[],
                    body_ops=allocate_body_ops,
                ))
                for ai in alloc_fields:
                    elem_t = _writable(_chost_arg_type(ai)).element_type
                    private_member_ops.append(CppFieldDeclOp(
                        f"_{ai['host']}", OwnedArrayType(elem_t),
                    ))

            emit(CppStructDefOp(
                "State", member_ops=member_ops, is_pod=False,
                method_ops=method_ops, private_member_ops=private_member_ops,
            ))

            for cpp_fn, sargs in lc_data:
                if not sargs:
                    continue   # zero-arg lifecycle (e.g. finalize) — existing fn is clean
                has_loop_bounds = any(
                    ai["is_col_start"] or ai["is_col_end"] for ai in sargs
                )
                blank()
                state = ReadOnlyType(DerivedType("State"))
                if has_loop_bounds:
                    param_names = ["s", "col_start", "col_end"]
                    param_types = [state, i32, i32]
                else:
                    param_names = ["s"]
                    param_types = [state]

                field_names    = []
                field_value_ops = []
                for ai in sargs:
                    field_names.append(ai["host"])
                    if ai["is_col_start"]:
                        field_value_ops.append(VarRefExprOp("col_start"))
                    elif ai["is_col_end"]:
                        field_value_ops.append(VarRefExprOp("col_end"))
                    else:
                        field_value_ops.append(MemberAccessExprOp(VarRefExprOp("s"), ai["host"]))

                emit(CFunctionSigOp(
                    fn_name=cpp_fn, return_type=DerivedType("Status"), is_inline=True,
                    param_names=param_names, param_types=param_types,
                    param_comments=[""] * len(param_names),
                    body_ops=[CppBraceInitCallOp(
                        callee=cpp_fn, field_names=field_names, field_value_ops=field_value_ops,
                    )],
                ))

        blank()

        return [CppNamespaceOp(ns_name=ns_name, body_ops=body_ops)]

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        assert ccpp_mod is not None

        # Same condition CCPPCAP.apply() used to check inline: only generate
        # the chost cap when a host/module/control table declares
        # language = "c++". Includes "control" (type-control-gap): a chost
        # host's own table (e.g. tiny_r3_host_sub.meta) migrated from HOST
        # to CONTROL must not silently stop being recognized as the C++
        # host -- caught by chost-r3-ftn.mlir's own FileCheck golden going
        # from "whole chost cap module present" to "entirely missing".
        host_lang_cpp = any(
            isa(tbl_op, ccpp.TablePropertiesOp)
            and tbl_op.table_type.data in ("host", "module", "control")
            and "language" in tbl_op.attributes
            and tbl_op.attributes["language"].data == "c++"
            for tbl_op in ccpp_mod.body.ops
        )
        if not host_lang_cpp:
            return

        # Re-derive the same descriptor objects generate-ccpp-cap builds from
        # the IR at the start of its own apply().
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data_descriptions = bmdd.meta_data

        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)
        suite_descriptions = bsd.schemes

        ddt_source_module = collect_ddt_source_modules(ccpp_mod)

        # Re-locate the ccpp cap module generate-ccpp-cap just inserted.
        cap_mod = None
        for candidate in op.body.block.ops:
            if (
                isa(candidate, builtin.ModuleOp)
                and candidate.sym_name is not None
                and candidate.sym_name.data.endswith("_ccpp_cap")
            ):
                cap_mod = candidate
                break
        assert cap_mod is not None, (
            "generate-cpp-cap must run after generate-ccpp-cap has inserted "
            "the <HostName>_ccpp_cap module"
        )

        # Same public_fns generate-ccpp-cap computed (suite-cap modules'
        # public functions) -- exclude cap_mod itself, since the original
        # computation ran before cap_mod existed in the block.
        public_fns = _collect_public_suite_functions(
            m for m in op.body.block.ops if m is not cap_mod
        )

        chost_op = self._generate_chost_cap_module(
            suite_descriptions, meta_data_descriptions, cap_mod, ccpp_mod,
            public_fns=public_fns,
            ddt_source_module=ddt_source_module,
        )
        op.body.block.add_op(chost_op)
