"""C++/BIND(C) host-interop cap generation ("chost").

Extracted from ccpp_cap.py's CCPPCAP pass (Phase 1 of the restructuring plan):
this module owns everything needed to emit a BIND(C) Fortran cap module plus
matching C++ header/wrapper text for a C++ host model, given the already-
generated ccpp_cap module. Runs as its own pass, generate-cpp-cap, right after
generate-ccpp-cap in the pipeline.
"""

from xdsl.context import Context
from xdsl.dialects import builtin, func
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    Float32Type,
    IntegerType,
    MemRefType,
)
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import (
    CHostCapOp,
    DerivedType,
    RealKindType,
)
from xdsl_ccpp.transforms.ccpp_cap import (
    _collect_public_suite_functions,
    _resolve_ddt_access_path,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _CCPP_CONSTITUENT_MOD,
    _CONSTITUENT_DDT_NAME,
    _bare,
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
    CCPP_SCHEME_NAME_LEN,
    CCPP_VERT_DIM_STD_NAME,
    CCPP_VERTICAL_DIMENSIONS,
)

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
                # rank >= 3: use explicit shape for the 3rd dim when known so the
                # array can be passed to assumed-shape (:,:,:) suite cap dummies.
                _n3 = ai.get("dim_n3")
                if _n3:
                    return (f"    real({c_real}), target,"
                            f" intent({ai['intent']}) :: {host}({_dn}, {_dz}, {_n3})")
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
            # +1 on each: the Fortran side writes a null terminator at
            # len_trim(...)+1, which is one past the end of a buffer sized
            # exactly CCPP_*_LEN when the string fully fills it.
            if has_sname:
                A(f"    char   scheme_name[{CCPP_SCHEME_NAME_LEN + 1}]  = {{}};")
            if has_errmsg:
                A(f"    char   errmsg[{CCPP_ERRMSG_LEN + 1}]      = {{}};")
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

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        assert ccpp_mod is not None

        # Same condition CCPPCAP.apply() used to check inline: only generate
        # the chost cap when a host/module table declares language = "c++".
        host_lang_cpp = any(
            isa(tbl_op, ccpp.TablePropertiesOp)
            and tbl_op.table_type.data in ("host", "module")
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
