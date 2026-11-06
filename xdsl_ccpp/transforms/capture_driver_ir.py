"""The scheme I/O capture test driver as IR (scheme-io-capture-driver-as-ir).

`build_test_driver` turns the phases SchemeIOCapturePass resolved for one
scheme ([(table name, [TestDriverParam], scheme module)], in lifecycle
order) into a ProgramOp that the Fortran printer prints like any other
unit: `use` lines come from external declarations and use stubs,
declarations from named allocas, statements from the same ops the caps
use. Nothing here spells Fortran.

The program, for each phase in order:

  * a compared phase (something captured) replays every captured call:
        n_calls = ccpp_capture_call_count('<table>')
        if (n_calls == 0) <FAIL: no captured calls>
        do call_count = 1, n_calls
          call ccpp_capture_open_call('<table>', call_count, found)
          <log unit, scalar reads, allocations, array reads>
          <device copies in>  call <table>(...)  <errflg check>
          <device copies out>  <after reads>  call ccpp_capture_close()
          <compares, each reported by ccpp_capture_report>
        end do
  * a call-only phase (nothing captured, every argument supplied by the
    driver -- scheme-io-capture-uncaptured-phases) is called once.

then prints ALL TESTS PASSED, or the failure count and `call exit(1)`.
"""

from dataclasses import dataclass

