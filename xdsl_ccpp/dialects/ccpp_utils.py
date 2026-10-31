import re

from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    ArrayAttr,
    BoolAttr,
    IntegerAttr,
    IntegerType,
    MemRefType,
    StringAttr,
    UnitAttr,
    i1,
)
from xdsl.dialects.llvm import LLVMArrayType
from xdsl.ir import (
    Attribute,
    Block,
    Dialect,
    Operation,
    ParametrizedAttribute,
    Region,
    SSAValue,
    TypeAttribute,
    VerifyException,
)
from xdsl.irdl import (
    AttrSizedOperandSegments,
    AttrSizedRegionSegments,
    IRDLOperation,
    irdl_attr_definition,
    irdl_op_definition,
    operand_def,
    opt_operand_def,
    opt_prop_def,
    opt_region_def,
    opt_result_def,
    param_def,
    prop_def,
    region_def,
    result_def,
    traits_def,
    var_operand_def,
    var_region_def,
    var_result_def,
)
from xdsl.traits import NoTerminator


def _coerce_str_attr(value: "str | StringAttr | None") -> "StringAttr | None":
    """Coerce a plain str to StringAttr, passing an already-built StringAttr
    (or None) through.

    Extracted after this exact
    2-line `if isinstance(value, str): value = StringAttr(value)` pattern
    was found repeated, byte-identical, across 15 op/attribute constructors
    in this file. Accepts None because StrCmpOp.__init__ calls this
    unconditionally on its own optional `literal` param.
    """
    return StringAttr(value) if isinstance(value, str) else value


def _coerce_int_attr(value: "int | IntegerAttr", width: int = 64) -> IntegerAttr:
    """Coerce a plain int to IntegerAttr (given bit width), passing an
    already-built IntegerAttr through. Sibling of _coerce_str_attr -- see
    its docstring; this covers VerticalFlipOp/VerticalFlipWriteBackOp's own
    int-coercion pattern, found alongside the 15 str-coercion sites."""
    return IntegerAttr.from_int_and_width(value, width) if isinstance(value, int) else value


def _coerce_str_list_attr(value: "list[str] | ArrayAttr") -> ArrayAttr:
    """Coerce a list[str] to ArrayAttr[StringAttr], passing an already-built
    ArrayAttr through. Sibling of _coerce_str_attr -- see its docstring;
    this covers RowMajorConvertOp/RowMajorWriteBackOp's own list-coercion
    pattern, found alongside the 15 str-coercion sites."""
    return ArrayAttr([StringAttr(e) for e in value]) if isinstance(value, list) else value


def _flatten_floating_deps(root: Operation) -> "list[Operation]":
    """Return [*dependencies, root] in dependency order.

    When root is a freshly-built arith/math op tree (e.g. an
    arith.CmpiOp whose operands are a brand-new VarRefExprOp and
    arith.ConstantOp, built just for this one expression and never
    inserted into any block), every op it transitively depends on via a
    real SSA operand must be an explicit sibling in the same block as
    root -- xDSL's IsolatedFromAbove verifier rejects a region
    referencing a value whose defining op isn't itself a proper member
    of that same region (real MLIR semantics: an SSA edge alone isn't
    enough, the defining op must actually be placed in the IR tree).
    Already-attached operand providers (e.g. a block argument, or an op
    already inserted elsewhere in the real function body -- such as
    UnitConvertOp's own `source` operand) are left alone; only ops with
    no parent block get collected and placed alongside root.
    """
    seen: set[int] = set()
    order: list[Operation] = []

    def visit(op: Operation) -> None:
        if id(op) in seen:
            return
        seen.add(id(op))
        for operand in op.operands:
            owner = operand.owner
            if isinstance(owner, Operation) and owner.parent is None:
                visit(owner)
        order.append(op)

    visit(root)
    return order


def _single_op_region(ops: "list | None", *, required: bool = True) -> "Region":
    """Build a Region containing exactly one op (or zero, if required=False
    and ops is empty) -- the shared 'expression slot' shape for the new
    ccpp_utils expr-* ops that have no real SSA value to anchor an operand
    to. Raises ValueError on any other op count.

    Precedent for enforcing "exactly one op" despite IRDL enforcing
    nothing about region cardinality: CppStructDefOp.__init__ already
    raises ValueError for an invariant IRDL can't express.

    The single op given may itself be the root of a freshly-built
    arith/math expression tree (e.g. an AssignOp's arith.AddiOp rhs) --
    see _flatten_floating_deps for
    why its unattached operand-providing ops must also become block
    siblings here, not just the root itself.
    """
    ops = list(ops or [])
    if required and len(ops) != 1:
        raise ValueError(f"expected exactly one op in expression slot, got {len(ops)}")
    if not required and len(ops) > 1:
        raise ValueError(f"expected at most one op in expression slot, got {len(ops)}")
    if not ops:
        return Region([Block()])
    (root,) = ops
    return Region([Block(_flatten_floating_deps(root))])


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _name_or_target(op_name: str, field: str, name, target_op) -> tuple:
    """(properties, target region) for an op that names a variable either by
    a plain identifier (*name*, the property *field*) or by a reference
    expression (*target_op*, e.g. a MemberAccessExprOp for
    ``lc_instances(instance)%x``). A reference is never text: a *name* that
    is not an identifier is rejected."""
    if (name is None) == (target_op is None):
        raise ValueError(f"{op_name}: pass exactly one of {field} or target_op")
    if name is not None:
        if not _IDENTIFIER.match(name):
            raise ValueError(
                f"{op_name}: {field} {name!r} is not an identifier; pass the "
                f"reference as target_op (an expression op) instead"
            )
        return {field: StringAttr(name)}, None
    return {}, _single_op_region([target_op])


@irdl_attr_definition
class RealKindType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran real with a named kind qualifier.

    Used for Fortran code generation only — carries the kind name through
    the IR so the printer can emit 'real(kind=kind_name)' declarations.
    """

    name = "ccpp_utils.real_kind"
    kind_name: StringAttr = param_def()

    def __init__(self, kind_name: str | StringAttr):
        super().__init__(_coerce_str_attr(kind_name))


@irdl_attr_definition
class DerivedType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran derived data type (DDT).

    Used for Fortran code generation only — carries the DDT name through
    the IR so the printer can emit 'type(type_name)' declarations.
    """

    name = "ccpp_utils.derived_type"
    type_name: StringAttr = param_def()

    def __init__(self, type_name: str | StringAttr):
        super().__init__(_coerce_str_attr(type_name))


@irdl_attr_definition
class ReadOnlyType(ParametrizedAttribute, TypeAttribute):
    """Read-only access to a value of type ``inner``: a pointer or derived
    type the callee may not modify (C++ ``const T*`` / ``const T&``)."""

    name = "ccpp_utils.readonly"
    inner: Attribute = param_def()

    def __init__(self, inner: Attribute):
        super().__init__(inner)


@irdl_attr_definition
class OwnedArrayType(ParametrizedAttribute, TypeAttribute):
    """An owned, resizable one-dimensional array of ``element_type`` (C++
    ``std::vector<T>``, a Fortran allocatable array)."""

    name = "ccpp_utils.owned_array"
    element_type: Attribute = param_def()

    def __init__(self, element_type: Attribute):
        super().__init__(element_type)


@irdl_attr_definition
class OwnedStringType(ParametrizedAttribute, TypeAttribute):
    """An owned, resizable character string (C++ ``std::string``, a Fortran
    ``character(len=:), allocatable``)."""

    name = "ccpp_utils.owned_string"


@irdl_op_definition
class StrCmpOp(IRDLOperation):
    """String equality comparison.

    Two modes (enforced by verify_):
      - rhs/length mode: lhs and rhs are LLVMArrayType or MemRefType buffers;
        length is the number of bytes to compare.  literal must be absent.
        Emitted as: lhs .eq. rhs
      - literal mode: lhs is a MemRefType buffer; literal is a compile-time
        string constant.  rhs and length must be absent.
        Emitted as: trim(lhs) .eq. 'literal'

    Returns i1: 1 if equal, 0 if not.
    """

    name = "ccpp_utils.strcmp"

    lhs = operand_def(LLVMArrayType | MemRefType)
    rhs = opt_operand_def(LLVMArrayType | MemRefType)
    length = opt_prop_def(IntegerAttr)
    literal = opt_prop_def(StringAttr)
    res = result_def(i1)

    def __init__(
        self,
        lhs,
        rhs=None,
        length: int | None = None,
        literal: str | StringAttr | None = None,
    ):
        literal = _coerce_str_attr(literal)
        props: dict = {}
        if length is not None:
            props["length"] = IntegerAttr.from_int_and_width(length, 64)
        if literal is not None:
            props["literal"] = literal
        super().__init__(
            operands=[lhs, rhs],
            properties=props,
            result_types=[i1],
        )

    def verify_(self) -> None:
        has_rhs = self.rhs is not None
        has_length = self.length is not None
        has_literal = self.literal is not None
        if has_literal and (has_rhs or has_length):
            raise VerifyException(
                "StrCmpOp: literal cannot be combined with rhs or length"
            )
        if not has_literal and not (has_rhs and has_length):
            raise VerifyException(
                "StrCmpOp: must have either (rhs and length) or literal"
            )


@irdl_op_definition
class HostVarRefOp(IRDLOperation):
    """SSA reference to a host model module variable.

    Produces an SSA value of the given result type representing `var_name`
    from `module_name`.  No Fortran code is emitted — the printer registers
    the reference as the variable name for the result so that downstream
    ops (e.g. call arguments) print the correct host variable name.

    When `member_path` is set the variable is a DDT member: the member
    names from `var_name` down to the leaf, printed ``var_name%a%b``
    (e.g. ``phys_state%ps``). `member_subscripts` holds the leaf's
    subscripts, one expression op each (a SliceExprOp for ``:``, a constant,
    or a VarRefExprOp), e.g. ``phys_state%q(:, :, index_qv)``. The USE
    statement is still generated for `var_name` (the DDT instance), not
    the member.

    When `index_expr` is also set (real capgen-v1's multi-instance model:
    `var_name` is itself a HOST-owned array of DDT, one entry per model
    instance -- see cap_shared.py's _build_ddt_resolution_maps and
    run_dispatch.py's CCPP_INSTANCE_NUMBER_STD_NAME handling), the printed
    reference becomes ``var_name(index_expr)%member`` -- `var_name` is
    subscripted before the member access, matching real capgen-v1's own
    ``instance_data(instance)%data_array`` shape. `index_expr` is the
    index variable's name.

    A corresponding llvm.GlobalOp stub (with a 'module' attribute) is placed
    at the enclosing module level to drive 'use module, only: var' generation
    -- for `var_name` itself (the bare array/DDT name), never for `index_expr`.
    """

    name = "ccpp_utils.host_var_ref"

    var_name = prop_def(StringAttr)
    module_name = prop_def(StringAttr)
    member_path = opt_prop_def(ArrayAttr[StringAttr])
    member_subscripts = var_region_def("single_block")
    # index_expr is stored in the attributes dict (not a formal property).
    res = result_def()  # type set at construction to match callee expectation

    traits = traits_def(NoTerminator())

    def __init__(
        self, var_name: str | StringAttr, module_name: str | StringAttr,
        result_type, member_path: "str | list[str] | tuple | None" = None,
        index_expr: str | None = None, subscript_ops: "list | None" = None,
    ):
        var_name = _coerce_str_attr(var_name)
        module_name = _coerce_str_attr(module_name)
        props: dict = {"var_name": var_name, "module_name": module_name}
        if isinstance(member_path, str):
            member_path = [member_path]
        if member_path is not None:
            for member in member_path:
                if not _IDENTIFIER.match(member):
                    raise ValueError(
                        f"HostVarRefOp: member {member!r} is not an identifier; "
                        "pass the path as a list and subscripts as subscript_ops"
                    )
            props["member_path"] = ArrayAttr([StringAttr(m) for m in member_path])
        elif subscript_ops:
            raise ValueError("HostVarRefOp: subscript_ops needs a member_path")
        super().__init__(
            properties=props,
            regions=[[_single_op_region([s]) for s in subscript_ops or []]],
            result_types=[result_type],
        )
        if index_expr is not None:
            if not _IDENTIFIER.match(index_expr):
                raise ValueError(f"HostVarRefOp: index_expr {index_expr!r} is not an identifier")
            self.attributes["index_expr"] = StringAttr(index_expr)


@irdl_op_definition
class ClearStringOp(IRDLOperation):
    """Set a character buffer to an empty string: dest = ''"""

    name = "ccpp_utils.clear_string"

    dest = operand_def(MemRefType)

    def __init__(self, dest):
        super().__init__(operands=[dest])


@irdl_op_definition
class WriteErrMsgOp(IRDLOperation):
    """Write a formatted error message into an errmsg buffer.

    dest is a memref<512xi8> (errmsg buffer).
    var is a memref<?xi8> (the dynamic string part, will be trim()-ed).
    prefix and suffix are compile-time string literals.

    Printed as: write(dest, '(3a)') "prefix", trim(var), "suffix"
    """

    name = "ccpp_utils.write_errmsg"

    dest = operand_def(MemRefType)  # memref<512xi8>
    var = operand_def(MemRefType | LLVMArrayType)  # memref<?xi8> or !llvm.array<N x i8>
    prefix = prop_def(StringAttr)
    suffix = prop_def(StringAttr)

    def __init__(self, dest, var, prefix: str | StringAttr, suffix: str | StringAttr):
        prefix = _coerce_str_attr(prefix)
        suffix = _coerce_str_attr(suffix)
        super().__init__(
            operands=[dest, var],
            properties={"prefix": prefix, "suffix": suffix},
        )


@irdl_op_definition
class WriteStmtOp(IRDLOperation):
    """A list of character expressions written into a character variable.

    Emits::

        write({dest}, '(<n>a)') {item_0}, {item_1}, ...

    dest and every item are expression ops; the printer spells the format.
    Use WriteErrMsgOp instead when the dynamic part is an SSA buffer value.
    """

    name = "ccpp_utils.write_stmt"

    dest  = region_def("single_block")
    items = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, dest_op, item_ops: list):
        super().__init__(regions=[
            _single_op_region([dest_op]), [_single_op_region([i]) for i in item_ops],
        ])


