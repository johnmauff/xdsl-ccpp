import sys
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    ArrayAttr,
    DictionaryAttr,
    Float32Type,
    IndexType,
    IntegerAttr,
    IntegerType,
    MemRefType,
    StringAttr,
    UnitAttr,
    i8,
)
from xdsl.ir import Block, Region
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import (
    ArraySectionOp,
    CapVarRefOp,
    CHostCapOp,
    ConstituentApiOp,
    DerivedType,
    HostVarRefOp,
    KeywordCallOp,
    ModuleVarOp,
    RealKindType,
    RowMajorConvertOp,
    RowMajorWriteBackOp,
    SetStringOp,
    StrCmpOp,
    SuiteVariablesOp,
    TrimOp,
    WriteErrMsgOp,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPType,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.transforms.util.ccpp_descriptors import XMLSubcycle as _XMLSubcycle
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    CCPP_ERROR_STD_NAMES,
    CCPP_ERRMSG_LEN,
    CCPP_FRAMEWORK_STD_NAMES,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_HORIZONTAL_DIMENSIONS,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_SCHEME_NAME_LEN,
    CCPP_VERT_DIM_STD_NAME,
    CCPP_VERTICAL_DIMENSIONS,
)

_CCPP_CONSTITUENT_MOD = "ccpp_constituent_prop_mod"

_CONSTITUENT_DDT_NAME = "ccpp_constituent_properties_t"

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


def _iter_schemes(group):
    """Yield all XMLScheme leaves from a group, descending into XMLSubcycle nodes."""
    for child in group:
        if isinstance(child, _XMLSubcycle):
            yield from child
        else:
            yield child


def _bare(name: str) -> str:
    """Strip __alloc, __opt, or __in suffix from an arg name hint to get the bare Fortran name."""
    if name.endswith("__alloc"):
        return name[:-7]
    if name.endswith("__opt"):
        return name[:-5]
    if name.endswith("__in"):
        return name[:-4]
    return name


def _emit_subr_header(append_fn, cfn: str, vnames: list, max_col: int = 92) -> None:
    """Emit a subroutine header line with bind(C), using continuation if needed."""
    prefix = f"  subroutine {cfn}("
    bind_line = f"      bind(C, name='{cfn}')"
    single = prefix + ", ".join(vnames) + ") &"
    if len(single) <= max_col:
        append_fn(single)
    else:
        append_fn(prefix + " &")
        indent = "      "
        cur = indent
        for i, nm in enumerate(vnames):
            sep = ", " if i < len(vnames) - 1 else ""
            if len(cur) + len(nm) + len(sep) + 4 > max_col:
                append_fn(cur + " &")
                cur = indent + nm + sep
            else:
                cur += nm + sep
        append_fn(cur + ") &")
    append_fn(bind_line)


def _emit_call(append_fn, fn_name: str, call_exprs: list, max_col: int = 80) -> None:
    """Emit 'call fn(args)' with Fortran continuation lines when needed."""
    prefix = f"    call {fn_name}("
    single = prefix + ", ".join(call_exprs) + ")"
    if len(single) <= max_col:
        append_fn(single)
        return
    append_fn(prefix + " &")
    indent = "        "
    cur = indent
    for i, expr in enumerate(call_exprs):
        sep = ", " if i < len(call_exprs) - 1 else ""
        if len(cur) + len(expr) + len(sep) + 4 > max_col:
            append_fn(cur + " &")
            cur = indent + expr + sep
        else:
            cur += expr + sep
    append_fn(cur + ")")


def _chost_kind_iso_map(ccpp_mod) -> dict:
    """Extract kind-name → ISO-constant mapping from ccpp.kinds ops in the ccpp module."""
    kind_iso: dict = {}
    for inner in ccpp_mod.body.ops:
        if not isa(inner, ccpp.KindsOp):
            continue
        for kind_op in inner.body.ops:
            if isa(kind_op, ccpp.KindOp):
                kind_iso[kind_op.kind_name.data] = kind_op.kind_value.data
    return kind_iso


def _real_width_from_iso(iso_constant: str) -> int:
    """Return 32 or 64 given an ISO_FORTRAN_ENV constant like 'REAL32'/'REAL64'."""
    return 32 if iso_constant == "REAL32" else 64


def _chost_build_maps(meta_data):
    """Build std→host and local→std name maps from metadata for chost arg classification."""
    std_to_host: dict = {}
    for props in meta_data.values():
        if props.getAttr("type") not in (CCPPType.HOST, CCPPType.MODULE):
            continue
        for atbl in props.arg_tables.values():
            for var in atbl.getFunctionArguments():
                if var.hasAttr("standard_name"):
                    sn = var.getAttr("standard_name").lower()
                    if sn not in std_to_host:
                        std_to_host[sn] = var.name

    local_to_std: dict = {}
    for props in meta_data.values():
        for atbl in props.arg_tables.values():
            for var in atbl.getFunctionArguments():
                if var.hasAttr("standard_name") and var.name not in local_to_std:
                    local_to_std[var.name] = var.getAttr("standard_name").lower()

    ncol_var = (std_to_host.get(CCPP_HORIZ_DIM_STD_NAME)
                or std_to_host.get(CCPP_LOOP_EXTENT_STD_NAME) or "ncol")
    nz_var = std_to_host.get(CCPP_VERT_DIM_STD_NAME, "nz")
    return std_to_host, local_to_std, ncol_var, nz_var


