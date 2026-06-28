from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import IO, cast

from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    DenseIntOrFPElementsAttr,
    Float32Type,
    Float64Type,
    FloatAttr,
    FunctionType,
    IntAttr,
    IntegerAttr,
    IntegerType,
    MemRefType,
    ModuleOp,
    StringAttr,
)
from xdsl.ir import Attribute, Block, Operation, OpResult, Region, SSAValue
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import ArraySectionOp as CCPPArraySectionOp
from xdsl_ccpp.dialects.ccpp_utils import DerivedType as CCPPDerivedType
from xdsl_ccpp.dialects.ccpp_utils import HostVarRefOp as CCPPHostVarRefOp
from xdsl_ccpp.dialects.ccpp_utils import KeywordCallOp as CCPPKeywordCallOp
from xdsl_ccpp.dialects.ccpp_utils import KindCastOp as CCPPKindCastOp
from xdsl_ccpp.dialects.ccpp_utils import KindDefOp as CCPPKindDefOp
from xdsl_ccpp.dialects.ccpp_utils import KindWriteBackOp as CCPPKindWriteBackOp
from xdsl_ccpp.dialects.ccpp_utils import UnitConvertOp as CCPPUnitConvertOp
from xdsl_ccpp.dialects.ccpp_utils import UnitWriteBackOp as CCPPUnitWriteBackOp
from xdsl_ccpp.dialects.ccpp_utils import RealKindType as CCPPRealKindType
from xdsl_ccpp.dialects.ccpp_utils import SetStringOp as CCPPSetStringOp
from xdsl_ccpp.dialects.ccpp_utils import StrCmpOp as CCPPStrCmpOp
from xdsl_ccpp.dialects.ccpp_utils import TrimOp as CCPPTrimOp
from xdsl_ccpp.dialects.ccpp_utils import ClearStringOp as CCPPClearStringOp
from xdsl_ccpp.dialects.ccpp_utils import WriteErrMsgOp as CCPPWriteErrMsgOp
from xdsl_ccpp.dialects.ccpp_utils import AccDataBeginOp as CCPPAccDataBeginOp
from xdsl_ccpp.dialects.ccpp_utils import AccDataEndOp as CCPPAccDataEndOp
from xdsl_ccpp.dialects.ccpp_utils import AccUpdateSelfOp as CCPPAccUpdateSelfOp
from xdsl_ccpp.dialects.ccpp_utils import AccUpdateDeviceOp as CCPPAccUpdateDeviceOp
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetDataBeginOp as CCPPOmpTargetDataBeginOp
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetDataEndOp    as CCPPOmpTargetDataEndOp
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetUpdateFromOp as CCPPOmpTargetUpdateFromOp
from xdsl_ccpp.dialects.ccpp_utils import OmpTargetUpdateToOp   as CCPPOmpTargetUpdateToOp
from xdsl_ccpp.dialects.ccpp_utils import ModuleVarOp           as CCPPModuleVarOp
from xdsl_ccpp.dialects.ccpp_utils import LazyAllocOp          as CCPPLazyAllocOp
from xdsl_ccpp.dialects.ccpp_utils import SafeDeallocOp        as CCPPSafeDeallocOp
from xdsl_ccpp.dialects.ccpp_utils import RankReducingSliceOp   as CCPPRankReducingSliceOp
from xdsl_ccpp.dialects.ccpp_utils import PresentCheckOp         as CCPPPresentCheckOp
from xdsl_ccpp.dialects.ccpp_utils import PromotionLoopOp        as CCPPPromotionLoopOp
from xdsl_ccpp.dialects.ccpp_utils import SubcycleLoopOp         as CCPPSubcycleLoopOp
from xdsl_ccpp.dialects.ccpp_utils import SuiteVariablesOp      as CCPPSuiteVariablesOp
from xdsl_ccpp.dialects.ccpp_utils import ConstituentApiOp      as CCPPConstituentApiOp
from xdsl_ccpp.dialects.ccpp_utils import CapVarRefOp           as CCPPCapVarRefOp


_MAX_LINE_LEN = 99