@irdl_op_definition
class PrintStmtOp(IRDLOperation):
    """List-directed output of expressions to standard output.

    Emits::

        write(*,*) {item_0}, {item_1}, ...

    Every item is an expression op.
    """

    name = "ccpp_utils.print_stmt"

    items = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, item_ops: list):
        super().__init__(regions=[[_single_op_region([i]) for i in item_ops]])


@irdl_op_definition
class KindDefOp(IRDLOperation):
    """Declare a named Fortran kind parameter in the @ccpp_kinds module.

    Represents one ``integer, parameter :: kind_name = kind_value`` line in the
    generated ``ccpp_kinds`` Fortran module.  ``kind_name`` is the Fortran
    identifier (e.g. ``kind_phys``) and ``kind_value`` is its definition (e.g.
    ``REAL64`` from iso_fortran_env, or a spec name imported from a real
    host/scheme module).  ``kind_module`` names that source module --
    ``"iso_fortran_env"`` by default, matching this codebase's existing
    behavior when no metadata ``kind_spec`` resolved the kind instead.
    """

    name = "ccpp_utils.kind_def"

    kind_name = prop_def(StringAttr)
    kind_value = prop_def(StringAttr)
    kind_module = prop_def(StringAttr)

    def __init__(
        self,
        kind_name: str | StringAttr,
        kind_value: str | StringAttr,
        kind_module: str | StringAttr = "iso_fortran_env",
    ):
        kind_name = _coerce_str_attr(kind_name)
        kind_value = _coerce_str_attr(kind_value)
        kind_module = _coerce_str_attr(kind_module)
        super().__init__(
            properties={
                "kind_name": kind_name,
                "kind_value": kind_value,
                "kind_module": kind_module,
            }
        )


@irdl_op_definition
class SetStringOp(IRDLOperation):
    """Assign a string constant (llvm.array) into a character memref buffer.

    dest is a memref<?xi8> (character buffer).
    src is an !llvm.array<N x i8> obtained by loading a module-level global
    via llvm.mlir.addressof + llvm.load.

    No Fortran statement is emitted directly; the printer registers the global
    name as the variable name for dest so that a downstream memref.StoreOp into
    an allocatable can emit the correct assignment (e.g. suites(1) = str_name).
    """

    name = "ccpp_utils.set_string"

    dest = operand_def(MemRefType)  # memref<?xi8>
    src = operand_def(LLVMArrayType)  # !llvm.array<N x i8>

    def __init__(self, dest, src):
        super().__init__(operands=[dest, src])


@irdl_op_definition
class TrimOp(IRDLOperation):
    """Apply Fortran trim() to an assumed-length string memref.

    Used purely for Fortran code generation — the result carries the trimmed
    string expression through the IR so the printer emits 'trim(var_name)'
    wherever the result is used as a sub-expression.
    """

    name = "ccpp_utils.trim"

    lhs = operand_def(LLVMArrayType | MemRefType)
    res = result_def()

    def __init__(self, lhs):
        lhs_val = SSAValue.get(lhs)
        super().__init__(
            operands=[lhs],
            result_types=[lhs_val.type],
        )


@irdl_op_definition
class KeywordCallOp(IRDLOperation):
    """Fortran subroutine call with keyword (named) argument syntax.

    Used when one or more arguments are overridden with compile-time literal
    values.  All arguments — both SSA-sourced and literal-overridden — are
    printed with ``name=value`` syntax::

        call hello_scheme_run(var_a=92, ncol=ncol, lev=lev, errmsg=errmsg)

    Properties:
        callee:         The called subroutine name.
        operand_names:  Scheme parameter names for each SSA operand, in order.
        result_names:   Scheme parameter names for each SSA result, in order.

    ``override_ops`` holds the compile-time overrides, one
    ``KeywordArgExprOp`` per overridden argument.

    The printer deduplicates inout arguments (which appear in both operands
    and results) using a seen-names set.
    """

    name = "ccpp_utils.kw_call"

    callee = prop_def(StringAttr)
    operand_names = prop_def(ArrayAttr)
    result_names = prop_def(ArrayAttr)
    override_ops_region = var_region_def("single_block")

    args = var_operand_def()
    res = var_result_def()

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        callee: str | StringAttr,
        operand_names: ArrayAttr,
        result_names: ArrayAttr,
        args: list,
        out_types: list,
        *,
        override_ops: "list | None" = None,
    ):
        super().__init__(
            operands=[args],
            properties={
                "callee": _coerce_str_attr(callee),
                "operand_names": operand_names,
                "result_names": result_names,
            },
            regions=[[_single_op_region([o]) for o in override_ops or []]],
            result_types=[out_types],
        )

@irdl_op_definition
class AccDataBeginOp(IRDLOperation):
    """Emit !$acc data copy(...) copyin(...) copyout(...) present(...) directive."""
    name = "ccpp_utils.acc_data_begin"
    copy_arrays    = var_operand_def()   # arrays to copy both ways (inout)
    copyin_arrays  = var_operand_def()   # arrays to copy host → device only
    copyout_arrays = var_operand_def()   # arrays to copy device → host only
    present_arrays = var_operand_def()   # arrays asserted already on device

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, copy=None, copyin=None, copyout=None, present=None):
        super().__init__(operands=[
            list(copy    or []),
            list(copyin  or []),
            list(copyout or []),
            list(present or []),
        ])

@irdl_op_definition
class AccDataEndOp(IRDLOperation):
    """Emit !$acc end data directive."""
    name = "ccpp_utils.acc_data_end"

    def __init__(self):
        super().__init__()
@irdl_op_definition
class AccUpdateSelfOp(IRDLOperation):
    """Emit !$acc update self(...) — copies variables from GPU to CPU."""
    name = "ccpp_utils.acc_update_self"
    arrays = var_operand_def()   # SSA values from HostVarRefOp or RankReducingSliceOp

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class AccUpdateDeviceOp(IRDLOperation):
    """Emit !$acc update device(...) — copies variables from CPU to GPU."""
    name = "ccpp_utils.acc_update_device"
    arrays = var_operand_def()   # SSA values from HostVarRefOp or RankReducingSliceOp

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class AccEnterDataOp(IRDLOperation):
    """Emit !$acc enter data copyin(...) create(...) -- unstructured: no
    matching 'begin/end' pairing is enforced by the compiler, unlike
    AccDataBeginOp/AccDataEndOp. Must be balanced by hand with exactly one
    later AccExitDataOp on the same variables, or the device reference count
    never reaches zero (a silent per-run device-memory leak, not a compile
    or runtime error).

    copyin_arrays: host->device transfer, establishing residency for
        variables some caller reads before writing (needs_in).
    create_arrays: device allocation only, no initial transfer -- variables
        that are always written before being read (needs_in is False).
    """
    name = "ccpp_utils.acc_enter_data"
    copyin_arrays = var_operand_def()
    create_arrays = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, copyin=None, create=None):
        super().__init__(operands=[
            list(copyin or []),
            list(create or []),
        ])

@irdl_op_definition
class AccExitDataOp(IRDLOperation):
    """Emit !$acc exit data copyout(...) delete(...) -- unstructured, the
    exit half of an AccEnterDataOp/AccExitDataOp pair (see AccEnterDataOp).

    copyout_arrays: device->host transfer, then release residency --
        variables some caller reads back after the hoisted region closes
        (needs_out).
    delete_arrays: release residency only, no transfer back -- variables
        nothing reads back on the host side (needs_out is False). Still
        required to balance the matching AccEnterDataOp's reference count
        even though no data moves.
    """
    name = "ccpp_utils.acc_exit_data"
    copyout_arrays = var_operand_def()
    delete_arrays  = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, copyout=None, delete=None):
        super().__init__(operands=[
            list(copyout or []),
            list(delete or []),
        ])

@irdl_op_definition
class AccParallelOp(IRDLOperation):
    """An OpenACC compute region around ``body``.

    Emits::

        !$acc parallel present(...)
        <body>
        !$acc end parallel

    ``present_arrays`` are the values asserted to be on the device (SSA
    values, as for AccDataBeginOp); with none, the clause is omitted.
    """

    name = "ccpp_utils.acc_parallel"
    present_arrays = var_operand_def()
    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, body_ops: list, present=None):
        super().__init__(
            operands=[list(present or [])],
            regions=[Region([Block(list(body_ops))])],
        )

@irdl_op_definition
class OmpTargetDataBeginOp(IRDLOperation):
    """Emit !$omp target data map(tofrom:...) map(alloc:...) directive."""
    name = "ccpp_utils.omp_target_data_begin"
    tofrom_arrays = var_operand_def()   # copy both ways (equivalent to copyin+copyout)
    alloc_arrays  = var_operand_def()   # already on device (equivalent to present)

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, tofrom=None, alloc=None):
        super().__init__(operands=[
            list(tofrom or []),
            list(alloc  or []),
        ])

@irdl_op_definition
class OmpTargetDataEndOp(IRDLOperation):
    """Emit !$omp end target data directive."""
    name = "ccpp_utils.omp_target_data_end"

    def __init__(self):
        super().__init__()

@irdl_op_definition
class OmpTargetUpdateFromOp(IRDLOperation):
    """Emit !$omp target update from(...) — copies variables from GPU to CPU."""
    name = "ccpp_utils.omp_target_update_from"
    arrays = var_operand_def()

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class OmpTargetUpdateToOp(IRDLOperation):
    """Emit !$omp target update to(...) — copies variables from CPU to GPU."""
    name = "ccpp_utils.omp_target_update_to"
    arrays = var_operand_def()

    def __init__(self, array_refs):
        super().__init__(operands=[list(array_refs)])

@irdl_op_definition
class OmpTargetEnterDataOp(IRDLOperation):
    """Emit !$omp target enter data map(to:...) map(alloc:...) -- unstructured,
    the OMP equivalent of AccEnterDataOp (see there for the general
    unstructured-pairing caveat: must be balanced by hand with exactly one
    later OmpTargetExitDataOp on the same variables, or the device reference
    count never reaches zero).

    to_arrays: host->device transfer, establishing residency for variables
        some caller reads before writing (needs_in) -- OMP's map(to:...)
        is the direct equivalent of ACC's copyin(...).
    alloc_arrays: device allocation only, no initial transfer -- variables
        that are always written before being read (needs_in is False) --
        equivalent to ACC's create(...).
    """
    name = "ccpp_utils.omp_target_enter_data"
    to_arrays    = var_operand_def()
    alloc_arrays = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, to=None, alloc=None):
        super().__init__(operands=[
            list(to    or []),
            list(alloc or []),
        ])

@irdl_op_definition
class OmpTargetExitDataOp(IRDLOperation):
    """Emit !$omp target exit data map(from:...) map(release:...) --
    unstructured, the exit half of an OmpTargetEnterDataOp/OmpTargetExitDataOp
    pair (see OmpTargetEnterDataOp).

    from_arrays: device->host transfer, then release residency -- variables
        some caller reads back after the hoisted region closes (needs_out) --
        equivalent to ACC's copyout(...).
    release_arrays: release residency only, no transfer back -- variables
        nothing reads back on the host side (needs_out is False). Still
        required to balance the matching OmpTargetEnterDataOp's reference
        count even though no data moves. "release" (decrements the
        reference count, freeing only once it reaches zero) is the direct
        equivalent of ACC's delete(...) -- deliberately not OMP 5.0's
        stronger map(delete:...), which forces removal regardless of
        reference count and could tear down a mapping something else still
        expects to be live.
    """
    name = "ccpp_utils.omp_target_exit_data"
    from_arrays    = var_operand_def()
    release_arrays = var_operand_def()

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, from_=None, release=None):
        super().__init__(operands=[
            list(from_   or []),
            list(release or []),
        ])

def _kind_and_char_len_props(op_name: str, base_type: str, kind, char_len) -> dict:
    """A declaration's kind (an identifier, e.g. kind_phys or c_char, or an
    integer kind such as 8) and character length (a positive integer)
    properties."""
    props: dict = {}
    if kind is not None:
        if not (_IDENTIFIER.match(kind) or (kind.isdigit() and base_type != "character")):
            raise ValueError(f"{op_name}: kind {kind!r} is not an identifier or integer; "
                             "pass a character length as char_len")
        props["kind"] = StringAttr(kind)
    if char_len is not None:
        if char_len <= 0:
            raise ValueError(f"{op_name}: char_len must be positive, got {char_len}")
        props["char_len"] = IntegerAttr.from_int_and_width(char_len, 64)
    return props