def _chost_arg_info(hint, mtype, local_to_std, std_to_host, kind_iso_map=None,
                    local_to_dim_names=None):
    """Return an arg descriptor dict for a single suite cap input argument."""
    bare = _bare(hint) if hint else ""
    std  = local_to_std.get(bare, "")
    host = std_to_host.get(std, bare)

    is_col_start = (std == CCPP_LOOP_BEGIN_STD_NAME)
    is_col_end   = (std == CCPP_LOOP_END_STD_NAME)
    is_ncol      = std in {CCPP_HORIZ_DIM_STD_NAME, CCPP_LOOP_EXTENT_STD_NAME}
    is_nz        = std in {CCPP_VERT_DIM_STD_NAME}
    is_errmsg    = (std == "ccpp_error_message")
    is_errflg    = (std == "ccpp_error_code")
    is_sname     = (std == "scheme_name" or bare == "scheme_name")
    is_in_only   = (hint is not None and hint.endswith("__in"))

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
            f"the C-interoperable chost interface. Flatten the DDT into individual "
            f"scalar/array members, or see multilanguage_limitations.md for options."
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
                iso = kind_iso_map.get(elem.kind_name.data, "REAL64")
                real_width = _real_width_from_iso(iso)
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

    return dict(
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
    char_member_blanks: list = []   # character members — not exposed, init to ' '

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

        _PRIMITIVE_TYPES = {"real", "integer", "logical", "character", "complex"}
        if vtype not in _PRIMITIVE_TYPES:
            # Nested DDT member: expand recursively, re-root paths under this local.
            # Option B (direct path): nested members are accessed as
            # outer_local%member_name%leaf so no separate inner local is declared.
            nested_ais, nested_li = _chost_expand_ddt_arg(
                f"{prefix}_{var.name}", vtype, meta_data,
                local_to_std, std_to_host, kind_iso_map, ncol_var, nz_var,
                original_intent=original_intent,
            )
            for nai in nested_ais:
                nai["_ddt_member"] = f"{var.name}%{nai['_ddt_member']}"
                nai["_ddt_local"]  = f"{prefix}_local"
                nai["_ddt_prefix"] = prefix
            member_ais.extend(nested_ais)
            for cmn in nested_li.get("char_member_blanks", []):
                char_member_blanks.append(f"{var.name}%{cmn}")
            continue

        if vtype == "character":
            # Character members (e.g. ccpp_info_t%errmsg) are not exposed in the
            # C interface; the chost cap initialises them to blank instead.
            char_member_blanks.append(var.name)
            continue

        real_width = 64
        if is_real and var.hasAttr("kind"):
            iso = kind_iso_map.get(var.getAttr("kind"), "REAL64")
            real_width = _real_width_from_iso(iso)

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

        ai = dict(
            hint=None, bare=flat_name, host=flat_name, std=std,
            is_col_start=False, is_col_end=False,
            is_ncol=is_ncol, is_nz=is_nz, is_dim_scalar=False,
            is_errmsg=False, is_errflg=False, is_sname=False,
            is_char=False, is_int=is_int, is_real=is_real, is_logical=is_logical,
            real_width=real_width, rank=ndim, intent=intent,
            _ddt_member=var.name,
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
                out_infos.append(dict(
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
                out_infos.append(dict(
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
            out_infos.append(dict(
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
        visible = [dict(
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
            to_inject[dz] = dict(
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
    "_ccpp_physics_register":         "register",
    "_ccpp_physics_initialize":       "initialize",
    "_ccpp_physics_finalize":         "finalize",
    "_ccpp_physics_timestep_initial": "timestep_initial",
    "_ccpp_physics_timestep_final":   "timestep_final",
    "_ccpp_physics_run":              "run",
}


def _lc_of(fn_name: str):
    """Return the lifecycle name for a bind-C function name, or None if not recognised."""
    for suffix, lc in _LIFECYCLE.items():
        if fn_name.endswith(suffix):
            return lc
    return None


def _chost_fn_name(fn_name: str) -> str:
    """Map a suite-cap bind-C function name to its chost counterpart."""
    return fn_name.replace("_ccpp_physics_", "_chost_physics_")


def _suite_fns_for(lc: str, suite_name: str, suite_descriptions: dict) -> list:
    """Return the list of suite cap function names for a given lifecycle."""
    if lc == "run":
        return [
            f"{suite_name}_suite_{grp.attributes['name']}"
            for grp in suite_descriptions.get(suite_name, [])
        ]
    return [f"{suite_name}_suite_{lc}"]


def _chost_cpp_type(ai: dict) -> str:
    """Map a chost arg descriptor to its C++ type string."""
    if ai["is_ncol"] or ai["is_nz"]:
        return "int"
    if ai["is_int"] and not ai["is_errflg"]:
        return "int"
    if ai["is_real"]:
        cpp_real = "float" if ai.get("real_width", 64) == 32 else "double"
        if ai["rank"] == 0:
            return cpp_real
        if ai["intent"] == "in":
            return f"const {cpp_real}*"
        return f"{cpp_real}*"
    if ai.get("is_logical"):
        return "bool"
    if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
        return "const char*" if ai.get("intent") == "in" else "char*"
    if ai["is_sname"] or ai["is_errmsg"]:
        return "char*"
    if ai["is_errflg"]:
        return "int*"
    return "void*"


# Map CCPP lifecycle names to scheme entry-point name suffixes.
_LC_TO_ENTRY_SUFFIX = {
    "run":              ("_run",),
    "initialize":       ("_init", "_initialize"),
    "timestep_initial": ("_timestep_initial",),
    "timestep_final":   ("_timestep_final",),
    "finalize":         ("_finalize",),
    "register":         ("_register",),
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
    bind_c_fns, suite_name, suite_descriptions, public_fns,
    ncol_var, local_to_std, std_to_host, kind_iso_map,
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
    """
    # Build local_name → [dim_std_name, ...] for correct vertical-dim resolution.
    local_to_dim_names: dict = {}
    if meta_data is not None:
        for props in meta_data.values():
            for atbl in props.arg_tables.values():
                for var in atbl.getFunctionArguments():
                    if var.hasAttr("dim_names") and var.name not in local_to_dim_names:
                        local_to_dim_names[var.name] = var.getAttr("dim_names")

    contexts = []
    for fn in bind_c_fns:
        fn_name = fn.sym_name.data
        lc = _lc_of(fn_name)
        if lc is None:
            continue
        sfns = _suite_fns_for(lc, suite_name, suite_descriptions)
        suite_fn = next((s for s in sfns if s in public_fns), None)
        if suite_fn is None:
            continue
        _, pfn_out_types, pfn_types, pfn_hints = public_fns[suite_fn]

        infos = []
        ddt_locals: dict = {}
        suite_call_pieces: list = []
        constituent_vars: list = []

        for h, t in zip(pfn_hints, pfn_types):
            bare = _bare(h) if h else ""
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
                    "name": f"_chost_{bare}",
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
                    local_to_dim_names=local_to_dim_names,
                )
                # Scalar char args don't get the __in hint suffix from suite_cap
                # (that's only for array args), so their intent defaults to "inout".
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
            "cfn": _chost_fn_name(fn_name),
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


def _resolve_ddt_access_path(
    ddt_type_name: str,
    ddt_instance_map: dict,
    ddt_parent_map: dict,
    _depth: int = 0,
) -> "tuple[str, str, str] | None":
    """Resolve a DDT type name to (instance_var, instance_module, path_prefix).

    For a type that has a direct module-level instance, path_prefix is "".
    For a nested DDT — e.g. type B is a member of type A, and A has a
    module-level instance — path_prefix is "b_member%" so the full Fortran
    accessor becomes ``instance_var%path_prefix%leaf_member``
    (e.g. ``phys_state%rad%temperature``).

    Returns None when no reachable module-level instance exists.
    The depth limit guards against circular DDT type definitions.
    """
    if _depth > 8:
        return None
    if ddt_type_name in ddt_instance_map:
        instance_var, instance_module = ddt_instance_map[ddt_type_name]
        return instance_var, instance_module, ""
    for member_var_name, parent_ddt_type in ddt_parent_map.get(ddt_type_name, []):
        result = _resolve_ddt_access_path(
            parent_ddt_type, ddt_instance_map, ddt_parent_map, _depth + 1
        )
        if result is not None:
            instance_var, instance_module, parent_prefix = result
            return instance_var, instance_module, parent_prefix + member_var_name + "%"
    return None


@dataclass
class _RunMetadataMaps:
    """Lookup structures built from metadata for use in _generate_run_fn."""
    host_var_map: dict
    host_block_std_names: set
    constituent_std_names: set
    ddt_type_names: set
    ddt_instance_map: dict
    ddt_parent_map: dict


@dataclass
class _RunBlockSignature:
    """Block structure and SSA value mappings for the run dispatcher function."""
    new_block: "object"           # Block
    all_block_types: list
    block_arg_map: dict
    non_host_std_to_canonical: dict
    suite_name_arg: "object"      # BlockArgument
    suite_part_arg: "object"      # BlockArgument
    errmsg_arg: "object"          # SSAValue
    errflg_arg: "object"          # SSAValue
    col_start_ref: "object"       # HostVarRefOp | None
    col_end_ref: "object"         # HostVarRefOp | None
    errmsg_alloc: "object"        # HostVarRefOp | None
    errflg_alloc: "object"        # HostVarRefOp | None
    ccpp_info_block_arg: "object" # BlockArgument | None
    ccpp_data_block_arg: "object" # BlockArgument | None
    ccpp_info_type: "object"      # memref type or None
    ccpp_t_type: "object"         # memref type or None


@dataclass
class _RunChainPreamble:
    """Seed ops and grouping structures for the dispatch-chain construction."""
    err_const: "object"       # arith.ConstantOp — initialises errflg to 0
    store_errflg: "object"    # memref.StoreOp
    trim_suite_name: "object" # TrimOp
    current_false_ops: list   # innermost else: "no suite matched" error sequence
    all_decls: list           # accumulator for external FuncOp declarations
    per_suite_grouped: dict   # suite_name → [info, ...], preserving order


@dataclass(frozen=True)
class CCPPCAP(ModulePass):
    """MLIR pass that generates a single combined CCPP physics cap dispatcher module.

    Runs after generate-suite-cap.  For all suites found in the ccpp module,
    generates a single named ModuleOp containing lifecycle dispatcher subroutines
    that use nested if/else chains on ``suite_name`` to dispatch to the appropriate
    suite cap subroutine (generated by generate-suite-cap).

    Output is one ModuleOp (e.g. ``test_host_ccpp_cap``) inserted into the
    top-level module alongside the suite cap modules.
    """

    name = "generate-ccpp-cap"

    # Optional override for the CamelCase host name prefix applied to all
    # generated lifecycle subroutines.  When absent, the prefix is derived
    # automatically from the first suite name (e.g. hello_world_suite → HelloWorld).
    host_name: str = ""

    # When True, generated lifecycle and run subroutines in the ccpp_cap module
    # use BIND(C, name='...') and ISO_C_BINDING-typed arguments so they can be
    # called from C++ / Kokkos host models.
    bind_c: bool = False

    def _collect_public_suite_functions(self, ops):
        """Scan all named ModuleOps in ops and return a map of public function info.

        Returns:
            dict mapping function_name → (module_name, output_types,
            input_types, input_names).
        """
        public_fns = {}
        for op in ops:
            if not (isa(op, builtin.ModuleOp) and op.sym_name is not None):
                continue
            mod_name = op.sym_name.data
            for child in op.body.block.ops:
                if (
                    isa(child, func.FuncOp)
                    and not child.is_declaration
                    and child.sym_visibility is not None
                    and child.sym_visibility.data == "public"
                ):
                    public_fns[child.sym_name.data] = (
                        mod_name,
                        list(child.function_type.outputs),
                        list(child.function_type.inputs),
                        [arg.name_hint for arg in child.body.block.args],
                    )
        return public_fns

    def _derive_camel_case_name(self, suite_name: str) -> str:
        """Convert a snake_case suite name to CamelCase, stripping any '_suite' suffix."""
        name = suite_name
        if name.endswith("_suite"):
            name = name[:-6]
        return "".join(word.capitalize() for word in name.split("_"))

    def _build_suite_variables_fn(self, suite_descriptions, ccpp_mod,
                                   host_std_names, protected_std_names) -> "SuiteVariablesOp":
        """Build the ccpp_physics_suite_variables subroutine for all suites.

        Scans the MLIR IR directly (ArgumentOp properties) rather than going
        through the descriptor layer, avoiding subtle descriptor-build issues.

        Filtering rules (applied per ArgumentOp):
        - Skip if standard_name belongs to ANY interstitial arg (producer or
          consumer) — collected in a first pass across all scheme tables
        - Skip if standard_name is in _INTERNAL (horizontal_loop_extent only;
          ccpp_constituents / ccpp_constituent_tendencies are physics arrays
          and must appear in the list)
        - Skip if standard_name is in protected_std_names (dimension params)
        - ccpp_error_code/ccpp_error_message always go to output-only
        - advected=.true. args go to both input and output regardless of intent
        - state_variable=true args go to both if scheme units == host units;
          if units differ (unit conversion needed), intent-based rules apply
        - All others go to input/output by declared intent
        - After the main scan a dimension-name sweep adds vars that appear only
          as array dimension sizes (e.g. number_of_ccpp_constituents)
        - Union across all entry points (_init, _run, _finalize, etc.)
        """
        _CCPP_ERR = CCPP_ERROR_STD_NAMES
        # Only the loop-extent scalar is truly framework-internal and excluded.
        # The constituent-array names are real physics arrays and must appear.
        _INTERNAL = frozenset({CCPP_LOOP_EXTENT_STD_NAME})
        CM = 36  # character length matching cm=36 in test driver

        suite_vars: dict = {}
        for suite_name, suite_desc in suite_descriptions.items():
            # Collect the set of scheme names belonging to this suite
            scheme_names: set = set()
            for group in suite_desc:
                for scheme in _iter_schemes(group):
                    scheme_names.add(scheme.attributes["name"])

            # Pass 1a: collect every standard_name that is marked is_interstitial
            # on ANY occurrence.  host_var_match_pass marks the CONSUMER (_run)
            # but not the PRODUCER (_init), so we need the full set to exclude
            # both sides of an intra-suite interstitial (e.g. tcld).
            #
            # Pass 1b: collect state_variable args where ANY scheme in this
            # suite declares the variable in different units than the host.
            # When a unit mismatch exists, the suite cap converts the value
            # in-place (e.g. Pa→hPa) — the host should not treat the returned
            # value as a meaningful physics output.
            interstitial_std_names: set = set()
            state_var_unit_mismatch: set = set()
            for tbl_op in ccpp_mod.body.ops:
                if not isa(tbl_op, ccpp.TablePropertiesOp):
                    continue
                if tbl_op.table_type.data != "scheme":
                    continue
                if tbl_op.table_name.data not in scheme_names:
                    continue
                for arg_table_op in tbl_op.body.ops:
                    if not isa(arg_table_op, ccpp.ArgumentTableOp):
                        continue
                    for arg_op in arg_table_op.body.ops:
                        if not isa(arg_op, ccpp.ArgumentOp):
                            continue
                        if arg_op.properties.get("is_interstitial") is not None:
                            sn_prop = arg_op.properties.get("standard_name")
                            if sn_prop is not None:
                                interstitial_std_names.add(sn_prop.data.lower())
                        if arg_op.properties.get("state_variable") is not None:
                            sn_prop = arg_op.properties.get("standard_name")
                            if sn_prop is not None:
                                _sn = sn_prop.data.lower()
                                _su = arg_op.properties.get("units")
                                _su_str = _su.data.lower() if _su is not None else None
                                _hu = host_std_names.get(_sn)
                                if (_su_str is not None and _hu is not None
                                        and _su_str != _hu):
                                    state_var_unit_mismatch.add(_sn)

            input_vars: set = set()
            output_vars: set = set()
            all_dim_names: set = set()

            # Pass 2: build input/output variable sets
            for tbl_op in ccpp_mod.body.ops:
                if not isa(tbl_op, ccpp.TablePropertiesOp):
                    continue
                if tbl_op.table_type.data != "scheme":
                    continue
                if tbl_op.table_name.data not in scheme_names:
                    continue

                # Iterate all entry-point arg tables (_init, _run, _finalize …)
                for arg_table_op in tbl_op.body.ops:
                    if not isa(arg_table_op, ccpp.ArgumentTableOp):
                        continue

                    for arg_op in arg_table_op.body.ops:
                        if not isa(arg_op, ccpp.ArgumentOp):
                            continue

                        sn_prop = arg_op.properties.get("standard_name")
                        if sn_prop is None:
                            continue
                        std_name = sn_prop.data.lower()

                        # Collect dimension names for the post-scan sweep
                        dim_names_prop = arg_op.properties.get("dim_names")
                        if dim_names_prop is not None:
                            for dn in dim_names_prop.data.split(","):
                                dn = dn.strip().lower()
                                # Skip bare colons and integer literals
                                if dn and dn[0].isalpha():
                                    all_dim_names.add(dn)

                        if std_name in interstitial_std_names:
                            continue
                        if std_name in _INTERNAL:
                            continue

                        # Variables with a default_value that are not matched to a
                        # host variable AND are not advected constituents are managed
                        # internally by the cap and must not appear in the variable list.
                        # Advected constituents (advected=true) have default_value as an
                        # initial fill, but are still real physics arrays visible to the host.
                        if (arg_op.properties.get("default_value") is not None
                                and arg_op.properties.get("model_var_name") is None
                                and arg_op.properties.get("advected") is None):
                            continue

                        # Error flags → output-only special case
                        if std_name in _CCPP_ERR:
                            output_vars.add(std_name)
                            continue

                        # intent: StringAttr when set
                        intent_prop = arg_op.properties.get("intent")
                        intent = intent_prop.data.lower() if intent_prop is not None else None

                        if std_name in protected_std_names:
                            # Protected vars are blocked from input, but a scheme
                            # may still write one as output (e.g. constituent-index
                            # arrays like test_banana_constituent_indices).
                            if intent in ("out", "inout"):
                                output_vars.add(std_name)
                            continue

                        # Advected constituents go to both input and output.
                        # state_variable=true args go to both ONLY when no scheme
                        # in the suite uses different units than the host (unit
                        # conversion would mean the suite cap rewrites the value
                        # in-place, so the host should not treat the returned value
                        # as a meaningful physics output in that case).
                        if arg_op.properties.get("advected") is not None:
                            input_vars.add(std_name)
                            output_vars.add(std_name)
                        elif arg_op.properties.get("state_variable") is not None:
                            if std_name not in state_var_unit_mismatch:
                                input_vars.add(std_name)
                                output_vars.add(std_name)
                            else:
                                if intent in ("in", "inout"):
                                    input_vars.add(std_name)
                                if intent in ("out", "inout"):
                                    output_vars.add(std_name)
                        else:
                            if intent in ("in", "inout"):
                                input_vars.add(std_name)
                            if intent in ("out", "inout"):
                                output_vars.add(std_name)

            # Pass 3: add dimension standard names not already covered.
            # Picks up vars like number_of_ccpp_constituents that appear only as
            # array dimension sizes, never as explicit scheme arguments.
            for dim_name in all_dim_names:
                if (dim_name not in _INTERNAL
                        and dim_name not in protected_std_names
                        and dim_name not in interstitial_std_names
                        and dim_name not in input_vars
                        and dim_name not in output_vars
                        and dim_name not in _CCPP_ERR):
                    input_vars.add(dim_name)

            required_vars = input_vars | output_vars
            suite_vars[suite_name] = (
                sorted(input_vars),
                sorted(output_vars),
                sorted(required_vars),
            )

        # Build the complete Fortran subroutine as a Python string
        lines: list[str] = []
        lines.append(
            "subroutine ccpp_physics_suite_variables"
            "(suite_name, var_list, errmsg, errflg, input_vars, output_vars)"
        )
        lines.append("  character(len=*), intent(in) :: suite_name")
        lines.append("  character(len=*), allocatable, intent(out) :: var_list(:)")
        lines.append(f"  character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg")
        lines.append("  integer, intent(out) :: errflg")
        lines.append("  logical, optional, intent(in) :: input_vars")
        lines.append("  logical, optional, intent(in) :: output_vars")
        lines.append("  logical :: do_input, do_output")
        lines.append("  errmsg = ''")
        lines.append("  errflg = 0")
        lines.append("  do_input = .true.")
        lines.append("  do_output = .true.")
        lines.append("  if (present(input_vars)) do_input = input_vars")
        lines.append("  if (present(output_vars)) do_output = output_vars")

        for idx, (suite_name, (in_v, out_v, req_v)) in enumerate(suite_vars.items()):
            kw = "if" if idx == 0 else "else if"
            lines.append(f"  {kw} (trim(suite_name) .eq. '{suite_name}') then")
            for branch_name, var_list in (
                ("input only",  "do_input .and. .not. do_output"),
                ("output only", ".not. do_input .and. do_output"),
                ("required",    None),
            ):
                if branch_name == "input only":
                    lines.append(f"    if ({var_list}) then")
                    vlist = in_v
                elif branch_name == "output only":
                    lines.append(f"    else if ({var_list}) then")
                    vlist = out_v
                else:
                    lines.append("    else")
                    vlist = req_v
                lines.append(f"      allocate(var_list({len(vlist)}))")
                for j, v in enumerate(vlist):
                    lines.append(f"      var_list({j + 1}) = '{v:<{CM}}'")
            lines.append("    end if")

        lines.append("  else")
        lines.append(
            '    write(errmsg, \'(3a)\') "No suite named ", trim(suite_name), " found"'
        )
        lines.append("    errflg = 1")
        lines.append("  end if")
        lines.append("end subroutine ccpp_physics_suite_variables")

        return SuiteVariablesOp("\n".join(lines))

    def _build_host_var_map(self, meta_data, include_host: bool = True) -> dict:
        """Build a standard_name → (var_name, table_name) map from host metadata.

        Args:
            meta_data:    descriptor dict from BuildMetaDataDescriptions.
            include_host: when True (default) includes both MODULE and HOST type
                          tables.  When False, only MODULE type tables are scanned.
                          HOST-type variables are ephemeral values passed directly
                          by the host caller; MODULE-type variables are accessible
                          via USE statements.

        Returns:
            dict mapping lowercase standard_name → (local_var_name, table_name).
        """
        table_types = (
            (CCPPType.MODULE, CCPPType.HOST) if include_host else (CCPPType.MODULE,)
        )
        result: dict = {}
        for tbl_name, props in meta_data.items():
            if props.getAttr("type") not in table_types:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if var.hasAttr("standard_name"):
                    result[var.getAttr("standard_name").lower()] = (var.name, tbl_name)
        return result

    def _build_run_metadata_maps(self, meta_data) -> "_RunMetadataMaps":
        """Build all host/DDT lookup maps needed by _generate_run_fn.

        Pure read of meta_data — no IR ops created, no side effects.
        """
        host_var_map = self._build_host_var_map(meta_data, include_host=False)

        host_block_std_names: set = set()
        for tbl_name, props in meta_data.items():
            if props.getAttr("type") != CCPPType.HOST:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if var.hasAttr("standard_name"):
                    host_block_std_names.add(var.getAttr("standard_name").lower())

        constituent_std_names: set = set()
        for _mod_name, props in meta_data.items():
            if props.getAttr("type") != CCPPType.SCHEME:
                continue
            for arg_tbl in props.arg_tables.values():
                for var in arg_tbl.getFunctionArguments():
                    if var.hasAttr("constituent") and var.hasAttr("standard_name"):
                        constituent_std_names.add(var.getAttr("standard_name").lower())

        ddt_type_names = {
            tbl_name
            for tbl_name, props in meta_data.items()
            if props.getAttr("type") == CCPPType.DDT
        }
        ddt_instance_map: dict = {}
        for tbl_name, props in meta_data.items():
            if props.getAttr("type") not in (CCPPType.MODULE, CCPPType.HOST):
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if var.hasAttr("type"):
                    var_type = var.getAttr("type")
                    if var_type in ddt_type_names:
                        ddt_instance_map[var_type] = (var.name, tbl_name)

        ddt_parent_map: dict = {}
        for tbl_name, props in meta_data.items():
            if props.getAttr("type") != CCPPType.DDT:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if var.hasAttr("type"):
                    child_type = var.getAttr("type")
                    if child_type in ddt_type_names:
                        ddt_parent_map.setdefault(child_type, []).append(
                            (var.name, tbl_name)
                        )

        return _RunMetadataMaps(
            host_var_map=host_var_map,
            host_block_std_names=host_block_std_names,
            constituent_std_names=constituent_std_names,
            ddt_type_names=ddt_type_names,
            ddt_instance_map=ddt_instance_map,
            ddt_parent_map=ddt_parent_map,
        )

    def _build_per_suite_run_info(
        self,
        suite_run_entries,
        public_fns: dict,
        meta_data,
        maps: "_RunMetadataMaps",
        cap_var_map,
        seen_host_globals: set,
    ) -> "tuple[list, list]":
        """Classify each suite run entry's args and build per-suite info dicts.

        For every (suite_name, suite_part, suite_callee, scheme_names) entry,
        resolves which callee args come from host module variables, DDT members,
        cap-owned vars, or caller block args.  Emits GlobalOp USE-statement stubs
        into seen_host_globals (mutated in-place — shared across lifecycle functions).

        Returns (per_suite, host_global_ops).
        """
        host_block_std_names = maps.host_block_std_names
        constituent_std_names = maps.constituent_std_names
        ddt_instance_map = maps.ddt_instance_map
        ddt_parent_map = maps.ddt_parent_map

        per_suite = []
        host_global_ops: list = []

        for suite_name, suite_part, suite_callee, scheme_names in suite_run_entries:
            (
                callee_module,
                callee_output_types,
                callee_input_types,
                callee_input_names,
            ) = public_fns[suite_callee]

            # Build {local_arg_name → standard_name} from the _run arg tables.
            std_name_of = {}
            for scheme_name in scheme_names:
                table_name = scheme_name + "_run"
                if scheme_name not in meta_data:
                    continue
                if table_name not in meta_data[scheme_name].arg_tables:
                    continue
                for fn_arg in (
                    meta_data[scheme_name]
                    .getArgTable(table_name)
                    .getFunctionArguments()
                ):
                    if fn_arg.name not in std_name_of and fn_arg.hasAttr(
                        "standard_name"
                    ):
                        std_name_of[fn_arg.name] = fn_arg.getAttr("standard_name").lower()

            # Also check HOST and MODULE tables for suite-level args (like col_start/
            # col_end) that don't appear directly in any scheme _run table but are
            # part of the suite cap's signature for loop bounds / array sectioning.
            for callee_arg in callee_input_names:
                if _bare(callee_arg) in std_name_of:
                    continue
                bare = _bare(callee_arg)
                for tbl_name, props in meta_data.items():
                    if props.getAttr("type") not in (CCPPType.HOST, CCPPType.MODULE):
                        continue
                    if tbl_name not in props.arg_tables:
                        continue
                    for var in props.getArgTable(tbl_name).getFunctionArguments():
                        if var.name == bare and var.hasAttr("standard_name"):
                            std_name_of[bare] = var.getAttr("standard_name").lower()
                            break

            # Build local_name → (host_var, host_module, is_ddt) from the match pass
            # results stored in descriptor objects.  HostVariableMatchPass already
            # computed model_var_name / model_module_name for every matched scheme arg
            # and stored them as properties on the IR ops; BuildMetaDataDescriptions
            # copies those into the CCPPArgument descriptors via known_props.
            # Using this avoids re-deriving the same information from raw metadata.
            local_to_host_info: dict = {}
            for scheme_name in scheme_names:
                table_name = scheme_name + "_run"
                if scheme_name not in meta_data:
                    continue
                if table_name not in meta_data[scheme_name].arg_tables:
                    continue
                for fn_arg in (
                    meta_data[scheme_name]
                    .getArgTable(table_name)
                    .getFunctionArguments()
                ):
                    bare_name = _bare(fn_arg.name)
                    if bare_name not in local_to_host_info and fn_arg.hasAttr(
                        "model_var_name"
                    ):
                        local_to_host_info[bare_name] = (
                            fn_arg.getAttr("model_var_name"),
                            fn_arg.getAttr("model_module_name"),
                            fn_arg.hasAttr("model_var_is_ddt"),
                        )

            # Build bare_name → (dim_std_names, intent) for rank≥2 row_major args.
            # These will be transposed via RowMajorConvertOp in the dispatch chain.
            local_to_array_layout: dict = {}
            for scheme_name in scheme_names:
                table_name = scheme_name + "_run"
                if scheme_name not in meta_data:
                    continue
                if table_name not in meta_data[scheme_name].arg_tables:
                    continue
                for fn_arg in (
                    meta_data[scheme_name]
                    .getArgTable(table_name)
                    .getFunctionArguments()
                ):
                    bare_name = _bare(fn_arg.name)
                    if (
                        bare_name not in local_to_array_layout
                        and fn_arg.hasAttr("model_var_array_layout")
                        and fn_arg.getAttr("model_var_array_layout") == "row_major"
                        and fn_arg.hasAttr("dim_names")
                        and fn_arg.hasAttr("dimensions")
                        and fn_arg.getAttr("dimensions") >= 2
                    ):
                        local_to_array_layout[bare_name] = (
                            fn_arg.getAttr("dim_names"),
                            fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in",
                        )

            # Classify each callee input arg using match pass results as primary source.
            physics_arg_sources = []
            for arg_name in callee_input_names:
                bare = _bare(arg_name)
                std_name = std_name_of.get(bare) or std_name_of.get(arg_name)

                if bare in local_to_host_info and not (
                    std_name and std_name in host_block_std_names
                ):
                    # local_to_host_info has a match, AND it is not a protected
                    # HOST-type block arg (those are passed by the caller, not
                    # accessed via a USE statement).
                    host_var, host_mod, is_ddt = local_to_host_info[bare]
                    if is_ddt:
                        # DDT member: model_module_name is the DDT table/type name.
                        # Resolve to a module-level instance, following parent DDTs
                        # for nested types (e.g. A contains B contains x → a%b%x).
                        ddt_type_name = host_mod
                        result = _resolve_ddt_access_path(
                            ddt_type_name, ddt_instance_map, ddt_parent_map
                        )
                        if result is not None:
                            instance_var, instance_module, path_prefix = result
                            full_member = path_prefix + host_var
                            # Skip DDT instances whose instance variable lives in a HOST-type
                            # table (e.g. ccpp_info_t accessed through 'ccpp' in test_host).
                            # HOST-type tables are caller-provided interfaces, not Fortran
                            # modules — their contents become block args, not USE stubs.
                            if (
                                instance_module in meta_data
                                and meta_data[instance_module].getAttr("type") == CCPPType.HOST
                            ):
                                physics_arg_sources.append(("block",))
                            else:
                                physics_arg_sources.append(
                                    ("ddt_member", instance_var, instance_module, full_member)
                                )
                        else:
                            print(
                                f"Warning: '{suite_callee}' arg '{arg_name}' "
                                f"(standard_name='{std_name}') matched DDT type "
                                f"'{ddt_type_name}' but no module-level instance was "
                                f"found — treating as a host-caller block argument.",
                                file=sys.stderr,
                            )
                            physics_arg_sources.append(("block",))
                    else:
                        physics_arg_sources.append(("host", host_var, host_mod))
                elif std_name and cap_var_map and std_name in cap_var_map:
                    # Cap-owned module variable (e.g. vmr interstitial DDT)
                    physics_arg_sources.append(("cap_var", std_name))
                else:
                    if std_name and std_name not in host_block_std_names \
                            and std_name not in CCPP_FRAMEWORK_STD_NAMES \
                            and std_name not in constituent_std_names \
                            and not arg_name.endswith("__opt"):
                        print(
                            f"Warning: '{suite_callee}' arg '{arg_name}' "
                            f"(standard_name='{std_name}') has no host variable "
                            f"match — treating as a host-caller block argument. "
                            f"Check that the host metadata provides this variable.",
                            file=sys.stderr,
                        )
                    physics_arg_sources.append(("block",))

            non_host_args = [
                (callee_input_names[i], callee_input_types[i],
                 std_name_of.get(_bare(callee_input_names[i]),
                                 callee_input_names[i]))
                for i, src in enumerate(physics_arg_sources)
                if src[0] == "block"
                # cap_var sources are cap-internal; don't expose as block args
            ]

            # Collect module-level host global stubs (shared across all suites).
            for i, (_arg_name, _arg_type) in enumerate(
                zip(callee_input_names, callee_input_types)
            ):
                src = physics_arg_sources[i]
                if src[0] == "host":
                    _, host_var_name, host_module_name = src
                    stub_name, stub_module = host_var_name, host_module_name
                elif src[0] == "ddt_member":
                    _, instance_var, instance_module, _member = src
                    stub_name, stub_module = instance_var, instance_module
                elif src[0] == "cap_var":
                    continue  # cap vars live in the same module, no USE needed
                else:
                    continue
                key = (stub_name, stub_module)
                if key not in seen_host_globals:
                    seen_host_globals.add(key)
                    glob = llvm.GlobalOp(
                        llvm.LLVMArrayType.from_size_and_type(1, i8),
                        stub_name,
                        "external",
                    )
                    glob.attributes["module"] = StringAttr(stub_module)
                    host_global_ops.append(glob)

            per_suite.append(
                {
                    "suite_name": suite_name,
                    "suite_part": suite_part,
                    "suite_callee": suite_callee,
                    "callee_module": callee_module,
                    "callee_output_types": callee_output_types,
                    "callee_input_types": callee_input_types,
                    "callee_input_names": callee_input_names,
                    "physics_arg_sources": physics_arg_sources,
                    "non_host_args": non_host_args,
                    "std_name_of": std_name_of,
                    "scheme_names": scheme_names,
                    "local_to_array_layout": local_to_array_layout,
                }
            )

        return per_suite, host_global_ops

    def _build_run_block_signature(
        self,
        per_suite: list,
        meta_data,
        kwargs: dict,
        suite_name_type,
        suite_part_type,
        errmsg_type,
        errflg_type,
        int_base,
    ) -> "_RunBlockSignature":
        """Build the function block and all arg/SSA mappings for the run dispatcher.

        Computes the union of non-host args across all suites, filters out args
        provided by ccpp_info_t / ccpp_t framework types, constructs the Block with
        the correct arg-type list, and returns every SSA value needed by the
        dispatch chain and function assembly phases.
        """
        ccpp_info_type = kwargs.get("ccpp_info_type")
        ccpp_info_module = kwargs.get("ccpp_info_module")
        ccpp_t_type = kwargs.get("ccpp_t_type")
        ccpp_t_var_name = kwargs.get("ccpp_t_var_name", "ccpp_data")

        # ── Union of non-host args across all suites (ordered by first appearance) ──
        # Deduplicate by standard_name: different schemes may use different local
        # names for the same variable (e.g. 'cols'/'cole' vs 'col_start'/'col_end'
        # for horizontal_loop_begin/end).  Only the first-seen local name is kept.
        union_non_host_args: dict = {}  # canonical_arg_name → arg_type
        seen_non_host_std_names: dict = {}  # std_name → canonical_arg_name
        # Also build a rename map for per-suite block_arg_map construction below.
        non_host_std_to_canonical: dict = {}  # suite-level std_name → canonical name
        for info in per_suite:
            for arg_name, arg_type, std_name in info["non_host_args"]:
                if std_name and std_name in seen_non_host_std_names:
                    # Same standard_name seen before — record the rename
                    canonical = seen_non_host_std_names[std_name]
                    non_host_std_to_canonical[std_name] = canonical
                elif arg_name not in union_non_host_args:
                    union_non_host_args[arg_name] = arg_type
                    if std_name:
                        seen_non_host_std_names[std_name] = arg_name
                        non_host_std_to_canonical[std_name] = arg_name

        # When the host uses the ccpp_info_t pattern, loop bounds (col_start/col_end)
        # come from ccpp_info%col_start/col_end — exclude them from the block args.
        if ccpp_info_type is not None:
            # Collect all member names of the ccpp_info_t DDT from meta_data.
            # These are fields provided by ccpp_info, not separate block args.
            _ccpp_ddt_name = ccpp_info_type.element_type.type_name.data
            _ccpp_member_names: set = set()
            _ccpp_member_std_names: set = {CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME}
            for _mn, _mp in meta_data.items():
                if _mn != _ccpp_ddt_name:
                    continue
                if _mn not in _mp.arg_tables:
                    continue
                for _mv in _mp.getArgTable(_mn).getFunctionArguments():
                    _ccpp_member_names.add(_mv.name)
                    if _mv.hasAttr("standard_name"):
                        _ccpp_member_std_names.add(_mv.getAttr("standard_name").lower())

            # Also collect canonical arg names for loop-begin/end std_names.
            _ccpp_provided_canonicals = {
                non_host_std_to_canonical[s]
                for s in _ccpp_member_std_names
                if s in non_host_std_to_canonical
            }
            # Filter: remove args whose arg_name matches a ccpp_info member OR
            # whose canonical name maps to a ccpp_info-provided std_name.
            union_non_host_args = {
                k: v for k, v in union_non_host_args.items()
                if k not in _ccpp_member_names and k not in _ccpp_provided_canonicals
            }

        if ccpp_t_type is not None and ccpp_t_var_name in union_non_host_args:
            # Remove the ccpp_t variable; it is threaded at a fixed position (args[2]).
            union_non_host_args = {
                k: v for k, v in union_non_host_args.items()
                if k != ccpp_t_var_name
            }

        n_non_host = len(union_non_host_args)

        if ccpp_info_type is not None:
            all_block_types = (
                [suite_name_type, suite_part_type, ccpp_info_type]
                + list(union_non_host_args.values())
            )
        elif ccpp_t_type is not None:
            all_block_types = (
                [suite_name_type, suite_part_type, ccpp_t_type]
                + list(union_non_host_args.values())
                + [errmsg_type, errflg_type]
            )
        else:
            all_block_types = (
                [suite_name_type, suite_part_type]
                + list(union_non_host_args.values())
                + [errmsg_type, errflg_type]
            )
        new_block = Block(arg_types=all_block_types)

        suite_name_arg = new_block.args[0]
        suite_name_arg.name_hint = "suite_name"
        suite_part_arg = new_block.args[1]

        ccpp_info_block_arg = None
        ccpp_data_block_arg = None
        col_start_ref = None
        col_end_ref = None
        errmsg_alloc = None
        errflg_alloc = None

        if ccpp_info_type is not None:
            ccpp_info_block_arg = new_block.args[2]
            ccpp_info_block_arg.name_hint = "ccpp_info"
            suite_part_arg.name_hint = "suite_part"

            block_arg_map = {}
            for i, arg_name in enumerate(union_non_host_args):
                ba = new_block.args[3 + i]
                ba.name_hint = arg_name
                block_arg_map[arg_name] = ba

            # Loop bounds from ccpp_info%col_start / col_end
            int_type = memref.MemRefType(int_base, [])
            col_start_ref = HostVarRefOp(
                "ccpp_info", ccpp_info_module, int_type, member_name="col_start"
            )
            col_end_ref = HostVarRefOp(
                "ccpp_info", ccpp_info_module, int_type, member_name="col_end"
            )
            col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
            col_end_key = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
            if col_begin_key:
                block_arg_map[col_begin_key] = col_start_ref.res
            if col_end_key:
                block_arg_map[col_end_key] = col_end_ref.res
            # Also map the ccpp_info_t member names directly so callee arg
            # lookup works even when the callee uses member names with no std_name.
            block_arg_map["col_start"] = col_start_ref.res
            block_arg_map["col_end"] = col_end_ref.res

            # errmsg/errflg from ccpp_info members (no separate block args)
            errmsg_alloc = HostVarRefOp(
                "ccpp_info", ccpp_info_module, errmsg_type, member_name="errmsg"
            )
            errflg_alloc = HostVarRefOp(
                "ccpp_info", ccpp_info_module, errflg_type, member_name="errflg"
            )
            errmsg_arg = errmsg_alloc.res
            errflg_arg = errflg_alloc.res
            # Map member names for errmsg/errflg so callee arg lookup works.
            block_arg_map["errmsg"] = errmsg_alloc.res
            block_arg_map["errflg"] = errflg_alloc.res
        elif ccpp_t_type is not None:
            # ccpp_t pattern: ccpp_data at args[2], non-host args follow, then errmsg/errflg.
            ccpp_data_block_arg = new_block.args[2]
            ccpp_data_block_arg.name_hint = ccpp_t_var_name
            suite_part_arg.name_hint = "suite_part"

            block_arg_map = {}
            for i, arg_name in enumerate(union_non_host_args):
                ba = new_block.args[3 + i]
                ba.name_hint = arg_name
                block_arg_map[arg_name] = ba
            block_arg_map[ccpp_t_var_name] = ccpp_data_block_arg

            errmsg_arg = new_block.args[3 + n_non_host]
            errmsg_arg.name_hint = "errmsg"
            errflg_arg = new_block.args[3 + n_non_host + 1]
            errflg_arg.name_hint = "errflg"
        else:
            suite_part_arg.name_hint = "suite_part"
            block_arg_map = {}
            for i, arg_name in enumerate(union_non_host_args):
                ba = new_block.args[2 + i]
                ba.name_hint = arg_name
                block_arg_map[arg_name] = ba

            errmsg_arg = new_block.args[2 + n_non_host]
            errmsg_arg.name_hint = "errmsg"
            errflg_arg = new_block.args[2 + n_non_host + 1]
            errflg_arg.name_hint = "errflg"

        return _RunBlockSignature(
            new_block=new_block,
            all_block_types=all_block_types,
            block_arg_map=block_arg_map,
            non_host_std_to_canonical=non_host_std_to_canonical,
            suite_name_arg=suite_name_arg,
            suite_part_arg=suite_part_arg,
            errmsg_arg=errmsg_arg,
            errflg_arg=errflg_arg,
            col_start_ref=col_start_ref,
            col_end_ref=col_end_ref,
            errmsg_alloc=errmsg_alloc,
            errflg_alloc=errflg_alloc,
            ccpp_info_block_arg=ccpp_info_block_arg,
            ccpp_data_block_arg=ccpp_data_block_arg,
            ccpp_info_type=ccpp_info_type,
            ccpp_t_type=ccpp_t_type,
        )

    @staticmethod
    def _build_run_chain_preamble(
        per_suite: list,
        suite_name_arg,
        errmsg_arg,
        errflg_arg,
    ) -> "_RunChainPreamble":
        """Build the seed ops and grouping data for the if/else dispatch chain.

        Creates the errflg initialisation op, the suite-name trim, the innermost
        "no suite matched" error sequence (the seed for inside-out chain building),
        and groups per_suite entries by suite_name for the outer loop.

        Pure function — no side effects, no IR mutation beyond creating new ops.
        """
        err_const = arith.ConstantOp.from_int_and_width(0, 32)
        store_errflg = memref.StoreOp.get(err_const, errflg_arg, [])
        trim_suite_name = TrimOp(suite_name_arg)

        write_suite_name_err = WriteErrMsgOp(
            errmsg_arg, trim_suite_name.res, "No suite named ", "found"
        )
        one_outer_err = arith.ConstantOp.from_int_and_width(1, 32)
        store_outer_err = memref.StoreOp.get(one_outer_err, errflg_arg, [])

        current_false_ops = [
            write_suite_name_err,
            one_outer_err,
            store_outer_err,
            scf.YieldOp(),
        ]

        per_suite_grouped: dict = {}
        for _info in per_suite:
            _sn = _info["suite_name"]
            if _sn not in per_suite_grouped:
                per_suite_grouped[_sn] = []
            per_suite_grouped[_sn].append(_info)

        return _RunChainPreamble(
            err_const=err_const,
            store_errflg=store_errflg,
            trim_suite_name=trim_suite_name,
            current_false_ops=current_false_ops,
            all_decls=[],
            per_suite_grouped=per_suite_grouped,
        )

    def _build_run_dispatch_chain(
        self,
        per_suite_grouped: dict,
        trim_suite_name,
        suite_part_arg,
        errmsg_arg,
        errflg_arg,
        errmsg_type,
        errflg_type,
        block_arg_map: dict,
        non_host_std_to_canonical: dict,
        host_var_map: dict,
        meta_data,
        cap_var_map,
        seen_host_globals: set,
        current_false_ops: list,
        ccpp_t_type,
        ccpp_data_block_arg,
    ) -> "tuple[list, list, list]":
        """Build the nested if/else dispatch chain over suite_name and suite_part.

        Iterates per_suite_grouped in reverse (inside-out IfOp construction) to
        produce the final chain of strcmp/IfOp pairs rooted at ``trim_suite_name``.
        Host variable refs and array sections are hoisted to the outer (suite_name)
        if-true region so that GPUCcppCapPass can find them for directive generation.

        seen_host_globals is mutated in place (shared deduplication set).

        Returns (main_chain_ops, decls, chain_global_ops):
          - main_chain_ops: inner ops for the main block (excluding trailing YieldOp)
          - decls: external FuncOp declarations for every suite callee
          - chain_global_ops: GlobalOp USE stubs emitted during chain construction
        """
        decls = []
        chain_global_ops = []

        for suite_name, suite_infos in reversed(list(per_suite_grouped.items())):
            # trim_suite_part is created once and shared across all parts of this suite.
            trim_suite_part = TrimOp(suite_part_arg)

            # Innermost false branch: no suite_part matched.
            write_part_err = WriteErrMsgOp(
                errmsg_arg, trim_suite_part.res,
                "No suite part named ", f" found in suite {suite_name}",
            )
            one_part_err = arith.ConstantOp.from_int_and_width(1, 32)
            store_part_err = memref.StoreOp.get(one_part_err, errflg_arg, [])
            part_inner_false = [write_part_err, one_part_err, store_part_err, scf.YieldOp()]

            # Collect host var refs and array section ops across all suite parts so
            # they can be placed in the outer (suite_name) if's true region.  This
            # makes them visible to GPUCcppCapPass, which looks for HostVarRefOps in
            # the outer true_block when building !$acc data directives.  SSA values
            # defined in the outer block are still accessible inside the inner if's
            # true region (dominance), so the suite physics call is unaffected.
            suite_host_refs: list = []
            suite_array_secs: list = []

            for info in reversed(suite_infos):
                suite_part = info["suite_part"]
                suite_callee = info["suite_callee"]
                callee_module = info["callee_module"]
                callee_output_types = info["callee_output_types"]
                callee_input_types = info["callee_input_types"]
                callee_input_names = info["callee_input_names"]
                physics_arg_sources = info["physics_arg_sources"]
                std_name_of = info["std_name_of"]
                scheme_names = info["scheme_names"]
                local_to_array_layout = info.get("local_to_array_layout", {})

                # ── Build standard_name → dim_names for cap_var sources ──────
                cap_var_std_to_dims: dict = {}
                for _sv_scheme in scheme_names:
                    _sv_run_tbl = _sv_scheme + "_run"
                    if _sv_scheme not in meta_data:
                        continue
                    if _sv_run_tbl not in meta_data[_sv_scheme].arg_tables:
                        continue
                    for _sv_fa in (
                        meta_data[_sv_scheme].getArgTable(_sv_run_tbl).getFunctionArguments()
                    ):
                        if _sv_fa.hasAttr("standard_name") and _sv_fa.hasAttr("dim_names"):
                            _sv_sn = _sv_fa.getAttr("standard_name").lower()
                            if _sv_sn not in cap_var_std_to_dims:
                                cap_var_std_to_dims[_sv_sn] = _sv_fa.getAttr("dim_names")

                # ── HostVarRefOps ─────────────────────────────────────────────
                host_var_ref_ops = []
                host_var_ref_results = {}
                host_name_to_ref_result = {}

                for i, (arg_name, arg_type) in enumerate(
                    zip(callee_input_names, callee_input_types)
                ):
                    src = physics_arg_sources[i]
                    if src[0] == "host":
                        _, host_var_name, host_module_name = src
                        ref_op = HostVarRefOp(host_var_name, host_module_name, arg_type)
                        host_var_ref_ops.append(ref_op)
                        host_var_ref_results[arg_name] = ref_op.res
                        host_name_to_ref_result[host_var_name] = ref_op.res
                    elif src[0] == "ddt_member":
                        _, instance_var, instance_module, member_name = src
                        # Resolve std_name tokens in subscript to local variable names
                        resolved_member, sub_vars = self._resolve_member_subscripts(
                            member_name, host_var_map
                        )
                        ref_op = HostVarRefOp(
                            instance_var, instance_module, arg_type,
                            member_name=resolved_member,
                        )
                        host_var_ref_ops.append(ref_op)
                        host_var_ref_results[arg_name] = ref_op.res
                        host_name_to_ref_result[f"{instance_var}%{resolved_member}"] = ref_op.res
                        # Emit USE stubs for subscript variables (already resolved to local names)
                        for local_name, module_name in sub_vars:
                            key = (local_name, module_name)
                            if key not in seen_host_globals:
                                seen_host_globals.add(key)
                                sv_glob = llvm.GlobalOp(
                                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                                    local_name, "external",
                                )
                                sv_glob.attributes["module"] = StringAttr(module_name)
                                chain_global_ops.append(sv_glob)
                    elif src[0] == "cap_var":
                        _, std_name_cv = src
                        cv_name, cv_type, _ftn = cap_var_map[std_name_cv]
                        _cv_dims = cap_var_std_to_dims.get(std_name_cv, [])
                        if _cv_dims and _cv_dims[0].lower() == CCPP_LOOP_EXTENT_STD_NAME:
                            _cv_rank = (
                                len(list(arg_type.shape.data))
                                if hasattr(arg_type, "shape") else 0
                            )
                            if _cv_rank > 0:
                                cv_name = f"{cv_name}({', '.join([':'] * _cv_rank)})"
                        cap_ref = CapVarRefOp(cv_name, arg_type)
                        host_var_ref_ops.append(cap_ref)
                        host_var_ref_results[arg_name] = cap_ref.res

                # ── ArraySectionOps ───────────────────────────────────────────
                array_section_pre_ops = []
                array_section_extra_ops = []
                array_section_main_ops = []
                one_const_for_sections = None

                for i, (arg_name, arg_type) in enumerate(
                    zip(callee_input_names, callee_input_types)
                ):
                    # Row-major rank≥2 arrays are handled by RowMajorConvertOp below;
                    # skip ArraySectionOp for them so we don't double-slice.
                    if _bare(arg_name) in local_to_array_layout:
                        continue
                    src = physics_arg_sources[i]
                    if src[0] == "host":
                        _, host_var_name, host_module_name = src
                        lookup_var, lookup_mod = host_var_name, host_module_name
                    elif src[0] == "ddt_member":
                        _, instance_var, instance_module, member_name = src
                        # For nested paths like "b%x" or "b%x(ncol)", strip the
                        # chain prefix and any array subscripts to get the leaf
                        # member name for the var descriptor lookup.
                        leaf = member_name.rsplit("%", 1)[-1].split("(")[0]
                        lookup_var, lookup_mod = leaf, instance_module
                    elif src[0] == "cap_var":
                        _, std_name_cv = src
                        _cv_dims = cap_var_std_to_dims.get(std_name_cv, [])
                        if not _cv_dims or _cv_dims[0].lower() != CCPP_LOOP_EXTENT_STD_NAME:
                            continue
                        col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
                        col_end_key   = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
                        if not col_begin_key or not col_end_key:
                            continue
                        if col_begin_key not in block_arg_map or col_end_key not in block_arg_map:
                            continue
                        section = ArraySectionOp(
                            host_var_ref_results[arg_name],
                            [block_arg_map[col_begin_key]],
                            [block_arg_map[col_end_key]],
                        )
                        array_section_main_ops.append(section)
                        host_var_ref_results[arg_name] = section.res
                        continue
                    else:
                        continue

                    # Look up the var descriptor; for DDT members, search the DDT table
                    host_var_name = lookup_var
                    host_module_name = lookup_mod
                    try:
                        # Try the module table first, then DDT tables
                        if lookup_mod in meta_data and lookup_mod in meta_data[lookup_mod].arg_tables:
                            mod_arg_table = meta_data[lookup_mod].getArgTable(lookup_mod)
                            host_var_desc = mod_arg_table.getFunctionArgument(lookup_var)
                        else:
                            # DDT member: search all DDT tables for the member
                            raise AssertionError("not found in module, try DDT")
                    except (KeyError, AssertionError):
                        # Try DDT tables
                        found = False
                        for tbl_name, props in meta_data.items():
                            if props.getAttr("type") != CCPPType.DDT:
                                continue
                            if tbl_name not in props.arg_tables:
                                continue
                            try:
                                host_var_desc = props.getArgTable(tbl_name).getFunctionArgument(lookup_var)
                                found = True
                                break
                            except (KeyError, AssertionError):
                                continue
                        if not found:
                            continue

                    if not host_var_desc.hasAttr("dim_names"):
                        continue
                    dim_names_list = host_var_desc.getAttr("dim_names")
                    if not dim_names_list or dim_names_list[0].lower() != CCPP_HORIZ_DIM_STD_NAME:
                        continue

                    # Find the canonical block arg names for loop begin/end via
                    # standard_name, since different schemes use different local names.
                    col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
                    col_end_key   = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
                    if not col_begin_key or not col_end_key:
                        continue
                    if col_begin_key not in block_arg_map or col_end_key not in block_arg_map:
                        continue

                    lowers = [block_arg_map[col_begin_key]]
                    uppers = [block_arg_map[col_end_key]]

                    valid = True
                    for dim_std_name in dim_names_list[1:]:
                        if dim_std_name not in host_var_map:
                            valid = False
                            break
                        dim_var_name, dim_module_name = host_var_map[dim_std_name]

                        if dim_var_name in host_name_to_ref_result:
                            dim_upper_ref = host_name_to_ref_result[dim_var_name]
                        else:
                            dim_ref_op = HostVarRefOp(
                                dim_var_name,
                                dim_module_name,
                                TypeConversions.getBaseType("integer"),
                            )
                            array_section_extra_ops.append(dim_ref_op)
                            host_name_to_ref_result[dim_var_name] = dim_ref_op.res
                            dim_upper_ref = dim_ref_op.res

                            key = (dim_var_name, dim_module_name)
                            if key not in seen_host_globals:
                                seen_host_globals.add(key)
                                dim_glob = llvm.GlobalOp(
                                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                                    dim_var_name,
                                    "external",
                                )
                                dim_glob.attributes["module"] = StringAttr(dim_module_name)
                                chain_global_ops.append(dim_glob)

                        if one_const_for_sections is None:
                            one_const_for_sections = arith.ConstantOp.from_int_and_width(
                                1, 32
                            )
                            array_section_pre_ops.append(one_const_for_sections)

                        lowers.append(one_const_for_sections.result)
                        uppers.append(dim_upper_ref)

                    if not valid or len(lowers) < 2:
                        continue

                    section = ArraySectionOp(
                        host_var_ref_results[arg_name],
                        lowers,
                        uppers,
                    )
                    array_section_main_ops.append(section)
                    host_var_ref_results[arg_name] = section.res

                array_section_ops = (
                    array_section_pre_ops + array_section_extra_ops + array_section_main_ops
                )

                # ── RowMajorConvertOps (rank≥2 row_major host arrays) ─────────
                # Transpose row-major host arrays to column-major temps before
                # passing them to the suite.  ArraySectionOps are skipped for
                # these args (see check above) so host_var_ref_results[arg_name]
                # still holds the raw HostVarRefOp result at this point.
                row_major_convert_ops: list = []
                row_major_write_back_pairs: list = []  # (conv_op, host_ref_result)

                for i, (arg_name, arg_type) in enumerate(
                    zip(callee_input_names, callee_input_types)
                ):
                    src = physics_arg_sources[i]
                    if src[0] != "host":
                        continue
                    bare = _bare(arg_name)
                    if bare not in local_to_array_layout:
                        continue

                    dim_std_names, intent = local_to_array_layout[bare]
                    dim_exprs: list = []
                    valid = True
                    for dim_sn in dim_std_names:
                        sn_lower = dim_sn.lower()
                        if sn_lower == CCPP_LOOP_EXTENT_STD_NAME:
                            # horizontal loop extent: express as col_end - col_start + 1
                            col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
                            col_end_key   = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
                            if (col_begin_key and col_end_key
                                    and col_begin_key in block_arg_map
                                    and col_end_key in block_arg_map):
                                dim_exprs.append(f"{col_end_key} - {col_begin_key} + 1")
                            else:
                                valid = False
                                break
                        else:
                            canonical = non_host_std_to_canonical.get(sn_lower)
                            if canonical:
                                dim_exprs.append(canonical)
                            elif sn_lower in host_var_map:
                                # Dimension is a host module variable; use its name directly
                                dim_exprs.append(host_var_map[sn_lower][0])
                            else:
                                valid = False
                                break
                    if not valid:
                        continue

                    host_ref_result = host_var_ref_results[arg_name]
                    conv_op = RowMajorConvertOp(host_ref_result, dim_exprs, arg_type)
                    conv_op.res.name_hint = f"{bare}_col"
                    row_major_convert_ops.append(conv_op)
                    host_var_ref_results[arg_name] = conv_op.res

                    if intent in ("inout", "out"):
                        row_major_write_back_pairs.append((conv_op, host_ref_result, dim_exprs))

                # ── Build call args in callee order ───────────────────────────
                call_args = []
                call_arg_bare_names = []
                for i, arg_name in enumerate(callee_input_names):
                    src = physics_arg_sources[i]
                    if src[0] in ("host", "ddt_member", "cap_var"):
                        call_args.append(host_var_ref_results[arg_name])
                    else:
                        # Block arg: use canonical name if this arg was deduplicated
                        bare = _bare(arg_name)
                        std = std_name_of.get(bare, bare)
                        canonical = non_host_std_to_canonical.get(std, arg_name)
                        # Fall back to arg_name if canonical not in block_arg_map
                        key = canonical if canonical in block_arg_map else arg_name
                        call_args.append(block_arg_map[key])
                    call_arg_bare_names.append(_bare(arg_name))

                # ── Verify argument count matches callee signature ─────────────
                if len(call_args) != len(callee_input_types):
                    raise ValueError(
                        f"Signature mismatch for '{suite_callee}': "
                        f"generated {len(call_args)} input arg(s) but callee expects "
                        f"{len(callee_input_types)}.\n"
                        f"  Callee inputs:   {callee_input_names}\n"
                        f"  Generated args:  {[str(a) for a in call_args]}"
                    )

                # ── Inner if for suite_part ───────────────────────────────────
                suite_part_eq = StrCmpOp(trim_suite_part.res, literal=suite_part)

                # Use keyword-argument call when any suite cap input is optional
                # so that Fortran correctly forwards the OPTIONAL absence status.
                suite_has_optional = any(n.endswith("__opt") for n in callee_input_names)
                if suite_has_optional:
                    # Derive result keyword names from output types
                    _result_names = [
                        "errmsg" if rt == errmsg_type
                        else "errflg" if rt == errflg_type
                        else f"_out_{_i}"
                        for _i, rt in enumerate(callee_output_types)
                    ]
                    call_op = KeywordCallOp(
                        suite_callee,
                        ArrayAttr([StringAttr(n) for n in call_arg_bare_names]),
                        ArrayAttr([StringAttr(n) for n in _result_names]),
                        DictionaryAttr({}),
                        call_args,
                        callee_output_types,
                    )
                else:
                    call_op = func.CallOp(suite_callee, call_args, callee_output_types)

                # CapVarRefOps for inout-echo returns must be placed BEFORE the call
                # so the printer can resolve their names when processing return positions.
                #
                # Use _get_suite_lifecycle_ret_info to get std_names for alloc returns
                # (intent=out scalars).  Suite cap returns: inout_vals first, then
                # alloc_vals.  Compute the offset so alloc positions are matched by
                # standard_name rather than type, preventing false errflg matches when
                # another intent=out scalar (e.g. const_index) has the same MLIR type.
                _run_ret_alloc = self._get_suite_lifecycle_ret_info(
                    scheme_names, meta_data, "_run"
                )
                _n_inout_ret = len(callee_output_types) - len(_run_ret_alloc)

                cap_var_inout_refs: list = []
                copy_ops = []
                for idx, ret_type in enumerate(callee_output_types):
                    result = call_op.results[idx]
                    if idx < _n_inout_ret:
                        # inout return vals: type-match only (no positional info available)
                        if ret_type == errmsg_type:
                            copy_ops.append(memref.CopyOp(result, errmsg_arg))
                        elif ret_type == errflg_type:
                            copy_ops.append(memref.CopyOp(result, errflg_arg))
                        elif (
                            ccpp_t_type is not None
                            and hasattr(ret_type, "element_type")
                            and hasattr(ret_type.element_type, "type_name")
                            and ret_type.element_type.type_name.data == "ccpp_t"
                        ):
                            # ccpp_t is intent(inout) — mirror back to the block arg
                            # so the printer's inout-echo detection fires.
                            copy_ops.append(memref.CopyOp(result, ccpp_data_block_arg))
                    else:
                        ri_idx = idx - _n_inout_ret
                        ret_std_name = _run_ret_alloc[ri_idx][2]
                        ret_local_name = _run_ret_alloc[ri_idx][1]
                        if ret_std_name == CCPP_ERROR_MESSAGE:
                            copy_ops.append(memref.CopyOp(result, errmsg_arg))
                        elif ret_std_name == CCPP_ERROR_CODE:
                            copy_ops.append(memref.CopyOp(result, errflg_arg))
                        else:
                            # Non-error scalar out (e.g. const_index).
                            # 1) block arg (e.g. when not host-matched)
                            canonical = non_host_std_to_canonical.get(
                                ret_std_name, ret_local_name
                            ) if ret_std_name else ret_local_name
                            if canonical and canonical in block_arg_map:
                                copy_ops.append(
                                    memref.CopyOp(result, block_arg_map[canonical])
                                )
                            elif ret_std_name and ret_std_name in host_var_map:
                                # 2) host module var: write result back to the host.
                                # (intent=out scalars are not in callee_input_names so
                                # no HostVarRefOp exists yet — create one here.)
                                hv_name, hv_module = host_var_map[ret_std_name]
                                hv_ref = HostVarRefOp(hv_name, hv_module, ret_type)
                                cap_var_inout_refs.append(hv_ref)
                                copy_ops.append(memref.CopyOp(result, hv_ref.res))
                                hv_key = (hv_name, hv_module)
                                if hv_key not in seen_host_globals:
                                    seen_host_globals.add(hv_key)
                                    hv_glob = llvm.GlobalOp(
                                        llvm.LLVMArrayType.from_size_and_type(1, i8),
                                        hv_name, "external",
                                    )
                                    hv_glob.attributes["module"] = StringAttr(hv_module)
                                    chain_global_ops.append(hv_glob)
                            elif cap_var_map:
                                # 3) cap_var inout echo: suite cap returns cap-owned scalar.
                                for i, (a_name, a_type) in enumerate(
                                    zip(callee_input_names, callee_input_types)
                                ):
                                    if (a_type == ret_type
                                            and physics_arg_sources[i][0] == "cap_var"):
                                        _, std_name_cv = physics_arg_sources[i]
                                        cv_name, cv_type, _ = cap_var_map[std_name_cv]
                                        cap_ref = CapVarRefOp(cv_name, a_type)
                                        cap_var_inout_refs.append(cap_ref)
                                        copy_ops.append(memref.CopyOp(result, cap_ref.res))
                                        break

                # Build write-back ops for row-major arrays (inout/out only).
                row_major_write_back_ops: list = []
                for conv_op, host_ref_result, dim_exprs in row_major_write_back_pairs:
                    wb_op = RowMajorWriteBackOp(conv_op.res, host_ref_result, dim_exprs)
                    row_major_write_back_ops.append(wb_op)

                inner_if_true = (
                    cap_var_inout_refs
                    + row_major_convert_ops
                    + [call_op]
                    + copy_ops
                    + row_major_write_back_ops
                )

                inner_if = scf.IfOp(
                    suite_part_eq.res,
                    [],
                    [*inner_if_true, scf.YieldOp()],
                    part_inner_false,
                )
                part_inner_false = [suite_part_eq, inner_if, scf.YieldOp()]
                suite_host_refs.extend(host_var_ref_ops)
                suite_array_secs.extend(array_section_ops)

                decl = func.FuncOp.external(
                    suite_callee, callee_input_types, callee_output_types
                )
                decl.attributes["module"] = StringAttr(callee_module)
                decls.append(decl)

            # Outer if for suite_name (after processing all groups).
            # suite_host_refs and suite_array_secs are placed here (before the
            # suite-part dispatch) so GPUCcppCapPass can find them in true_block.
            true_branch_ops = [trim_suite_part, *suite_host_refs, *suite_array_secs, *part_inner_false[:-1], scf.YieldOp()]
            strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite_name)
            if_op = scf.IfOp(
                strcmp_op.res,
                [],
                true_branch_ops,
                current_false_ops,
            )
            current_false_ops = [strcmp_op, if_op, scf.YieldOp()]

        main_chain_ops = current_false_ops[:-1]
        return main_chain_ops, decls, chain_global_ops

    @staticmethod
    def _assemble_run_fn(
        fn_name: str,
        sig: "_RunBlockSignature",
        pre: "_RunChainPreamble",
        main_chain_ops: list,
        errmsg_type,
        errflg_type,
    ):
        """Assemble the FuncOp from the block signature, preamble ops, and dispatch chain.

        Determines the return type and preamble based on the host framework
        pattern (ccpp_info_t, ccpp_t, or standard capgen), fills new_block
        with all ops in execution order, and returns a public FuncOp.
        """
        if sig.ccpp_info_type is not None:
            ret_op = func.ReturnOp(sig.ccpp_info_block_arg)  # ccpp_info is inout
            fn_type = builtin.FunctionType.from_lists(
                sig.all_block_types, [sig.ccpp_info_type]
            )
            # Place col_start/col_end/errmsg/errflg HostVarRefOps before dispatch
            preamble_ops = [sig.col_start_ref, sig.col_end_ref, sig.errmsg_alloc, sig.errflg_alloc]
        elif sig.ccpp_t_type is not None:
            ret_op = func.ReturnOp(sig.ccpp_data_block_arg, sig.errmsg_arg, sig.errflg_arg)
            fn_type = builtin.FunctionType.from_lists(
                sig.all_block_types, [sig.ccpp_t_type, errmsg_type, errflg_type]
            )
            preamble_ops = []
        else:
            ret_op = func.ReturnOp(sig.errmsg_arg, sig.errflg_arg)
            fn_type = builtin.FunctionType.from_lists(
                sig.all_block_types, [errmsg_type, errflg_type]
            )
            preamble_ops = []

        sig.new_block.add_ops(
            [
                *preamble_ops,
                pre.err_const,
                pre.store_errflg,
                pre.trim_suite_name,
                *main_chain_ops,
                ret_op,
            ]
        )

        body = Region()
        body.add_block(sig.new_block)
        return func.FuncOp(fn_name, fn_type, body, visibility="public")

    @staticmethod
    def _resolve_member_subscripts(member_name: str, host_var_map: dict) -> tuple:
        """Resolve standard_name tokens in a DDT member subscript to local var names.

        For 'q(:,:,index_of_water_vapor_specific_humidity)' with a host_var_map that
        maps the standard_name to ('index_qv', 'test_host_mod'), returns
        ('q(:,:,index_qv)', [('index_qv', 'test_host_mod')]).

        Bare colons and integer literals are passed through unchanged.
        """
        paren = member_name.find("(")
        if paren < 0:
            return member_name, []
        base = member_name[:paren]
        subscript = member_name[paren + 1: member_name.rfind(")")]
        resolved_tokens = []
        sub_vars = []
        for token in subscript.split(","):
            t = token.strip()
            if t == ":" or t.isdigit():
                resolved_tokens.append(t)
            else:
                t_lower = t.lower()
                if t_lower in host_var_map:
                    local_name, module_name = host_var_map[t_lower]
                    resolved_tokens.append(local_name)
                    sub_vars.append((local_name, module_name))
                else:
                    resolved_tokens.append(t)
        return f"{base}({', '.join(resolved_tokens)})", sub_vars

    def _get_suite_lifecycle_return_types(self, scheme_names, meta_data, table_postfix):
        """Derive the ordered return types of a suite lifecycle subroutine."""
        return [t for t, _n, _s in
                self._get_suite_lifecycle_ret_info(scheme_names, meta_data, table_postfix)]

    def _get_suite_lifecycle_ret_info(self, scheme_names, meta_data, table_postfix):
        """Return [(mlir_type, arg_name, standard_name)] for intent=out scalar args.

        Applies the same filters as suite_cap.py's ``output_arg_list`` so the
        returned types match the actual FuncOp return signature generated by the
        suite cap:
        - intent=out only
        - Scalar (dimensions = 0 or absent) — array outs are block args, not returns
        - Not allocatable — those become __alloc block args
        - Not interstitial — framework-managed vars are not suite cap outputs
        """
        all_out_args = {}
        for scheme_name in scheme_names:
            table_name = scheme_name + table_postfix
            if scheme_name not in meta_data:
                continue
            if table_name not in meta_data[scheme_name].arg_tables:
                continue
            arg_table = meta_data[scheme_name].getArgTable(table_name)
            for fn_arg in arg_table.getFunctionArguments():
                has_dims = fn_arg.hasAttr("dimensions") and fn_arg.getAttr("dimensions") > 0
                # Mirror suite_cap.py's _is_framework_managed logic:
                # interstitials of any type (real, integer, DDT) are excluded —
                # they are stored at suite cap module scope, not returned to caller.
                is_framework_managed = fn_arg.hasAttr("is_interstitial")
                # Deduplicate by standard_name so different local names for the
                # same logical arg (e.g. errflg vs errcode for ccpp_error_code)
                # don't produce duplicate return types.
                _dedup_key = (
                    fn_arg.getAttr("standard_name").lower()
                    if fn_arg.hasAttr("standard_name")
                    else fn_arg.name
                )
                if (
                    fn_arg.getAttr("intent") == "out"
                    and _dedup_key not in all_out_args
                    and not has_dims
                    and not fn_arg.hasAttr("allocatable")
                    and not is_framework_managed
                ):
                    all_out_args[_dedup_key] = fn_arg

        result = []
        for arg in all_out_args.values():
            mlir_type = TypeConversions.convert(
                arg.getAttr("type"),
                arg.getAttr("kind") if arg.hasAttr("kind") else None,
                0,
            )
            raw = arg.getAttr("standard_name") if arg.hasAttr("standard_name") else None
            std_name = raw.lower() if raw else None
            result.append((mlir_type, arg.name, std_name))
        return result

    def _collect_constituent_info(self, meta_data):
        """Extract constituent info from scheme metadata.

        Scans all SCHEME tables to find:
          - dynamic_array_names: bare arg names in _register tables with
            allocatable=True, type=ccpp_constituent_properties_t
          - fixed_advected: list of (std_name, units, default_val) for args
            with advected=.true. in non-register scheme tables

        Returns (dynamic_array_names, fixed_advected).
        """
        dynamic_array_names: list = []
        fixed_advected: list = []
        seen_fixed: set = set()

        for _scheme_name, props in meta_data.items():
            if props.getAttr("type") != CCPPType.SCHEME:
                continue
            for table_name, arg_table in props.arg_tables.items():
                is_register = table_name.endswith("_register")
                for fn_arg in arg_table.getFunctionArguments():
                    if (
                        is_register
                        and fn_arg.hasAttr("allocatable")
                        and fn_arg.hasAttr("type")
                        and fn_arg.getAttr("type") == "ccpp_constituent_properties_t"
                    ):
                        bare = _bare(fn_arg.name)
                        if bare not in dynamic_array_names:
                            dynamic_array_names.append(bare)
                    elif (
                        not is_register
                        and fn_arg.hasAttr("advected")
                        and fn_arg.hasAttr("standard_name")
                    ):
                        std_name = fn_arg.getAttr("standard_name").lower()
                        units = (
                            fn_arg.getAttr("units")
                            if fn_arg.hasAttr("units")
                            else "kg kg-1"
                        )
                        default_val = (
                            fn_arg.getAttr("default_value")
                            if fn_arg.hasAttr("default_value")
                            else None
                        )
                        if std_name not in seen_fixed:
                            seen_fixed.add(std_name)
                            fixed_advected.append((std_name, units, default_val))

        return dynamic_array_names, fixed_advected

    def _generate_lifecycle_fn(
        self,
        fn_name,
        suite_entries,
        suite_name_type,
        errmsg_type,
        errflg_type,
        char_base,
        int_base,
        public_fns,
        meta_data,
        seen_host_globals=None,
        cap_var_map=None,
        host_var_map_lc=None,
        **kwargs,
    ):
        """Build one combined CCPP cap lifecycle FuncOp dispatching over all suites.

        ``suite_entries`` is a list of
        ``(suite_name, suite_callee, call_ret_types, scheme_names, entry_postfix)``
        tuples.

        For lifecycle functions that have no host inputs (timestep_initial/final),
        ``entry_postfix`` is None and the call passes no input arguments.

        For initialize/finalize, ``entry_postfix`` is ``"_init"`` / ``"_finalize"``.
        The callee's input args are looked up in the scheme entry-point metadata and
        resolved against host module variables, mirroring what ``_generate_run_fn``
        does for the physics call.

        Returns ``(FuncOp, [external_decl_FuncOp, ...], [host_GlobalOp, ...])``.
        """
        for suite_name, suite_callee, _ret, _sn, _ep, _ri in suite_entries:
            assert suite_callee in public_fns, (
                f"Suite callee '{suite_callee}' not found among public suite cap "
                f"functions; available: {sorted(public_fns)}"
            )

        # MODULE only: lifecycle input arg lookups use USE statements, which only
        # work for MODULE-type tables.  HOST-type tables are caller-provided args
        # (not Fortran modules) so they must not generate USE stubs.
        host_var_map = self._build_host_var_map(meta_data, include_host=False)

        ccpp_info_type = kwargs.get("ccpp_info_type")
        ccpp_info_module = kwargs.get("ccpp_info_module")
        ccpp_t_type = kwargs.get("ccpp_t_type")
        ccpp_t_var_name = kwargs.get("ccpp_t_var_name", "ccpp_data")

        if ccpp_info_type is not None:
            # ccpp_info_t pattern: single inout arg bundles errmsg/errflg.
            # Use HostVarRefOps (member access) in place of AllocaOps so the
            # printer emits ccpp_info%errmsg / ccpp_info%errflg everywhere.
            new_block = Block(arg_types=[suite_name_type, ccpp_info_type])
            new_block.args[0].name_hint = "suite_name"
            new_block.args[1].name_hint = "ccpp_info"
            errmsg_alloc = HostVarRefOp(
                "ccpp_info", ccpp_info_module, errmsg_type, member_name="errmsg"
            )
            errflg_alloc = HostVarRefOp(
                "ccpp_info", ccpp_info_module, errflg_type, member_name="errflg"
            )
        elif ccpp_t_type is not None:
            # ccpp_t pattern: ccpp_data is threaded as intent(inout); errmsg/errflg
            # are still local allocas returned as intent(out) to the host.
            new_block = Block(arg_types=[suite_name_type, ccpp_t_type])
            new_block.args[0].name_hint = "suite_name"
            new_block.args[1].name_hint = ccpp_t_var_name
            errmsg_alloc = memref.AllocaOp.get(char_base, shape=[CCPP_ERRMSG_LEN])
            errmsg_alloc.memref.name_hint = "errmsg"
            errflg_alloc = memref.AllocaOp.get(int_base, shape=[])
            errflg_alloc.memref.name_hint = "errflg"
        else:
            # capgen pattern: function returns errmsg/errflg as separate outputs.
            errmsg_alloc = memref.AllocaOp.get(char_base, shape=[CCPP_ERRMSG_LEN])
            errmsg_alloc.memref.name_hint = "errmsg"
            errflg_alloc = memref.AllocaOp.get(int_base, shape=[])
            errflg_alloc.memref.name_hint = "errflg"
            new_block = Block(arg_types=[suite_name_type])
            new_block.args[0].name_hint = "suite_name"

        err_const = arith.ConstantOp.from_int_and_width(0, 32)
        store_errflg = memref.StoreOp.get(err_const, errflg_alloc, [])
        trim_suite_name = TrimOp(new_block.args[0])

        # Innermost else: no suite matched
        write_err = WriteErrMsgOp(
            errmsg_alloc, trim_suite_name.res, "No suite named ", "found"
        )
        one_err = arith.ConstantOp.from_int_and_width(1, 32)
        store_errflg_err = memref.StoreOp.get(one_err, errflg_alloc, [])
        current_false_ops = [write_err, one_err, store_errflg_err, scf.YieldOp()]

        all_host_global_ops: list = []
        # Use the shared set if provided to avoid duplicate GlobalOps across calls
        if seen_host_globals is None:
            seen_host_globals = set()
        decls = []
        # Placeholder allocas for unmatched args must be declared at function scope,
        # not inside IfOp branches. Collect them here and hoist to the main block.
        hoisted_alloc_ops: list = []

        _cap_var_map = cap_var_map or {}
        _host_var_map_lc = host_var_map_lc or {}

        for suite_name, suite_callee, call_ret_types, scheme_names, entry_postfix, ret_info \
                in reversed(suite_entries):
            _, _, callee_input_types, callee_input_names = public_fns[suite_callee]

            # Build {bare_arg_name → standard_name} from the scheme entry-point tables
            std_name_of: dict = {}
            if entry_postfix is not None:
                # atmospheric_physics uses _timestep_init/_timestep_final; accept both.
                _lc_postfix_aliases: dict[str, str] = {
                    "_timestep_initialize": "_timestep_init",
                    "_timestep_finalize": "_timestep_final",
                }
                _lc_candidates = [entry_postfix]
                if entry_postfix in _lc_postfix_aliases:
                    _lc_candidates.append(_lc_postfix_aliases[entry_postfix])
                for scheme_name in scheme_names:
                    if scheme_name not in meta_data:
                        continue
                    for _lc_cand in _lc_candidates:
                        entry_name = scheme_name + _lc_cand
                        if entry_name not in meta_data[scheme_name].arg_tables:
                            continue
                        for fn_arg in (
                            meta_data[scheme_name]
                            .getArgTable(entry_name)
                            .getFunctionArguments()
                        ):
                            # Strip __alloc/__opt suffix used for allocatable/optional name_hints
                            bare = _bare(fn_arg.name)
                            if bare not in std_name_of and fn_arg.hasAttr("standard_name"):
                                std_name_of[bare] = fn_arg.getAttr("standard_name").lower()
                        break  # found entry for this scheme; stop trying candidates

            # Resolve each input arg: host-mapped → HostVarRefOp, other → alloca
            true_branch_pre_ops: list = []
            call_inputs: list = []

            for arg_name, arg_type in zip(callee_input_names, callee_input_types):
                bare = _bare(arg_name)
                std_name = std_name_of.get(bare)

                if std_name and std_name in host_var_map:
                    host_var_name, host_module_name = host_var_map[std_name]
                    ref_op = HostVarRefOp(host_var_name, host_module_name, arg_type)
                    true_branch_pre_ops.append(ref_op)
                    call_inputs.append(ref_op.res)
                    # Emit host global stub for USE statement generation
                    key = (host_var_name, host_module_name)
                    if key not in seen_host_globals:
                        seen_host_globals.add(key)
                        glob = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            host_var_name,
                            "external",
                        )
                        glob.attributes["module"] = StringAttr(host_module_name)
                        all_host_global_ops.append(glob)
                elif (
                    ccpp_info_type is not None
                    and std_name == "host_standard_ccpp_type"
                ):
                    # The ccpp_info_t block arg IS the CCPP framework handle — pass
                    # it directly to callees that expect host_standard_ccpp_type.
                    call_inputs.append(new_block.args[1])
                elif (
                    ccpp_t_type is not None
                    and hasattr(arg_type, "element_type")
                    and hasattr(arg_type.element_type, "type_name")
                    and arg_type.element_type.type_name.data == "ccpp_t"
                ):
                    # The ccpp_t block arg is passed directly to suite callees.
                    call_inputs.append(new_block.args[1])
                else:
                    # Not host-matched (e.g. optional arg or allocatable DDT arg).
                    # Hoist the alloca to function scope so Fortran can declare it
                    # at the top of the subroutine (not inside an IfOp branch).
                    elem_type = arg_type.element_type
                    shape = list(arg_type.shape.data)
                    n_dyn = sum(1 for d in shape if d.data == DYNAMIC_INDEX)
                    if (
                        isinstance(elem_type, DerivedType)
                        and elem_type.type_name.data == "ccpp_constituent_properties_t"
                        and n_dyn > 0
                    ):
                        # Constituent-property arrays are declared at module scope
                        # via ModuleVarOp.  Reference them with CapVarRefOp so the
                        # allocated values persist after physics_register returns.
                        cap_ref = CapVarRefOp(f"lc_{bare}", arg_type)
                        hoisted_alloc_ops.append(cap_ref)
                        call_inputs.append(cap_ref.res)
                        _ddt_mod = _CCPP_CONSTITUENT_MOD
                        _key = (elem_type.type_name.data, _ddt_mod)
                        if _key not in seen_host_globals:
                            seen_host_globals.add(_key)
                            _g = llvm.GlobalOp(
                                llvm.LLVMArrayType.from_size_and_type(1, i8),
                                elem_type.type_name.data,
                                "external",
                            )
                            _g.attributes["module"] = StringAttr(_ddt_mod)
                            all_host_global_ops.append(_g)
                    elif n_dyn > 0:
                        # Dynamic-dim alloca requires size operands per MLIR rules.
                        # Use zero index constants as placeholders — these are
                        # allocatable args whose storage is managed by the callee.
                        zero_idx = arith.ConstantOp(
                            IntegerAttr(0, IndexType()), IndexType()
                        )
                        alloc_op = memref.AllocaOp.get(
                            elem_type, shape=shape,
                            dynamic_sizes=[zero_idx.result] * n_dyn,
                        )
                        alloc_op.memref.name_hint = f"lc_{bare}__alloc"
                        hoisted_alloc_ops.append(zero_idx)
                        # Ensure the DDT type's module appears in the USE list.
                        _CCPP_DDT_MODS = {
                            "ccpp_constituent_properties_t": _CCPP_CONSTITUENT_MOD,
                        }
                        if isinstance(elem_type, DerivedType):
                            _ddt_mod = _CCPP_DDT_MODS.get(elem_type.type_name.data)
                            if _ddt_mod:
                                _key = (elem_type.type_name.data, _ddt_mod)
                                if _key not in seen_host_globals:
                                    seen_host_globals.add(_key)
                                    _g = llvm.GlobalOp(
                                        llvm.LLVMArrayType.from_size_and_type(1, i8),
                                        elem_type.type_name.data,
                                        "external",
                                    )
                                    _g.attributes["module"] = StringAttr(_ddt_mod)
                                    all_host_global_ops.append(_g)
                        hoisted_alloc_ops.append(alloc_op)
                        call_inputs.append(alloc_op.memref)
                    else:
                        alloc_op = memref.AllocaOp.get(elem_type, shape=shape)
                        alloc_op.memref.name_hint = f"lc_{bare}"
                        hoisted_alloc_ops.append(alloc_op)
                        call_inputs.append(alloc_op.memref)

            # ── Verify argument count matches callee signature ─────────────────
            if len(call_inputs) != len(callee_input_types):
                raise ValueError(
                    f"Signature mismatch for '{suite_callee}': "
                    f"generated {len(call_inputs)} input arg(s) but callee expects "
                    f"{len(callee_input_types)}.\n"
                    f"  Callee inputs: {callee_input_names}"
                )

            # Build the call, then handle each return value:
            #   errmsg/errflg  → copy to the function's errmsg/errflg allocas
            #   cap-owned DDT  → copy to the module-level cap variable
            #   host variable  → copy back to the host module variable
            call_op = func.CallOp(suite_callee, call_inputs, call_ret_types)
            copy_ops = []
            copy_pre_ops = []  # CapVarRefOps / HostVarRefOps placed before the call
            for idx, (ret_type, _arg_name, std_name) in enumerate(ret_info):
                result = call_op.results[idx]
                # Match errmsg/errflg by standard_name when available (init/finalize),
                # or fall back to type matching for timestep functions where
                # ret_info has std_name=None (built from call_ret_types only).
                if std_name == CCPP_ERROR_MESSAGE or (
                    std_name is None and ret_type == errmsg_type
                ):
                    copy_ops.append(memref.CopyOp(result, errmsg_alloc))
                elif std_name == CCPP_ERROR_CODE or (
                    std_name is None and ret_type == errflg_type
                ):
                    copy_ops.append(memref.CopyOp(result, errflg_alloc))
                elif std_name and std_name in _cap_var_map:
                    # Cap-owned interstitial: copy to module-level var.
                    # Use the SSA result type; cap_var_map may store None for
                    # framework-managed and scratch vars whose type is only
                    # known from the actual return value.
                    var_name, var_type, _ftn = _cap_var_map[std_name]
                    cap_ref = CapVarRefOp(var_name, var_type or ret_type)
                    copy_pre_ops.append(cap_ref)
                    copy_ops.append(memref.CopyOp(result, cap_ref.res))
                elif std_name and std_name in _host_var_map_lc:
                    # Host variable: write result back to host module var
                    hv_name, hv_module = _host_var_map_lc[std_name]
                    hv_ref = HostVarRefOp(hv_name, hv_module, ret_type)
                    copy_pre_ops.append(hv_ref)
                    copy_ops.append(memref.CopyOp(result, hv_ref.res))
                    key = (hv_name, hv_module)
                    if key not in (seen_host_globals or set()):
                        if seen_host_globals is not None:
                            seen_host_globals.add(key)
                        hv_glob = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            hv_name, "external",
                        )
                        hv_glob.attributes["module"] = StringAttr(hv_module)
                        all_host_global_ops.append(hv_glob)
                elif (
                    ccpp_t_type is not None
                    and hasattr(ret_type, "element_type")
                    and hasattr(ret_type.element_type, "type_name")
                    and ret_type.element_type.type_name.data == "ccpp_t"
                ):
                    # ccpp_t is intent(inout) — mirror back to the block arg so
                    # the printer's inout-echo detection fires and the arg is not
                    # duplicated in the Fortran call argument list.
                    copy_ops.append(memref.CopyOp(result, new_block.args[1]))

            # copy_pre_ops (CapVarRefOp/HostVarRefOp) must come BEFORE the call so
            # the printer registers their results in `variables` before _print_call
            # resolves the return-value destinations.
            strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite_name)
            if_op = scf.IfOp(
                strcmp_op.res,
                [],
                true_branch_pre_ops + copy_pre_ops + [call_op] + copy_ops + [scf.YieldOp()],
                current_false_ops,
            )
            current_false_ops = [strcmp_op, if_op, scf.YieldOp()]

        main_chain_ops = current_false_ops[:-1]

        if ccpp_info_type is not None:
            ret_op = func.ReturnOp(new_block.args[1])  # return ccpp_info as inout
            fn_type = builtin.FunctionType.from_lists(
                [suite_name_type, ccpp_info_type],
                [ccpp_info_type],
            )
        elif ccpp_t_type is not None:
            ret_op = func.ReturnOp(new_block.args[1], errmsg_alloc, errflg_alloc)
            fn_type = builtin.FunctionType.from_lists(
                [suite_name_type, ccpp_t_type],
                [ccpp_t_type, errmsg_type, errflg_type],
            )
        else:
            ret_op = func.ReturnOp(errmsg_alloc, errflg_alloc)
            fn_type = builtin.FunctionType.from_lists(
                [suite_name_type],
                [errmsg_type, errflg_type],
            )

        new_block.add_ops(
            [
                errmsg_alloc,
                errflg_alloc,
                *hoisted_alloc_ops,   # placeholder allocas declared at function scope
                err_const,
                store_errflg,
                trim_suite_name,
                *main_chain_ops,
                ret_op,
            ]
        )

        body = Region()
        body.add_block(new_block)
        cap_fn = func.FuncOp(fn_name, fn_type, body, visibility="public")

        for suite_name, suite_callee, call_ret_types, scheme_names, entry_postfix, _ri \
                in suite_entries:
            callee_module, _, callee_input_types, _ = public_fns[suite_callee]
            decl = func.FuncOp.external(suite_callee, callee_input_types, call_ret_types)
            decl.attributes["module"] = StringAttr(callee_module)
            decls.append(decl)

        return cap_fn, decls, all_host_global_ops

    def _generate_run_fn(
        self,
        fn_name,
        suite_run_entries,
        suite_name_type,
        errmsg_type,
        errflg_type,
        char_base,
        int_base,
        public_fns,
        meta_data,
        cap_var_map=None,
        seen_host_globals=None,
        **kwargs,
    ):
        """Build the combined CCPP cap physics run FuncOp dispatching over all suites.

        ``suite_run_entries`` is a list of
        ``(suite_name, suite_part, suite_callee, scheme_names)`` tuples.

        The generated function signature uses the union of non-host physics args
        across all suites.  A nested if/else chain on ``suite_name`` dispatches to
        the appropriate suite; each matching branch has an inner if/else on
        ``suite_part``.  Host variable references and array sections are placed
        inside each suite's branch.

        Returns ``(FuncOp, [external_decl_FuncOp, ...], host_global_ops)``.
        """
        for _, _, suite_callee, _ in suite_run_entries:
            assert suite_callee in public_fns, (
                f"Suite callee '{suite_callee}' not found; available: {sorted(public_fns)}"
            )

        suite_part_type = suite_name_type

        # ── Build host variable maps from metadata ─────────────────────────────
        _maps = self._build_run_metadata_maps(meta_data)
        host_var_map = _maps.host_var_map
        host_block_std_names = _maps.host_block_std_names
        constituent_std_names = _maps.constituent_std_names
        ddt_type_names = _maps.ddt_type_names
        ddt_instance_map = _maps.ddt_instance_map
        ddt_parent_map = _maps.ddt_parent_map

        # ── Per-suite information ──────────────────────────────────────────────
        # Use the caller-provided seen_host_globals set so GlobalOps are deduplicated
        # across all functions (lifecycle + run) in the same cap module.
        if seen_host_globals is None:
            seen_host_globals = set()
        per_suite, all_host_global_ops = self._build_per_suite_run_info(
            suite_run_entries, public_fns, meta_data, _maps, cap_var_map,
            seen_host_globals,
        )

        # ── Block signature ────────────────────────────────────────────────────
        _sig = self._build_run_block_signature(
            per_suite, meta_data, kwargs,
            suite_name_type, suite_part_type, errmsg_type, errflg_type, int_base,
        )
        new_block = _sig.new_block
        all_block_types = _sig.all_block_types
        block_arg_map = _sig.block_arg_map
        non_host_std_to_canonical = _sig.non_host_std_to_canonical
        suite_name_arg = _sig.suite_name_arg
        suite_part_arg = _sig.suite_part_arg
        errmsg_arg = _sig.errmsg_arg
        errflg_arg = _sig.errflg_arg
        col_start_ref = _sig.col_start_ref
        col_end_ref = _sig.col_end_ref
        errmsg_alloc = _sig.errmsg_alloc
        errflg_alloc = _sig.errflg_alloc
        ccpp_info_block_arg = _sig.ccpp_info_block_arg
        ccpp_data_block_arg = _sig.ccpp_data_block_arg
        ccpp_info_type = _sig.ccpp_info_type
        ccpp_t_type = _sig.ccpp_t_type

        # ── Dispatch chain preamble ────────────────────────────────────────────
        _pre = self._build_run_chain_preamble(
            per_suite, suite_name_arg, errmsg_arg, errflg_arg,
        )
        err_const = _pre.err_const
        store_errflg = _pre.store_errflg
        trim_suite_name = _pre.trim_suite_name
        current_false_ops = _pre.current_false_ops
        all_decls = _pre.all_decls
        per_suite_grouped = _pre.per_suite_grouped

        # ── Build nested if/else chain from inside out ─────────────────────────
        main_chain_ops, all_decls, chain_global_ops = self._build_run_dispatch_chain(
            per_suite_grouped=per_suite_grouped,
            trim_suite_name=trim_suite_name,
            suite_part_arg=suite_part_arg,
            errmsg_arg=errmsg_arg,
            errflg_arg=errflg_arg,
            errmsg_type=errmsg_type,
            errflg_type=errflg_type,
            block_arg_map=block_arg_map,
            non_host_std_to_canonical=non_host_std_to_canonical,
            host_var_map=host_var_map,
            meta_data=meta_data,
            cap_var_map=cap_var_map,
            seen_host_globals=seen_host_globals,
            current_false_ops=current_false_ops,
            ccpp_t_type=ccpp_t_type,
            ccpp_data_block_arg=ccpp_data_block_arg,
        )
        all_host_global_ops.extend(chain_global_ops)

        # ── Assemble the function ──────────────────────────────────────────────
        cap_fn = self._assemble_run_fn(
            fn_name, _sig, _pre, main_chain_ops, errmsg_type, errflg_type
        )
        return cap_fn, all_decls, all_host_global_ops

    def _generate_suite_part_list_fn(
        self,
        suite_part_entries,
        inner_char_type,
        allocatable_type,
        suite_name_type,
        errmsg_type,
        errflg_type,
        char_base,
        int_base,
    ):
        """Build the ccpp_physics_suite_part_list FuncOp for all suites.

        ``suite_part_entries`` is a list of ``(suite_name, [part_names])`` tuples.
        Generates a subroutine with a nested if/else chain that checks suite_name
        and fills part_list with the matching suite's part names.

        Returns (FuncOp, list[llvm.GlobalOp]).
        """
        # Collect ALL unique part names for shared global string constants.
        all_part_names = list(
            dict.fromkeys(
                pn for _, part_names in suite_part_entries for pn in part_names
            )
        )

        part_global_ops = []
        part_global_names: dict = {}
        for pn in all_part_names:
            str_global_name = f"str_{pn}"
            arr_type = llvm.LLVMArrayType.from_size_and_type(len(pn), i8)
            part_global_ops.append(
                llvm.GlobalOp(
                    arr_type,
                    str_global_name,
                    "internal",
                    constant=True,
                    value=StringAttr(pn),
                )
            )
            part_global_names[pn] = (str_global_name, arr_type)

        new_block = Block(arg_types=[suite_name_type, allocatable_type])
        new_block.args[0].name_hint = "suite_name"
        new_block.args[1].name_hint = "part_list"

        errmsg_alloc = memref.AllocaOp.get(char_base, shape=[CCPP_ERRMSG_LEN])
        errmsg_alloc.memref.name_hint = "errmsg"
        errflg_alloc = memref.AllocaOp.get(int_base, shape=[])
        errflg_alloc.memref.name_hint = "errflg"

        err_const = arith.ConstantOp.from_int_and_width(0, 32)
        store_errflg = memref.StoreOp.get(err_const, errflg_alloc, [])

        trim_suite_name = TrimOp(new_block.args[0])

        # Innermost else: no suite matched
        write_err = WriteErrMsgOp(
            errmsg_alloc, trim_suite_name.res, "No suite named ", " found"
        )
        one_err = arith.ConstantOp.from_int_and_width(1, 32)
        store_errflg_err = memref.StoreOp.get(one_err, errflg_alloc, [])

        # Build chain from inside out
        current_false_ops = [write_err, one_err, store_errflg_err, scf.YieldOp()]

        for suite_name, part_names in reversed(suite_part_entries):
            strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite_name)

            true_ops = []
            for pn in part_names:
                str_global_name, arr_type = part_global_names[pn]
                str_len_const = arith.ConstantOp(
                    IntegerAttr(len(pn), IndexType()), IndexType()
                )
                str_alloc = memref.AllocOp([str_len_const.result], [], inner_char_type)
                addr_op = llvm.AddressOfOp(str_global_name, llvm.LLVMPointerType())
                load_op = llvm.LoadOp(addr_op, arr_type)
                set_str_op = SetStringOp(str_alloc.memref, load_op.dereferenced_value)
                store_ref_op = memref.StoreOp.get(
                    str_alloc.memref, new_block.args[1], []
                )
                true_ops.extend(
                    [
                        str_len_const,
                        str_alloc,
                        addr_op,
                        load_op,
                        set_str_op,
                        store_ref_op,
                    ]
                )
            true_ops.append(scf.YieldOp())

            if_op = scf.IfOp(strcmp_op.res, [], true_ops, current_false_ops)
            current_false_ops = [strcmp_op, if_op, scf.YieldOp()]

        main_chain_ops = current_false_ops[:-1]
        ret_op = func.ReturnOp(errmsg_alloc, errflg_alloc)

        new_block.add_ops(
            [
                errmsg_alloc,
                errflg_alloc,
                err_const,
                store_errflg,
                trim_suite_name,
                *main_chain_ops,
                ret_op,
            ]
        )

        body = Region()
        body.add_block(new_block)

        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type, allocatable_type],
            [errmsg_type, errflg_type],
        )
        suite_part_list_fn = func.FuncOp(
            "ccpp_physics_suite_part_list", fn_type, body, visibility="public"
        )
        return suite_part_list_fn, part_global_ops

    def _generate_constituent_api(
        self,
        camel_name: str,
        dynamic_array_names: list,
        fixed_advected: list,
        scratch_vars: list | None = None,
    ):
        """Generate constituent registration API as raw Fortran text.

        Returns (module_var_ops, constituent_api_op, global_stub_ops).
        """
        h = camel_name
        dyn_lc = [f"lc_{n}" for n in dynamic_array_names]

        # ── Module-level variable declarations ──────────────────────────────
        module_var_ops: list = []
        for n in dynamic_array_names:
            module_var_ops.append(
                ModuleVarOp(f"lc_{n}", "type", ddt_name="ccpp_constituent_properties_t", rank=1)
            )
        module_var_ops.append(
            ModuleVarOp(
                "lc_all_constituents",
                "type",
                ddt_name="ccpp_constituent_properties_t",
                ftn_attrs="target",
                rank=1,
            )
        )
        module_var_ops.append(
            ModuleVarOp("lc_constituent_array", "real", kind="kind_phys", ftn_attrs="target", rank=3)
        )
        module_var_ops.append(
            ModuleVarOp("lc_const_tend", "real", kind="kind_phys", ftn_attrs="target", rank=3)
        )
        module_var_ops.append(
            ModuleVarOp("lc_const_props", "type", ddt_name="ccpp_constituent_prop_ptr_t", ftn_attrs="target", rank=1)
        )
        for lc_name, rank, _alloc_dims, _cst_std in (scratch_vars or []):
            module_var_ops.append(
                ModuleVarOp(lc_name, "real", kind="kind_phys",
                            ftn_attrs="pointer" if _cst_std else None, rank=rank)
            )

        # ── Helper: dedup fragment ───────────────────────────────────────────
        def _dedup_block(src_sname, src_units, src_assign, indent="    "):
            lines = []
            lines.append(f"{indent}lc_found = .false.")
            lines.append(f"{indent}do lc_j = 1, lc_num")
            lines.append(f"{indent}  if (trim(lc_tmp(lc_j)%std_name) == trim({src_sname})) then")
            lines.append(f"{indent}    lc_found = .true.")
            lines.append(f"{indent}    if (trim(lc_tmp(lc_j)%units) /= trim({src_units})) then")
            lines.append(
                f"{indent}      write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: "
                f"Trying to add constituent ', trim({src_sname}), &"
            )
            lines.append(
                f"{indent}        ' but an incompatible constituent with this name already exists'"
            )
            lines.append(f"{indent}      errflg = 1")
            lines.append(f"{indent}      return")
            lines.append(f"{indent}    end if")
            lines.append(f"{indent}    exit")
            lines.append(f"{indent}  end if")
            lines.append(f"{indent}end do")
            lines.append(f"{indent}if (.not. lc_found) then")
            lines.append(f"{indent}  lc_num = lc_num + 1")
            lines.append(f"{indent}  lc_tmp(lc_num) = {src_assign}")
            lines.append(f"{indent}end if")
            return lines

        # ── 1. is_scheme_constituent ─────────────────────────────────────────
        fixed_names_str = ", ".join(f"'{s}'" for s, _u, _d in fixed_advected)
        isc_lines = [
            f"  subroutine {h}_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)",
            f"    character(len=*), intent(in) :: std_name",
            f"    logical, intent(out) :: is_const",
            f"    integer, intent(out) :: errflg",
            f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            f"    integer :: lc_idx",
            f"    errflg = 0",
            f"    errmsg = ''",
            f"    is_const = .false.",
            f"    select case (trim(std_name))",
        ]
        if fixed_names_str:
            isc_lines += [
                f"    case ({fixed_names_str})",
                f"      is_const = .true.",
            ]
        isc_lines.append(f"    case default")
        for dyn_var in dyn_lc:
            isc_lines += [
                f"      if (allocated({dyn_var})) then",
                f"        do lc_idx = 1, size({dyn_var})",
                f"          if (trim({dyn_var}(lc_idx)%std_name) == trim(std_name)) then",
                f"            is_const = .true.",
                f"            return",
                f"          end if",
                f"        end do",
                f"      end if",
            ]
        isc_lines += [
            f"    end select",
            f"  end subroutine {h}_ccpp_is_scheme_constituent",
        ]

        # ── 2. deallocate_dynamic_constituents ───────────────────────────────
        da_lines = [f"  subroutine {h}_ccpp_deallocate_dynamic_constituents()"]
        for dyn_var in dyn_lc:
            da_lines.append(f"    if (allocated({dyn_var})) deallocate({dyn_var})")
        da_lines += [
            f"    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)",
            f"    if (allocated(lc_const_props)) deallocate(lc_const_props)",
            f"    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)",
            f"    if (allocated(lc_const_tend)) deallocate(lc_const_tend)",
        ]
        for lc_name, _rank, _alloc_dims, _cst_std in (scratch_vars or []):
            if _cst_std:
                da_lines.append(f"    nullify({lc_name})")
            else:
                da_lines.append(f"    if (allocated({lc_name})) deallocate({lc_name})")
        da_lines.append(f"  end subroutine {h}_ccpp_deallocate_dynamic_constituents")

        # ── 3. register_constituents ─────────────────────────────────────────
        n_fixed = len(fixed_advected)
        rc_lines = [
            f"  subroutine {h}_ccpp_register_constituents(host_constituents, errmsg, errflg)",
            f"    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents",
            f"    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)",
            f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            f"    integer, intent(out) :: errflg",
            f"    integer :: lc_max, lc_num, lc_i, lc_j",
            f"    logical :: lc_found",
            f"    type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)",
            f"    errflg = 0",
            f"    errmsg = ''",
            f"    lc_max = 0",
        ]
        for dyn_var in dyn_lc:
            rc_lines.append(f"    if (allocated({dyn_var})) lc_max = lc_max + size({dyn_var})")
        rc_lines += [
            f"    lc_max = lc_max + {n_fixed}",
            f"    lc_max = lc_max + size(host_constituents)",
            f"    allocate(lc_tmp(lc_max))",
            f"    lc_num = 0",
        ]
        for dyn_var in dyn_lc:
            rc_lines += [
                f"    if (allocated({dyn_var})) then",
                f"      do lc_i = 1, size({dyn_var})",
            ]
            rc_lines += _dedup_block(
                f"{dyn_var}(lc_i)%std_name",
                f"{dyn_var}(lc_i)%units",
                f"{dyn_var}(lc_i)",
                indent="        ",
            )
            rc_lines += [f"      end do", f"    end if"]
        for std_name_f, units_f, default_val_f in fixed_advected:
            rc_lines += [
                f"    lc_found = .false.",
                f"    do lc_j = 1, lc_num",
                f"      if (trim(lc_tmp(lc_j)%std_name) == '{std_name_f}') then",
                f"        lc_found = .true.",
                f"        if (trim(lc_tmp(lc_j)%units) /= '{units_f}') then",
                f"          write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: "
                f"Trying to add constituent ', '{std_name_f}', &",
                f"            ' but an incompatible constituent with this name already exists'",
                f"          errflg = 1",
                f"          return",
                f"        end if",
                f"        exit",
                f"      end if",
                f"    end do",
                f"    if (.not. lc_found) then",
                f"      lc_num = lc_num + 1",
            ]
            long_name_f = std_name_f.replace('_', ' ').capitalize()
            inst_args = (
                f"std_name='{std_name_f}', long_name='{long_name_f}', "
                f"units='{units_f}', errcode=errflg, errmsg=errmsg, advected=.true."
            )
            if default_val_f is not None:
                inst_args += f", default_value={default_val_f}"
            rc_lines += [
                f"      call lc_tmp(lc_num)%instantiate({inst_args})",
                f"      if (errflg /= 0) return",
                f"    end if",
            ]
        rc_lines += [f"    do lc_i = 1, size(host_constituents)"]
        rc_lines += _dedup_block(
            "host_constituents(lc_i)%std_name",
            "host_constituents(lc_i)%units",
            "host_constituents(lc_i)",
            indent="      ",
        )
        rc_lines += [
            f"    end do",
            f"    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)",
            f"    allocate(lc_all_constituents(lc_num))",
            f"    lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)",
            f"    deallocate(lc_tmp)",
            f"    if (allocated(lc_const_props)) deallocate(lc_const_props)",
            f"    allocate(lc_const_props(lc_num))",
            f"    do lc_i = 1, lc_num",
            f"      lc_const_props(lc_i)%ptr => lc_all_constituents(lc_i)",
            f"    end do",
            f"    call ccpp_scheme_utils_set_constituents(lc_all_constituents)",
            f"  end subroutine {h}_ccpp_register_constituents",
        ]

        # ── 4. number_constituents ───────────────────────────────────────────
        nc_lines = [
            f"  subroutine {h}_ccpp_number_constituents(num_advected, errmsg, errflg)",
            f"    integer, intent(out) :: num_advected",
            f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            f"    integer, intent(out) :: errflg",
            f"    errflg = 0",
            f"    errmsg = ''",
            f"    if (allocated(lc_all_constituents)) then",
            f"      num_advected = size(lc_all_constituents)",
            f"    else",
            f"      num_advected = 0",
            f"    end if",
            f"  end subroutine {h}_ccpp_number_constituents",
        ]

        # ── 5. initialize_constituents ───────────────────────────────────────
        ic_lines = [
            f"  subroutine {h}_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)",
            f"    integer, intent(in) :: ncols",
            f"    integer, intent(in) :: pver",
            f"    integer, intent(out) :: errflg",
            f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            f"    integer :: lc_num, lc_i",
            f"    errflg = 0",
            f"    errmsg = ''",
            f"    if (.not. allocated(lc_all_constituents)) then",
            f"      errflg = 1",
            f"      errmsg = 'ccpp_initialize_constituents: register_constituents not called'",
            f"      return",
            f"    end if",
            f"    lc_num = size(lc_all_constituents)",
            f"    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)",
            f"    allocate(lc_constituent_array(ncols, pver, lc_num))",
            f"    lc_constituent_array = 0.0_kind_phys",
            f"    do lc_i = 1, lc_num",
            f"      if (lc_all_constituents(lc_i)%default_val_set) then",
            f"        lc_constituent_array(:, :, lc_i) = lc_all_constituents(lc_i)%default_val",
            f"      end if",
            f"    end do",
            f"    if (allocated(lc_const_tend)) deallocate(lc_const_tend)",
            f"    allocate(lc_const_tend(ncols, pver, lc_num))",
            f"    lc_const_tend = 0.0_kind_phys",
        ]
        for lc_name, _rank, alloc_dims, _cst_std in (scratch_vars or []):
            if _cst_std:
                ic_lines += [
                    f"    nullify({lc_name})",
                    f"    do lc_i = 1, lc_num",
                    f"      if (trim(lc_all_constituents(lc_i)%std_name) == '{_cst_std}') then",
                    f"        {lc_name} => lc_const_tend(:, :, lc_i)",
                    f"        exit",
                    f"      end if",
                    f"    end do",
                ]
            else:
                ic_lines += [
                    f"    if (allocated({lc_name})) deallocate({lc_name})",
                    f"    allocate({lc_name}({alloc_dims}))",
                    f"    {lc_name} = 0.0_kind_phys",
                ]
        ic_lines.append(f"  end subroutine {h}_ccpp_initialize_constituents")

        # ── 6. constituents_array ────────────────────────────────────────────
        ca_lines = [
            f"  function {h}_constituents_array() result(ptr)",
            f"    real(kind=kind_phys), pointer :: ptr(:, :, :)",
            f"    ptr => lc_constituent_array",
            f"  end function {h}_constituents_array",
        ]

        # ── 7. const_get_index ───────────────────────────────────────────────
        ci_lines = [
            f"  subroutine {h}_const_get_index(std_name, index, errflg, errmsg)",
            f"    character(len=*), intent(in) :: std_name",
            f"    integer, intent(out) :: index",
            f"    integer, intent(out) :: errflg",
            f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            f"    integer :: lc_i",
            f"    errflg = 0",
            f"    errmsg = ''",
            f"    index = -1",
            f"    if (.not. allocated(lc_all_constituents)) then",
            f"      errflg = 1",
            f"      errmsg = 'const_get_index: constituents not registered'",
            f"      return",
            f"    end if",
            f"    do lc_i = 1, size(lc_all_constituents)",
            f"      if (trim(lc_all_constituents(lc_i)%std_name) == trim(std_name)) then",
            f"        index = lc_i",
            f"        return",
            f"      end if",
            f"    end do",
            f"    errflg = 1",
            f"    write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'",
            f"  end subroutine {h}_const_get_index",
        ]

        # ── 8. model_const_properties ────────────────────────────────────────
        mp_lines = [
            f"  function {h}_model_const_properties() result(ptr)",
            f"    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)",
            f"    ptr => lc_const_props",
            f"  end function {h}_model_const_properties",
        ]

        all_lines = (
            isc_lines + [""]
            + da_lines + [""]
            + rc_lines + [""]
            + nc_lines + [""]
            + ic_lines + [""]
            + ca_lines + [""]
            + ci_lines + [""]
            + mp_lines
        )
        body_text = "\n".join(all_lines)

        public_names_list = [
            f"{h}_ccpp_is_scheme_constituent",
            f"{h}_ccpp_deallocate_dynamic_constituents",
            f"{h}_ccpp_register_constituents",
            f"{h}_ccpp_number_constituents",
            f"{h}_ccpp_initialize_constituents",
            f"{h}_constituents_array",
            f"{h}_const_get_index",
            f"{h}_model_const_properties",
        ]

        api_op = ConstituentApiOp(body_text, public_names_list)

        # ── USE stubs for ccpp_constituent_prop_mod ──────────────────────────
        global_stubs: list = []
        for type_name in ("ccpp_constituent_properties_t", "ccpp_constituent_prop_ptr_t"):
            _g = llvm.GlobalOp(
                llvm.LLVMArrayType.from_size_and_type(1, i8),
                type_name,
                "external",
            )
            _g.attributes["module"] = StringAttr(_CCPP_CONSTITUENT_MOD)
            global_stubs.append(_g)

        return module_var_ops, api_op, global_stubs

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

        ftn_text = self._build_chost_ftn_text(
            camel_name, mod_name, suite_cap_mod_name, bind_c_fns, meta_data, ccpp_mod,
            public_fns or {}, suite_descriptions,
            ddt_source_module=ddt_source_module,
        )
        cpp_text = self._build_chost_cpp_text(
            camel_name, mod_name, bind_c_fns,
            meta_data, public_fns or {}, suite_descriptions, ccpp_mod,
            ddt_source_module=ddt_source_module,
        )
        wrapper_text = self._build_chost_wrapper_text(
            camel_name, mod_name, bind_c_fns,
            meta_data, public_fns or {}, suite_descriptions, ccpp_mod,
            ddt_source_module=ddt_source_module,
        )

        return CHostCapOp(ftn_text, cpp_text, mod_name, wrapper_text)

    def _build_chost_ftn_text(
        self, camel_name, mod_name, suite_cap_mod_name, bind_c_fns, meta_data, ccpp_mod,
        public_fns, suite_descriptions, ddt_source_module=None,
    ):
        """Generate the complete Fortran BIND(C) chost cap module text."""
        # ── Metadata maps ──────────────────────────────────────────────────────
        # std_to_host: standard_name → host-local variable name (MODULE + HOST tables)
        std_to_host: dict = {}
        for props in meta_data.values():
            if props.getAttr("type") not in (CCPPType.HOST, CCPPType.MODULE):
                continue
            for atbl in props.arg_tables.values():
                for var in atbl.getFunctionArguments():
                    if var.hasAttr("standard_name"):
                        sn = var.getAttr("standard_name").lower()
                        if sn not in std_to_host:
                            std_to_host[sn] = var.name

        # local_to_std: any local name (all table types) → standard_name
        # Covers SCHEME args like lv_in, col_start (from HOST), etc.
        local_to_std: dict = {}
        for props in meta_data.values():
            for atbl in props.arg_tables.values():
                for var in atbl.getFunctionArguments():
                    if var.hasAttr("standard_name") and var.name not in local_to_std:
                        local_to_std[var.name] = var.getAttr("standard_name").lower()

        ncol_var = (std_to_host.get(CCPP_HORIZ_DIM_STD_NAME)
                    or std_to_host.get(CCPP_LOOP_EXTENT_STD_NAME) or "ncol")
        nz_var = std_to_host.get(CCPP_VERT_DIM_STD_NAME, "nz")

        kind_iso_map = _chost_kind_iso_map(ccpp_mod)

        suite_name = next(iter(suite_descriptions), "")

        def ftn_decl(ai):
            host = ai["host"]
            if ai["is_ncol"] or ai["is_nz"] or (ai["is_int"] and not ai["is_errflg"]):
                return f"    integer(c_int), value, intent(in) :: {host}"
            if ai["is_real"]:
                c_real = "c_float" if ai.get("real_width", 64) == 32 else "c_double"
                _dn = ai.get("dim_ncol") or ncol_var
                _dz = ai.get("dim_nz")   or nz_var
                if ai["rank"] == 0:
                    return f"    real({c_real}), value, intent(in) :: {host}"
                if ai["rank"] == 1:
                    return (f"    real({c_real}), target,"
                            f" intent({ai['intent']}) :: {host}({_dn})")
                if ai["rank"] == 2:
                    return (f"    real({c_real}), target,"
                            f" intent({ai['intent']}) :: {host}({_dn}, {_dz})")
                # rank >= 3: higher dimensions are assumed-size (*).
                return (f"    real({c_real}), target,"
                        f" intent({ai['intent']}) :: {host}({_dn}, {_dz}, *)")
            if ai.get("is_logical"):
                return f"    logical(c_bool), value, intent({ai['intent']}) :: {host}"
            if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
                return f"    character(kind=c_char, len=1), intent({ai['intent']}) :: {host}(*)"
            if ai["is_sname"]:
                return f"    character(kind=c_char, len=1), intent(out) :: {host}(*)"
            if ai["is_errmsg"]:
                return f"    character(kind=c_char, len=1), intent(out) :: {host}(*)"
            if ai["is_errflg"]:
                return f"    integer(c_int),               intent(out) :: {host}"
            return f"    ! unclassified arg: {host}"

        fn_ctxs = _chost_fn_contexts(
            bind_c_fns, suite_name, suite_descriptions, public_fns,
            ncol_var, local_to_std, std_to_host, kind_iso_map,
            meta_data=meta_data, ddt_source_module=ddt_source_module, nz_var=nz_var,
        )

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

        # ── Module header ───────────────────────────────────────────────────────
        L: list = []
        A = L.append

        A(f"module {mod_name}")
        A("")
        A("  use ccpp_kinds, only: kind_phys")
        A("  use iso_c_binding")
        for tn, mod in sorted(ddt_uses.items()):
            A(f"  use {mod}, only: {tn}")
        if all_constituent_vars:
            A(f"  use {_CCPP_CONSTITUENT_MOD}, only: {_CONSTITUENT_DDT_NAME}")
        for sfn in used_suite_fns:
            A(f"  use {suite_cap_mod_name}, only: {sfn}")
        A("")
        A("  implicit none")
        A("  private")
        A("")
        for fn_op in bind_c_fns:
            A(f"  public :: {_chost_fn_name(fn_op.sym_name.data)}")
        if all_constituent_vars:
            A(f"  public :: {mod_name}_nconstituents")
            A(f"  public :: {mod_name}_get_constituent_info")
            A("")
            A("  ! BIND(C) struct mirroring CcppConstituentInfo on the C++ side")
            A("  type, public, bind(c) :: chost_constituent_info_t")
            for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS:
                if fkind == "char":
                    A(f"    character(kind=c_char) :: {fname}({flen + 1})")
                elif fkind == "real":
                    A(f"    real(c_double)         :: {fname}")
                else:  # logical
                    A(f"    logical(c_bool)        :: {fname}")
            A("  end type chost_constituent_info_t")
            A("")
            for cv in all_constituent_vars:
                A(f"  type({_CONSTITUENT_DDT_NAME}), allocatable, save :: _chost_{cv}(:)")
        A("")
        A("contains")

        # ── Subroutines ─────────────────────────────────────────────────────────
        for ctx in fn_ctxs:
            cfn, lc, sfns = ctx["cfn"], ctx["lc"], ctx["sfns"]
            suite_fn, infos, out_infos, visible = (
                ctx["suite_fn"], ctx["infos"], ctx["out_infos"], ctx["visible"]
            )
            ddt_locals      = ctx.get("ddt_locals", {})
            suite_call_pcs  = ctx.get("suite_call_pieces", [])

            has_errmsg = any(ai["is_errmsg"] for ai in visible)
            has_sname  = any(ai["is_sname"]  for ai in visible)
            plain_char_args = [ai for ai in visible
                               if ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]]

            # ── Subroutine signature ──────────────────────────────────────────
            A("")
            _emit_subr_header(A, cfn, [ai["host"] for ai in visible])

            # ── Declarations ─────────────────────────────────────────────────
            for ai in visible:
                A(ftn_decl(ai))
            if has_errmsg or has_sname or plain_char_args:
                A("    integer :: i")
            if has_sname:
                sn = next(ai["host"] for ai in visible if ai["is_sname"])
                A(f"    character(len={CCPP_SCHEME_NAME_LEN})  :: {sn}_f")
            if has_errmsg:
                em = next(ai["host"] for ai in visible if ai["is_errmsg"])
                A(f"    character(len={CCPP_ERRMSG_LEN}) :: {em}_f")
            for ai in plain_char_args:
                cl = ai.get("char_len") or CCPP_ERRMSG_LEN
                A(f"    character(len={cl}) :: {ai['host']}_f")
            for li in ddt_locals.values():
                A(f"    type({li['ddt_type']}) :: {li['local_name']}")

            # ── Body initialization ───────────────────────────────────────────
            A("")
            if has_errmsg:
                A(f"    {em}_f = ' '")
            if has_sname:
                A(f"    {sn}_f = ' '")
            if any(ai["is_errflg"] for ai in visible):
                ef = next(ai["host"] for ai in visible if ai["is_errflg"])
                A(f"    {ef} = 0")
            # C→F copy-in for plain character(len=N) args (intent=in or intent=inout)
            for ai in plain_char_args:
                if ai.get("intent") in ("in", "inout"):
                    h = ai["host"]
                    A(f"    {h}_f = ' '")
                    A(f"    do i = 1, len({h}_f)")
                    A(f"      if ({h}(i) == c_null_char) exit")
                    A(f"      {h}_f(i:i) = {h}(i)")
                    A(f"    end do")

            # ── DDT copy-in: scalars assigned, arrays allocated and filled ────
            for li in ddt_locals.values():
                lname = li["local_name"]
                # Character members are not in the C interface; initialise blank.
                for mn in li.get("char_member_blanks", []):
                    A(f"    {lname}%{mn} = ' '")
                for ai in li["member_ais"]:
                    mn = ai["_ddt_member"]
                    fn_ = ai["bare"]
                    if ai["rank"] == 0:
                        A(f"    {lname}%{mn} = {fn_}")
                    else:
                        _dn = ai.get("dim_ncol") or ncol_var
                        _dz = ai.get("dim_nz")   or nz_var
                        if ai["rank"] == 1:
                            dims = _dn
                        elif ai["rank"] == 2:
                            dims = f"{_dn}, {_dz}"
                        else:
                            dims = f"{_dn}, {_dz}, *"
                        if ai["intent"] != "out":
                            # intent=out: scheme allocates internally; skip pre-alloc.
                            A(f"    allocate({lname}%{mn}({dims}))")
                            A(f"    {lname}%{mn} = real({fn_}, kind_phys)")

            # ── Suite cap calls ───────────────────────────────────────────────
            for sfn_i in sfns:
                if sfn_i not in public_fns:
                    continue
                call_exprs = []
                if suite_call_pcs:
                    for piece in suite_call_pcs:
                        if piece["kind"] == "ddt_local":
                            call_exprs.append(piece["name"])
                        elif piece["kind"] == "constituent_mod_var":
                            call_exprs.append(piece["name"])
                        else:
                            ai = piece["ai"]
                            if ai["is_col_start"] or ai["is_col_end"]:
                                call_exprs.append(ai["host"])
                            elif ai["is_real"] and ai["rank"] == 0:
                                call_exprs.append(f"real({ai['host']}, kind_phys)")
                            elif ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
                                call_exprs.append(f"{ai['host']}_f")
                            else:
                                call_exprs.append(ai["host"])
                else:
                    for ai in infos:
                        if ai["is_col_start"] or ai["is_col_end"]:
                            call_exprs.append(ai["host"])
                        elif ai["is_real"] and ai["rank"] == 0:
                            call_exprs.append(f"real({ai['host']}, kind_phys)")
                        elif ai["is_char"] and not ai["is_errmsg"] and not ai["is_sname"]:
                            call_exprs.append(f"{ai['host']}_f")
                        else:
                            call_exprs.append(ai["host"])
                # intent=out DDT locals come before errmsg/errflg in the call.
                for ddt_local_name in ctx.get("ddt_out_locals", []):
                    call_exprs.append(ddt_local_name)
                # Output args (suite cap output order: errmsg_f / scheme_name_f / errflg)
                for oai in out_infos:
                    if oai["is_errmsg"] or oai["is_sname"]:
                        call_exprs.append(f"{oai['host']}_f")
                    else:
                        call_exprs.append(oai["host"])
                _emit_call(A, sfn_i, call_exprs)

            # ── DDT cleanup: writeback inout arrays, deallocate all arrays ───────
            for li in ddt_locals.values():
                lname = li["local_name"]
                for ai in li["array_ais"]:
                    mn  = ai["_ddt_member"]
                    fn_ = ai["bare"]
                    if ai["intent"] != "in":
                        c_real = "c_float" if ai.get("real_width", 64) == 32 else "c_double"
                        A(f"    {fn_} = real({lname}%{mn}, {c_real})")
                    A(f"    deallocate({lname}%{mn})")

            # ── F→C string copy loops ─────────────────────────────────────────
            if has_sname:
                A(f"    do i = 1, len_trim({sn}_f)")
                A(f"      {sn}(i) = {sn}_f(i:i)")
                A(f"    end do")
                A(f"    {sn}(len_trim({sn}_f)+1) = c_null_char")
            if has_errmsg:
                A(f"    do i = 1, len_trim({em}_f)")
                A(f"      {em}(i) = {em}_f(i:i)")
                A(f"    end do")
                A(f"    {em}(len_trim({em}_f)+1) = c_null_char")
            for ai in plain_char_args:
                if ai.get("intent") in ("out", "inout"):
                    h = ai["host"]
                    A(f"    do i = 1, len_trim({h}_f)")
                    A(f"      {h}(i) = {h}_f(i:i)")
                    A(f"    end do")
                    A(f"    {h}(len_trim({h}_f)+1) = c_null_char")

            A(f"  end subroutine {cfn}")

        # ── Constituent query functions ──────────────────────────────────────────
        if all_constituent_vars:
            A("")
            A(f"  function {mod_name}_nconstituents() result(n) &")
            A(f"      bind(c, name=\"{mod_name}_nconstituents\")")
            A("    integer(c_int) :: n")
            A("    n = 0_c_int")
            for cv in all_constituent_vars:
                A(f"    if (allocated(_chost_{cv})) &")
                A(f"        n = n + int(size(_chost_{cv}), c_int)")
            A(f"  end function {mod_name}_nconstituents")
            A("")
            A(f"  subroutine {mod_name}_get_constituent_info(buf, n) &")
            A(f"      bind(c, name=\"{mod_name}_get_constituent_info\")")
            A("    type(chost_constituent_info_t), intent(out) :: buf(n)")
            A("    integer(c_int), value, intent(in) :: n")
            A("    integer :: _chost_idx, _chost_j, _chost_slen, _chost_i")
            A("    _chost_idx = 0")
            for cv in all_constituent_vars:
                A(f"    if (allocated(_chost_{cv})) then")
                A(f"      do _chost_i = 1, size(_chost_{cv})")
                A("        _chost_idx = _chost_idx + 1")
                A("        if (_chost_idx > n) return")
                for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS:
                    src = f"_chost_{cv}(_chost_i)%{fname}"
                    dst = f"buf(_chost_idx)%{fname}"
                    if fkind == "char":
                        A(f"        _chost_slen = min(len_trim({src}), {flen})")
                        A(f"        do _chost_j = 1, _chost_slen")
                        A(f"          {dst}(_chost_j) = {src}(_chost_j:_chost_j)")
                        A(f"        end do")
                        A(f"        {dst}(min(_chost_slen+1,{flen+1})) = c_null_char")
                    elif fkind == "real":
                        A(f"        {dst} = real({src}, c_double)")
                    else:  # logical
                        A(f"        {dst} = logical({src}, c_bool)")
                A(f"      end do")
                A(f"    end if")
            A(f"  end subroutine {mod_name}_get_constituent_info")

        A("")
        A(f"end module {mod_name}")

        return "\n".join(L) + "\n"

    def _build_chost_cpp_text(
        self, camel_name, mod_name, bind_c_fns,
        meta_data, public_fns, suite_descriptions, ccpp_mod=None,
        ddt_source_module=None,
    ):
        """Generate the complete C++ header text for the chost cap."""
        std_to_host, local_to_std, ncol_var, nz_var = _chost_build_maps(meta_data)

        kind_iso_map = _chost_kind_iso_map(ccpp_mod) if ccpp_mod is not None else {}

        suite_name = next(iter(suite_descriptions), "")

        L: list = []
        A = L.append
        A("// Generated by xdsl-ccpp."
          " Array arguments are column-major (Fortran order).")
        A("// Pass Kokkos::View with LayoutLeft, or transpose before calling.")
        A("#pragma once")
        A("#ifdef __cplusplus")
        A('extern "C" {')
        A("#endif")
        A("")

        all_constituent_vars_cpp: list = []
        _seen_cv_cpp: set = set()
        fn_ctxs_cpp = list(_chost_fn_contexts(
            bind_c_fns, suite_name, suite_descriptions, public_fns,
            ncol_var, local_to_std, std_to_host, kind_iso_map,
            meta_data=meta_data, ddt_source_module=ddt_source_module, nz_var=nz_var,
        ))
        for ctx in fn_ctxs_cpp:
            for cv in ctx.get("constituent_vars", []):
                if cv not in _seen_cv_cpp:
                    _seen_cv_cpp.add(cv)
                    all_constituent_vars_cpp.append(cv)

        for ctx in fn_ctxs_cpp:
            cfn, visible = ctx["cfn"], ctx["visible"]
            params = [(ai["host"], _chost_cpp_type(ai)) for ai in visible]

            if not params:
                A(f"void {cfn}(void);")
            else:
                A(f"void {cfn}(")
                for i, (name, cpp_t) in enumerate(params):
                    comma = "," if i < len(params) - 1 else " "
                    A(f"    {cpp_t:<16} {name}{comma}")
                A(");")
            A("")

        A("#ifdef __cplusplus")
        A("}")
        A("#endif")

        if all_constituent_vars_cpp:
            A("")
            A("#include <stdbool.h>")
            A("struct CcppConstituentInfo {")
            for fname, fkind, flen in _CONSTITUENT_STRUCT_FIELDS:
                if fkind == "char":
                    A(f"    char     {fname}[{flen + 1}];")
                elif fkind == "real":
                    A(f"    double   {fname};")
                else:  # logical
                    A(f"    bool     {fname};")
            A("};")
            A("")
            A("#ifdef __cplusplus")
            A('extern "C" {')
            A("#endif")
            A(f"int  {mod_name}_nconstituents(void);")
            A(f"void {mod_name}_get_constituent_info(struct CcppConstituentInfo* buf, int n);")
            A("#ifdef __cplusplus")
            A("}")
            A("#endif")

        return "\n".join(L) + "\n"

    def _build_chost_wrapper_text(
        self, camel_name, mod_name, bind_c_fns,
        meta_data, public_fns, suite_descriptions, ccpp_mod=None,
        ddt_source_module=None,
    ):
        """Generate the C++ ergonomics wrapper (.hpp) for the chost cap.

        Produces a header-only wrapper with:
        - A ``Status`` struct carrying an int code and std::string message.
        - Per-lifecycle named arg structs (e.g. ``RunArgs``) — errmsg/errflg/
          scheme_name are excluded and handled internally.
        - ``inline`` free functions inside ``namespace <camel_name>_chost``.
        """
        std_to_host, local_to_std, ncol_var, nz_var = _chost_build_maps(meta_data)
        kind_iso_map = _chost_kind_iso_map(ccpp_mod) if ccpp_mod is not None else {}
        suite_name = next(iter(suite_descriptions), "")
        ns_name = f"{camel_name}_chost"

        _CPP_FN_NAME = {"register": "do_register"}  # 'register' is a C++ keyword

        def struct_name(lc):
            return "".join(w.capitalize() for w in lc.split("_")) + "Args"

        L: list = []
        A = L.append
        A(f"// Generated by xdsl-ccpp. C++ ergonomics wrapper for {mod_name}.")
        A("// Array arguments are column-major (Fortran order).")
        A("#pragma once")
        A("#include <string>")
        A("#include <vector>")
        A(f'#include "{mod_name}.h"')
        A("")
        A(f"namespace {ns_name} {{")
        A("")
        A("struct Status {")
        A("    int         code;")
        A("    std::string message;")
        A("    bool ok() const { return code == 0; }")
        A("};")

        # Collect constituent vars across all lifecycles for this wrapper
        all_constituent_vars_hpp: list = []
        _seen_cv_hpp: set = set()
        fn_ctxs_hpp = list(_chost_fn_contexts(
            bind_c_fns, suite_name, suite_descriptions, public_fns,
            ncol_var, local_to_std, std_to_host, kind_iso_map,
            meta_data=meta_data, ddt_source_module=ddt_source_module, nz_var=nz_var,
        ))
        for ctx in fn_ctxs_hpp:
            for cv in ctx.get("constituent_vars", []):
                if cv not in _seen_cv_hpp:
                    _seen_cv_hpp.add(cv)
                    all_constituent_vars_hpp.append(cv)

        if all_constituent_vars_hpp:
            A("")
            A("// ── constituent query ─────────────────────────────────────────────────────")
            A("// CcppConstituentInfo is declared in the included .h file.")
            A("// Use nconstituents() + get_constituents() after do_register().")
            A("")
            A("inline int nconstituents() {")
            A(f"    return {mod_name}_nconstituents();")
            A("}")
            A("")
            A("inline std::vector<CcppConstituentInfo> get_constituents() {")
            A("    int n = nconstituents();")
            A("    std::vector<CcppConstituentInfo> v(static_cast<std::size_t>(n));")
            A(f"    if (n > 0) {mod_name}_get_constituent_info(v.data(), n);")
            A("    return v;")
            A("}")

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
            dashes = "─" * max(1, 72 - len(lc))
            A("")
            A(f"// ── {lc} {dashes}")
            A("")

            # ── Arg struct (only if there are physics args) ────────────────────
            if struct_args:
                A(f"struct {sn} {{")
                for ai in struct_args:
                    cpp_t = _chost_cpp_type(ai)
                    A(f"    {cpp_t:<16} {ai['host']};")
                A("};")
                A("")
                A(f"inline Status {cpp_fn}(const {sn}& a) {{")
            else:
                A(f"inline Status {cpp_fn}() {{")

            # ── Internal buffers ───────────────────────────────────────────────
            if has_sname:
                A(f"    char   scheme_name[{CCPP_SCHEME_NAME_LEN}]  = {{}};")
            if has_errmsg:
                A(f"    char   errmsg[{CCPP_ERRMSG_LEN}]      = {{}};")
            if has_errflg:
                A("    int    errflg           = 0;")

            # ── C function call ────────────────────────────────────────────────
            call_args = []
            for ai in visible:
                if ai["is_errmsg"]:
                    call_args.append("errmsg")
                elif ai["is_errflg"]:
                    call_args.append("&errflg")
                elif ai["is_sname"]:
                    call_args.append("scheme_name")
                else:
                    call_args.append(f"a.{ai['host']}")

            chunks = [call_args[i:i + 4] for i in range(0, len(call_args), 4)]
            if len(chunks) == 1:
                A(f"    {cfn}({', '.join(chunks[0])});")
            elif chunks:
                A(f"    {cfn}(")
                for j, chunk in enumerate(chunks):
                    comma = "," if j < len(chunks) - 1 else ""
                    A(f"        {', '.join(chunk)}{comma}")
                A("    );")

            # ── Return ─────────────────────────────────────────────────────────
            if has_errflg and has_errmsg:
                A('    return {errflg, errflg ? errmsg : ""};')
            else:
                A("    return {0, \"\"};")
            A("}")

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
            A("")
            A("// ── State " + "─" * 69)
            A("")
            A("struct State {")
            for ai in state_fields:
                # Host owns the memory — strip const so allocate() and init can write
                cpp_t   = _chost_cpp_type(ai).replace("const ", "")
                default = " = nullptr" if cpp_t.endswith("*") else " = 0"
                A(f"    {cpp_t:<16} {ai['host']}{default};")

            # Constructor: initialise ncol and all is_nz scalars; other fields
            # default via their in-class initialisers.  Prevents aggregate-init
            # errors when State has a private: section from allocate().
            ncol_fields = [ai for ai in state_fields if ai["is_ncol"]]
            nz_fields   = [ai for ai in state_fields if ai["is_nz"] or ai.get("is_dim_scalar")]
            dim_scalar_fields = ncol_fields + nz_fields
            if dim_scalar_fields:
                params_str = ", ".join(
                    f"int {ai['host']} = 0" for ai in dim_scalar_fields
                )
                inits_str = ", ".join(
                    f"{ai['host']}({ai['host']})" for ai in dim_scalar_fields
                )
                A("")
                A(f"    State({params_str})")
                A(f"        : {inits_str} {{}}")

            # Array fields whose size we can express from their dim_ncol / dim_nz / dim_n3
            alloc_fields = [
                ai for ai in state_fields
                if not ai["is_int"]
                and (
                    ai["rank"] in (1, 2)
                    or (ai["rank"] >= 3 and ai.get("dim_n3"))
                )
            ]
            if alloc_fields:
                A("")
                A("    // Allocate all array fields from internal storage.")
                A("    // Set ncol (and nz/ncnst for higher-rank arrays) before calling.")
                A("    void allocate() {")
                for ai in alloc_fields:
                    elem_t = _chost_cpp_type(ai).replace("const ", "").replace("*", "").strip()
                    _dn = ai.get("dim_ncol") or ncol_var
                    _dz = ai.get("dim_nz")   or nz_var
                    if ai["rank"] == 1:
                        size_expr = f"static_cast<std::size_t>({_dn})"
                    elif ai["rank"] == 2:
                        size_expr = f"static_cast<std::size_t>({_dn}) * {_dz}"
                    else:
                        _n3 = ai.get("dim_n3") or "1"
                        size_expr = f"static_cast<std::size_t>({_dn}) * {_dz} * {_n3}"
                    A(f"        _{ai['host']}.assign({size_expr}, 0);")
                    A(f"        {ai['host']} = _{ai['host']}.data();")
                A("    }")
                A("")
                A("private:")
                for ai in alloc_fields:
                    elem_t = _chost_cpp_type(ai).replace("const ", "").replace("*", "").strip()
                    A(f"    std::vector<{elem_t}> _{ai['host']};")

            A("};")

            for cpp_fn, sargs in lc_data:
                if not sargs:
                    continue   # zero-arg lifecycle (e.g. finalize) — existing fn is clean
                has_loop_bounds = any(
                    ai["is_col_start"] or ai["is_col_end"] for ai in sargs
                )
                A("")
                if has_loop_bounds:
                    A(f"inline Status {cpp_fn}(const State& s, int col_start, int col_end) {{")
                else:
                    A(f"inline Status {cpp_fn}(const State& s) {{")
                A(f"    return {cpp_fn}({{")
                for ai in sargs:
                    if ai["is_col_start"]:
                        A(f"        .{ai['host']}=col_start,")
                    elif ai["is_col_end"]:
                        A(f"        .{ai['host']}=col_end,")
                    else:
                        A(f"        .{ai['host']}=s.{ai['host']},")
                A("    });")
                A("}")

        A("")
        A(f"}} // namespace {ns_name}")

        return "\n".join(L) + "\n"

    def _generate_ccpp_cap_module(self, suite_descriptions, meta_data, public_fns,
                                   ddt_source_module=None, protected_std_names=None,
                                   host_std_names=None, ccpp_mod=None):
        """Build a single combined CCPP cap ModuleOp for all suites.

        Generates one module whose lifecycle subroutines use nested if/else chains
        to dispatch to the appropriate suite cap subroutine.
        """
        all_suite_names = list(suite_descriptions.keys())

        camel_name = (
            self.host_name
            if self.host_name
            else self._derive_camel_case_name(all_suite_names[0])
        )

        # Module name uses the same CamelCase prefix as the subroutine names
        # so that 'module HelloWorld_ccpp_cap' matches 'use HelloWorld_ccpp_cap'
        # in host model files.  --host-name can still override when needed.
        mod_name = camel_name + "_ccpp_cap"

        char_base = TypeConversions.getBaseType("character")
        int_base = TypeConversions.getBaseType("integer")
        suite_name_type = memref.MemRefType(char_base, [DYNAMIC_INDEX])
        errmsg_type = memref.MemRefType(char_base, [CCPP_ERRMSG_LEN])
        errflg_type = memref.MemRefType(int_base, [])

        common = dict(
            suite_name_type=suite_name_type,
            errmsg_type=errmsg_type,
            errflg_type=errflg_type,
            char_base=char_base,
            int_base=int_base,
            public_fns=public_fns,
        )

        lifecycle_specs = [
            ("_ccpp_physics_register", "_register", "_suite_register", None),
            ("_ccpp_physics_initialize", "_init", "_suite_initialize", None),
            ("_ccpp_physics_finalize", "_finalize", "_suite_finalize", None),
            ("_ccpp_physics_timestep_initial", "_timestep_initialize", "_suite_timestep_initial", None),
            ("_ccpp_physics_timestep_final", "_timestep_finalize", "_suite_timestep_final", None),
            # Run: per-group dispatch — each group calls its own suite cap function.
            ("_ccpp_physics_run", None, "_suite_", "__per_group__"),
        ]

        all_globals: list = []
        all_definitions: list = []
        all_declarations: list = []
        # Shared across ALL function calls (lifecycle AND run) to avoid duplicate GlobalOps.
        # Both lifecycle and run functions can reference the same host variables (e.g.
        # a DDT instance used in the run function may also appear in lifecycle functions).
        shared_seen_host_globals: set = set()

        # ── Build cap_var_map: interstitial DDT values returned from lifecycle ──
        # These need module-level storage in the cap so they persist between calls.
        # Format: standard_name → (var_name, mlir_type, fortran_type_str)
        # Also build host_var_map_lc for identifying host-var returns (write-back).
        cap_var_map: dict = {}
        # MODULE only: write-back targets (like num_model_times) live in MODULE
        # tables.  HOST-type tables are caller-provided interfaces, not modules.
        host_var_map_lc = self._build_host_var_map(meta_data, include_host=False)

        # ── Pre-populate cap_var_map for framework-managed and scheme-scratch arrays ──
        # Framework arrays (ccpp_constituents, ccpp_constituent_tendencies) are owned by
        # the cap module.  Scheme-specific scratch arrays with no host metadata match
        # (e.g. tendency_of_cloud_liquid_dry_mixing_ratio) are also allocated at cap
        # module scope so they never appear as physics_run block arguments.
        _FRAMEWORK_TO_CAP_VAR = {
            "ccpp_constituents": "lc_constituent_array",
            "ccpp_constituent_tendencies": "lc_const_tend",
        }
        _host_block_std: set = set()
        for _tbl_cv, _props_cv in meta_data.items():
            if _props_cv.getAttr("type") != CCPPType.HOST:
                continue
            if _tbl_cv not in _props_cv.arg_tables:
                continue
            for _var_cv in _props_cv.getArgTable(_tbl_cv).getFunctionArguments():
                if _var_cv.hasAttr("standard_name"):
                    _host_block_std.add(_var_cv.getAttr("standard_name").lower())
        _DIM_TO_ALLOC = {
            CCPP_LOOP_EXTENT_STD_NAME: "ncols",
            CCPP_HORIZ_DIM_STD_NAME: "ncols",
            CCPP_VERT_DIM_STD_NAME: "pver",
            "number_of_ccpp_constituents": "lc_num",
        }
        scratch_var_list: list = []
        scratch_var_seen: set = set()
        for _sn_cv, _sd_cv in suite_descriptions.items():
            for _grp_cv in _sd_cv:
                _grp_name_cv = _grp_cv.attributes["name"]
                _callee_cv = _sn_cv + "_suite_" + _grp_name_cv
                if _callee_cv not in public_fns:
                    continue
                _, _, _ci_types, _ci_names = public_fns[_callee_cv]
                _grp_schemes = [_s.attributes["name"] for _s in _grp_cv]
                _sno_cv: dict = {}
                _dno_cv: dict = {}
                _cno_cv: dict = {}  # bare_name → True when constituent=True
                _matched_cv: set = set()
                for _scheme_cv in _grp_schemes:
                    _run_tbl_cv = _scheme_cv + "_run"
                    if _scheme_cv not in meta_data:
                        continue
                    if _run_tbl_cv not in meta_data[_scheme_cv].arg_tables:
                        continue
                    for _fa_cv in (
                        meta_data[_scheme_cv].getArgTable(_run_tbl_cv).getFunctionArguments()
                    ):
                        _bn_cv = _bare(_fa_cv.name)
                        if _bn_cv not in _sno_cv and _fa_cv.hasAttr("standard_name"):
                            _sno_cv[_bn_cv] = _fa_cv.getAttr("standard_name").lower()
                        if _bn_cv not in _dno_cv and _fa_cv.hasAttr("dim_names"):
                            _dno_cv[_bn_cv] = _fa_cv.getAttr("dim_names")
                        if _fa_cv.hasAttr("constituent"):
                            _cno_cv[_bn_cv] = True
                        if _fa_cv.hasAttr("model_var_name"):
                            _matched_cv.add(_bn_cv)
                for _an_cv, _at_cv in zip(_ci_names, _ci_types):
                    _bn_cv = _bare(_an_cv)
                    if _bn_cv in _matched_cv:
                        continue  # host-matched (including DDT members)
                    _std_cv = _sno_cv.get(_bn_cv)
                    if not _std_cv:
                        continue
                    if _std_cv in _FRAMEWORK_TO_CAP_VAR:
                        if _std_cv not in cap_var_map:
                            cap_var_map[_std_cv] = (_FRAMEWORK_TO_CAP_VAR[_std_cv], None, None)
                        continue
                    if (_std_cv in CCPP_FRAMEWORK_STD_NAMES
                            or _std_cv in CCPP_ERROR_STD_NAMES
                            or _std_cv in _host_block_std
                            or _std_cv in host_var_map_lc):
                        continue
                    if _std_cv not in scratch_var_seen:
                        scratch_var_seen.add(_std_cv)
                        _lc_cv = f"lc_{_bn_cv}"
                        _rank_cv = (
                            len(list(_at_cv.shape.data))
                            if hasattr(_at_cv, "shape") else 0
                        )
                        _dims_cv = _dno_cv.get(_bn_cv, [])
                        _alloc_cv = ", ".join(
                            _DIM_TO_ALLOC.get(_d.lower(), "1") for _d in _dims_cv
                        ) if _dims_cv else "ncols, pver"
                        # Constituent-tendency scratch vars (constituent=True in meta)
                        # are pointer slices into lc_const_tend, not separate allocatables.
                        _const_std_name = None
                        if _cno_cv.get(_bn_cv) and _std_cv.startswith("tendency_of_"):
                            _const_std_name = _std_cv[len("tendency_of_"):]
                        cap_var_map[_std_cv] = (_lc_cv, None, None)
                        scratch_var_list.append((_lc_cv, _rank_cv, _alloc_cv, _const_std_name))

        # Detect the ccpp_info_t pattern: HOST table contains a variable with
        # standard_name = host_standard_ccpp_type (e.g. ddthost).  When present,
        # lifecycle and run functions accept a single ccpp_info_t inout arg that
        # bundles errmsg/errflg and (for run) col_start/col_end.
        ccpp_info_type = None
        ccpp_info_module_name = None
        for _tbl, _props in meta_data.items():
            if _props.getAttr("type") != CCPPType.HOST:
                continue
            if _tbl not in _props.arg_tables:
                continue
            for _var in _props.getArgTable(_tbl).getFunctionArguments():
                if (
                    _var.hasAttr("standard_name")
                    and _var.getAttr("standard_name").lower() == "host_standard_ccpp_type"
                    and _var.hasAttr("type")
                ):
                    _ddt_type_name = _var.getAttr("type")
                    _src = (ddt_source_module or {}).get(_ddt_type_name)
                    if _src:
                        ccpp_info_type = memref.MemRefType(
                            DerivedType(_ddt_type_name), []
                        )
                        ccpp_info_module_name = _src
                        # The USE stub for ccpp_info_t is emitted by the DDT
                        # type loop below (it scans all arg table types).
                    break
            if ccpp_info_type is not None:
                break

        # Detect CcppHandleOp for ccpp_t threading through generated subroutines.
        ccpp_t_type = None
        ccpp_t_var_name = None
        if ccpp_mod is not None and ccpp_info_type is None:
            for _op in ccpp_mod.body.block.ops:
                if isa(_op, ccpp.CcppHandleOp):
                    ccpp_t_type = memref.MemRefType(DerivedType("ccpp_t"), [])
                    ccpp_t_var_name = _op.var_name.data
                    break

        errmsg_type_tmp = memref.MemRefType(
            TypeConversions.getBaseType("character"), [CCPP_ERRMSG_LEN]
        )
        errflg_type_tmp = memref.MemRefType(
            TypeConversions.getBaseType("integer"), []
        )
        for _, table_postfix, callee_suffix, suite_part in lifecycle_specs:
            if suite_part is not None or table_postfix is None:
                continue  # only init/finalize produce cap-owned returns
            for suite_name, suite_desc in suite_descriptions.items():
                suite_callee = suite_name + callee_suffix
                if suite_callee not in public_fns:
                    continue
                scheme_names_lc = [
                    s.attributes["name"]
                    for g in suite_desc for s in g
                ]
                ret_info = self._get_suite_lifecycle_ret_info(
                    scheme_names_lc, meta_data, table_postfix
                )
                for ret_type, arg_name, std_name in ret_info:
                    if ret_type in (errmsg_type_tmp, errflg_type_tmp):
                        continue
                    if std_name in host_var_map_lc:
                        continue  # host var — will be written back, not cap-owned
                    # DDT interstitials (e.g. vmr_type) are now declared at suite
                    # cap module scope by generateSuiteModuleOp.  The top-level cap
                    # no longer needs to track or pass them via cap_var_map.

        for fn_suffix, table_postfix, callee_suffix, suite_part in lifecycle_specs:
            if suite_part is not None:
                # Run function: one dispatch entry per XML group, all pointing to
                # the combined _suite_physics callee.  This correctly maps each
                # group name (e.g. 'physics1', 'physics2') to the same combined
                # function while keeping per-group state intact at module scope.
                suite_run_entries = []
                for suite_name, suite_desc in suite_descriptions.items():
                    for group in suite_desc:
                        group_name = group.attributes["name"]
                        # Per-group callee: e.g. temp_suite_suite_physics1
                        suite_callee = suite_name + callee_suffix + group_name
                        if suite_callee not in public_fns:
                            continue
                        # Only this group's scheme names — matches the per-group callee's signature
                        group_scheme_names = [
                            scheme.attributes["name"] for scheme in _iter_schemes(group)
                        ]
                        suite_run_entries.append(
                            (suite_name, group_name, suite_callee, group_scheme_names)
                        )

                if not suite_run_entries:
                    continue

                cap_fn, decls, host_global_ops = self._generate_run_fn(
                    fn_name=camel_name + fn_suffix,
                    suite_run_entries=suite_run_entries,
                    meta_data=meta_data,
                    cap_var_map=cap_var_map,
                    seen_host_globals=shared_seen_host_globals,
                    ccpp_info_type=ccpp_info_type,
                    ccpp_info_module=ccpp_info_module_name,
                    ccpp_t_type=ccpp_t_type,
                    ccpp_t_var_name=ccpp_t_var_name,
                    **common,
                )
                all_globals.extend(host_global_ops)
                all_declarations.extend(decls)
            else:
                # Lifecycle function: collect per-suite callee info
                suite_entries = []
                for suite_name, suite_desc in suite_descriptions.items():
                    suite_callee = suite_name + callee_suffix
                    if suite_callee not in public_fns:
                        continue
                    scheme_names = [
                        scheme.attributes["name"]
                        for group in suite_desc
                        for scheme in _iter_schemes(group)
                    ]
                    if table_postfix is not None:
                        ret_info = self._get_suite_lifecycle_ret_info(
                            scheme_names, meta_data, table_postfix
                        )
                        call_ret_types = [t for t, _n, _s in ret_info]
                        # If no scheme-level outputs (e.g. register when no scheme
                        # has a _register entry), fall back to the callee's signature
                        # so errmsg/errflg are included.
                        if not call_ret_types:
                            _, call_ret_types, _, _ = public_fns[suite_callee]
                            ret_info = [(t, None, None) for t in call_ret_types]
                    else:
                        _, call_ret_types, _, _ = public_fns[suite_callee]
                        ret_info = [(t, None, None) for t in call_ret_types]
                    # entry_postfix is the scheme-level entry point suffix
                    # (e.g. "_init" for initialize, "_finalize" for finalize,
                    # None for timestep functions that have no host inputs).
                    entry_postfix = table_postfix
                    suite_entries.append(
                        (suite_name, suite_callee, call_ret_types,
                         scheme_names, entry_postfix, ret_info)
                    )

                if not suite_entries:
                    continue

                cap_fn, decls, lc_host_ops = self._generate_lifecycle_fn(
                    fn_name=camel_name + fn_suffix,
                    suite_entries=suite_entries,
                    meta_data=meta_data,
                    seen_host_globals=shared_seen_host_globals,
                    cap_var_map=cap_var_map,
                    host_var_map_lc=host_var_map_lc,
                    ccpp_info_type=ccpp_info_type,
                    ccpp_info_module=ccpp_info_module_name,
                    ccpp_t_type=ccpp_t_type,
                    ccpp_t_var_name=ccpp_t_var_name,
                    **common,
                )
                all_globals.extend(lc_host_ops)
                all_declarations.extend(decls)

            all_definitions.append(cap_fn)
            if self.bind_c:
                cap_fn.attributes["bind_c"] = UnitAttr()

        # Generate ccpp_physics_suite_list listing ALL suite names.
        inner_char_type = memref.MemRefType(i8, [DYNAMIC_INDEX])
        allocatable_type = memref.MemRefType(inner_char_type, [])
        suite_list_block = Block(arg_types=[allocatable_type])
        suite_list_block.args[0].name_hint = "suites"

        body_ops = []
        for sn in all_suite_names:
            str_global_name = f"str_{sn}"
            str_len = len(sn)
            arr_type = llvm.LLVMArrayType.from_size_and_type(str_len, i8)

            all_globals.append(
                llvm.GlobalOp(
                    arr_type,
                    str_global_name,
                    "internal",
                    constant=True,
                    value=StringAttr(sn),
                )
            )

            str_len_const = arith.ConstantOp(
                IntegerAttr(str_len, IndexType()), IndexType()
            )
            str_alloc = memref.AllocOp([str_len_const.result], [], inner_char_type)
            addr_op = llvm.AddressOfOp(str_global_name, llvm.LLVMPointerType())
            load_op = llvm.LoadOp(addr_op, arr_type)
            set_str_op = SetStringOp(str_alloc.memref, load_op.dereferenced_value)
            store_ref_op = memref.StoreOp.get(
                str_alloc.memref, suite_list_block.args[0], []
            )
            body_ops.extend(
                [str_len_const, str_alloc, addr_op, load_op, set_str_op, store_ref_op]
            )

        suite_list_block.add_ops([*body_ops, func.ReturnOp()])
        suite_list_region = Region()
        suite_list_region.add_block(suite_list_block)
        suite_list_fn = func.FuncOp(
            "ccpp_physics_suite_list",
            builtin.FunctionType.from_lists([allocatable_type], []),
            suite_list_region,
            visibility="public",
        )
        all_definitions.append(suite_list_fn)

        # Generate ccpp_physics_suite_part_list — use actual XML group names per suite.
        suite_part_entries = [
            (sn, [grp.attributes["name"] for grp in suite_descriptions[sn]])
            for sn in all_suite_names
        ]

        suite_part_list_fn, part_global_ops = self._generate_suite_part_list_fn(
            suite_part_entries=suite_part_entries,
            inner_char_type=inner_char_type,
            allocatable_type=allocatable_type,
            suite_name_type=suite_name_type,
            errmsg_type=errmsg_type,
            errflg_type=errflg_type,
            char_base=char_base,
            int_base=int_base,
        )
        all_globals.extend(part_global_ops)
        all_definitions.append(suite_part_list_fn)
        suite_vars_op = self._build_suite_variables_fn(
            suite_descriptions, ccpp_mod,
            host_std_names or {},
            protected_std_names or set(),
        )
        all_definitions.append(suite_vars_op)

        # Generate constituent registration API if any scheme has constituent arrays
        # or if there are cap-owned scratch arrays (framework-managed or scheme-scratch).
        dyn_names, fixed_adv = self._collect_constituent_info(meta_data)
        if dyn_names or fixed_adv or scratch_var_list:
            const_var_ops, const_api_op, const_global_stubs = self._generate_constituent_api(
                camel_name, dyn_names, fixed_adv, scratch_vars=scratch_var_list
            )
            for var_op in const_var_ops:
                _key = (var_op.var_name.data, "_cap_module_var")
                if _key not in shared_seen_host_globals:
                    shared_seen_host_globals.add(_key)
                    all_definitions.append(var_op)
            for stub in const_global_stubs:
                _key = (stub.sym_name.data,
                        stub.attributes.get("module", StringAttr("")).data)
                if _key not in shared_seen_host_globals:
                    shared_seen_host_globals.add(_key)
                    all_globals.append(stub)
            all_definitions.append(const_api_op)

        # Emit USE-association stubs for DDT types used in any scheme across all suites.
        if ddt_source_module:
            primitive_types = {"real", "integer", "character", "logical", "complex"}
            seen_type_imports: set[str] = set()
            for props in meta_data.values():
                for arg_table in props.arg_tables.values():
                    for arg in arg_table.getFunctionArguments():
                        if not arg.hasAttr("type"):
                            continue
                        arg_type = arg.getAttr("type")
                        if arg_type in primitive_types or arg_type in seen_type_imports:
                            continue
                        mod = ddt_source_module.get(arg_type)
                        if mod is None:
                            continue
                        seen_type_imports.add(arg_type)
                        stub = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(0, i8),
                            arg_type,
                            "internal",
                        )
                        stub.attributes["module"] = StringAttr(mod)
                        all_globals.append(stub)

        module_ops = all_globals + all_definitions + all_declarations

        return builtin.ModuleOp(
            module_ops,
            sym_name=builtin.StringAttr(mod_name),
        )

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        assert ccpp_mod is not None

        # Build Python descriptor objects from the CCPP metadata IR
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data_descriptions = bmdd.meta_data

        # Build the suite hierarchy descriptors
        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)
        suite_descriptions = bsd.schemes

        # Collect public functions from suite cap modules already in the IR
        public_fns = self._collect_public_suite_functions(op.body.block.ops)

        # Build DDT-type-name → Fortran-module-name map (shared utility).
        ddt_source_module = collect_ddt_source_modules(ccpp_mod)

        # Build dict of ALL standard_names provided by the host model (from
        # non-scheme tables in the IR) mapped to their declared units.
        # Used in _build_suite_variables_fn to check for unit conversions on
        # state_variable args (a unit mismatch means the suite cap rewrites the
        # value in-place, so it should not be listed as an output variable).
        host_std_names: dict[str, str | None] = {}
        for tbl_op in ccpp_mod.body.ops:
            if not isa(tbl_op, ccpp.TablePropertiesOp):
                continue
            if tbl_op.table_type.data == "scheme":
                continue
            for arg_table_op in tbl_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if arg_op.standard_name is not None:
                        _sn = arg_op.standard_name.data.lower()
                        _u = arg_op.properties.get("units")
                        host_std_names[_sn] = _u.data.lower() if _u is not None else None

        # Build set of protected host-variable standard_names.
        # Protected variables (e.g. vertical_layer_dimension, horizontal_dimension)
        # are framework-managed and excluded from ccpp_physics_suite_variables lists.
        protected_std_names: set[str] = set()
        for tbl_op in ccpp_mod.body.ops:
            if not isa(tbl_op, ccpp.TablePropertiesOp):
                continue
            if tbl_op.table_type.data not in ("module", "host", "ddt"):
                continue
            for arg_table_op in tbl_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if (arg_op.properties.get("protected") is not None
                            and arg_op.standard_name is not None):
                        protected_std_names.add(
                            arg_op.standard_name.data.lower()
                        )

        # Generate ONE combined CCPP cap module for all suites
        cap_mod = self._generate_ccpp_cap_module(
            suite_descriptions, meta_data_descriptions, public_fns,
            ddt_source_module=ddt_source_module,
            protected_std_names=protected_std_names,
            host_std_names=host_std_names,
            ccpp_mod=ccpp_mod,
        )
        op.body.block.add_op(cap_mod)

        # Generate chost cap when any host/module TablePropertiesOp carries
        # language = "c++".
        host_lang_cpp = any(
            isa(tbl_op, ccpp.TablePropertiesOp)
            and tbl_op.table_type.data in ("host", "module")
            and "language" in tbl_op.attributes
            and tbl_op.attributes["language"].data == "c++"
            for tbl_op in ccpp_mod.body.ops
        )

        if host_lang_cpp:
            chost_op = self._generate_chost_cap_module(
                suite_descriptions, meta_data_descriptions, cap_mod, ccpp_mod,
                public_fns=public_fns,
                ddt_source_module=ddt_source_module,
            )
            op.body.block.add_op(chost_op)