@dataclass
class ftnPrintContext:
    """Stateful context for printing MLIR IR as Fortran source text.

    Each context owns an indentation prefix and a mapping from SSA values to
    Fortran variable names.  Nested structures (subroutines, if-blocks, etc.)
    are handled by creating a child context via `descend`, which inherits the
    current variable map and adds one level of indentation.
    """

    _INDEX = "i32"
    _INDENT = "  "
    output: IO[str]

    # Current indentation string prepended to every line
    _prefix: str = field(default="")

    # Map from SSA value to its Fortran variable name
    variables: dict[SSAValue, str] = field(default_factory=dict[SSAValue, str])

    # Counter used to generate unique fallback variable names
    _counter: int = field(default=0)

    # Buffer accumulating the current line being built via partial print() calls
    _line_buf: str = field(default="")

    # Maps arith op names to their Fortran infix operator strings
    _binops: dict[str, str] = field(default_factory=dict[str, str])

    # Maps comparison op names to a predicate-string → Fortran-operator dict
    _cmp_ops: dict[str, dict[str, str | None]] = field(
        default_factory=dict[str, dict[str, str | None]]
    )

    # Tracks how many times each allocatable char array has been stored to.
    # Key: id of the SSA value; value: 1-based index of the next store.
    # Used to emit allocate(arr(N)) once and suites(i) = ... with correct indices.
    _allocatable_store_indices: dict = field(default_factory=dict)

    def register_binops(self):
        """Populate the binary-operator and comparison-operator lookup tables.

        Must be called once before printing begins.  Kept separate from
        __init__ so that child contexts created by `descend` can share the
        already-populated dicts without re-building them.
        """
        self._binops.update(
            {
                arith.AddfOp.name: "+",
                arith.AddiOp.name: "+",
                arith.MulfOp.name: "*",
                arith.MuliOp.name: "*",
                arith.DivfOp.name: "/",
                arith.DivSIOp.name: "/",
                arith.DivUIOp.name: "/",
                arith.SubfOp.name: "-",
                arith.SubiOp.name: "-",
                arith.RemSIOp.name: "%",
                arith.RemUIOp.name: "%",
                arith.ShLIOp.name: "<<",
                arith.AndIOp.name: "&",
                arith.OrIOp.name: "|",
            }
        )
        self._cmp_ops.update(
            {
                arith.CmpiOp.name: {
                    "eq": ".eq.",
                    "ne": ".ne.",
                    "slt": ".lt.",
                    "sle": ".le.",
                    "sgt": ".gt.",
                    "sge": ".ge.",
                    "ult": ".lt.",
                    "ule": ".le.",
                    "ugt": ".gt.",
                    "uge": ".ge.",
                },
                arith.CmpfOp.name: {
                    "false": None,
                    "oeq": "==",
                    "ogt": ">",
                    "oge": ">=",
                    "olt": "<",
                    "ole": "<=",
                    "one": "!=",
                    "ord": None,
                    "ueq": "==",
                    "ugt": ">",
                    "uge": ">=",
                    "ult": "<",
                    "ule": "<=",
                    "une": "!=",
                    "uno": None,
                    "true": None,
                },
            }
        )

    def _get_variable_name_for(self, val: SSAValue, hint: str | None = None) -> str:
        """Return the Fortran variable name assigned to an SSA value.

        If the value has already been assigned a name it is returned directly.
        Otherwise a new name is chosen, preferring the value's name_hint (or
        the caller-supplied hint), and falling back to a numbered prefix when
        the hint is absent or already taken.
        """
        if val in self.variables:
            return self.variables[val]

        taken_names = set(self.variables.values())

        if hint is None:
            hint = val.name_hint

        if hint is not None and hint not in taken_names:
            name = hint
        else:
            # Generate a unique name using a numeric suffix
            prefix = "v" if val.name_hint is None else val.name_hint

            name = f"{prefix}{self._counter}"
            self._counter += 1

            while name in taken_names:
                name = f"{prefix}{self._counter}"
                self._counter += 1

        self.variables[val] = name
        return name

    @staticmethod
    def _is_allocatable_char(type_attr: Attribute) -> bool:
        """Return True if type_attr is memref<memref<?xi8>> (allocatable character array)."""
        match type_attr:
            case MemRefType(
                element_type=MemRefType(element_type=IntegerType(width=IntAttr(data=8)))
            ):
                return True
            case _:
                return False


    def mlir_type_to_ftn_type(self, type_attr: Attribute) -> str:
        """Convert an MLIR type attribute to its Fortran type declaration string.

        Supported types:
          - f32 / f64       → real(kind=4) / real(kind=8)
          - i1              → logical
          - i8              → character
          - i32             → integer
          - memref<T>       → the Fortran type of T (scalar, no dimensions)
          - memref<NxT>     → character(len=N) for character, T(N) otherwise
        """
        match type_attr:
            case CCPPDerivedType() as dt:
                return f"type({dt.type_name.data})"
            case CCPPRealKindType() as rkt:
                return f"real(kind={rkt.kind_name.data})"
            case Float32Type():
                return "real(kind=4)"
            case Float64Type():
                return "real(kind=8)"
            case IntegerType(width=IntAttr(1)):
                return "logical"
            case IntegerType(width=IntAttr(8)):
                return "character"
            case IntegerType():
                assert cast(IntegerType, type_attr).width.data == 32
                return "integer"
            case MemRefType(element_type=IntegerType(width=IntAttr(data=8)), shape=shape):
                # Character memref: the last dimension encodes the string length;
                # preceding dimensions (if any) are array dimensions.
                # e.g. memref<?xi8>   → character(len=*)  (scalar string)
                #      memref<32xi8>  → character(len=32) (scalar fixed-len)
                #      memref<?x?xi8> → character(len=*)  (1D array of strings)
                if not shape:
                    return "character"
                last_dim = list(shape)[-1]
                len_str = "*" if last_dim.data == DYNAMIC_INDEX else str(last_dim.data)
                return f"character(len={len_str})"
            case MemRefType(element_type=Attribute() as elem_t, shape=shape):
                if any(dim.data == DYNAMIC_INDEX for dim in shape):
                    # Dynamic-dimension array: return only the base type string.
                    # The caller uses _ftn_dim_suffix to append '(:, :)' etc. to
                    # the variable name in the declaration.
                    return self.mlir_type_to_ftn_type(elem_t)
                shape_str = ", ".join(str(s.data) for s in shape)
                type_str = self.mlir_type_to_ftn_type(elem_t)
                if not shape_str:
                    # Zero-dimensional memref — treat as a plain scalar
                    return type_str
                elif type_str == "character":
                    # Character length is expressed with len= rather than dimensions
                    return f"{type_str}(len={shape_str})"
                else:
                    return f"{type_str}({shape_str})"

    def _elem_kind_name(self, type_attr: Attribute) -> str | None:
        """Return the Fortran kind name for the element of a real memref, or None."""
        match type_attr:
            case MemRefType(element_type=CCPPRealKindType() as rk):
                return rk.kind_name.data
            case CCPPRealKindType() as rk:
                return rk.kind_name.data
            case _:
                return None

    @staticmethod
    def _suffix_kind_in_expr(expr: str, kind: str | None) -> str:
        """Append _{kind} to the numeric literal at the end of a unit-conv expression.

        Converts e.g. ``"+ 273.15"`` with kind ``"kind_phys"`` →
        ``"+ 273.15_kind_phys"`` so Fortran uses the correct precision for
        the constant instead of defaulting to the default-real kind (REAL32).
        """
        if not expr or kind is None:
            return expr
        # expression is "<op> <number>", e.g. "+ 273.15" or "* 100.0"
        parts = expr.rsplit(None, 1)
        if len(parts) == 2:
            return f"{parts[0]} {parts[1]}_{kind}"
        return expr

    def _ftn_dim_suffix(self, type_attr: Attribute) -> str:
        """Return the Fortran assumed-shape array suffix for a memref type.

        For a memref with N dynamic dimensions this returns ``"(:, :, ...)"``
        (N colons), which is appended to the variable name in a declaration to
        produce e.g. ``real(kind=8), intent(inout) :: temp_level(:, :)``.

        Returns an empty string for scalar types and statically-sized memrefs
        (such as ``character(len=512)``).
        """
        if self._is_allocatable_char(type_attr):
            return "(:)"
        match type_attr:
            case MemRefType(element_type=IntegerType(width=IntAttr(data=8)), shape=shape):
                # Character memref: last dim = string length, preceding = array dims.
                # Only the array dims (all but last) produce a '(:, ...)' suffix.
                n_array_dims = len(shape) - 1
                if n_array_dims <= 0:
                    return ""
                return "(" + ", ".join(":" for _ in range(n_array_dims)) + ")"
            case MemRefType(shape=shape) if any(
                dim.data == DYNAMIC_INDEX for dim in shape
            ):
                # One ':' per dynamic dimension
                return "(" + ", ".join(":" for _ in shape) + ")"
            case _:
                return ""

    def attribute_value_to_str(self, attr: Attribute) -> str:
        """Convert a value-carrying attribute to a Fortran literal string.

        Handles integer, float, string, and dense element attributes.
        Returns a diagnostic placeholder for unrecognised attribute kinds.
        """
        match attr:
            case IntAttr():
                return str(cast(IntAttr[int], attr).data)
            case IntegerAttr(value=val, type=IntegerType(width=IntAttr(data=1))):
                # i1 values are printed as Fortran logical literals
                return str(bool(val.data)).lower()
            case IntegerAttr(value=val):
                return str(val.data)
            case FloatAttr(value=val) if val.data == 0:
                return "0.0"
            case FloatAttr(value=val):
                return str(val.data)
            case StringAttr() as s:
                return f'"{s.data}"'
            case DenseIntOrFPElementsAttr():
                return f"{self.mlir_type_to_ftn_type(attr.get_type())} {{ {', '.join(self.attribute_value_to_str(a) for a in attr.iter_attrs())} }}"  # noqa: E501
            case _:
                return f"<!unknown value {attr}>"

    def _print_or_promote_to_inline_expr(
        self, var: OpResult, value_expr: str, brackets: bool = False
    ):
        """Print value_expr directly as an inline expression (no newline)."""
        self.print(f"{value_expr}", end="", use_prefix=False)

    def _value_to_expr_str(self, val: SSAValue) -> str:
        """Return the Fortran expression string for an SSA value without printing.

        Checks the variable map first, then falls back to reading the literal
        value for arith.ConstantOp results, and finally generates a fresh name.
        """
        if val in self.variables:
            return self.variables[val]
        if isa(val.owner, arith.ConstantOp):
            return self.attribute_value_to_str(val.owner.value)
        return self._get_variable_name_for(val)

    def find_ret_ssa_idx(self, ret_op, ssa):
        """Return the index of ssa in ret_op's argument list, or None."""
        for idx, arg in enumerate(ret_op.arguments):
            if arg == ssa:
                return idx
        return None

    def print_expr(self, op: Operation):
        """Recursively print op as an inline Fortran expression (no newline).

        Only operations that can appear as sub-expressions are handled here.
        Statement-level operations are handled by print_op instead.
        """
        match op:
            case arith.ConstantOp(value=v, result=r):
                # Emit the literal value of the constant
                self._print_or_promote_to_inline_expr(r, self.attribute_value_to_str(v))
            case memref.LoadOp(memref=arr):
                # A load from a memref is represented by the variable name itself
                self.print(self._get_variable_name_for(arr), end="", use_prefix=False)
            case arith.CmpiOp(predicate=v, lhs=l, rhs=r):
                # Emit lhs <op> rhs using the Fortran comparison operator
                str_pred = arith.CMPI_COMPARISON_OPERATIONS[v.value.data]
                self.print_expr(l.owner)
                self.print(
                    f" {self._cmp_ops[op.name][str_pred]} ", end="", use_prefix=False
                )
                self.print_expr(r.owner)
            case arith.XOrIOp():
                # XOrI(x, 1_i1) is a logical NOT; detect which operand is the constant
                l, r = op.lhs, op.rhs
                if isa(r.owner, arith.ConstantOp):
                    self.print(".NOT. (", end="", use_prefix=False)
                    self.print_expr(l.owner)
                    self.print(")", end="", use_prefix=False)
                elif isa(l.owner, arith.ConstantOp):
                    self.print(".NOT. (", end="", use_prefix=False)
                    self.print_expr(r.owner)
                    self.print(")", end="", use_prefix=False)
                else:
                    # General XOR — emit as logical inequality
                    self.print_expr(l.owner)
                    self.print(" .neqv. ", end="", use_prefix=False)
                    self.print_expr(r.owner)
            case CCPPTrimOp():
                lhs_name = self._get_variable_name_for(op.lhs)
                self.print(f"trim({lhs_name})", end="", use_prefix=False)
            case CCPPStrCmpOp():
                if op.literal is not None:
                    self.print_expr(op.lhs.owner)
                    self.print(f" .eq. '{op.literal.data}'", end="", use_prefix=False)
                else:
                    lhs_name = self._get_variable_name_for(op.lhs)
                    rhs_name = self._get_variable_name_for(op.rhs)
                    self.print(f"{lhs_name} .eq. {rhs_name}", end="", use_prefix=False)
            case arith.AddiOp():
                self.print_expr(op.lhs.owner)
                self.print(" + ", end="", use_prefix=False)
                self.print_expr(op.rhs.owner)
            case arith.SubiOp():
                self.print_expr(op.lhs.owner)
                self.print(" - ", end="", use_prefix=False)
                self.print_expr(op.rhs.owner)
            case _:
                raise AssertionError(f"Unhandled op in print_expr: {type(op)}")

    def print_op(self, op: Operation):
        """Dispatch an MLIR operation to the appropriate Fortran printer.

        Operations that produce values but emit no Fortran statement (e.g.
        address-of, load) register names in the variables dict and return
        silently.  Operations that have no Fortran equivalent (e.g. alloca,
        global declarations, yield) are skipped with a pass.
        """
        match op:
            case builtin.ModuleOp(sym_name=name, body=bdy):
                self._print_module(name, bdy)
            case memref.AllocaOp():
                pass  # Variable registration is handled up-front in _print_fn
            case llvm.GlobalOp():
                pass  # Module-level globals are declared in _print_module preamble
            case llvm.AddressOfOp():
                name = op.global_name.root_reference.data
                if "ccpp_instance_ref" in op.attributes:
                    instance_var = op.attributes["ccpp_instance_ref"].data
                    name = f"{name}({instance_var}%ccpp_instance)"
                self.variables[op.result] = name
            case llvm.LoadOp():
                # Propagate the pointer's name to the loaded value
                self.variables[op.dereferenced_value] = self._get_variable_name_for(
                    op.ptr
                )
            case llvm.StoreOp():
                if isa(op.ptr.type, MemRefType):
                    # Storing a loaded string value into a memref<?xi8> buffer:
                    # suppress output here — the Fortran assignment is emitted by
                    # the memref.StoreOp that places the buffer into the allocatable.
                    pass
                else:
                    # Emit a Fortran assignment from the source value to the destination
                    dst_name = self._get_variable_name_for(op.ptr)
                    src_name = self._get_variable_name_for(op.value)
                    self.print(f"{dst_name} = {src_name}")
            case func.FuncOp(sym_name=name, body=bdy, function_type=ftyp):
                # Skip external declarations; only print subroutine definitions
                if not op.is_declaration:
                    self._print_fn(name, bdy, ftyp)
            case func.CallOp(callee=tgt, arguments=args, res=results):
                self._print_call(tgt, args, results)
            case CCPPKeywordCallOp():
                self._print_kw_call(op)
            case scf.IfOp(
                cond=conditional, true_region=true_bdy, false_region=false_bdy
            ):
                self._print_if(conditional, true_bdy, false_bdy)
            case memref.AllocOp():
                pass  # Heap allocations are emitted via the StoreOp that uses the result
            case CCPPKindDefOp():
                pass  # Kind definitions are declared in _print_module preamble
            case CCPPTrimOp():
                pass  # Used only as a sub-expression; printed inline by print_expr
            case CCPPSetStringOp():
                # Register the source global name as the variable name for dest
                # so that the memref.StoreOp into the allocatable can find it.
                src_name = self._get_variable_name_for(op.src)
                self.variables[op.dest] = src_name
            case memref.StoreOp(value=val, memref=arr, indices=idxs):
                if self._is_allocatable_char(arr.type) and isa(
                    val.owner, memref.AllocOp
                ):
                    # Storing a memref<?xi8> (string buffer) into memref<memref<?xi8>>
                    # (the allocatable out arg).  On the first store emit
                    # allocate(arr(N)) where N is the total number of such stores in
                    # this block; then emit arr(i) = string_src for each store.
                    arr_name = self._get_variable_name_for(arr)
                    string_src = self.variables.get(val)
                    key = id(arr)
                    if key not in self._allocatable_store_indices:
                        total = sum(
                            1
                            for sibling in op.parent.ops
                            if isa(sibling, memref.StoreOp)
                            and sibling.memref is arr
                            and isa(sibling.value.owner, memref.AllocOp)
                        )
                        self._allocatable_store_indices[key] = (1, total)
                        self.print(f"allocate({arr_name}({total}))")
                    idx, total = self._allocatable_store_indices[key]
                    self._allocatable_store_indices[key] = (idx + 1, total)
                    if string_src is not None:
                        self.print(f"{arr_name}({idx}) = {string_src}")
                else:
                    arr_name = self._get_variable_name_for(arr)
                    idx_args = ", ".join(map(self._get_variable_name_for, idxs))
                    if len(idx_args) > 0:
                        self.print(f"{arr_name}[{idx_args}] = ", end="")
                    else:
                        self.print(f"{arr_name} = ", end="")
                    self.print_expr(val.owner)
                    self.print("")
            case CCPPCapVarRefOp():
                # Register the cap module variable name — no Fortran code emitted
                self.variables[op.res] = op.var_name.data
            case CCPPHostVarRefOp():
                # Register the host variable name for the result — no Fortran emitted.
                # When member_name is set the reference is var_name%member_name (DDT).
                member = op.attributes.get("member_name")
                ref_name = (
                    f"{op.var_name.data}%{member.data}"
                    if member is not None
                    else op.var_name.data
                )
                self.variables[op.res] = ref_name
            case CCPPClearStringOp():
                dest_name = self._get_variable_name_for(op.dest)
                self.print(f"{dest_name} = ''")
            case CCPPWriteErrMsgOp():
                dest_name = self._get_variable_name_for(op.dest)
                self.print(f"write({dest_name}, '(3a)') \"{op.prefix.data}\", ", end="")
                self.print_expr(op.var.owner)
                self.print(f', "{op.suffix.data}"', use_prefix=False)
            case CCPPArraySectionOp():
                # Register the full Fortran array-section expression as the
                # result's variable name so call-site printing emits it inline.
                source_name = self._value_to_expr_str(op.source)
                parts = []
                for lower, upper in zip(op.lowers, op.uppers):
                    lower_str = self._value_to_expr_str(lower)
                    upper_str = self._value_to_expr_str(upper)
                    parts.append(f"{lower_str}:{upper_str}")
                # If source already has subscripts (e.g. a DDT member with a
                # constituent-index subscript like q(:,:,index_qv)), merge the
                # section dims INTO those subscripts by replacing ':' placeholders
                # in order, rather than appending a second set of parens.
                paren_pos = source_name.find("(")
                if paren_pos >= 0:
                    base = source_name[:paren_pos]
                    existing = source_name[paren_pos + 1: source_name.rfind(")")]
                    section_iter = iter(parts)
                    merged = []
                    fixed = []
                    for tok in existing.split(","):
                        t = tok.strip()
                        if t == ":":
                            try:
                                merged.append(next(section_iter))
                            except StopIteration:
                                merged.append(":")
                        else:
                            fixed.append(t)
                    merged.extend(fixed)
                    self.variables[op.res] = f"{base}({', '.join(merged)})"
                else:
                    self.variables[op.res] = f"{source_name}({', '.join(parts)})"
            case builtin.UnrealizedConversionCastOp():
                # Type annotation cast — transparent to Fortran; map each result
                # to the same variable name as the corresponding input operand.
                for result, operand in zip(op.results, op.inputs):
                    self.variables[result] = self._get_variable_name_for(operand)
            case CCPPAccDataBeginOp():
                copy_names    = [self._get_variable_name_for(v) for v in op.copy_arrays]
                copyin_names  = [self._get_variable_name_for(v) for v in op.copyin_arrays]
                copyout_names = [self._get_variable_name_for(v) for v in op.copyout_arrays]
                present_names = [self._get_variable_name_for(v) for v in op.present_arrays]
                if not copy_names and not copyin_names and not copyout_names and not present_names:
                    self.print("!$acc data")
                else:
                    self._emit_acc_directive("data", [
                        ("copy",    copy_names),
                        ("copyin",  copyin_names),
                        ("copyout", copyout_names),
                        ("present", present_names),
                    ])
            case CCPPAccDataEndOp():
                self.print("!$acc end data")
            case CCPPModuleVarOp():
                pass  # declared in _print_module preamble, not here
            case CCPPLazyAllocOp():
                vname = op.var_name.data
                dim_names = [self._get_variable_name_for(v) for v in op.dim_vars]
                dim_str = ", ".join(dim_names)
                self.print(f"if (.not. allocated({vname})) then")
                with self.descend() as inner:
                    inner.print(f"allocate({vname}({dim_str}))")
                    if op.init_value is not None:
                        inner.print(
                            f"{vname} = {op.init_value.data}"
                        )
                self.print("end if")
            case CCPPSafeDeallocOp():
                vname = op.var_name.data
                self.print(f"if (allocated({vname})) deallocate({vname})")
            case CCPPPresentCheckOp():
                var_name = op.var_name.data
                self.print(f"if (present({var_name})) then")
                with self.descend() as inner:
                    inner.print_block(op.with_body.blocks[0])
                self.print("else")
                with self.descend() as inner:
                    inner.print_block(op.without_body.blocks[0])
                self.print("end if")
            case CCPPPromotionLoopOp():
                loop_name  = self._get_variable_name_for(op.loop_var)
                upper_name = self._get_variable_name_for(op.upper_bound)
                self.print(f"do {loop_name} = 1, {upper_name}")
                with self.descend() as inner:
                    inner.print_block(op.body.blocks[0])
                self.print("end do")
            case CCPPSubcycleLoopOp():
                loop_name = self._get_variable_name_for(op.loop_var)
                self.print(f"do {loop_name} = 1, {op.loop_count.data}")
                with self.descend() as inner:
                    inner.print_block(op.body.blocks[0])
                self.print("end do")
            case CCPPSuiteVariablesOp():
                # The body text is the complete pre-built Fortran subroutine.
                # Emit each line with the current indentation prefix.
                for line in op.body.data.splitlines():
                    self.print(line)
            case CCPPConstituentApiOp():
                for line in op.body.data.splitlines():
                    self.print(line)
            case CCPPRankReducingSliceOp():
                # Register the Fortran array-section expression for the result.
                # Scan dim_pattern left-to-right, consuming range pairs and
                # scalar indices to build subscript strings like:
                #   "RS" → source(lower:upper, scalar)
                #   "SR" → source(scalar, lower:upper)
                #   "RSS" → source(lower:upper, scalar1, scalar2)
                source_name = self._get_variable_name_for(op.source)
                pattern = op.dim_pattern.data
                r_lowers = list(op.range_lowers)
                r_uppers = list(op.range_uppers)
                scalars  = list(op.scalar_indices)
                r_idx = 0
                s_idx = 0
                subscripts = []
                for ch in pattern:
                    if ch == "R":
                        lo = self._value_to_expr_str(r_lowers[r_idx])
                        hi = self._value_to_expr_str(r_uppers[r_idx])
                        subscripts.append(f"{lo}:{hi}")
                        r_idx += 1
                    else:  # 'S'
                        subscripts.append(
                            self._get_variable_name_for(scalars[s_idx])
                        )
                        s_idx += 1
                self.variables[op.res] = (
                    f"{source_name}({', '.join(subscripts)})"
                )
            case CCPPAccUpdateSelfOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_acc_directive("update", [("self", var_names)])
            case CCPPAccUpdateDeviceOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_acc_directive("update", [("device", var_names)])
            case CCPPOmpTargetDataBeginOp():
                tofrom_names = [self._get_variable_name_for(v) for v in op.tofrom_arrays]
                alloc_names  = [self._get_variable_name_for(v) for v in op.alloc_arrays]
                if not tofrom_names and not alloc_names:
                    self.print("!$omp target data")
                else:
                    self._emit_omp_directive("target data", [
                        ("map(tofrom:", tofrom_names),
                        ("map(alloc:",  alloc_names),
                    ])
            case CCPPOmpTargetDataEndOp():
                self.print("!$omp end target data")
            case CCPPOmpTargetUpdateFromOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_omp_directive("target update", [("from", var_names)])
            case CCPPOmpTargetUpdateToOp():
                var_names = [self._get_variable_name_for(v) for v in op.arrays]
                self._emit_omp_directive("target update", [("to", var_names)])
            case CCPPKindCastOp():
                src_name    = self._get_variable_name_for(op.source)
                result_name = self._get_variable_name_for(op.res)
                target_kind = op.target_kind.data
                dim_suffix = self._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    # mold= requires matching kind; use explicit size() dims instead
                    rank = dim_suffix.count(":")
                    sizes = ", ".join(f"size({src_name}, {i+1})" for i in range(rank))
                    self.print(f"allocate({result_name}({sizes}))")
                self.print(f"{result_name} = real({src_name}, kind={target_kind})")
            case CCPPKindWriteBackOp():
                conv_name = self._get_variable_name_for(op.conv_result)
                dest_name = self._get_variable_name_for(op.original_dest)
                orig_kind = op.original_kind.data
                self.print(f"{dest_name} = real({conv_name}, kind={orig_kind})")
                if self._ftn_dim_suffix(op.conv_result.type):
                    self.print(f"deallocate({conv_name})")
            case CCPPUnitConvertOp():
                # Local-copy pre-conversion (host units → scheme units).
                # Allocates a local temp and copies the converted value into it;
                # the host's array is never modified.
                src_name    = self._get_variable_name_for(op.source)
                result_name = self._get_variable_name_for(op.res)
                scheme_kind = self._elem_kind_name(op.res.type)
                to_expr = self._suffix_kind_in_expr(op.to_scheme_expr.data, scheme_kind)
                dim_suffix = self._ftn_dim_suffix(op.res.type)
                if dim_suffix:
                    rank = dim_suffix.count(":")
                    sizes = ", ".join(f"size({src_name}, {i+1})" for i in range(rank))
                    self.print(f"allocate({result_name}({sizes}))")
                if to_expr:
                    self.print(f"{result_name} = {src_name} {to_expr}")
                # intent(out): no pre-copy — scheme fills the local from scratch
            case CCPPUnitWriteBackOp():
                # Post-conversion: write local temp back to host in original units.
                conv_name = self._get_variable_name_for(op.conv_result)
                dest_name = self._get_variable_name_for(op.original_dest)
                host_kind = self._elem_kind_name(op.original_dest.type)
                to_expr = self._suffix_kind_in_expr(op.to_host_expr.data, host_kind)
                self.print(f"{dest_name} = {conv_name} {to_expr}")
                if self._ftn_dim_suffix(op.conv_result.type):
                    self.print(f"deallocate({conv_name})")
    # ISO_FORTRAN_ENV named constants recognised as kind values
    _ISO_FORTRAN_ENV_KINDS: frozenset[str] = frozenset(
        {
            "REAL32",
            "REAL64",
            "REAL128",
            "INT8",
            "INT16",
            "INT32",
            "INT64",
        }
    )

    def _print_module(self, module_name, body):
        """Print a builtin.ModuleOp as a Fortran module block.

        The preamble contains:
          - use ccpp_kinds (skipped for the ccpp_kinds module itself)
          - use iso_fortran_env if any KindDefOp values are ISO constants
          - use <module>, only: <name> lines for external declarations
          - implicit none / private defaults
          - integer, parameter declarations for every KindDefOp
          - character variable declarations for every llvm.GlobalOp
          - a public :: line for each subroutine definition marked public
        The CONTAINS section follows only when subroutine definitions are present.
        """
        assert module_name is not None
        is_kinds_module = module_name.data == "ccpp_kinds"

        self.print(f"module {module_name.data}")

        # The ccpp_kinds module must not use itself (circular dependency)
        if not is_kinds_module:
            self.print("\nuse ccpp_kinds", prefix="  ")

        # For the ccpp_kinds module, emit ISO_FORTRAN_ENV renames:
        #   use ISO_FORTRAN_ENV, only: kind_phys => REAL64
        # This imports and re-exports each kind under its CCPP name in one step.
        if is_kinds_module:
            iso_renames = ", ".join(
                f"{op.kind_name.data} => {op.kind_value.data}"
                for op in body.ops
                if isa(op, CCPPKindDefOp)
                and op.kind_value.data in self._ISO_FORTRAN_ENV_KINDS
            )
            if iso_renames:
                self.print(f"use ISO_FORTRAN_ENV, only: {iso_renames}", prefix="  ")

        # Emit 'use <module>, only: <name>' lines.  Two sources:
        #   1. External FuncOps with a 'module' attribute (suite cap callees).
        #   2. llvm.GlobalOp stubs with a 'module' attribute (host model vars).
        use_map: dict[str, list[str]] = {}
        for op in body.ops:
            if isa(op, func.FuncOp) and op.is_declaration and "module" in op.attributes:
                mod = op.attributes["module"].data
                use_map.setdefault(mod, []).append(op.sym_name.data)
            elif isa(op, llvm.GlobalOp) and "module" in op.attributes:
                mod = op.attributes["module"].data
                use_map.setdefault(mod, []).append(op.sym_name.data)
        # Also emit USE statements for CCPP framework DDT types used as
        # function argument types — e.g. ccpp_constituent_properties_t.
        _CCPP_DDT_MODULES = {
            "ccpp_constituent_properties_t": "ccpp_constituent_prop_mod",
            "ccpp_constituent_prop_ptr_t":   "ccpp_constituent_prop_mod",
            "ccpp_t":                        "ccpp_types",
        }
        from xdsl_ccpp.dialects.ccpp_utils import DerivedType as _DerivedType
        for op in body.ops:
            if not isa(op, func.FuncOp):
                continue
            for blk in op.body.blocks:
                for arg in blk.args:
                    if not isa(arg.type, MemRefType):
                        continue
                    elem = cast(MemRefType, arg.type).element_type
                    if not isa(elem, _DerivedType):
                        continue
                    ddt_mod = _CCPP_DDT_MODULES.get(
                        cast(_DerivedType, elem).type_name.data
                    )
                    if ddt_mod:
                        use_map.setdefault(ddt_mod, [])
                        if cast(_DerivedType, elem).type_name.data \
                                not in use_map[ddt_mod]:
                            use_map[ddt_mod].append(
                                cast(_DerivedType, elem).type_name.data
                            )

        for mod, procs in sorted(use_map.items()):
            for proc in sorted(procs):
                self.print(f"use {mod}, only: {proc}", prefix="  ")

        self.print("\nimplicit none", prefix="  ")
        self.print("private", prefix="  ")
        self.print("")

        # Emit 'public :: kind_name' for each kind (the rename in the use statement
        # above already brings the name into scope; only visibility needs declaring).
        for op in body.ops:
            if isa(op, CCPPKindDefOp):
                self.print(f"public :: {op.kind_name.data}", prefix="  ")

        # Emit module-level character variable declarations for each LLVM global.
        # Globals with a 'module' attribute are USE-associated (already emitted
        # above as 'use' lines) and must not be re-declared here.
        for op in body.ops:
            if isa(op, llvm.GlobalOp) and "module" not in op.attributes:
                name = op.sym_name.data
                val = op.value.data if isa(op.value, StringAttr) else ""
                is_const = op.constant is not None
                # Derive character length from the LLVM array type when available
                char_len: int | str = 16
                if isa(op.global_type, llvm.LLVMArrayType):
                    char_len = cast(llvm.LLVMArrayType, op.global_type).size.data
                if is_const:
                    # Read-only string constants use the parameter attribute
                    self.print(
                        f"character(len={char_len}), parameter :: {name} = '{val}'",
                        prefix="  ",
                    )
                else:
                    # Mutable state variable (e.g. ccpp_suite_state).
                    # When "dimension" attribute is set, emit a per-instance array.
                    dim = op.attributes.get("dimension")
                    if dim is not None:
                        self.print(
                            f"character(len={char_len}), dimension({dim.data})"
                            f" :: {name} = '{val}'",
                            prefix="  ",
                        )
                    else:
                        self.print(
                            f"character(len={char_len}) :: {name} = '{val}'",
                            prefix="  ",
                        )

        # Emit module-level variable declarations (unified ModuleVarOp).
        # rank=0: scalar, rank>0: allocatable array with that many deferred dimensions.
        for op in body.ops:
            if isa(op, CCPPModuleVarOp):
                rank = op.rank.value.data
                ftn_type = op.fortran_type.data
                var_name = op.var_name.data
                if rank == 0:
                    self.print(f"{ftn_type} :: {var_name}", prefix="  ")
                else:
                    shape = ", ".join([":"] * rank)
                    if ", pointer" in ftn_type:
                        self.print(
                            f"{ftn_type} :: {var_name}({shape}) => null()",
                            prefix="  ",
                        )
                    else:
                        self.print(
                            f"{ftn_type}, allocatable :: {var_name}({shape})",
                            prefix="  ",
                        )

        # Emit one public :: line per subroutine definition that is marked public.
        public_procs = [
            op.sym_name.data
            for op in body.ops
            if (
                isa(op, func.FuncOp)
                and not op.is_declaration
                and op.sym_visibility is not None
                and op.sym_visibility.data == "public"
            )
        ] + [
            "ccpp_physics_suite_variables"
            for op in body.ops
            if isa(op, CCPPSuiteVariablesOp)
        ] + [
            name.data
            for op in body.ops
            if isa(op, CCPPConstituentApiOp)
            for name in op.public_names.data
        ]
        for proc in public_procs:
            self.print(f"public :: {proc}", prefix="  ")

        # Only emit CONTAINS when there are subroutine definitions to print
        has_func_defs = any(
            (isa(op, func.FuncOp) and not op.is_declaration)
            or isa(op, CCPPSuiteVariablesOp)
            or isa(op, CCPPConstituentApiOp)
            for op in body.ops
        )
        if has_func_defs:
            self.print("\nCONTAINS")
            with self.descend() as inner:
                inner.print_block(body)

        self.print(f"end module {module_name.data}")

    def get_call_result_var_ssa(self, res_ssa):
        """Resolve a call result SSA value to the Fortran variable it writes into.

        After a scheme subroutine call the MLIR IR contains a memref.CopyOp
        that copies each result into its destination storage.  This method
        follows that use edge to find the destination variable name.  If no
        CopyOp is found the result was pre-registered as an anonymous local by
        _print_fn and its name is looked up directly in self.variables.
        """
        for use in res_ssa.uses:
            if isa(use.operation, memref.CopyOp):
                return self._get_variable_name_for(use.operation.destination)
        # No CopyOp — must have been pre-registered as an anonymous local
        return self.variables.get(res_ssa)

    def _print_call(self, tgt, args, results):
        """Print a func.CallOp as a Fortran subroutine call statement.

        Input arguments are printed by variable name.  Output arguments are
        resolved through the CopyOp use-chain to find the destination variable
        that will receive each result.

        Inout-echo returns are suppressed: when the suite cap returns a scalar
        inout arg as an SSA value (MLIR SSA convention), the resolved destination
        name is the same variable already printed as an input.  Printing it again
        would produce an invalid duplicate argument in the Fortran call.
        """
        self.print(f"call {tgt.string_value()}(", end="")

        # Collect input variable names to detect inout-echo returns.
        input_var_names = {self._get_variable_name_for(arg) for arg in args}

        # Print input arguments
        printed = 0
        for arg in args:
            if printed > 0:
                self.print(", ", end="", use_prefix=False)
            self.print(self._get_variable_name_for(arg), end="", use_prefix=False)
            printed += 1

        # Print output argument destinations, skipping inout echoes
        for res in results:
            ret_name = self.get_call_result_var_ssa(res)
            if ret_name is not None and ret_name in input_var_names:
                continue  # inout echo — already in the input list, skip
            if printed > 0:
                self.print(", ", end="", use_prefix=False)
            self.print(ret_name, end="", use_prefix=False)
            printed += 1

        self.print(")", use_prefix=False)

    def _print_kw_call(self, op: CCPPKeywordCallOp):
        """Print a ccpp_utils.kw_call as a Fortran keyword-argument subroutine call.

        Compile-time literal overrides are emitted first as ``name=literal``,
        then SSA input operands as ``name=var_name``, then SSA output results
        as ``name=dest_var``.  Inout arguments (present in both operand_names
        and result_names) are deduplicated via a seen-names set.
        """
        self.print(f"call {op.callee.data}(", end="")
        idx = 0
        seen: set[str] = set()
        for name, val_attr in op.overrides.data.items():
            if idx > 0:
                self.print(", ", end="", use_prefix=False)
            self.print(f"{name}={val_attr.data}", end="", use_prefix=False)
            seen.add(name)
            idx += 1
        for name_attr, arg in zip(op.operand_names.data, op.args):
            name = name_attr.data
            if name not in seen:
                if idx > 0:
                    self.print(", ", end="", use_prefix=False)
                self.print(
                    f"{name}={self._get_variable_name_for(arg)}",
                    end="",
                    use_prefix=False,
                )
                seen.add(name)
                idx += 1
        for name_attr, res in zip(op.result_names.data, op.res):
            name = name_attr.data
            if name not in seen:
                if idx > 0:
                    self.print(", ", end="", use_prefix=False)
                self.print(
                    f"{name}={self.get_call_result_var_ssa(res)}",
                    end="",
                    use_prefix=False,
                )
                seen.add(name)
                idx += 1
        self.print(")", use_prefix=False)

    def _print_if(
        self,
        conditional,
        true_bdy: Region,
        false_bdy: Region,
    ):
        """Print an scf.IfOp as a Fortran if / else / end if block."""
        self.print("if (", end="")
        self.print_expr(conditional.owner)
        self.print(") then", use_prefix=False)

        with self.descend() as inner:
            inner.print_block(true_bdy)

        if len(false_bdy.blocks) > 0:
            self.print("else")
            with self.descend() as inner:
                inner.print_block(false_bdy)

        self.print("end if")

    def _print_fn(
        self,
        fn_name: StringAttr,
        bdy: Region,
        ftyp: FunctionType,
    ):
        """Print a func.FuncOp definition as a Fortran subroutine.

        Argument names are taken from the name_hint set on each block argument
        and alloca result during IR generation, falling back to positional
        names if no hint is present.

        The ReturnOp is scanned to detect inout arguments (block args that
        appear in the return list) so they can be declared intent(inout) rather
        than the default intent(in).  Pure output arguments come from AllocaOp
        results also present in the return list.
        """
        # Collect input arg names from block arg name hints.
        # Strip __alloc (allocatable), __opt (optional), or __in (intent-in array) suffix.
        input_names = [
            (arg.name_hint[:-7] if arg.name_hint and arg.name_hint.endswith("__alloc")
             else arg.name_hint[:-5] if arg.name_hint and arg.name_hint.endswith("__opt")
             else arg.name_hint[:-4] if arg.name_hint and arg.name_hint.endswith("__in")
             else (arg.name_hint if arg.name_hint is not None else f"arg_{idx}"))
            for idx, arg in enumerate(bdy.block.args)
        ]

        # Scan ReturnOp to separate output allocas from returned inout block args
        output_names: list[str] = []
        output_ret_vals: list = []
        inout_block_args: set = set()
        for op in bdy.block.ops:
            if isa(op, func.ReturnOp):
                for ret_val in op.arguments:
                    if isa(ret_val.owner, memref.AllocaOp):
                        # AllocaOp result → a true output argument
                        out_name = (
                            ret_val.name_hint
                            if ret_val.name_hint is not None
                            else f"out_{len(output_names)}"
                        )
                        output_names.append(out_name)
                        output_ret_vals.append(ret_val)
                    else:
                        # Block arg in return position → inout argument
                        inout_block_args.add(ret_val)
                break

        # Collect local allocas — AllocaOps whose result is not in the return list
        local_allocas = [
            op
            for op in bdy.block.ops
            if isa(op, memref.AllocaOp) and op.memref not in output_ret_vals
        ]

        # Collect call results that have no CopyOp consumer — they become anonymous locals
        # (e.g. DDT outputs from init that the ccpp_cap doesn't route anywhere).
        # Also look one level through UnrealizedConversionCastOp (inserted for type mismatches).
        def _has_copy_consumer(ssa):
            for u in ssa.uses:
                if isa(u.operation, memref.CopyOp):
                    return True
                if isa(u.operation, builtin.UnrealizedConversionCastOp):
                    if any(
                        isa(u2.operation, memref.CopyOp)
                        for u2 in u.operation.results[0].uses
                    ):
                        return True
            return False

        untracked_call_results: list[tuple[OpResult, str]] = []
        for nested_op in bdy.block.walk():
            if not isa(nested_op, func.CallOp) and not isa(
                nested_op, CCPPKeywordCallOp
            ):
                continue
            for res in nested_op.results:
                has_copy = _has_copy_consumer(res)
                if not has_copy:
                    hint = (
                        res.name_hint
                        if res.name_hint
                        else f"ccpp_tmp_{len(untracked_call_results)}"
                    )
                    untracked_call_results.append((res, hint))

        args_str = ", ".join(input_names + output_names)
        start_signature = f"\nsubroutine {fn_name.data}({args_str})"
        end_signature = f"end subroutine {fn_name.data}"

        with self.descend(start_signature, end_signature) as inner:
            # Register input block args so downstream ops can look them up by name
            for arg, arg_name in zip(bdy.block.args, input_names):
                inner.variables[arg] = arg_name

            # Register output alloca results so StoreOp and CallOp can resolve them
            for ret_val, out_name in zip(output_ret_vals, output_names):
                inner.variables[ret_val] = out_name

            # Declare input arguments with intent(in) or intent(inout).
            # Array block args (dynamic memref) are always intent(inout): the host
            # provides the buffer and the scheme may write to it in-place.
            # Exception: memref<memref<?xi8>> is an allocatable character array
            # passed intent(out) — the callee allocates and fills it.
            for arg, arg_name in zip(bdy.block.args, input_names):
                # Check the original name_hint for the __alloc / __opt / __in suffix
                is_alloc = (arg.name_hint is not None
                            and arg.name_hint.endswith("__alloc"))
                is_opt   = (arg.name_hint is not None
                            and arg.name_hint.endswith("__opt"))
                is_in    = (arg.name_hint is not None
                            and arg.name_hint.endswith("__in"))
                type_str = inner.mlir_type_to_ftn_type(arg.type)
                dim_suffix = inner._ftn_dim_suffix(arg.type)
                if ftnPrintContext._is_allocatable_char(arg.type):
                    type_str = type_str + ", allocatable"
                    intent = "out"
                elif is_alloc:
                    type_str = type_str + ", allocatable"
                    intent = "inout"
                elif is_in:
                    intent = "in"
                elif dim_suffix:
                    intent = "inout"
                elif arg in inout_block_args:
                    intent = "inout"
                else:
                    intent = "in"
                if is_opt:
                    type_str = type_str + ", optional"
                inner.print(f"{type_str}, intent({intent}) :: {arg_name}{dim_suffix}")

            # Declare output arguments with intent(out) (always scalars)
            for ret_val, out_name in zip(output_ret_vals, output_names):
                type_str = inner.mlir_type_to_ftn_type(ret_val.type)
                dim_suffix = inner._ftn_dim_suffix(ret_val.type)
                inner.print(f"{type_str}, intent(out) :: {out_name}{dim_suffix}")

            # Declare local variables (non-returned allocas, e.g. computed scalars)
            for alloca_op in local_allocas:
                var_name = (
                    alloca_op.memref.name_hint
                    if alloca_op.memref.name_hint is not None
                    else f"local_{id(alloca_op)}"
                )
                is_alloc = var_name.endswith("__alloc")
                ftn_name = var_name[: -len("__alloc")] if is_alloc else var_name
                inner.variables[alloca_op.memref] = ftn_name
                type_str = inner.mlir_type_to_ftn_type(alloca_op.memref.type)
                if is_alloc:
                    rank = len(alloca_op.memref.type.shape.data)
                    dim_suffix = "(" + ", ".join(":" for _ in range(rank)) + ")"
                    inner.print(f"{type_str}, allocatable :: {ftn_name}{dim_suffix}")
                else:
                    inner.print(f"{type_str} :: {var_name}")

            # Declare kind-cast and unit-convert temporaries
            for op in bdy.block.ops:
                if isa(op, CCPPKindCastOp):
                    var_name = (
                        op.res.name_hint
                        if op.res.name_hint is not None
                        else f"kind_cast_{id(op)}"
                    )
                    inner.variables[op.res] = var_name
                    type_str = inner.mlir_type_to_ftn_type(op.res.type)
                    dim_suffix = inner._ftn_dim_suffix(op.res.type)
                    if dim_suffix:
                        inner.print(f"{type_str}, allocatable :: {var_name}{dim_suffix}")
                    else:
                        inner.print(f"{type_str} :: {var_name}")
                elif isa(op, CCPPUnitConvertOp):
                    # Local-copy conversion: declare a temp in the same type as source.
                    var_name = (
                        op.res.name_hint
                        if op.res.name_hint is not None
                        else f"unit_conv_{id(op)}"
                    )
                    inner.variables[op.res] = var_name
                    type_str = inner.mlir_type_to_ftn_type(op.res.type)
                    dim_suffix = inner._ftn_dim_suffix(op.res.type)
                    if dim_suffix:
                        inner.print(f"{type_str}, allocatable :: {var_name}{dim_suffix}")
                    else:
                        inner.print(f"{type_str} :: {var_name}")

            # Declare anonymous locals for call results that have no CopyOp consumer
            for res, var_name in untracked_call_results:
                inner.variables[res] = var_name
                type_str = inner.mlir_type_to_ftn_type(res.type)
                dim_suffix = inner._ftn_dim_suffix(res.type)
                inner.print(f"{type_str} :: {var_name}{dim_suffix}")

            inner.print("")

            inner.print_block(bdy.block)

    @contextmanager
    def _emit_acc_directive(
        self, keyword: str, clauses: list[tuple[str, list[str]]], *, sentinel: str = "!$acc"
    ) -> None:
        """Emit an OpenACC directive with proper continuation at variable boundaries.

        Builds the directive token by token.  When adding the next token would
        push the current line past _MAX_LINE_LEN, the line is flushed with a
        Fortran continuation marker ' &' and a new line is started with the
        OpenACC sentinel prefix '!$acc     '.

        This handles both inter-clause breaks (between copyin/copyout/present)
        and intra-clause breaks within a long variable list, making it suitable
        for suites with 40+ variables per clause.

        Args:
            keyword:  The OpenACC directive keyword, e.g. 'data' or 'update'.
            clauses:  List of (clause_name, [var_name_strings]) pairs.
                      Pairs with empty variable lists are skipped.

        Example output for a long copyin list::

            !$acc data copyin(var1, var2, var3, &
            !$acc      var4, var5) copyout(var6)
        """
        acc_start = self._prefix + sentinel + " " + keyword
        acc_cont  = self._prefix + sentinel + "     "

        current = acc_start
        output_lines: list[str] = []

        for clause_name, var_names in clauses:
            if not var_names:
                continue
            # Build tokens: first includes the clause opener, last closes the paren.
            # e.g. ["copyin(var1,", "var2,", "var3)"]
            tokens = []
            for i, var in enumerate(var_names):
                prefix = f"{clause_name}(" if i == 0 else ""
                suffix = ")" if i == len(var_names) - 1 else ","
                tokens.append(prefix + var + suffix)

            for token in tokens:
                candidate = current + " " + token
                if len(candidate) <= _MAX_LINE_LEN:
                    current = candidate
                else:
                    output_lines.append(current + " &")
                    current = acc_cont + " " + token

        output_lines.append(current)
        for line in output_lines:
            print(line, file=self.output)
    def _emit_omp_directive(
        self, keyword: str, clauses: list[tuple[str, list[str]]]
    ) -> None:
        self._emit_acc_directive(keyword, clauses, sentinel="!$omp")

    @contextmanager
    def descend(self, block_start: str = None, block_end: str = None):
        """Return a child context with one extra level of indentation.

        The child inherits a copy of the parent's variable map so that names
        defined in an outer scope remain visible inside nested blocks.  An
        optional block_start string (e.g. a subroutine signature) is printed
        before yielding, and block_end (e.g. 'end subroutine') is printed
        after the with-block completes.

        Usage::

            with self.descend("subroutine foo()", "end subroutine foo") as inner:
                inner.print_block(body)
        """
        if block_start is not None:
            self.print(f"{block_start} ")
        yield ftnPrintContext(
            output=self.output,
            variables=self.variables.copy(),
            _cmp_ops=self._cmp_ops,
            _binops=self._binops,
            _counter=self._counter,
            _prefix=self._prefix + self._INDENT,
        )
        if block_end is not None:
            self.print(f"{block_end} ")

    def print(self, text: str, prefix: str = "", end: str = "\n", use_prefix=True):
        """Append text to the current line buffer, flushing on newline.

        Embedded newlines in text cause an immediate buffer flush each time
        they are encountered.  When end="\\n" (the default) the buffer is
        flushed at the end of the call.  Passing use_prefix=False suppresses
        the indentation prefix for inline continuations.
        """
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                self._emit_line()
            self._line_buf += (self._prefix + prefix if use_prefix else "") + part
        if end == "\n":
            self._emit_line()

    def _emit_line(self):
        """Flush the line buffer, splitting at commas if the line is too long."""
        line = self._line_buf
        self._line_buf = ""
        self._write_with_continuation(line, self._prefix + self._INDENT)

    def _write_with_continuation(self, line: str, cont_prefix: str):
        """Write line, inserting Fortran continuation markers at commas if needed.

        If line exceeds _MAX_LINE_LEN characters, the last comma at parenthesis
        depth zero at or before position _MAX_LINE_LEN - 2 is used as the split
        point: the first part is written with a trailing ' &' and the remainder
        is written on the next line starting with cont_prefix.  Recurses until
        the remainder fits.

        Only commas at depth zero are considered so that array subscript
        expressions such as arr(col_start:col_end, 1:pver) are never split
        in the middle.
        """
        if len(line) <= _MAX_LINE_LEN:
            print(line, file=self.output)
            return
        # Find the last comma at paren depth ≤ 1 within the line limit.
        # Depth 0: top-level commas.
        # Depth 1: commas between function/subroutine arguments — valid break points.
        # Depth > 1: commas inside nested subscript expressions such as
        #   arr(col_start:col_end, 1:pver) — never break inside these.
        split_pos = -1
        depth = 0
        for i, ch in enumerate(line[: _MAX_LINE_LEN - 2]):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth <= 1:
                split_pos = i
        if split_pos == -1:
            # No valid split point — emit as-is rather than produce invalid Fortran
            print(line, file=self.output)
            return
        print(line[: split_pos + 1].ljust(_MAX_LINE_LEN - 1) + "&", file=self.output)
        remainder = cont_prefix + line[split_pos + 1 :].lstrip()
        self._write_with_continuation(remainder, cont_prefix)

    def print_block(self, body: Block):
        """Iterate over every operation in body and dispatch it to print_op."""
        for op in body.ops:
            self.print_op(op)


def get_modules_in_module_op(module: ModuleOp):
    """Yield each named sub-ModuleOp directly contained in the top-level module.

    The top-level module is an anonymous wrapper; the named sub-modules (one
    per cap suite) are what get printed as individual Fortran files.
    """
    for op in module.body.ops:
        if isinstance(op, builtin.ModuleOp):
            yield op


def print_to_ftn(
    prog: ModuleOp, output: IO[str], Ctx: type[ftnPrintContext] = ftnPrintContext
):
    """Print all named sub-modules in prog as Fortran source to output.

    Each sub-module is preceded by a FILE comment that indicates the suggested
    output filename (e.g. '// FILE: hello_world_suite_cap.F90').  Multiple
    modules are separated by a '// -----' divider.
    """
    ctx = Ctx(output)
    ctx.register_binops()
    divider = False
    # Print each cap module as a separate Fortran file section
    for module in get_modules_in_module_op(prog):
        if divider:
            ctx.print("// -----")
        divider = True
        ctx.print("// FILE: " + module.sym_name.data + ".F90")
        ctx.print_op(module)