@irdl_op_definition
class ModuleVarOp(IRDLOperation):
    """Unified module-level variable declaration, covering both real vars and
    DDT vars with a single consistent representation.

    Type is described by structured attributes so that language backends other
    than Fortran can interpret the type without parsing:

        base_type  — CCPP base type: "real", "integer", "character",
                     "logical", or "type" (for DDTs)
        kind       — optional kind name, an identifier ("kind_phys", "c_char")
        char_len   — character length (512) when base_type == "character"
        ddt_name   — DDT type name when base_type == "type" (e.g. "vmr_type")
        is_pointer — True when the variable carries the Fortran POINTER attribute
        is_target  — True when the variable carries the Fortran TARGET attribute

    Printer emits in the module spec section before CONTAINS:
        rank=0: ``{type} :: {var_name}``
        rank>0: ``{type}, allocatable :: {var_name}(:, :, ...)``
        (is_pointer rank>0): ``{type}, pointer :: {var_name}(:) => null()``

    Examples::

        ModuleVarOp("temp_layer", "real", kind="kind_phys", rank=2)
        → real(kind=kind_phys), allocatable :: temp_layer(:, :)

        ModuleVarOp("vmr_cap_ddt_suite", "type", ddt_name="vmr_type")
        → type(vmr_type) :: vmr_cap_ddt_suite

        ModuleVarOp("lc_arr", "real", kind="kind_phys", is_target=True, rank=3)
        → real(kind=kind_phys), target, allocatable :: lc_arr(:, :, :)
    """

    name = "ccpp_utils.module_var"
    var_name   = prop_def(StringAttr)
    base_type  = prop_def(StringAttr)        # "real"|"integer"|"character"|"logical"|"type"
    kind       = opt_prop_def(StringAttr)    # kind name; None if not applicable
    char_len   = opt_prop_def(IntegerAttr)   # character length
    ddt_name   = opt_prop_def(StringAttr)    # DDT type name when base_type == "type"
    is_pointer = opt_prop_def(BoolAttr)      # True → Fortran POINTER attribute
    is_target  = opt_prop_def(BoolAttr)      # True → Fortran TARGET attribute
    rank       = prop_def(IntegerAttr)       # 0 = scalar, >0 = allocatable array
    fixed_dim  = opt_prop_def(IntegerAttr)   # if set: fixed-size non-allocatable 1D array
    # Optional initial value (for fixed_dim vars), an expression op.
    init_value_region = opt_region_def("single_block")
    needs_device_residency = opt_prop_def(BoolAttr)  # True -> also emit a
                                # module-level `!$acc declare create(var_name)`
                                # (guarded by #ifdef USE_GPU) right alongside
                                # this declaration. A runtime `!$acc enter
                                # data create(...)` inside a later subroutine
                                # (see LazyAllocOp) establishes the actual
                                # device buffer, but for a module-scope
                                # ALLOCATABLE array referenced across many
                                # separate, later subroutine calls over the
                                # life of the run (unlike a single lexically-
                                # scoped `!$acc data` region), nvfortran needs
                                # this companion `declare create` at the
                                # point of declaration itself, or the array's
                                # device-side descriptor/size is undefined --
                                # confirmed as the actual cause of a
                                # "PRESENT clause was not found on device"
                                # runtime failure for a SuiteOwned scratch
                                # array even after its enter-data-create/
                                # update-device calls were verified compiling
                                # and executing correctly.

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        var_name: str,
        base_type: str,
        *,
        kind: str | None = None,
        char_len: int | None = None,
        ddt_name: str | None = None,
        is_pointer: bool = False,
        is_target: bool = False,
        rank: int = 0,
        fixed_dim: int | None = None,
        init_value_op=None,
        needs_device_residency: bool = False,
    ):
        props: dict = {
            "var_name":  StringAttr(var_name),
            "base_type": StringAttr(base_type),
            "rank":      IntegerAttr.from_int_and_width(rank, 64),
            **_kind_and_char_len_props("ModuleVarOp", base_type, kind, char_len),
        }
        if ddt_name is not None:
            props["ddt_name"] = StringAttr(ddt_name)
        if is_pointer:
            props["is_pointer"] = BoolAttr.from_bool(True)
        if is_target:
            props["is_target"] = BoolAttr.from_bool(True)
        if fixed_dim is not None:
            props["fixed_dim"] = IntegerAttr.from_int_and_width(fixed_dim, 64)
        init_region = (
            _single_op_region([init_value_op]) if init_value_op is not None else None
        )
        if needs_device_residency:
            props["needs_device_residency"] = BoolAttr.from_bool(True)
        super().__init__(properties=props, regions=[init_region])


@irdl_op_definition
class LazyAllocOp(IRDLOperation):
    """Allocate a module-level array on its first use and initialize it.

    Emitted inside _suite_physics before the first scheme call:
        if (.not. allocated(var_name)) then
          allocate(var_name(d1, d2, ...))
          var_name = init_value
    #ifdef USE_GPU
          !$acc enter data create(var_name)
    #endif
        end if

    dim_vars are SSA values whose variable names supply the dimension extents.

    needs_device_residency (SuiteOwned GPU residency): when set, the printer
    also emits the enter-data-create line above, INSIDE this same
    `if (.not. allocated(...))` block -- deliberately not a separately
    inserted AccEnterDataOp, since this array can be allocated from either
    of two lifecycle functions (_suite_register/_suite_initialize, whichever
    runs first at simulation start), each emitting its own LazyAllocOp for
    the same var. A separate, unconditionally-inserted enter-data op after
    each occurrence would double-fire (both would execute regardless of
    which one's allocate actually ran), double-incrementing the OpenACC
    reference count. Baking it into this op's own printer means it inherits
    the exact same "already done" runtime guard the allocate itself uses,
    with no extra bookkeeping.

    realloc_on_resize (package-cap segments of repeating phases): the extents
    can change between calls (e.g. the daylit-column count), so an array
    allocated with other extents is first deallocated:
        if (allocated(var_name)) then
          if (any(shape(var_name) /= [d1, d2, ...])) deallocate(var_name)
        end if
    """

    name = "ccpp_utils.lazy_alloc"
    var_name   = prop_def(StringAttr)
    # Optional initial value, an expression op (e.g. a .meta default_value).
    init_value_region = opt_region_def("single_block")
    needs_device_residency = opt_prop_def(BoolAttr)
    is_run_local = opt_prop_def(BoolAttr)  # when True: plain allocate(), no lazy guard
    realloc_on_resize = opt_prop_def(BoolAttr)
    dim_vars   = var_operand_def()          # SSA values giving dimension sizes

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: str, dim_var_refs: list,
                 needs_device_residency: bool = False,
                 is_run_local: bool = False, *, init_value_op=None):
        props: dict = {"var_name": StringAttr(var_name)}
        init_region = (
            _single_op_region([init_value_op]) if init_value_op is not None else None
        )
        if needs_device_residency:
            props["needs_device_residency"] = BoolAttr.from_bool(needs_device_residency)
        if is_run_local:
            props["is_run_local"] = BoolAttr.from_bool(True)
        super().__init__(
            operands=[dim_var_refs], properties=props, regions=[init_region]
        )


@irdl_op_definition
class SafeDeallocOp(IRDLOperation):
    """Deallocate a module-level array if it is currently allocated.

    Emitted inside _suite_timestep_final:
        if (allocated(var_name)) deallocate(var_name)

    The variable is an identifier (var_name) or a reference expression
    (target_op), see _name_or_target.
    """

    name = "ccpp_utils.safe_dealloc"
    var_name = opt_prop_def(StringAttr)
    target = opt_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: "str | None" = None, *, target_op=None):
        props, target = _name_or_target("SafeDeallocOp", "var_name", var_name, target_op)
        super().__init__(properties=props, regions=[target])


@irdl_op_definition
class RankReducingSliceOp(IRDLOperation):
    """General rank-reducing Fortran array section.

    Each dimension of the source array is described by the ``dim_pattern``
    property as either a range (``'R'``) or a scalar index (``'S'``):

    - ``'R'`` — dimension is kept as a range ``lower:upper`` (rank preserved)
    - ``'S'`` — dimension is fixed to a scalar index (rank reduced by 1)

    Operands are grouped into two variadic lists, matched left-to-right as
    the pattern is scanned:
    - ``range_lowers`` / ``range_uppers`` — one pair per ``'R'`` in pattern
    - ``scalar_indices``                  — one value per ``'S'`` in pattern

    Examples::

        dim_pattern="RS", range=(col_start,col_end), scalar=(lev,)
            → source(col_start:col_end, lev)          2D→1D (common CCPP case)

        dim_pattern="SR", scalar=(lev,), range=(col_start,col_end)
            → source(lev, col_start:col_end)          2D→1D (reversed axes)

        dim_pattern="RSS", range=(col_start,col_end), scalar=(lev,spec)
            → source(col_start:col_end, lev, spec)    3D→1D

        dim_pattern="RSR", range=(cs,ce,ss,se), scalar=(lev,)
            → source(cs:ce, lev, ss:se)               3D→2D

    The result rank equals the number of ``'R'`` entries in ``dim_pattern``.
    """

    name = "ccpp_utils.rank_reducing_slice"

    source        = operand_def(MemRefType)
    # MemRefType | IntegerType, not MemRefType alone (task70-arraysection):
    # a bound can be a raw arith.ConstantOp result (e.g. the shared literal
    # '1' lower bound for an extra, non-column-chunked dimension), not
    # always a memref -- the same permissiveness the former ArraySectionOp's
    # own lowers/uppers already had, needed once this op absorbed its
    # all-'R' (plain array-section) case.
    range_lowers  = var_operand_def(MemRefType | IntegerType)   # lower bound per 'R' dimension
    range_uppers  = var_operand_def(MemRefType | IntegerType)   # upper bound per 'R' dimension
    scalar_indices = var_operand_def(MemRefType)  # scalar index per 'S' dimension
    # e.g. "RS" = first dim is range, second dim is scalar
    dim_pattern   = prop_def(StringAttr)
    res           = result_def(MemRefType)

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(
        self,
        source,
        dim_pattern: str,
        range_lowers: list,
        range_uppers: list,
        scalar_indices: list,
    ):
        source_val = SSAValue.get(source)
        src_type = source_val.type
        if scalar_indices:
            # Mixed/rank-reducing case (e.g. CCPP variable promotion):
            # result rank = number of 'R' entries, each retained dimension
            # dynamic.
            result_rank = dim_pattern.count("R")
            if isinstance(src_type, MemRefType):
                result_type = MemRefType(
                    src_type.element_type, [DYNAMIC_INDEX] * result_rank
                )
            else:
                result_type = src_type
        else:
            # All-'R' case (task70-arraysection: the former ArraySectionOp's
            # own case) -- mirror its exact type semantics, copying the
            # source's own type verbatim rather than recomputing rank from
            # dim_pattern's length. Not just equivalent: when source is
            # already a DDT-member ref whose own member subscripts include
            # a fixed index (e.g. "q(:, :, index_qv)"),
            # the printer's existing-subscript merge (print_ftn.py) only
            # consumes as many range parts as there are ':' placeholders
            # already in that subscript, silently discarding the rest --
            # so the true printed rank can be LOWER than len(range_lowers)
            # in that case. Trusting source's own type here, exactly as
            # ArraySectionOp always did, keeps this degenerate case
            # byte-for-byte behavior-preserving regardless.
            result_type = src_type
        super().__init__(
            operands=[source, list(range_lowers), list(range_uppers),
                      list(scalar_indices)],
            properties={"dim_pattern": StringAttr(dim_pattern)},
            result_types=[result_type],
        )


@irdl_op_definition
class PromotionLoopOp(IRDLOperation):
    """Fortran do loop for CCPP variable promotion.

    Generates::

        do {loop_var_name} = 1, upper_bound_val
          ... body ...
        end do

    ``loop_var`` is a scalar integer alloca whose name_hint becomes the
    Fortran loop variable name.  ``upper_bound`` is the integer value to
    loop to (inclusive), e.g. the SSA value of ``pver``.

    The body region contains scheme call ops.  Inside those calls,
    RankReducingSliceOp operands reference ``loop_var`` (via LoadOp) to
    produce column-slice expressions like ``arr(col_start:col_end, lev_idx)``.
    """

    name = "ccpp_utils.promotion_loop"

    loop_var    = operand_def(MemRefType)  # integer alloca; name_hint = loop var name
    upper_bound = operand_def(MemRefType)  # integer value giving loop upper bound
    body        = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, loop_var, upper_bound, body_ops):
        super().__init__(
            operands=[loop_var, upper_bound],
            regions=[body_ops],
        )


@irdl_op_definition
class SubcycleLoopOp(IRDLOperation):
    """Fortran do loop for CCPP subcycle blocks.

    Generates::

        do {loop_var_name} = 1, <loop_count>
          ... body ...
        end do

    ``loop_var`` is a scalar integer alloca whose name_hint becomes the
    Fortran loop variable name.  ``loop_count`` is either a literal integer
    from ``loop="N"`` in the suite XML or a CCPP standard name resolved at
    runtime; ``is_literal`` records which case applies.
    """

    name = "ccpp_utils.subcycle_loop"

    loop_count = opt_prop_def(StringAttr)
    # lang-neutral-expr-ir Stage 5: structured alternative to loop_count,
    # pass loop_count_op= instead. Exactly one of the two must be given.
    loop_count_region = opt_region_def("single_block")
    is_literal = prop_def(BoolAttr)
    loop_var   = operand_def(MemRefType)

    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, loop_count: "int | str | None" = None, loop_var=None,
                 body_ops=None, is_literal: bool = True, *, loop_count_op=None):
        if (loop_count is None) == (loop_count_op is None):
            raise ValueError(
                "SubcycleLoopOp: pass exactly one of loop_count or loop_count_op"
            )
        if isinstance(body_ops, list):
            body = Region([Block(body_ops)])
        else:
            body = body_ops
        props: dict = {}
        count_region = None
        if loop_count is not None:
            props["loop_count"] = StringAttr(str(loop_count))
        else:
            count_region = _single_op_region([loop_count_op])
        props["is_literal"] = BoolAttr.from_bool(is_literal)
        super().__init__(
            operands=[loop_var],
            properties=props,
            regions=[count_region, body],
        )


@irdl_op_definition
class PresentCheckOp(IRDLOperation):
    """Fortran if (present(var)) / else / end if for optional promoted args.

    Generates::

        if (present({var_name})) then
          ... with_body ...
        else
          ... without_body ...
        end if

    ``var_name`` is the bare Fortran variable name used in the present() test.
    ``with_body`` contains the slice op(s) + scheme call that include the
    optional arg.  ``without_body`` contains the scheme call that omits it.
    """

    name = "ccpp_utils.present_check"

    var_name = prop_def(StringAttr)

    with_body    = region_def("single_block")
    without_body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: str, with_body_ops: list, without_body_ops: list):
        super().__init__(
            properties={"var_name": StringAttr(var_name)},
            regions=[with_body_ops, without_body_ops],
        )


@irdl_op_definition
class ActiveCheckOp(IRDLOperation):
    """Fortran if (<condition>) / else / end if for an 'active'-gated optional arg.

    Generates::

        if ({condition}) then
          ... with_body ...
        else
          ... without_body ...
        end if

    Distinct from PresentCheckOp: this tests a host-declared logical
    expression (from an ArgumentOp's own 'active' property, e.g.
    'flag_for_opt_arg', copied onto a matched scheme arg as
    model_var_active_expr by HostVariableMatchPass), not whether the current
    subroutine's own optional dummy argument was passed by its caller --
    conceptually related but a different runtime condition, so kept as a
    separate op rather than generalizing PresentCheckOp.

    ``condition`` holds an i1 expression op. ``with_body`` contains the
    slice op(s) + scheme call that include the active-gated arg(s).
    ``without_body`` contains the scheme call that omits them.
    """

    name = "ccpp_utils.active_check"

    condition = region_def("single_block")

    with_body    = region_def("single_block")
    without_body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, condition_op, with_body_ops: "list | None" = None,
        without_body_ops: "list | None" = None,
    ):
        super().__init__(
            regions=[_single_op_region([condition_op]), with_body_ops or [],
                     without_body_ops or []],
        )


