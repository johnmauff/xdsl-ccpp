"""acc-derive-memory-space, stage 2: set scheme arguments' memory_space from
their entry points' own OpenACC (fparser2_to_meta._classify_acc_residency),
for a generation with --directive acc.

Applied by ccpp_dsl to the frontend module before ccpp_opt, so every pass
sees the derived value exactly as if the .meta had declared it. Only
arguments whose .meta is silent are touched: an explicit memory_space
(device, host or unified) always wins.

- "device" (present, deviceptr, update, use_device, default(present)):
  memory_space = device.
- "either" (a copy clause, or an array in a compute construct with no
  clause): the scheme works with host data (it copies the data itself) and
  with data already on the device (it then uses that copy). Rule (a),
  decided 2026-11-02: it becomes device only when the variable is device
  data elsewhere -- some other scheme argument or host variable with the
  same standard name has memory_space = device (declared or derived
  "device") -- and otherwise stays host. Leaving it host while the
  variable is on the device would be wrong: the cap would `update device`
  after the call and overwrite the scheme's device result with the stale
  host copy. Making it always device would change caps (RRTMGP's
  wrappers copy plain arrays no other scheme keeps on the device).

Derived-type arguments are never classified (the scheme moves its own
derived-type data). This module reads and sets CCPP metadata only.
"""

from __future__ import annotations

from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TableTypeKind

DEVICE = "device"
EITHER = "either"


def _arg_tables(module: builtin.ModuleOp):
    for op in module.walk():
        if isinstance(op, ArgumentTableOp):
            yield op


def _args(table: ArgumentTableOp):
    for op in table.body.block.ops:
        if isinstance(op, ArgumentOp):
            yield op


def _std_name(arg: ArgumentOp) -> str | None:
    return arg.standard_name.data.lower() if arg.standard_name is not None else None


def apply_derived_memory_space(
    module: builtin.ModuleOp, classification: dict[str, dict[str, str]]
) -> list[str]:
    """Set memory_space = device on the scheme arguments of *module* that
    *classification* (entry point -> {argument: "device" | "either"}, all
    lowercase) and rule (a) put on the device, where the .meta is silent.
    Returns one line per argument set, for --verbose 2."""
    scheme_args: list[tuple[str, ArgumentOp, str]] = []
    device_names: set[str] = set()
    for table in _arg_tables(module):
        is_scheme = table.table_type.data == TableTypeKind.Scheme
        table_name = table.table_name.data.lower()
        uses = classification.get(table_name, {}) if is_scheme else {}
        for arg in _args(table):
            declared = arg.memory_space.data if arg.memory_space is not None else None
            if declared == DEVICE:
                if _std_name(arg):
                    device_names.add(_std_name(arg))
                continue
            category = uses.get(arg.arg_name.data.lower())
            if declared is None and category is not None:
                scheme_args.append((table_name, arg, category))
                if category == DEVICE and _std_name(arg):
                    device_names.add(_std_name(arg))

    report: list[str] = []
    for table_name, arg, category in scheme_args:
        if category == EITHER and _std_name(arg) not in device_names:
            continue
        arg.properties["memory_space"] = StringAttr(DEVICE)
        why = (
            "its OpenACC requires it on the device"
            if category == DEVICE
            else "the scheme copies it itself, and it is device data elsewhere"
        )
        report.append(f"{table_name}: '{arg.arg_name.data}' memory_space = device ({why})")
    return report
