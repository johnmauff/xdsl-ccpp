from xdsl.dialects.builtin import (
    ArrayAttr,
    DictionaryAttr,
    IntegerAttr,
    IntegerType,
    MemRefType,
    StringAttr,
    i1,
)
from xdsl.dialects.llvm import LLVMArrayType
from xdsl.ir import (
    Dialect,
    ParametrizedAttribute,
    SSAValue,
    TypeAttribute,
    VerifyException,
)
from xdsl.irdl import (
    AttrSizedOperandSegments,
    IRDLOperation,
    irdl_attr_definition,
    irdl_op_definition,
    operand_def,
    opt_operand_def,
    opt_prop_def,
    param_def,
    prop_def,
    result_def,
    var_operand_def,
    var_result_def,
)


@irdl_attr_definition
class RealKindType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran real with a named kind qualifier.

    Used for Fortran code generation only — carries the kind name through
    the IR so the printer can emit 'real(kind=kind_name)' declarations.
    """

    name = "ccpp_utils.real_kind"
    kind_name: StringAttr = param_def()

    def __init__(self, kind_name: str | StringAttr):
        if isinstance(kind_name, str):
            kind_name = StringAttr(kind_name)
        super().__init__(kind_name)


@irdl_attr_definition
class DerivedType(ParametrizedAttribute, TypeAttribute):
    """MLIR type representing a Fortran derived data type (DDT).

    Used for Fortran code generation only — carries the DDT name through
    the IR so the printer can emit 'type(type_name)' declarations.
    """

    name = "ccpp_utils.derived_type"
    type_name: StringAttr = param_def()

    def __init__(self, type_name: str | StringAttr):
        if isinstance(type_name, str):
            type_name = StringAttr(type_name)
        super().__init__(type_name)


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
        if isinstance(literal, str):
            literal = StringAttr(literal)
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
    `var_name` as the variable name for the result so that downstream ops
    (e.g. call arguments) print the correct host variable name.

    A corresponding llvm.GlobalOp stub (with a 'module' attribute) is placed
    at the enclosing module level to drive 'use module, only: var' generation.
    """

    name = "ccpp_utils.host_var_ref"

    var_name = prop_def(StringAttr)
    module_name = prop_def(StringAttr)
    res = result_def()  # type set at construction to match callee expectation

    def __init__(
        self, var_name: str | StringAttr, module_name: str | StringAttr, result_type
    ):
        if isinstance(var_name, str):
            var_name = StringAttr(var_name)
        if isinstance(module_name, str):
            module_name = StringAttr(module_name)
        super().__init__(
            properties={"var_name": var_name, "module_name": module_name},
            result_types=[result_type],
        )


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
        if isinstance(prefix, str):
            prefix = StringAttr(prefix)
        if isinstance(suffix, str):
            suffix = StringAttr(suffix)
        super().__init__(
            operands=[dest, var],
            properties={"prefix": prefix, "suffix": suffix},
        )


@irdl_op_definition
class ArraySectionOp(IRDLOperation):
    """Represent a Fortran array section: source(lower0:upper0, lower1:upper1, ...).

    Used purely for Fortran code generation — no transformation semantics.
    The result type matches the source type.  The Fortran printer resolves the
    result to 'source_name(lower0:upper0, lower1:upper1)' so that downstream
    call ops emit the correct Fortran array-section notation.

    lowers and uppers must have the same length (one pair per dimension).
    """

    name = "ccpp_utils.array_section"

    source = operand_def(MemRefType)
    lowers = var_operand_def(MemRefType | IntegerType)
    uppers = var_operand_def(MemRefType | IntegerType)
    res = result_def(MemRefType)

    irdl_options = [AttrSizedOperandSegments()]

    def __init__(self, source, lowers, uppers):
        source_val = SSAValue.get(source)
        super().__init__(
            operands=[source, list(lowers), list(uppers)],
            result_types=[source_val.type],
        )


@irdl_op_definition
class KindDefOp(IRDLOperation):
    """Declare a named Fortran kind parameter in the @ccpp_kinds module.

    Represents one ``integer, parameter :: kind_name = kind_value`` line in the
    generated ``ccpp_kinds`` Fortran module.  Both properties are strings:
    ``kind_name`` is the Fortran identifier (e.g. ``kind_phys``) and
    ``kind_value`` is its definition (e.g. ``REAL64`` from iso_fortran_env).
    """

    name = "ccpp_utils.kind_def"

    kind_name = prop_def(StringAttr)
    kind_value = prop_def(StringAttr)

    def __init__(self, kind_name: str | StringAttr, kind_value: str | StringAttr):
        if isinstance(kind_name, str):
            kind_name = StringAttr(kind_name)
        if isinstance(kind_value, str):
            kind_value = StringAttr(kind_value)
        super().__init__(properties={"kind_name": kind_name, "kind_value": kind_value})


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
        overrides:      Compile-time literal overrides: {arg_name → value_str}.

    The printer deduplicates inout arguments (which appear in both operands
    and results) using a seen-names set.
    """

    name = "ccpp_utils.kw_call"

    callee = prop_def(StringAttr)
    operand_names = prop_def(ArrayAttr)
    result_names = prop_def(ArrayAttr)
    overrides = prop_def(DictionaryAttr)

    args = var_operand_def()
    res = var_result_def()

    def __init__(
        self,
        callee: str | StringAttr,
        operand_names: ArrayAttr,
        result_names: ArrayAttr,
        overrides: DictionaryAttr,
        args: list,
        out_types: list,
    ):
        if isinstance(callee, str):
            callee = StringAttr(callee)
        super().__init__(
            operands=[args],
            properties={
                "callee": callee,
                "operand_names": operand_names,
                "result_names": result_names,
                "overrides": overrides,
            },
            result_types=[out_types],
        )

@irdl_op_definition 
class AccDataBeginOp(IRDLOperation):
    """Emit !$acc data copyin(...) copyout(...) directive."""
    name = "ccpp_utils.acc_data_begin"
    copyin  = opt_prop_def(ArrayAttr)   # variables to copy host → device
    copyout = opt_prop_def(ArrayAttr)   # variables to copy device → host

    def __init__(self, copyin=None, copyout=None):
        props = {}
        if copyin:
            props["copyin"]  = ArrayAttr([StringAttr(v) for v in copyin])
        if copyout:
            props["copyout"] = ArrayAttr([StringAttr(v) for v in copyout])
        super().__init__(properties=props)

@irdl_op_definition
class AccDataEndOp(IRDLOperation):
    """Emit !$acc end data directive."""
    name = "ccpp_utils.acc_data_end"

    def __init__(self):
        super().__init__()

CCPPUtils = Dialect(
    "ccpp_utils",
    [
        StrCmpOp,
        TrimOp,
        HostVarRefOp,
        WriteErrMsgOp,
        ArraySectionOp,
        KindDefOp,
        SetStringOp,
        KeywordCallOp,
        AccDataBeginOp,
	AccDataEndOp,
    ],
    [RealKindType, DerivedType],
)