@irdl_op_definition
class NullifyPointerOp(IRDLOperation):
    """Null-initialise a Fortran POINTER variable.

    Emits::

        nullify({ptr_name})

    or, with if_associated::

        if (associated({ptr_name})) nullify({ptr_name})
    """

    name = "ccpp_utils.nullify_pointer"
    ptr_name = opt_prop_def(StringAttr)
    if_associated = opt_prop_def(UnitAttr)
    target = opt_region_def("single_block")   # see _name_or_target

    traits = traits_def(NoTerminator())

    def __init__(self, ptr_name: "str | None" = None, *, target_op=None,
                 if_associated: bool = False):
        props, target = _name_or_target("NullifyPointerOp", "ptr_name", ptr_name, target_op)
        if if_associated:
            props["if_associated"] = UnitAttr()
        super().__init__(properties=props, regions=[target])


@irdl_op_definition
class AllocateOp(IRDLOperation):
    """Allocate a Fortran allocatable or pointer variable, with an
    optional shape and an optional STAT= clause.

    Emits, with one or more dimension extents (expression ops, ``dim_ops``)::

        allocate({var_name}({dim0}, {dim1}, ...)[, stat={stat_var}])

    or, with none (a scalar allocatable/pointer allocation, e.g. a
    derived-type pointer target)::

        allocate({var_name}[, stat={stat_var}])

    The variable is an identifier (``var_name``) or a reference expression
    (``target_op``, see _name_or_target); ``stat_var`` is the identifier of
    the STAT= variable.
    """

    name = "ccpp_utils.allocate"
    var_name = opt_prop_def(StringAttr)
    target = opt_region_def("single_block")   # see _name_or_target
    dims_region = var_region_def("single_block")   # one expression op per dimension
    stat_var = opt_prop_def(StringAttr)

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(
        self, var_name: "str | None" = None, *, dim_ops: "list | None" = None,
        stat_var: "str | None" = None, target_op=None,
    ):
        props, target = _name_or_target("AllocateOp", "var_name", var_name, target_op)
        dims_regions = [_single_op_region([d]) for d in (dim_ops or [])]
        if stat_var is not None:
            props["stat_var"] = StringAttr(stat_var)
        super().__init__(properties=props, regions=[target, dims_regions])


@irdl_op_definition
class ZeroFillOp(IRDLOperation):
    """Assign 0.0_kind_phys to a real array variable.

    Emits::

        {var_name} = 0.0_kind_phys
    """

    name = "ccpp_utils.zero_fill"
    var_name = opt_prop_def(StringAttr)
    target = opt_region_def("single_block")   # see _name_or_target

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: "str | None" = None, *, target_op=None):
        props, target = _name_or_target("ZeroFillOp", "var_name", var_name, target_op)
        super().__init__(properties=props, regions=[target])


@irdl_op_definition
class PointerAssignOp(IRDLOperation):
    """Associate a pointer with an arbitrary right-hand-side expression.

    Emits::

        {ptr_name} => {rhs}

    The right-hand side is an expression op (``rhs_expr_op``): a variable,
    a member access, a function result, or a slice such as
    ``{array}(:, :, {index})`` (an IndexExprOp with SliceExprOp
    subscripts). The pointer is an identifier (``ptr_name``) or a
    reference expression (``target_op``, see _name_or_target).
    """

    name = "ccpp_utils.pointer_assign"
    ptr_name = opt_prop_def(StringAttr)
    target = opt_region_def("single_block")   # see _name_or_target
    rhs_expr_region = region_def("single_block")

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(self, ptr_name: "str | None" = None, *, rhs_expr_op, target_op=None):
        props, target = _name_or_target("PointerAssignOp", "ptr_name", ptr_name, target_op)
        super().__init__(properties=props, regions=[target, _single_op_region([rhs_expr_op])])


@irdl_op_definition
class AssignOp(IRDLOperation):
    """A plain (non-pointer) scalar or array-element assignment statement.

    Emits::

        {lhs} = {rhs}

    Both sides are expression ops (VarRefExprOp, IndexExprOp, arith
    constants and operators, ...), which the printer renders. Covers
    plain-value assignment; use PointerAssignOp instead for ``=>`` pointer
    association.
    """

    name = "ccpp_utils.assign"
    lhs = region_def("single_block")
    rhs = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, *, lhs_op, rhs_op):
        super().__init__(regions=[_single_op_region([lhs_op]), _single_op_region([rhs_op])])


@irdl_op_definition
class DdtMethodCallOp(IRDLOperation):
    """Call a type-bound procedure on a DDT object, with positional and/or
    keyword arguments.

    Emits::

        call {obj}%{method}({args joined with kwargs, comma-separated})

    The object (``obj_expr_op``, e.g. ``lc_instances(instance)%obj`` as a
    MemberAccessExprOp), the positional arguments (``arg_ops``) and the
    keyword arguments (``kwarg_ops``, KeywordArgExprOps) are expression
    ops. Distinct from CamDirectCallOp (a plain ``call {callee}(...)`` with
    positional-only args, no ``%`` receiver convention implied).
    """

    name = "ccpp_utils.ddt_method_call"
    obj_expr_region = region_def("single_block")
    method   = prop_def(StringAttr)
    args_region = var_region_def("single_block")
    kwargs_region = var_region_def("single_block")

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(
        self, *, obj_expr_op, method: str,
        arg_ops: "list | None" = None, kwarg_ops: "list | None" = None,
    ):
        if not _IDENTIFIER.match(method):
            raise ValueError(f"DdtMethodCallOp: method {method!r} is not an identifier")
        super().__init__(
            properties={"method": StringAttr(method)},
            regions=[
                _single_op_region([obj_expr_op]),
                [_single_op_region([a]) for a in (arg_ops or [])],
                [_single_op_region([k]) for k in (kwarg_ops or [])],
            ],
        )


@irdl_op_definition
class ErrorGuardOp(IRDLOperation):
    """Early-return guard: if NOT condition, set error state and return.

    Emits::

        if (.not. {condition}) then
          {errflg_var} = 1
          {errmsg_var} = '{errmsg_text}'
          return
        end if

    The condition is an expression op (``condition_op``); ``errmsg_text``
    is the message, data.
    """

    name = "ccpp_utils.error_guard"
    condition_region = region_def("single_block")
    errmsg_text = prop_def(StringAttr)
    errflg_var  = opt_prop_def(StringAttr)  # default "errflg" if unset
    errmsg_var  = opt_prop_def(StringAttr)  # default "errmsg" if unset

    traits = traits_def(NoTerminator())

    def __init__(
        self, *, condition_op, errmsg_text: str,
        errflg_var: str = "errflg", errmsg_var: str = "errmsg",
    ):
        props: dict = {"errmsg_text": StringAttr(errmsg_text)}
        if errflg_var != "errflg":
            props["errflg_var"] = StringAttr(errflg_var)
        if errmsg_var != "errmsg":
            props["errmsg_var"] = StringAttr(errmsg_var)
        super().__init__(properties=props, regions=[_single_op_region([condition_op])])


@irdl_op_definition
class DoLoopOp(IRDLOperation):
    """Fortran ``do {loop_var} = 1, {upper}`` whose trip count is an
    expression op (e.g. a CallExprOp for ``size(x)``), not an SSA value.

    Emits::

        do {loop_var} = 1, {upper}
          {body}
        end do

    Distinct from PromotionLoopOp/SubcycleLoopOp, which loop over SSA-valued
    bounds.
    """

    name = "ccpp_utils.do_loop"
    loop_var = prop_def(StringAttr)
    upper    = region_def("single_block")
    body     = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, loop_var: str, upper_op, body_ops: list):
        super().__init__(
            properties={"loop_var": StringAttr(loop_var)},
            regions=[_single_op_region([upper_op]), Region([Block(body_ops)])],
        )


@irdl_op_definition
class ScopedBlockOp(IRDLOperation):
    """Fortran BLOCK construct introducing a local scope with declarations.

    Emits::

        block
          <declaration of each local>
          {body ops}
        end block

    The locals are named allocas (name_local and friends) placed first in
    the body; the printer declares them here, in the block's own
    specification part, not in the enclosing function's.
    """

    name = "ccpp_utils.scoped_block"

    body        = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, local_allocas: list, body_ops: list):
        body = Region([Block([*local_allocas, *body_ops])])
        super().__init__(regions=[body])


@irdl_op_definition
class CToFortranStringCopyOp(IRDLOperation):
    """The fixed-shape C-to-Fortran NUL-terminated char-array copy-in idiom
    used by the chost BIND(C) cap to receive a ``character(kind=c_char)``
    array argument into a local deferred-length Fortran string.

    Emits::

        {f_var} = ' '
        do i = 1, len({f_var})
          if ({c_var}(i) == c_null_char) exit
          {f_var}(i:i) = {c_var}(i)
        end do

    ``c_var``/``f_var`` are opaque name text (see AssignOp's own docstring
    for why expression content stays unstructured). The shape is fixed --
    always blank-init then scan-until-NUL -- so a dedicated op is clearer
    here than composing it from smaller loop primitives; it never varies
    across its call sites.

    Relies on a surrounding scope having declared an untyped ``integer``
    loop variable named ``i`` (matching the original hand-written code;
    not owned by this op).
    """

    name = "ccpp_utils.c_to_fortran_string_copy"
    c_var = prop_def(StringAttr)
    f_var = prop_def(StringAttr)

    def __init__(self, c_var: str, f_var: str):
        super().__init__(properties={
            "c_var": StringAttr(c_var),
            "f_var": StringAttr(f_var),
        })


@irdl_op_definition
class FortranToCStringCopyOp(IRDLOperation):
    """The fixed-shape Fortran-to-C NUL-terminated char-array copy-out
    idiom used by the chost BIND(C) cap to return a local Fortran string
    through a ``character(kind=c_char)`` array argument.

    Emits::

        do i = 1, len_trim({f_var})
          {c_var}(i) = {f_var}(i:i)
        end do
        {c_var}(len_trim({f_var})+1) = c_null_char

    ``c_var``/``f_var`` are opaque name text (see AssignOp's own docstring
    for why expression content stays unstructured). Mirror image of
    CToFortranStringCopyOp; kept as a separate op rather than a direction
    flag since the two shapes share no printable text and a flag would
    just push the branching into the printer.

    Relies on a surrounding scope having declared an untyped ``integer``
    loop variable named ``i`` (matching the original hand-written code;
    not owned by this op).
    """

    name = "ccpp_utils.fortran_to_c_string_copy"
    c_var = prop_def(StringAttr)
    f_var = prop_def(StringAttr)

    def __init__(self, c_var: str, f_var: str):
        super().__init__(properties={
            "c_var": StringAttr(c_var),
            "f_var": StringAttr(f_var),
        })


@irdl_op_definition
class DdtComponentDeclOp(IRDLOperation):
    """One component declaration inside a DerivedTypeDefOp.

    Same shape as ModuleVarOp (base_type/kind/char_len/ddt_name/is_pointer/
    rank/fixed_dim/init_value) but deliberately has no is_target/
    needs_device_residency properties at all -- TARGET is illegal on a
    Fortran derived-type component (gfortran: "Attribute at (1) is not
    allowed in a TYPE definition"); omitting the property entirely (not
    just leaving it unset by convention) makes that structurally
    impossible to emit by accident.

    Printer output mirrors ModuleVarOp's own declaration-line shapes:
        rank=0: ``{type} :: {var_name}``
        rank>0, not pointer: ``{type}, allocatable :: {var_name}(:, ...)``
        rank>0, pointer: ``{type}, pointer :: {var_name}(:, ...) => null()``
        fixed_dim set: ``{type} :: {var_name}({n}) = {init_value}``
    """

    name = "ccpp_utils.ddt_component_decl"

    var_name   = prop_def(StringAttr)
    base_type  = prop_def(StringAttr)
    kind       = opt_prop_def(StringAttr)
    char_len   = opt_prop_def(IntegerAttr)
    ddt_name   = opt_prop_def(StringAttr)
    is_pointer = opt_prop_def(BoolAttr)
    rank       = prop_def(IntegerAttr)
    fixed_dim  = opt_prop_def(IntegerAttr)
    init_value_region = opt_region_def("single_block")   # as ModuleVarOp's

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: str, base_type: str, *, kind: str | None = None,
                 char_len: int | None = None,
                 ddt_name: str | None = None, is_pointer: bool = False,
                 rank: int = 0, fixed_dim: int | None = None, init_value_op=None):
        props: dict = {
            "var_name":  StringAttr(var_name),
            "base_type": StringAttr(base_type),
            "rank":      IntegerAttr.from_int_and_width(rank, 64),
            **_kind_and_char_len_props("DdtComponentDeclOp", base_type, kind, char_len),
        }
        if ddt_name is not None:
            props["ddt_name"] = StringAttr(ddt_name)
        if is_pointer:
            props["is_pointer"] = BoolAttr.from_bool(True)
        if fixed_dim is not None:
            props["fixed_dim"] = IntegerAttr.from_int_and_width(fixed_dim, 64)
        init_region = (
            _single_op_region([init_value_op]) if init_value_op is not None else None
        )
        super().__init__(properties=props, regions=[init_region])


@irdl_op_definition
class DerivedTypeDefOp(IRDLOperation):
    """A Fortran derived-type definition, emitted in the module
    specification part (before CONTAINS, since Fortran forbids a
    ``type :: ... end type`` block inside CONTAINS) -- a Region of
    DdtComponentDeclOp children.

    Emits::

        type[, public][, bind(c)] :: {type_name}
          {component declarations}
        end type {type_name}

    Lives as a child of ConstituentApiOp's own body Region
    (the multi-instance per-instance bundle type is its only user today)
    rather than being printed generically by the main statement dispatch --
    the printer gives it a no-op case there and instead emits it from a
    dedicated pre-scan alongside ModuleVarOp's own module-preamble
    emission, for the same "must come before CONTAINS" reason.
    """

    name = "ccpp_utils.derived_type_def"

    type_name = prop_def(StringAttr)
    is_public = opt_prop_def(UnitAttr)
    bind_c    = opt_prop_def(UnitAttr)   # interoperable with a C struct
    body      = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, type_name: str, component_ops: list, *,
                 is_public: bool = False, bind_c: bool = False):
        props: dict = {"type_name": StringAttr(type_name)}
        if is_public:
            props["is_public"] = UnitAttr()
        if bind_c:
            props["bind_c"] = UnitAttr()
        super().__init__(properties=props, regions=[Region([Block(component_ops)])])