from xdsl.dialects import arith, func, llvm, memref
from xdsl.dialects.builtin import FloatAttr, IntegerAttr, MemRefType, StringAttr, f64, i1, i8, i32
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import (
    AccEnterDataOp,
    AccExitDataOp,
    AllocateOp,
    AssignOp,
    BlankLineOp,
    CallExprOp,
    CallStatementOp,
    CommentOp,
    DerivedType,
    DoLoopOp,
    IndexExprOp,
    KeywordArgExprOp,
    OmpTargetEnterDataOp,
    OmpTargetExitDataOp,
    PrintStmtOp,
    ProgramOp,
    RealKindType,
    SafeDeallocOp,
    StringLiteralExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.util.cap_shared import _scf_if, directive_op
from xdsl_ccpp.util.ccpp_conventions import CCPP_KIND_PHYS, mark_allocatable_local, name_local


@dataclass(frozen=True)
class TestDriverParam:
    """One scheme-call keyword argument, classified by CCPP semantics
    (scheme_io_capture_pass._driver_param_category): "in"/"out"/"inout" (a
    captured argument, read from the capture and, for out/inout, compared),
    "error_arg" (errmsg/errflg -- declared and passed, checked, never
    compared), "log_unit" (the host's log unit -- the driver passes
    standard output), or "unverified" (outside the capture's type scope --
    declared and passed so the call compiles, never compared). `dims`
    names the other arguments sizing an unverified array; a captured
    array is sized from the capture file. `is_device` asks for a device
    copy around the call (scheme-io-capture-gpu-residency). A captured
    derived-type argument (scheme-io-capture-ddt-args) has `ddt_read`, the
    procedure (in module `ddt_read_module`) that rebuilds it, and
    `type_module`, the module declaring its type `arg_type`.
    """

    name: str
    category: str
    arg_type: "str | None"
    kind: "str | None"
    rank: int
    dims: "list[str] | None" = None
    is_device: bool = False
    ddt_read: "str | None" = None
    ddt_read_module: "str | None" = None
    type_module: "str | None" = None


# Categories of the arguments a test driver supplies itself, with nothing
# to read from a capture file.
_DRIVER_SUPPLIED_CATEGORIES = frozenset({"error_arg", "log_unit"})


def is_call_only_phase(params: "list[TestDriverParam]") -> bool:
    """Whether a phase is replayed as a plain call (scheme-io-capture-
    uncaptured-phases): nothing of it was captured and every argument is
    one the driver supplies itself, e.g. an `_init` with only errmsg/errflg
    that sets module state a later phase reads."""
    return all(p.category in _DRIVER_SUPPLIED_CATEGORIES for p in params)


_CAPTURE_MOD = "ccpp_capture_mod"
_REPLAY_MOD = "ccpp_capture_replay_mod"
_KINDS_MOD = "ccpp_kinds"
_ERRMSG_LEN = 512
_DEFAULT_CHAR_LEN = 512


def _var(name: str, result_type=None) -> VarRefExprOp:
    return VarRefExprOp(name, result_type=result_type)


def _int(value: int) -> arith.ConstantOp:
    return arith.ConstantOp(IntegerAttr(value, i32))


def _str(text: str) -> StringLiteralExprOp:
    return StringLiteralExprOp(text)


def _call(callee: str, *args) -> CallStatementOp:
    return CallStatementOp(callee, arg_ops=list(args))


def _assign(name: str, value_op, result_type=None) -> AssignOp:
    return AssignOp(lhs_op=_var(name, result_type), rhs_op=value_op)


def _not(name: str):
    """.not. <name>, as the codebase's XOrIOp-with-true idiom."""
    return arith.XOrIOp(_var(name, i1), arith.ConstantOp(IntegerAttr(1, i1)))


def _int_cmp(name: str, predicate: str, value: int):
    return arith.CmpiOp(_var(name, i32), _int(value), predicate)


def _char_len(kind: "str | None") -> int:
    """A character argument's length from its metadata kind (`len=64`);
    assumed length (`len=*`) gets a buffer of the default length."""
    if kind and "len" in kind:
        raw = kind.split("=", 1)[1].strip()
        if raw.isdigit():
            return int(raw)
    return _DEFAULT_CHAR_LEN


class _DriverBuilder:
    """Collects the program's locals, use declarations and statements."""

    def __init__(self, directive: "str | None"):
        self.directive = directive
        self.locals: dict = {}  # name -> memref.AllocaOp, in declaration order
        self.procedures: dict = {}  # name -> module
        self.symbols: dict = {}  # name -> module (kinds, types, constants)

    # -- declarations ---------------------------------------------------

    def local(self, name: str, element_type, shape=(), allocatable=False):
        """The alloca declaring local `name`; the first declaration wins
        (a scheme's phases share errmsg/errflg and other argument names)."""
        if name not in self.locals:
            alloca = memref.AllocaOp.get(element_type, shape=list(shape))
            if allocatable:
                mark_allocatable_local(alloca, name)
            else:
                name_local(alloca, name)
            self.locals[name] = alloca
        return self.locals[name]

    def use(self, name: str, module: str) -> str:
        self.procedures[name] = module
        return name

    def use_symbol(self, name: str, module: str) -> str:
        self.symbols[name] = module
        return name

    def element_type(self, p: TestDriverParam):
        if p.ddt_read is not None:
            self.use_symbol(p.arg_type, p.type_module)
            return DerivedType(p.arg_type)
        if p.arg_type == "real":
            kind = p.kind if p.kind and not p.kind.isdigit() else CCPP_KIND_PHYS
            self.use_symbol(kind, _KINDS_MOD)
            return RealKindType(kind)
        if p.arg_type == "logical":
            return i1
        if p.arg_type == "integer":
            return i32
        # A derived type outside the capture's scope (unverified): declared
        # with its type; its module is not known here, so such a driver
        # still needs scheme-io-capture-host-module-schemes to build.
        return DerivedType(p.arg_type)

    def declare_param(self, p: TestDriverParam, name: "str | None" = None):
        """The local for argument `p` (or its `<name>_expected` twin)."""
        name = name or p.name
        if p.arg_type == "character" and p.ddt_read is None:
            length = _ERRMSG_LEN if p.category == "error_arg" else _char_len(p.kind)
            if p.rank:
                # character(len=N), allocatable :: x(:)
                return self.local(name, MemRefType(i8, [length]), shape=[0] * p.rank,
                                  allocatable=True)
            return self.local(name, i8, shape=[length])  # character(len=N) :: x
        elem = self.element_type(p)
        if p.rank or p.ddt_read is not None:
            return self.local(name, elem, shape=[0] * p.rank, allocatable=True)
        return self.local(name, elem)

    # -- statements -----------------------------------------------------

    def allocate(self, name: str, rank: int, extents: "list[str] | None",
                 group: str, captured_name: str) -> list:
        """(Re)allocate `name` to `extents`, or, without them, to the shape
        of `captured_name` in `group` of the open capture file."""
        ops = [SafeDeallocOp(name)]
        if extents is None:
            ext = f"extents{rank}"
            self.local(ext, i32, shape=[rank])
            self.local("extents_found", i1)
            ops.append(_call(self.use("ccpp_capture_extents", _CAPTURE_MOD),
                             _str(group), _str(captured_name), _var(ext), _var("extents_found")))
            dims = [IndexExprOp(_var(ext), [_int(i)]) for i in range(1, rank + 1)]
        else:
            dims = [_var(d) for d in extents]
        ops.append(AllocateOp(name, dim_ops=dims))
        return ops

    def read(self, group: str, captured_name: str, target: str) -> CallStatementOp:
        return _call(self.use("ccpp_capture_read", _CAPTURE_MOD),
                     _str(group), _str(captured_name), _var(target))

    def report(self, name: str) -> CallStatementOp:
        return _call(self.use("ccpp_capture_report", _CAPTURE_MOD),
                     _str(name), _var("call_count"), _var("ok"), _var("n_failed"))

    def fail(self, *items) -> list:
        """write(*,*) <items>; n_failed = n_failed + 1"""
        return [PrintStmtOp(list(items)), self.count_failure()]

    def count_failure(self) -> AssignOp:
        return _assign("n_failed", arith.AddiOp(_var("n_failed", i32), _int(1)), i32)

    def compare(self, p: TestDriverParam) -> list:
        """ok = ccpp_capture_compare(...); report; diagnostics on failure."""
        compare = self.use("ccpp_capture_compare", _CAPTURE_MOD)
        expected = f"{p.name}_expected"
        args = [_var(p.name), _var(expected)]
        if p.rank == 0:
            if p.arg_type == "real":
                args.append(_var("tolerance"))
            diagnostics = [_str("  actual="), _var(p.name), _str(" expected="), _var(expected)]
        elif p.arg_type == "real":
            for name, elem in (("diag_max_abs_diff", RealKindType(CCPP_KIND_PHYS)),
                               ("diag_mean_abs_diff", RealKindType(CCPP_KIND_PHYS)),
                               ("diag_first_mismatch_index", i32)):
                self.local(name, elem)
            args += [_var("tolerance"), _var("diag_max_abs_diff"),
                     _var("diag_mean_abs_diff"), _var("diag_first_mismatch_index")]
            diagnostics = [_str("  max abs diff="), _var("diag_max_abs_diff"),
                           _str(" mean abs diff="), _var("diag_mean_abs_diff"),
                           _str(" first mismatch at linear index="),
                           _var("diag_first_mismatch_index")]
        else:
            self.local("diag_first_mismatch_index", i32)
            args.append(_var("diag_first_mismatch_index"))
            diagnostics = [_str("  first mismatch at linear index="),
                           _var("diag_first_mismatch_index")]
        return [
            _assign("ok", CallExprOp(compare, args, result_type=i1), i1),
            self.report(p.name),
            *_scf_if(_not("ok"), [PrintStmtOp(diagnostics)]),
        ]

    def errflg_check(self, table: str, errmsg: "str | None", errflg: "str | None") -> list:
        if errflg is None:
            return []
        items = [_str(f"FAIL: {table} returned errflg="), _var(errflg),
                 _str(" (call "), _var("call_count"), _str(")")]
        if errmsg is not None:
            items += [_str(" errmsg="), CallExprOp("trim", [_var(errmsg)])]
        return _scf_if(_int_cmp(errflg, "ne", 0), self.fail(*items))

    def device_copies(self, copy_in, create, copy_out, delete):
        """The enter/exit data ops around the call (None when not needed)."""
        if not self.directive:
            return None, None
        refs = lambda names: [self.locals[n].memref for n in names]
        enter = exit_ = None
        if copy_in or create:
            enter = directive_op(self.directive,
                                 AccEnterDataOp, {"copyin": refs(copy_in), "create": refs(create)},
                                 OmpTargetEnterDataOp, {"to": refs(copy_in), "alloc": refs(create)})
        if copy_out or delete:
            exit_ = directive_op(self.directive,
                                 AccExitDataOp, {"copyout": refs(copy_out), "delete": refs(delete)},
                                 OmpTargetExitDataOp, {"from_": refs(copy_out), "release": refs(delete)})
        return enter, exit_

    # -- one phase ------------------------------------------------------

    def phase(self, table: str, params: "list[TestDriverParam]", module: str) -> list:
        self.use(table, module)
        log_units, scalar_reads, allocations, array_reads = [], [], [], []
        after_reads, compares, kwargs = [], [], []
        copy_in, create, copy_out, delete = [], [], [], []
        errmsg = errflg = None

        for p in params:
            kwargs.append(KeywordArgExprOp(p.name, _var(p.name)))
            self.declare_param(p)
            if p.ddt_read is not None:
                # A derived type: rebuilt from the capture (its read
                # allocates it), never compared.
                array_reads.append(_call(self.use(p.ddt_read, p.ddt_read_module),
                                         _str("in"), _str(p.name), _var(p.name)))
                continue
            if p.category == "error_arg":
                if p.arg_type == "character":
                    errmsg = p.name
                elif p.arg_type == "integer":
                    errflg = p.name
                continue
            if p.category == "log_unit":
                # The captured unit is the host's, not open here
                # (scheme-io-capture-log-unit).
                unit = self.use_symbol("ccpp_capture_output_unit", _CAPTURE_MOD)
                log_units.append(_assign(p.name, _var(unit, i32), i32))
                continue
            if p.rank:
                group = "out" if p.category == "out" else "in"
                allocations += self.allocate(p.name, p.rank, p.dims, group, p.name)
            if p.category == "unverified":
                continue
            if self.directive and p.is_device:
                (copy_in if p.category in ("in", "inout") else create).append(p.name)
                (copy_out if p.category in ("out", "inout") else delete).append(p.name)
            if p.category in ("in", "inout"):
                (array_reads if p.rank else scalar_reads).append(self.read("in", p.name, p.name))
            if p.category in ("out", "inout"):
                expected = f"{p.name}_expected"
                self.declare_param(p, expected)
                if p.rank:
                    allocations += self.allocate(expected, p.rank, None, "out", p.name)
                after_reads.append(self.read("out", p.name, expected))
                compares += self.compare(p)

        call = CallStatementOp(table, arg_ops=kwargs)
        check = self.errflg_check(table, errmsg, errflg)
        if all(p.category in _DRIVER_SUPPLIED_CATEGORIES for p in params):
            return [CommentOp([f"-- {table} (nothing captured: called once, not compared) --"]),
                    *log_units, _assign("call_count", _int(1), i32), call, *check]

        enter, exit_ = self.device_copies(copy_in, create, copy_out, delete)
        self.local("n_calls", i32)
        self.local("found", i1)
        loop_body = [
            _call(self.use("ccpp_capture_open_call", _CAPTURE_MOD),
                  _str(table), _var("call_count"), _var("found")),
            *log_units, *scalar_reads, *allocations, *array_reads,
            *([enter] if enter else []), call, *check, *([exit_] if exit_ else []),
            *after_reads,
            _call(self.use("ccpp_capture_close", _CAPTURE_MOD)),
            *compares,
        ]
        count = CallExprOp(self.use("ccpp_capture_call_count", _CAPTURE_MOD), [_str(table)],
                           result_type=i32)
        return [
            CommentOp([f"-- {table} --"]),
            _assign("n_calls", count, i32),
            *_scf_if(_int_cmp("n_calls", "eq", 0),
                     self.fail(_str(f"FAIL: no captured calls of {table} found"))),
            DoLoopOp("call_count", _var("n_calls", i32), loop_body),
        ]


def build_test_driver(
    scheme_name: str,
    phase_tables: "list[tuple[str, list[TestDriverParam], str]]",
    tolerance: float,
    directive: "str | None" = None,
) -> ProgramOp:
    """The test driver program test_<scheme_name> replaying `phase_tables`
    (already in lifecycle order) against the capture. `tolerance` is the
    compiled-in default the CCPP_CAPTURE_TOLERANCE environment variable
    overrides at run time; `directive` ("acc"/"omp"/None) adds device
    copies around the calls of device-resident arguments."""
    b = _DriverBuilder(directive)
    b.use_symbol(CCPP_KIND_PHYS, _KINDS_MOD)
    for name, elem in (("tolerance", RealKindType(CCPP_KIND_PHYS)), ("n_failed", i32),
                       ("call_count", i32), ("ok", i1)):
        b.local(name, elem)

    default = arith.ConstantOp(FloatAttr(tolerance, f64))
    default.attributes["kind"] = StringAttr(CCPP_KIND_PHYS)
    override = CallExprOp(b.use("ccpp_capture_tolerance_override", _CAPTURE_MOD), [default],
                          result_type=f64)
    body = [
        _assign("tolerance", override),
        _assign("n_failed", _int(0), i32),
        CommentOp(["The run's constituent table, for ccpp_constituent_index lookups",
                   "(nothing when the capture has none)."]),
        _call(b.use("ccpp_capture_restore_constituents", _REPLAY_MOD)),
    ]
    for table, params, module in phase_tables:
        body += [BlankLineOp(), *b.phase(table, params, module)]
    body += [
        BlankLineOp(),
        *_scf_if(_int_cmp("n_failed", "eq", 0),
                 [PrintStmtOp([_str("ALL TESTS PASSED")])],
                 [PrintStmtOp([_var("n_failed"), _str(" TEST(S) FAILED")]),
                  _call("exit", _int(1))]),
        func.ReturnOp(),
    ]

    main_name = f"test_{scheme_name}_main"
    main = func.FuncOp(main_name, ((), ()), Region(Block([*b.locals.values(), *body])))
    declarations = []
    for name, module in b.procedures.items():
        decl = func.FuncOp.external(name, [], [])
        decl.attributes["module"] = StringAttr(module)
        declarations.append(decl)
    for name, module in b.symbols.items():
        stub = llvm.GlobalOp(llvm.LLVMArrayType.from_size_and_type(1, i8), name, "external")
        stub.attributes["module"] = StringAttr(module)
        declarations.append(stub)
    header = CommentOp([
        "Generated by xdsl_ccpp's --capture-test-driver-dir: replays the captured calls of",
        f"{scheme_name} ({', '.join(t for t, _, _ in phase_tables)})",
        "in lifecycle order and compares the outputs with the captured 'after' values.",
        "Not hand-maintained: regenerate rather than edit.",
    ])
    return ProgramOp(f"test_{scheme_name}", main_name, [header, *declarations, main])