@irdl_op_definition
class ConstituentApiOp(IRDLOperation):
    """Container for the host cap's constituent registration API.

    ``public_names`` — names to export with ``public ::`` in the module preamble.
    ``body``         — single-block Region of the API's ``func.FuncOp`` s
                       (cap_shared.fixed_interface_fn),
                       optionally preceded by one DerivedTypeDefOp (the
                       multi-instance per-instance bundle type, when present --
                       the printer's module-preamble pre-scan looks for it here
                       rather than this op carrying a separate type_defs property).
    """

    name = "ccpp_utils.constituent_api"

    public_names = prop_def(ArrayAttr)          # ArrayAttr[StringAttr]
    body         = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, public_names_list: "list[str]", fn_ops: list):
        super().__init__(
            properties={"public_names": ArrayAttr([StringAttr(n) for n in public_names_list])},
            regions=[Region([Block(fn_ops)])],
        )


@irdl_op_definition
class CppIncludeOp(IRDLOperation):
    """A C/C++ ``#include`` directive.

    Emits::

        #include <{header}>      (default: system/angle-bracket form)
        #include "{header}"      (``local=True``: quoted form)
    """

    name = "ccpp_utils.cpp_include"
    header = prop_def(StringAttr)
    local  = opt_prop_def(BoolAttr)

    def __init__(self, header: str, local: bool = False):
        props: dict = {"header": StringAttr(header)}
        if local:
            props["local"] = BoolAttr.from_bool(True)
        super().__init__(properties=props)


@irdl_op_definition
class ExternCGuardOp(IRDLOperation):
    """Wraps a region in the ``#ifdef __cplusplus`` / ``extern "C"`` guard
    block used by every generated C++-interop header.

    Emits::

        #ifdef __cplusplus
        extern "C" {
        #endif
        {body}
        #ifdef __cplusplus
        }
        #endif

    No properties -- the guard text is fixed. Replaces what were two
    independently hand-duplicated copies of this exact block in
    ``cpp_interop.py`` (``_build_chost_cpp_text``) and a third in
    ``print_cpp_header.py`` (``_emit_cap_header``).
    """

    name = "ccpp_utils.extern_c_guard"
    body = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, body_ops: list):
        super().__init__(regions=[Region([Block(body_ops)])])


@irdl_op_definition
class CFunctionSigOp(IRDLOperation):
    """A C function prototype, or an ``inline`` C++ function definition.

    Emits, when ``body`` is empty (a declaration)::

        {return_type} {fn_name}(
            {param_type}       {param_name},  {param_comment}
            ...
        );

    or, with no params::

        {return_type} {fn_name}(void);

    When ``body`` is non-empty (a definition -- Stage 3's own use, not yet
    exercised by Stage 2)::

        inline {return_type} {fn_name}(...) {
          {body}
        }

    ``param_names``/``param_types``/``param_comments`` are parallel arrays
    (``param_comments`` entries may be empty strings). The types are MLIR
    types -- an element type passed by value, a memref passed by pointer,
    a ``ReadOnlyType``, a ``DerivedType`` -- which ``print_cpp_header.py``'s
    ``cpp_type_name`` spells; ``return_type`` likewise, absent for none.

    ``is_const`` (Stage 3): a trailing ``const`` qualifier, for a member
    function nested inside a ``CppStructDefOp.methods`` region (e.g.
    ``bool ok() const { ... }``). Struct-method printing is a distinct
    code path from this op's own top-level printing (member functions
    never print ``inline`` even when ``is_inline`` is set, and empty
    params print ``()`` not ``(void)``) -- see ``CppStructDefOp``.
    """

    name = "ccpp_utils.c_function_sig"

    fn_name         = prop_def(StringAttr)
    return_type     = opt_prop_def(TypeAttribute)   # absent: no result
    is_inline       = opt_prop_def(BoolAttr)
    is_const        = opt_prop_def(BoolAttr)
    param_names     = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_types     = prop_def(ArrayAttr)   # ArrayAttr[TypeAttribute]
    param_comments  = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    body            = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, fn_name: str, param_names: "list[str]", param_types: list,
        param_comments: "list[str]", body_ops: list,
        return_type=None, is_inline: bool = False, is_const: bool = False,
    ):
        props: dict = {
            "fn_name":        StringAttr(fn_name),
            "param_names":    ArrayAttr([StringAttr(n) for n in param_names]),
            "param_types":    ArrayAttr(list(param_types)),
            "param_comments": ArrayAttr([StringAttr(c) for c in param_comments]),
        }
        if return_type is not None:
            props["return_type"] = return_type
        if is_inline:
            props["is_inline"] = BoolAttr.from_bool(True)
        if is_const:
            props["is_const"] = BoolAttr.from_bool(True)
        super().__init__(properties=props, regions=[Region([Block(body_ops)])])


@irdl_op_definition
class CppFieldDeclOp(IRDLOperation):
    """One member-variable declaration inside a CppStructDefOp.

    Emits::

        {type:<{width}} {field_name}{array_suffix}{ = init_expr};

    where ``width = type_width`` if given, else ``8`` (the pad-plus-
    mandatory-space formula below is byte-identical to Stage 2's own
    original pad-to-9-no-space formula for every string <= 8 chars --
    Stage 2's only 3 actual type strings -- so this change is a pure
    extension, not a Stage-2 behavior change; it also fixes a latent
    bug in that original formula, which silently produced *zero*
    separating space for any type name >= 9 chars, never triggered
    before Stage 3 passes wider type strings).

    ``field_type`` is an MLIR type (see ``CFunctionSigOp``); a
    static-shape memref, e.g. ``memref<129xi8>``, is an inline array
    (``char name[129]``). A default member initializer is an expression op
    (``init_expr_op``, e.g. ``NullPointerExprOp`` or an ``arith``
    constant).
    """

    name = "ccpp_utils.cpp_field_decl"
    field_name   = prop_def(StringAttr)
    field_type   = prop_def(TypeAttribute)
    init_expr_region = opt_region_def("single_block")
    type_width   = opt_prop_def(IntegerAttr)

    traits = traits_def(NoTerminator())

    def __init__(
        self, field_name: str, field_type,
        type_width: "int | None" = None, *, init_expr_op=None,
    ):
        props: dict = {"field_name": StringAttr(field_name), "field_type": field_type}
        init_region = (
            _single_op_region([init_expr_op]) if init_expr_op is not None else None
        )
        if type_width is not None:
            props["type_width"] = IntegerAttr.from_int_and_width(type_width, 32)
        super().__init__(properties=props, regions=[init_region])


@irdl_op_definition
class CppStructDefOp(IRDLOperation):
    """A C/C++ struct definition.

    Emits::

        struct {struct_name} {
          {members}
          {methods, each printed via its own distinct member-function
           form -- never 'inline', '()' not '(void)' for empty params,
           single-line body when it's exactly one statement}

        private:
          {private_members}
        };

    ``is_pod`` (default True) now has real printer effect (Stage 2's own
    docstring noted it previously didn't): ``__init__`` raises if
    ``method_ops``/``private_member_ops`` is non-empty while
    ``is_pod=True``. Stage 2's own use (``CcppConstituentInfo``) stays
    POD (fields only); Stage 3's ``Status``/``State`` pass
    ``is_pod=False`` explicitly.
    """

    name = "ccpp_utils.cpp_struct_def"
    struct_name      = prop_def(StringAttr)
    is_pod           = opt_prop_def(BoolAttr)
    members          = region_def("single_block")
    methods          = region_def("single_block")
    private_members  = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, struct_name: str, member_ops: list, is_pod: bool = True,
        method_ops: "list | None" = None, private_member_ops: "list | None" = None,
    ):
        method_ops = method_ops or []
        private_member_ops = private_member_ops or []
        if is_pod and (method_ops or private_member_ops):
            raise ValueError(
                f"CppStructDefOp({struct_name!r}): method_ops/private_member_ops "
                f"given but is_pod defaulted to True -- pass is_pod=False explicitly "
                f"for a struct with member functions or a private section."
            )
        props: dict = {"struct_name": StringAttr(struct_name)}
        if is_pod:
            props["is_pod"] = BoolAttr.from_bool(True)
        super().__init__(
            properties=props,
            regions=[
                Region([Block(member_ops)]),
                Region([Block(method_ops)]),
                Region([Block(private_member_ops)]),
            ],
        )


@irdl_op_definition
class CppNamespaceOp(IRDLOperation):
    """A C++ namespace block.

    Emits::

        namespace {ns_name} {
        {body}
        } // namespace {ns_name}

    Body children are printed with no added indent, matching the
    generated wrapper's own existing un-indented namespace-body style.
    """

    name = "ccpp_utils.cpp_namespace"
    ns_name = prop_def(StringAttr)
    body    = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, ns_name: str, body_ops: list):
        super().__init__(
            properties={"ns_name": StringAttr(ns_name)},
            regions=[Region([Block(body_ops)])],
        )


@irdl_op_definition
class CppCallStatementOp(IRDLOperation):
    """A column-wrapped ``callee(args...);`` C++ call statement.

    The C++-syntax sibling of ``CallStatementOp`` (Fortran's ``call
    {callee}(args)``): emits ``{callee}(args);``, column-wrapped via the
    shared ``wrap_paren_list`` helper (``print_ftn.py``, generalized with a
    ``cont_marker`` parameter so it no longer hardcodes Fortran's ``" &"``
    continuation) when the single-line form would be too long -- with no
    continuation marker needed in C++.
    """

    name = "ccpp_utils.cpp_call_statement"

    callee    = prop_def(StringAttr)
    call_args_region = var_region_def("single_block")   # expression ops

    traits = traits_def(NoTerminator())

    def __init__(self, callee: str, *, call_arg_ops: list):
        super().__init__(
            properties={"callee": StringAttr(callee)},
            regions=[[_single_op_region([a]) for a in call_arg_ops]],
        )


@irdl_op_definition
class CppBraceInitCallOp(IRDLOperation):
    """A designated-initializer struct-literal call, always returned.

    Emits::

        return {callee}({
            .{field_names[0]}={field_values[0]},
            ...
        });

    Always multi-line, one field per line, unconditionally -- matches the
    generated wrapper's own existing unconditional one-per-line style for
    this idiom (the State-struct convenience overloads); no column-budget
    logic needed here, unlike ``CppCallStatementOp``.
    """

    name = "ccpp_utils.cpp_brace_init_call"

    callee        = prop_def(StringAttr)
    field_names   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr] -- struct member names
    field_values_region = var_region_def("single_block")   # expression ops

    traits = traits_def(NoTerminator())

    def __init__(self, callee: str, field_names: "list[str]", *, field_value_ops: list):
        super().__init__(
            properties={
                "callee":      StringAttr(callee),
                "field_names": ArrayAttr([StringAttr(n) for n in field_names]),
            },
            regions=[[_single_op_region([v]) for v in field_value_ops]],
        )


@irdl_op_definition
class CppConstructorOp(IRDLOperation):
    """A C++ constructor with a member-initializer list, nested inside a
    ``CppStructDefOp``'s ``methods`` region.

    Emits::

        {struct_name}({param_type} {param_name} = {param_default}, ...)
            : {init_member}({init_expr}), ... {}

    (or ``{ ...body... }`` if ``body`` is non-empty -- not exercised by
    today's conversion, harmless future-proofing matching
    ``CFunctionSigOp``'s own empty-vs-non-empty-body convention.)

    No ``struct_name`` property: only ever appears nested inside a
    ``CppStructDefOp.methods`` region, so the containing struct supplies
    the name at print time -- storing it redundantly on the child risks
    the two disagreeing.
    """

    name = "ccpp_utils.cpp_constructor"

    param_names    = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_types    = prop_def(ArrayAttr)   # ArrayAttr[TypeAttribute]
    init_members   = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]
    param_defaults = var_region_def("single_block")   # one expression op per param
    init_exprs     = var_region_def("single_block")   # one expression op per member
    body           = region_def("single_block")

    irdl_options = (AttrSizedRegionSegments(),)
    traits = traits_def(NoTerminator())

    def __init__(
        self, param_names: "list[str]", param_types: list,
        param_default_ops: list, init_members: "list[str]",
        init_expr_ops: list, body_ops: list,
    ):
        super().__init__(
            properties={
                "param_names":    ArrayAttr([StringAttr(n) for n in param_names]),
                "param_types":    ArrayAttr(list(param_types)),
                "init_members":   ArrayAttr([StringAttr(m) for m in init_members]),
            },
            regions=[
                [_single_op_region([d]) for d in param_default_ops],
                [_single_op_region([e]) for e in init_expr_ops],
                Region([Block(body_ops)]),
            ],
        )


@irdl_op_definition
class CHostCapOp(IRDLOperation):
    """Carries the auto-generated BIND(C) cap for a C++ host model.

    ``ftn_body`` holds the complete Fortran module as structured IR,
    printed by ``print_ftn.py``. ``cpp_body`` holds the complete C header
    as structured IR, and ``wrapper_body`` holds the complete C++
    ergonomics wrapper (.hpp) as structured IR, both printed by
    ``print_cpp_header.py``.

    ``mod_name`` is the base name used for the module and header file, e.g.
    ``"Kessler_ccpp_chost_cap"``.
    """

    name = "ccpp_utils.chost_cap"

    ftn_body     = region_def("single_block")   # complete Fortran module, as ops
    cpp_body     = region_def("single_block")   # complete C++ header, as ops
    wrapper_body = region_def("single_block")   # complete C++ wrapper, as ops
    mod_name     = prop_def(StringAttr)   # base name, e.g. "Kessler_ccpp_chost_cap"

    traits = traits_def(NoTerminator())

    def __init__(self, ftn_body_ops: list, cpp_body_ops: list, mod_name: str,
                 wrapper_body_ops: list = ()):
        super().__init__(
            properties={
                "mod_name": StringAttr(mod_name),
            },
            regions=[
                Region([Block(ftn_body_ops)]),
                Region([Block(cpp_body_ops)]),
                Region([Block(list(wrapper_body_ops))]),
            ],
        )


@irdl_op_definition
class CapVarRefOp(IRDLOperation):
    """Reference to a module-level variable declared in the same cap module.

    Like HostVarRefOp but no USE statement is generated — the variable is
    in the current module.  The printer registers the reference as the
    result's text so that downstream ops emit it correctly. The reference is
    the variable's identifier (``var_name``) or an expression op
    (``target_op``, see _name_or_target): a multi-instance component, a
    whole-array section, or a count such as ``size(lc_all_constituents)``.
    """

    name = "ccpp_utils.cap_var_ref"

    var_name = opt_prop_def(StringAttr)
    target = opt_region_def("single_block")   # see _name_or_target
    res = result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, var_name: "str | None", result_type, *, target_op=None):
        props, target = _name_or_target("CapVarRefOp", "var_name", var_name, target_op)
        super().__init__(properties=props, regions=[target], result_types=[result_type])


@irdl_op_definition
class KindCastOp(IRDLOperation):
    """Convert a real variable to a different Fortran KIND for a scheme call.

    Represents the statement pair::

        allocate(result, mold=source)            ! arrays only
        result = real(source, kind=target_kind)

    The *result* SSA value carries the target-kind type and is declared as a
    local allocatable in the enclosing suite-cap function.  For scalars the
    allocate is omitted.

    In the write direction (from scheme back to host) use ``KindWriteBackOp``.
    """

    name = "ccpp_utils.kind_cast"

    source      = operand_def()
    target_kind = prop_def(StringAttr)

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        target_kind: "str | StringAttr",
        result_type,
    ):
        target_kind = _coerce_str_attr(target_kind)
        super().__init__(
            operands=[source],
            properties={"target_kind": target_kind},
            result_types=[result_type],
        )


### lang-neutral-expr-ir Stage 1b: new expression ops ########################
#
# None of these has an MLIR-standard analog (arith/math already cover
# arithmetic/logical/comparison/numeric+boolean literals directly -- see
# print_ftn.py's print_expr). Each composes through the same recursive
# print_expr/expr_to_cpp_str dispatch as arith ops and StrCmpOp/TrimOp do
# today; a region child is any op that dispatch already knows how to
# print, so no further "wrapper" op is needed anywhere below.


@irdl_op_definition
class StringLiteralExprOp(IRDLOperation):
    """A compile-time string literal used as a sub-expression.

    Emits ``'{text}'`` (Fortran) or ``"{text}"`` (C++) -- pure print-time
    text embedding, a different, simpler problem than the existing
    llvm.GlobalOp mechanism (which exists for when *generated code
    itself* needs a real runtime string constant with a real address --
    already solved, not what this is for).
    """

    name = "ccpp_utils.string_literal_expr"
    text = prop_def(StringAttr)

    def __init__(self, text: str):
        super().__init__(properties={"text": StringAttr(text)})


@irdl_op_definition
class StringConcatExprOp(IRDLOperation):
    """Fortran string concatenation: ``piece0 // piece1 // ...``
    (C++: an ``operator+`` chain).

    ``pieces`` holds two or more children, each any print_expr/
    expr_to_cpp_str-dispatchable string-valued expression op
    (StringLiteralExprOp, VarRefExprOp, CallExprOp, or a real compiled
    string value such as a CCPPTrimOp/CCPPStrCmpOp result) -- composes
    directly through the existing recursion. No dedicated "piece" wrapper
    op is needed: a region already holds real ops, not bare SSA values,
    so an op with a real result (like CCPPTrimOp) is simply one of the
    children directly.
    """

    name = "ccpp_utils.string_concat_expr"
    # One region per piece (not one shared region holding N sibling
    # ops): a piece can itself be a freshly-built arith/math sub-tree
    # (e.g. a CallExprOp wrapping comparison ops), whose own floating
    # operand dependencies must be flattened into ITS OWN region via
    # _single_op_region -- sharing one region/block across all pieces
    # would make the printer unable to tell a flattened dependency op
    # apart from a genuine sibling piece.
    pieces = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, piece_ops: "list"):
        piece_ops = list(piece_ops)
        if len(piece_ops) < 2:
            raise ValueError("StringConcatExprOp needs at least 2 pieces")
        super().__init__(regions=[[_single_op_region([p]) for p in piece_ops]])


@irdl_op_definition
class VarRefExprOp(IRDLOperation):
    """Reference to a cap-gen-synthesized local/variable name that was
    never a real SSA value.

    Emits the bare name verbatim. Covers e.g. constituent_cap.py's
    locals, which are plain names rather than SSA values, as a structured
    expression leaf.

    ``result_type`` is optional (``res``, like ``CapVarRefOp``/
    ``HostVarRefOp``, carries "type set at construction to match callee
    expectation"): pass it when this reference needs to compose as a
    real operand of an ``arith``/``math`` op (e.g. ``state%errflg`` on
    one side of an ``arith.CmpiOp``) -- omit it when this op is only
    ever a region child printed by recursion, never an operand.
    """

    name = "ccpp_utils.var_ref_expr"
    var_name = prop_def(StringAttr)
    res = opt_result_def()

    def __init__(self, var_name: str, result_type=None):
        if not _IDENTIFIER.match(var_name):
            raise ValueError(f"VarRefExprOp: {var_name!r} is not an identifier")
        super().__init__(
            properties={"var_name": StringAttr(var_name)},
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class AddressOfExprOp(IRDLOperation):
    """The address of a variable, for a C function taking a pointer to it
    (C++ ``&x``)."""

    name = "ccpp_utils.address_of_expr"
    operand = region_def("single_block")
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, operand_op, result_type=None):
        super().__init__(
            regions=[_single_op_region([operand_op])],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class NullPointerExprOp(IRDLOperation):
    """The null pointer (C++ ``nullptr``, Fortran ``null()``)."""

    name = "ccpp_utils.null_pointer_expr"
    res = opt_result_def()

    def __init__(self, result_type=None):
        super().__init__(result_types=[result_type] if result_type is not None else [None])


@irdl_op_definition
class StructLiteralExprOp(IRDLOperation):
    """A value of a struct type given field by field, in declaration order
    (C++ ``{a, b}``)."""

    name = "ccpp_utils.struct_literal_expr"
    fields = var_region_def("single_block")
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, field_ops: list, result_type=None):
        super().__init__(
            regions=[[_single_op_region([f]) for f in field_ops]],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class ConditionalExprOp(IRDLOperation):
    """``then`` if ``cond`` holds, else ``otherwise`` (C++ ``c ? a : b``,
    Fortran ``merge(a, b, c)``)."""

    name = "ccpp_utils.conditional_expr"
    cond = region_def("single_block")
    then = region_def("single_block")
    otherwise = region_def("single_block")
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, cond_op, then_op, otherwise_op, result_type=None):
        super().__init__(
            regions=[_single_op_region([cond_op]), _single_op_region([then_op]),
                     _single_op_region([otherwise_op])],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class CastExprOp(IRDLOperation):
    """``value`` converted to ``result_type`` (e.g. ``index``, an array
    extent: C++ ``static_cast<std::size_t>(x)``)."""

    name = "ccpp_utils.cast_expr"
    value = region_def("single_block")
    res = result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, value_op, result_type):
        super().__init__(
            regions=[_single_op_region([value_op])], result_types=[result_type],
        )


@irdl_op_definition
class LocalVarOp(IRDLOperation):
    """A local variable declaration with an optional initial value.

    One of: ``init_op`` (an expression), ``zero_init`` (every element
    zero), or ``size_op`` (an owned array of that many elements). For a
    static-shape memref type the variable is an inline array. ``type_width``
    and ``name_width`` pad the type and name columns, for aligned blocks of
    declarations.
    """

    name = "ccpp_utils.local_var"
    var_name   = prop_def(StringAttr)
    var_type   = prop_def(TypeAttribute)
    zero_init  = opt_prop_def(BoolAttr)
    type_width = opt_prop_def(IntegerAttr)
    name_width = opt_prop_def(IntegerAttr)
    init = opt_region_def("single_block")
    size = opt_region_def("single_block")

    irdl_options = (AttrSizedRegionSegments(),)
    traits = traits_def(NoTerminator())

    def __init__(self, var_name: str, var_type, *, init_op=None, zero_init: bool = False,
                 size_op=None, type_width: "int | None" = None,
                 name_width: "int | None" = None):
        if not _IDENTIFIER.match(var_name):
            raise ValueError(f"LocalVarOp: {var_name!r} is not an identifier")
        if (init_op is not None) + zero_init + (size_op is not None) > 1:
            raise ValueError("LocalVarOp: pass at most one of init_op, zero_init, size_op")
        props: dict = {"var_name": StringAttr(var_name), "var_type": var_type}
        if zero_init:
            props["zero_init"] = BoolAttr.from_bool(True)
        if type_width is not None:
            props["type_width"] = IntegerAttr.from_int_and_width(type_width, 32)
        if name_width is not None:
            props["name_width"] = IntegerAttr.from_int_and_width(name_width, 32)
        super().__init__(properties=props, regions=[
            _single_op_region([init_op]) if init_op is not None else None,
            _single_op_region([size_op]) if size_op is not None else None,
        ])


@irdl_op_definition
class CommentOp(IRDLOperation):
    """Comment lines in generated source; each entry is one line's text."""

    name = "ccpp_utils.comment"
    lines = prop_def(ArrayAttr)   # ArrayAttr[StringAttr]

    def __init__(self, lines: "list[str]"):
        super().__init__(properties={"lines": ArrayAttr([StringAttr(t) for t in lines])})


@irdl_op_definition
class BlankLineOp(IRDLOperation):
    """An empty line in generated source, separating sections."""

    name = "ccpp_utils.blank_line"

    def __init__(self):
        super().__init__()


@irdl_op_definition
class MetadataLiteralExprOp(IRDLOperation):
    """A literal copied verbatim from the generator's input: the metadata
    (e.g. a scheme argument's ``default_value``, which the CCPP metadata
    format defines as a Fortran literal) or the suite definition (a Python
    suite's keyword-argument override, e.g. ``hello_scheme(ncol=5)``). The
    generator never writes this text itself."""

    name = "ccpp_utils.metadata_literal_expr"
    text = prop_def(StringAttr)
    res = opt_result_def()

    def __init__(self, text: str, result_type=None):
        super().__init__(
            properties={"text": StringAttr(text)},
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class MethodCallExprOp(IRDLOperation):
    """A type-bound function call as an expression: ``{base}%{method}(args)``
    (e.g. ``cam_constituents_obj%field_data_ptr()``). DdtMethodCallOp is the
    statement form (``call base%method(...)``)."""

    name = "ccpp_utils.method_call_expr"
    base = region_def("single_block")
    method = prop_def(StringAttr)
    args = var_region_def("single_block")
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, base_op, method: str, arg_ops: "list" = (), result_type=None):
        if not _IDENTIFIER.match(method):
            raise ValueError(f"MethodCallExprOp: method {method!r} is not an identifier")
        super().__init__(
            properties={"method": StringAttr(method)},
            regions=[_single_op_region([base_op]), [_single_op_region([a]) for a in arg_ops]],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class ValueExprOp(IRDLOperation):
    """An existing SSA value (a block argument, a HostVarRefOp result, an
    array section, ...) as an expression leaf: the printer renders it as
    it renders that value anywhere else, so its spelling is never decided
    here. VarRefExprOp is the counterpart for a name that is not an SSA
    value."""

    name = "ccpp_utils.value_expr"
    value = operand_def()
    res = opt_result_def()

    def __init__(self, value, result_type=None):
        """result_type, as for VarRefExprOp: pass it when this leaf is an
        operand of an arith op (e.g. a logical in an .and.)."""
        super().__init__(
            operands=[value],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class ExprTextLiteralOp(IRDLOperation):
    """A string literal holding an expression's printed spelling, between
    ``prefix`` and ``suffix`` message text -- e.g. a diagnostic label that
    names the variable it reports on. The printer spells ``expr`` as it
    would anywhere else, then quotes the whole as one literal.
    """

    name = "ccpp_utils.expr_text_literal"
    prefix = prop_def(StringAttr)
    suffix = prop_def(StringAttr)
    expr = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, expr_op, prefix: str = "", suffix: str = ""):
        super().__init__(
            properties={"prefix": StringAttr(prefix), "suffix": StringAttr(suffix)},
            regions=[_single_op_region([expr_op])],
        )


@irdl_op_definition
class MemberAccessExprOp(IRDLOperation):
    """Derived-type/struct member access.

    Emits ``{base}%{member}`` (Fortran, always) or ``{base}.{member}`` /
    ``{base}->{member}`` (C++, selected by ``via``).

    ``base`` holds exactly one child expression op -- needs to support
    nesting, since real call sites chain, e.g.
    ``lc_instances(instance)%cam_constituents_obj``.

    ``result_type`` is optional, same "type set at construction to match
    callee expectation" convention as ``VarRefExprOp``'s own -- see its
    docstring; pass it when this access needs to compose as a real
    operand of an ``arith``/``math`` op.
    """

    name = "ccpp_utils.member_access_expr"
    base = region_def("single_block")
    member = prop_def(StringAttr)
    via = opt_prop_def(StringAttr)  # "value"|"pointer"; default "value"
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(
        self, base_op, member: str, via: "str | None" = None, result_type=None
    ):
        if not _IDENTIFIER.match(member):
            raise ValueError(f"MemberAccessExprOp: member {member!r} is not an identifier")
        props: dict = {"member": StringAttr(member)}
        if via is not None:
            if via not in ("value", "pointer"):
                raise ValueError(
                    f"MemberAccessExprOp: via must be 'value' or 'pointer', got {via!r}"
                )
            props["via"] = StringAttr(via)
        super().__init__(
            properties=props,
            regions=[_single_op_region([base_op])],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class IndexExprOp(IRDLOperation):
    """Array indexing.

    Emits ``{base}(i0, i1, ...)`` (Fortran) or ``{base}[i0][i1]...``
    (C++). ``base`` holds exactly one child expr; ``indices`` holds one
    child per subscript -- each either a plain expression op or a
    SliceExprOp (Fortran range syntax only; C++ slicing is unsupported,
    see SliceExprOp).

    ``result_type`` is optional, same "type set at construction to match
    callee expectation" convention as ``VarRefExprOp``'s own -- see its
    docstring; pass it when an indexed element needs to compose as a
    real operand of an ``arith``/``math`` op (e.g. ``arr(i) + 1``).
    """

    name = "ccpp_utils.index_expr"
    base = region_def("single_block")
    # One region per subscript (see StringConcatExprOp.pieces's own
    # comment for why: a subscript can itself be a freshly-built
    # arith/math sub-tree whose floating dependencies need their own
    # region, not a shared block mixed in with sibling subscripts).
    indices = var_region_def("single_block")
    res = opt_result_def()

    traits = traits_def(NoTerminator())

    def __init__(self, base_op, index_ops: "list", result_type=None):
        index_ops = list(index_ops)
        if not index_ops:
            raise ValueError("IndexExprOp needs at least one index")
        super().__init__(
            regions=[
                _single_op_region([base_op]),
                [_single_op_region([i]) for i in index_ops],
            ],
            result_types=[result_type] if result_type is not None else [None],
        )


@irdl_op_definition
class SliceExprOp(IRDLOperation):
    """Fortran array-section range: ``{lower}:{upper}[:{stride}]`` (any of
    the three may be omitted, e.g. a bare ``:`` when all are absent).

    Appears only as a child of IndexExprOp.indices. Unsupported for a
    C++-targeted print -- no equivalent syntax, so the printer raises.
    """

    name = "ccpp_utils.slice_expr"
    lower = opt_region_def("single_block")
    upper = opt_region_def("single_block")
    stride = opt_region_def("single_block")

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(self, lower_op=None, upper_op=None, stride_op=None):
        super().__init__(
            regions=[
                _single_op_region([lower_op]) if lower_op is not None else None,
                _single_op_region([upper_op]) if upper_op is not None else None,
                _single_op_region([stride_op]) if stride_op is not None else None,
            ]
        )


@irdl_op_definition
class KeywordArgExprOp(IRDLOperation):
    """One keyword argument of a CallExprOp: ``{arg_name}={value}``.

    Fortran only -- C++ has no named-argument syntax for free functions;
    CallExprOp raises at print time if any KeywordArgExprOp children are
    present on a C++-targeted print.
    """

    name = "ccpp_utils.keyword_arg_expr"
    arg_name = prop_def(StringAttr)
    value = region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, arg_name: str, value_op):
        super().__init__(
            properties={"arg_name": StringAttr(arg_name)},
            regions=[_single_op_region([value_op])],
        )


@irdl_op_definition
class CallExprOp(IRDLOperation):
    """Expression-level call with positional and/or keyword arguments.

    Emits ``{callee}(args, kwargs)`` (Fortran) or ``{callee}(args)``
    (C++ -- raises if ``kwargs`` is non-empty, since C++ free functions
    have no named-argument syntax).

    Distinct from the *statement*-level DdtMethodCallOp/CallStatementOp:
    this is a sub-expression (e.g. a function-call RHS, ``trim(x)`` as
    one piece of a StringConcatExprOp), not a call statement in its own
    right.

    ``result_type`` is optional, same "type set at construction to match
    callee expectation" convention as ``VarRefExprOp``'s own -- see its
    docstring; pass it when a numeric call's result needs to compose as
    a real operand of an ``arith``/``math`` op (e.g. ``len(x) + 1``).
    """

    name = "ccpp_utils.call_expr"
    callee = prop_def(StringAttr)
    # One region per positional/keyword arg (see StringConcatExprOp.pieces's
    # own comment for why): an arg can itself be a freshly-built
    # arith/math sub-tree (e.g. CallExprOp("any", [a_cmpi_tree])), whose
    # floating operand dependencies need their own region, not a shared
    # block mixed in with sibling args.
    args = var_region_def("single_block")  # positional argument expr ops
    kwargs = var_region_def("single_block")  # KeywordArgExprOp children
    res = opt_result_def()

    irdl_options = [AttrSizedRegionSegments()]
    traits = traits_def(NoTerminator())

    def __init__(
        self, callee: str, arg_ops: "list | None" = None, kwarg_ops: "list | None" = None,
        result_type=None,
    ):
        super().__init__(
            properties={"callee": StringAttr(callee)},
            result_types=[result_type] if result_type is not None else [None],
            regions=[
                [_single_op_region([a]) for a in (arg_ops or [])],
                [_single_op_region([k]) for k in (kwarg_ops or [])],
            ],
        )


@irdl_op_definition
class ArrayConstructorExprOp(IRDLOperation):
    """Fortran array-constructor literal: ``[ {elem_type} :: e0, e1, ... ]``
    (``elem_type`` omitted when not given). ``elem_type`` is a type (e.g.
    ``memref<32xi8>`` for ``character(len=32)``), spelled by the printer.
    C++: ``{ e0, e1, ... }`` brace-init-list -- imperfect but reasonable;
    no real C++ call site needs this yet.
    """

    name = "ccpp_utils.array_constructor_expr"
    elem_type = opt_prop_def(TypeAttribute)
    # One region per element (see StringConcatExprOp.pieces's own
    # comment for why).
    elements = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, element_ops: "list", elem_type=None):
        props: dict = {}
        if elem_type is not None:
            props["elem_type"] = elem_type
        super().__init__(
            properties=props,
            regions=[[_single_op_region([e]) for e in element_ops]],
        )


### end lang-neutral-expr-ir Stage 1b new expression ops #####################


_UNIT_OPERATIONS = ("add", "sub", "mul")
_REAL_LITERAL = re.compile(r"^[0-9]+\.[0-9]*([Ee][-+]?[0-9]+)?$")


def _unit_conversion_props(op_name: str, operation, factor) -> dict:
    """Properties of a unit conversion by `operation` ("add", "sub" or "mul")
    with `factor`, an unsigned real literal kept as written (e.g. "1.0E6");
    none when both are None (no conversion)."""
    if operation is None and factor is None:
        return {}
    if operation not in _UNIT_OPERATIONS:
        raise ValueError(f"{op_name}: operation must be one of {_UNIT_OPERATIONS}, "
                         f"got {operation!r}")
    if factor is None or not _REAL_LITERAL.match(factor):
        raise ValueError(f"{op_name}: factor {factor!r} is not an unsigned real literal")
    return {"operation": StringAttr(operation), "factor": StringAttr(factor)}


@irdl_op_definition
class UnitConvertOp(IRDLOperation):
    """Allocate a local temp and optionally apply a host→scheme unit conversion.

    With a conversion (``intent(in)`` / ``intent(inout)``), e.g. operation
    "mul" and factor "0.01"::

        allocate(result(size(source,1), ...))   ! arrays only
        result = source * 0.01_kind_phys

    Without one (``intent(out)``: the scheme does not read the value), only
    the allocation is emitted::

        allocate(result(size(source,1), ...))   ! arrays only

    The host's source array is never modified.  The result SSA value is
    declared as a local (allocatable for arrays, plain for scalars) in the
    enclosing function.  Use ``UnitWriteBackOp`` to write back after the
    scheme call for ``intent(inout)`` / ``intent(out)`` arguments.
    """

    name = "ccpp_utils.unit_convert"

    source    = operand_def()
    operation = opt_prop_def(StringAttr)   # "add" | "sub" | "mul"; unset: no conversion
    factor    = opt_prop_def(StringAttr)   # unsigned real literal, e.g. "273.15"
    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        result_type,
        operation: "str | None" = None,
        factor: "str | None" = None,
    ):
        super().__init__(
            operands=[source],
            properties=_unit_conversion_props("UnitConvertOp", operation, factor),
            result_types=[result_type],
        )


@irdl_op_definition
class UnitWriteBackOp(IRDLOperation):
    """Write a unit-converted value back to the original host variable.

    Represents, e.g. for operation "sub" and factor "273.15"::

        original_dest = conv_result - 273.15_kind_phys
        deallocate(conv_result)                       ! arrays only

    Emitted after the scheme call for ``intent(inout)`` / ``intent(out)``
    arguments that required a unit conversion.
    """

    name = "ccpp_utils.unit_write_back"

    conv_result   = operand_def()
    original_dest = operand_def()
    operation     = prop_def(StringAttr)   # "add" | "sub" | "mul"
    factor        = prop_def(StringAttr)   # unsigned real literal

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        operation: str,
        factor: str,
    ):
        super().__init__(
            operands=[conv_result, original_dest],
            properties=_unit_conversion_props("UnitWriteBackOp", operation, factor),
        )


@irdl_op_definition
class KindWriteBackOp(IRDLOperation):
    """Write a kind-converted value back to the original host variable.

    Represents::

        original_dest = real(conv_result, kind=original_kind)
        deallocate(conv_result)                  ! arrays only

    Emitted after the scheme call for ``intent(inout)`` / ``intent(out)``
    arguments that required a kind conversion.
    """

    name = "ccpp_utils.kind_write_back"

    conv_result   = operand_def()   # temp in scheme kind
    original_dest = operand_def()   # block arg in host kind

    original_kind = prop_def(StringAttr)   # host kind name

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        original_kind: "str | StringAttr",
    ):
        original_kind = _coerce_str_attr(original_kind)
        super().__init__(
            operands=[conv_result, original_dest],
            properties={"original_kind": original_kind},
        )


@irdl_op_definition
class VerticalFlipOp(IRDLOperation):
    """Allocate a local temp and reverse an array section along the vertical
    (layer) dimension, for a scheme call whose own top_at_one convention
    differs from the shared value's current convention.

    Represents::

        allocate(result(size(source,1), ...))
        result = source(:, ..., size(source, vertical_dim):1:-1, ..., :)

    ``vertical_dim`` is the 1-based Fortran dimension index (matching the
    argument's own dimensions/dim_names) to reverse; every other dimension
    copies through unchanged (``:``). The host's source array is never
    modified. Use ``VerticalFlipWriteBackOp`` to flip back after the scheme
    call for ``intent(inout)`` / ``intent(out)`` arguments.
    """

    name = "ccpp_utils.vertical_flip"

    source       = operand_def()
    vertical_dim = prop_def(IntegerAttr)   # 1-based Fortran dimension index

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        vertical_dim: "int | IntegerAttr",
        result_type,
    ):
        vertical_dim = _coerce_int_attr(vertical_dim)
        super().__init__(
            operands=[source],
            properties={"vertical_dim": vertical_dim},
            result_types=[result_type],
        )


@irdl_op_definition
class VerticalFlipWriteBackOp(IRDLOperation):
    """Write a vertically-flipped value back to the original host variable.

    Represents::

        original_dest = conv_result(:, ..., size(conv_result, vertical_dim):1:-1, ..., :)
        deallocate(conv_result)

    Reversing a reversed section restores the original order, so the
    write-back applies the identical reversed-section expression to the
    *source* side of the assignment (``conv_result``) and assigns into the
    plain, unreversed destination.

    Emitted after the scheme call for ``intent(inout)`` / ``intent(out)``
    arguments that required a vertical flip.
    """

    name = "ccpp_utils.vertical_flip_write_back"

    conv_result   = operand_def()   # temp with the scheme's own vertical convention
    original_dest = operand_def()   # block arg with the host's convention

    vertical_dim = prop_def(IntegerAttr)   # same index as the matching VerticalFlipOp

    def __init__(
        self,
        conv_result:   "SSAValue | IRDLOperation",
        original_dest: "SSAValue | IRDLOperation",
        vertical_dim:  "int | IntegerAttr",
    ):
        vertical_dim = _coerce_int_attr(vertical_dim)
        super().__init__(
            operands=[conv_result, original_dest],
            properties={"vertical_dim": vertical_dim},
        )


@irdl_op_definition
class RowMajorConvertOp(IRDLOperation):
    """Transpose a row-major host array to column-major order for Fortran scheme consumption.

    Emits::

        allocate(result(dim0, dim1, ...))
        result = reshape(source, [dim0, dim1, ...], order=[rank, ..., 1])

    ``dim_exprs`` holds the target (column-major) dimension sizes as Fortran
    expressions matching the scheme's dimension order.  Use
    ``RowMajorWriteBackOp`` to transpose back after the scheme call for
    ``intent(inout)`` / ``intent(out)`` arguments.
    """

    name = "ccpp_utils.row_major_convert"

    source    = operand_def()
    dim_exprs = prop_def(ArrayAttr)   # Fortran expressions, e.g. ["ncol", "nz"]

    res = result_def()

    def __init__(
        self,
        source: "SSAValue | IRDLOperation",
        dim_exprs: "list[str] | ArrayAttr",
        result_type,
    ):
        dim_exprs = _coerce_str_list_attr(dim_exprs)
        super().__init__(
            operands=[source],
            properties={"dim_exprs": dim_exprs},
            result_types=[result_type],
        )


@irdl_op_definition
class RowMajorWriteBackOp(IRDLOperation):
    """Write a column-major local array back to the row-major host variable.

    Emits::

        host_var = reshape(local_val, [dim_{rank-1}, ..., dim0], order=[rank, ..., 1])
        deallocate(local_val)

    ``dim_exprs`` must match the ``dim_exprs`` from the corresponding
    ``RowMajorConvertOp`` (column-major dimension order).  The write-back
    reverses the dimension list and applies the same ORDER so the result
    matches the host's row-major layout.
    """

    name = "ccpp_utils.row_major_write_back"

    local_val = operand_def()
    host_var  = operand_def()
    dim_exprs = prop_def(ArrayAttr)   # same order as RowMajorConvertOp (column-major)

    def __init__(
        self,
        local_val: "SSAValue | IRDLOperation",
        host_var:  "SSAValue | IRDLOperation",
        dim_exprs: "list[str] | ArrayAttr",
    ):
        dim_exprs = _coerce_str_list_attr(dim_exprs)
        super().__init__(
            operands=[local_val, host_var],
            properties={"dim_exprs": dim_exprs},
        )


@irdl_op_definition
class CamDirectCallOp(IRDLOperation):
    """Emit a direct Fortran subroutine call, on one line.

    Prints as::

        call {callee}(arg0, arg1, ...)

    Unlike ``func.CallOp``, the arguments are expression ops (``arg_ops``)
    rather than SSA values — suitable for calls where the arguments are
    module-scope variables accessed by name (e.g. ``errmsg``, ``errcode``).
    """

    name = "ccpp_utils.cam_direct_call"

    callee   = prop_def(StringAttr)
    arg_exprs = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, callee: str, arg_ops: list):
        super().__init__(
            properties={"callee": StringAttr(callee)},
            regions=[[_single_op_region([a]) for a in arg_ops]],
        )


@irdl_op_definition
class CallStatementOp(IRDLOperation):
    """A column-wrapped ``call {callee}(args...)`` statement.

    Emits::

        call {callee}(a, b, c)

    or, when the single-line form would exceed the printer's column
    budget, Fortran-continuation-wraps the argument list (shared
    ``wrap_paren_list`` helper in print_ftn.py) -- replaces cpp_interop.py's own
    independently hand-rolled ``_emit_call`` wrap loop.

    Distinct from CamDirectCallOp (no wrapping at all -- retrofitting it
    risked destabilizing its own already-proven single-line output format
    across its existing callers).

    The arguments are expression ops (arg_ops: VarRefExprOp,
    StringLiteralExprOp, CallExprOp, ...), which the printer renders.
    """

    name = "ccpp_utils.call_statement"

    callee    = prop_def(StringAttr)
    arg_exprs = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(self, callee: str, *, arg_ops):
        super().__init__(
            properties={"callee": StringAttr(callee)},
            regions=[[_single_op_region([o]) for o in arg_ops]],
        )


@irdl_op_definition
class ClearErrStateOp(IRDLOperation):
    """Reset the error state.

    Prints as::

        {errcode_var} = 0
        {errmsg_var} = ''

    E.g. at the top of each constituent-API subroutine, or in a CAM
    timestep-init/final wrapper with no per-group dispatcher (no scheme
    registered a timestep-init/final hook), which must still zero out the
    error state before returning.
    """

    name = "ccpp_utils.clear_err_state"

    errcode_var = prop_def(StringAttr)
    errmsg_var  = prop_def(StringAttr)

    def __init__(self, errcode_var: str, errmsg_var: str):
        super().__init__(properties={
            "errcode_var": StringAttr(errcode_var),
            "errmsg_var":  StringAttr(errmsg_var),
        })


@irdl_op_definition
class CamQminPreambleOp(IRDLOperation):
    """Emit the constituent-minimum (lc_qmin) preamble in cam_ccpp_physics_run.

    Emitted when the run dispatcher takes ``ccpp_constituent_minimum_values``
    as a block argument (i.e. at least one run-phase scheme reads qmin).
    Prints as::

        integer :: lc_n, lc_i
        real(kind=kind_phys), allocatable :: lc_qmin(:)
        if (allocated(lc_const_props)) then
          lc_n = size(lc_const_props)
        else
          lc_n = 0
        end if
        allocate(lc_qmin(lc_n))
        do lc_i = 1, lc_n
          call lc_const_props(lc_i)%minimum(lc_qmin(lc_i), {errcode_var}, {errmsg_var})
          if ({errcode_var} /= 0) then
            deallocate(lc_qmin)
            return
          end if
        end do

    The declarations (``integer :: lc_n``, etc.) appear inline in the
    subroutine body — valid in Fortran 2003+ and accepted by gfortran/nvhpc.
    ``kind_phys`` is imported from ``ccpp_kinds`` at module scope and is
    therefore available without a redundant subroutine-scope USE.
    """

    name = "ccpp_utils.cam_qmin_preamble"

    errcode_var = prop_def(StringAttr)
    errmsg_var  = prop_def(StringAttr)

    def __init__(self, errcode_var: str, errmsg_var: str):
        super().__init__(properties={
            "errcode_var": StringAttr(errcode_var),
            "errmsg_var":  StringAttr(errmsg_var),
        })


@irdl_op_definition
class CamQminPostambleOp(IRDLOperation):
    """Emit ``deallocate(lc_qmin)`` after the run dispatcher call.

    Paired with ``CamQminPreambleOp`` to clean up the constituent-minimum
    temporary array after ``ccpp_physics_run`` has used it.
    """

    name = "ccpp_utils.cam_qmin_postamble"

    def __init__(self):
        super().__init__()


@irdl_op_definition
class ErrorPropagateOp(IRDLOperation):
    """Emit an early-return guard on an integer error-code variable.

    Prints as::

        if ({errcode_var} /= 0) return
    """

    name = "ccpp_utils.error_propagate"
    errcode_var = prop_def(StringAttr)

    def __init__(self, errcode_var: str):
        super().__init__(properties={"errcode_var": StringAttr(errcode_var)})


@irdl_op_definition
class ReturnStmtOp(IRDLOperation):
    """A return statement in generated source (not func.ReturnOp, which
    ends a generated function and carries its outputs).

    Prints as ``return``, or with condition_op (an i1 expression)::

        if ({condition}) return

    value_op (C++ only so far) is the returned value: ``return {value};``.
    """

    name = "ccpp_utils.return_stmt"
    condition = opt_region_def("single_block")
    value = opt_region_def("single_block")

    irdl_options = (AttrSizedRegionSegments(),)
    traits = traits_def(NoTerminator())

    def __init__(self, condition_op=None, *, value_op=None):
        cond_region = (
            _single_op_region([condition_op]) if condition_op is not None else None
        )
        value_region = _single_op_region([value_op]) if value_op is not None else None
        super().__init__(regions=[cond_region, value_region])


@irdl_op_definition
class ErrorExitOp(IRDLOperation):
    """Set the error state and return.

    Prints as::

        {errflg_var} = 1
        {errmsg_var} = '{errmsg_text}'      (or = <message_op>)
        return

    errflg_var is omitted when the flag is already set, e.g. by an
    allocate's stat=. The message is a static literal (errmsg_text) or a
    string expression (message_op, e.g. a StringConcatExprOp); exactly one
    of the two must be given. ErrorGuardOp is this op's body behind an
    `if (.not. condition)`.
    """

    name = "ccpp_utils.error_exit"
    errflg_var = opt_prop_def(StringAttr)
    errmsg_var = prop_def(StringAttr)
    errmsg_text = opt_prop_def(StringAttr)
    message = opt_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self, errmsg_text: "str | None" = None, *, message_op=None,
        errflg_var: "str | None" = None, errmsg_var: str = "errmsg",
    ):
        if (errmsg_text is None) == (message_op is None):
            raise ValueError("ErrorExitOp: pass exactly one of errmsg_text or message_op")
        props: dict = {"errmsg_var": StringAttr(errmsg_var)}
        if errflg_var is not None:
            props["errflg_var"] = StringAttr(errflg_var)
        if errmsg_text is not None:
            props["errmsg_text"] = StringAttr(errmsg_text)
        message = _single_op_region([message_op]) if message_op is not None else None
        super().__init__(properties=props, regions=[message])


@irdl_op_definition
class CamSuiteDispatchOp(IRDLOperation):
    """Emit the if/else suite-group dispatch chain in a CAM lifecycle wrapper.

    Represents the per-group dispatch pattern::

        if (trim(suite_name) == 'suite1') then
          call {dispatcher_fn}(arg1, 'group1', arg3, ...)
          if ({errcode_var} /= 0) return
          call {dispatcher_fn}(arg1, 'group2', arg3, ...)
          if ({errcode_var} /= 0) return
        else if (trim(suite_name) == 'suite2') then
          ...
        else
          write({errmsg_var}, '(3a)') '{wrapper_fn}: no suite named ', &
              trim(suite_name), ' found'
          {errcode_var} = 1
        end if

    Properties
    ----------
    dispatcher_fn : StringAttr
        Name of the internal dispatcher function (e.g. ``ccpp_physics_init``).
    wrapper_fn : StringAttr
        Name of the outer wrapper subroutine; used in the else-branch error message.
    errcode_var : StringAttr
        Fortran variable name for the integer error code (e.g. ``lc_errcode``).
    errmsg_var : StringAttr
        Fortran variable name for the error message string (e.g. ``lc_errmsg``).
    suite_groups : ArrayAttr[ArrayAttr[StringAttr]]
        Outer array has one inner ArrayAttr per suite.  In each inner array,
        element [0] is the suite name and elements [1:] are the group names
        that have a generated dispatcher for this lifecycle phase.
    suite_part_index : IntegerAttr
        Position of the suite-part argument in the dispatcher call: the
        group name literal, for each call in the chain.
    arg_exprs : regions
        The other dispatcher call arguments, in order, as expression ops.
    """

    name = "ccpp_utils.cam_suite_dispatch"

    dispatcher_fn      = prop_def(StringAttr)
    wrapper_fn         = prop_def(StringAttr)
    errcode_var        = prop_def(StringAttr)
    errmsg_var         = prop_def(StringAttr)
    suite_groups       = prop_def(ArrayAttr)   # ArrayAttr[ArrayAttr[StringAttr]]
    suite_part_index   = prop_def(IntegerAttr)
    arg_exprs          = var_region_def("single_block")

    traits = traits_def(NoTerminator())

    def __init__(
        self,
        dispatcher_fn: str,
        wrapper_fn: str,
        errcode_var: str,
        errmsg_var: str,
        suite_groups: "list[tuple[str, list[str]]]",
        arg_ops: list,
        suite_part_index: int,
    ):
        """
        Parameters
        ----------
        suite_groups
            List of (suite_name, [group1, group2, ...]) tuples.
        arg_ops
            The dispatcher call arguments other than the suite part.
        suite_part_index
            Where the suite part (the quoted group name) goes among them.
        """
        groups_attr = ArrayAttr([
            ArrayAttr([StringAttr(sn)] + [StringAttr(g) for g in groups])
            for sn, groups in suite_groups
        ])
        super().__init__(
            properties={
                "dispatcher_fn":    StringAttr(dispatcher_fn),
                "wrapper_fn":       StringAttr(wrapper_fn),
                "errcode_var":      StringAttr(errcode_var),
                "errmsg_var":       StringAttr(errmsg_var),
                "suite_groups":     groups_attr,
                "suite_part_index": IntegerAttr.from_int_and_width(suite_part_index, 32),
            },
            regions=[[_single_op_region([a]) for a in arg_ops]],
        )


@irdl_op_definition
class CamSuiteSchemeListOp(IRDLOperation):
    """Emit the suite-keyed scheme-list assignment block in ccpp_physics_suite_schemes.

    Represents the body of the ``ccpp_physics_suite_schemes`` subroutine::

        if (trim(suite_name) == 'suite1') then
          allocate(scheme_list(N))
          scheme_list(1) = 'scheme_a'
          scheme_list(2) = 'scheme_b'
          ...
        else if (trim(suite_name) == 'suite2') then
          ...
        else
          write({errmsg_var}, '(3a)') 'No suite named ', trim(suite_name), ' found'
          {errflg_var} = 1
        end if

    Properties
    ----------
    suite_schemes : ArrayAttr[ArrayAttr[StringAttr]]
        Outer array has one inner ArrayAttr per suite.  In each inner array,
        element [0] is the suite name and elements [1:] are the scheme names
        in first-occurrence order (duplicates already removed by the caller).
    errmsg_var : StringAttr
        Name of the character variable to write the error message into.
    errflg_var : StringAttr
        Name of the integer variable to set to 1 on error.
    """

    name = "ccpp_utils.cam_suite_scheme_list"

    suite_schemes = prop_def(ArrayAttr)   # ArrayAttr[ArrayAttr[StringAttr]]
    errmsg_var    = prop_def(StringAttr)
    errflg_var    = prop_def(StringAttr)

    def __init__(self, suite_schemes: "list[tuple[str, list[str]]]",
                 errmsg_var: str = "errmsg", errflg_var: str = "errflg"):
        """
        Parameters
        ----------
        suite_schemes
            List of (suite_name, [scheme1, scheme2, ...]) tuples.
        errmsg_var
            Fortran variable name for the error message output.
        errflg_var
            Fortran variable name for the error flag output.
        """
        attr = ArrayAttr([
            ArrayAttr([StringAttr(sn)] + [StringAttr(s) for s in schemes])
            for sn, schemes in suite_schemes
        ])
        super().__init__(properties={
            "suite_schemes": attr,
            "errmsg_var":    StringAttr(errmsg_var),
            "errflg_var":    StringAttr(errflg_var),
        })


CCPPUtils = Dialect(
    "ccpp_utils",
    [
        StrCmpOp,
        TrimOp,
        HostVarRefOp,
        ClearStringOp,
        WriteErrMsgOp,
        WriteStmtOp,
        PrintStmtOp,
        KindDefOp,
        SetStringOp,
        KeywordCallOp,
        AccDataBeginOp,
        AccDataEndOp,
        AccUpdateSelfOp,
        AccUpdateDeviceOp,
        AccEnterDataOp,
        AccExitDataOp,
        AccParallelOp,
        OmpTargetDataBeginOp,
        OmpTargetDataEndOp,
        OmpTargetUpdateFromOp,
        OmpTargetUpdateToOp,
        OmpTargetEnterDataOp,
        OmpTargetExitDataOp,
        ModuleVarOp,
        LazyAllocOp,
        SafeDeallocOp,
        RankReducingSliceOp,
        PromotionLoopOp,
        SubcycleLoopOp,
        PresentCheckOp,
        ActiveCheckOp,
        NullifyPointerOp,
        AllocateOp,
        ZeroFillOp,
        PointerAssignOp,
        AssignOp,
        DdtMethodCallOp,
        ErrorGuardOp,
        DoLoopOp,
        ScopedBlockOp,
        CToFortranStringCopyOp,
        FortranToCStringCopyOp,
        ConstituentApiOp,
        DdtComponentDeclOp,
        DerivedTypeDefOp,
        CppIncludeOp,
        ExternCGuardOp,
        CFunctionSigOp,
        CppFieldDeclOp,
        CppStructDefOp,
        CppNamespaceOp,
        CppCallStatementOp,
        CppBraceInitCallOp,
        CppConstructorOp,
        CHostCapOp,
        CapVarRefOp,
        KindCastOp,
        KindWriteBackOp,
        StringLiteralExprOp,
        StringConcatExprOp,
        VarRefExprOp,
        ValueExprOp,
        ExprTextLiteralOp,
        MetadataLiteralExprOp,
        MethodCallExprOp,
        AddressOfExprOp,
        NullPointerExprOp,
        StructLiteralExprOp,
        ConditionalExprOp,
        CastExprOp,
        LocalVarOp,
        CommentOp,
        BlankLineOp,
        MemberAccessExprOp,
        IndexExprOp,
        SliceExprOp,
        KeywordArgExprOp,
        CallExprOp,
        ArrayConstructorExprOp,
        UnitConvertOp,
        UnitWriteBackOp,
        RowMajorConvertOp,
        RowMajorWriteBackOp,
        VerticalFlipOp,
        VerticalFlipWriteBackOp,
        CamDirectCallOp,
        CallStatementOp,
        ClearErrStateOp,
        CamQminPreambleOp,
        CamQminPostambleOp,
        ErrorPropagateOp,
        ReturnStmtOp,
        ErrorExitOp,
        CamSuiteDispatchOp,
        CamSuiteSchemeListOp,
    ],
    [RealKindType, DerivedType, ReadOnlyType, OwnedArrayType, OwnedStringType],
)
