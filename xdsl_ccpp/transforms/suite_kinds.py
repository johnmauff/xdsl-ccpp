from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.util.ccpp_conventions import CCPP_KIND_TO_ISO, parse_kind_spec_value


def _collect_metadata_kind_specs(ccpp_module: builtin.ModuleOp) -> dict[str, tuple[str, str]]:
    """Aggregate ``kind_spec`` declarations across every table in *ccpp_module*.

    Returns ``kind_name -> (module, spec)``.  Mirrors real capgen-v1's own
    ``ccpp_capgen.py:_collect_metadata_kind_specs``: multiple tables may
    declare the same kind_name, as long as they agree; a genuine conflict
    (same kind_name, different module/spec) is a hard error, since silently
    picking one would generate Fortran that only accidentally matches one of
    the tables that asked for it.
    """
    resolved: dict[str, tuple[str, str]] = {}
    for table_prop_op in ccpp_module.body.ops:
        if not isa(table_prop_op, ccpp.TablePropertiesOp):
            continue
        kind_specs_attr = table_prop_op.attributes.get("kind_specs")
        if kind_specs_attr is None:
            continue
        table_name = table_prop_op.table_name.data
        for entry in kind_specs_attr.data:
            kind_name, module, spec = parse_kind_spec_value(entry.data)
            existing = resolved.get(kind_name)
            if existing is not None and existing != (module, spec):
                raise ValueError(
                    f"Conflicting kind_spec for kind '{kind_name}': table "
                    f"'{table_name}' declares '{module}:{spec}' but another "
                    f"table already declared '{existing[0]}:{existing[1]}'"
                )
            resolved[kind_name] = (module, spec)
    return resolved


@dataclass(frozen=True)
class MetaKind(ModulePass):
    """Pass that discovers real kind parameters from CCPP metadata and records them.

    Runs after ``generate-meta-cap``, which has already consolidated all CCPP IR
    into the ``@ccpp`` named module.  This pass walks every ``ccpp.arg`` op inside
    that module and collects the unique kind names attached to ``real`` arguments
    (e.g. ``kind_phys``).

    If any are found, a single ``ccpp.kinds`` op is prepended to the ``@ccpp``
    module's body, containing one ``ccpp.kind`` op per unique kind name.  The
    kind ops appear in the order they were first encountered.

    If no real kinds are present, the ``@ccpp`` module is left unchanged.

    Pipeline position: generate-meta-cap → **generate-meta-kinds** → generate-suite-cap

    Parameters
    ----------
    kind_map:
        Optional pipe-separated ``KIND:ISO`` pairs that supplement the built-in
        ``CCPP_KIND_TO_ISO`` table for this invocation only.
        Example: ``kind_dyn:REAL32|kind_ext:REAL128``
    """

    name = "generate-meta-kinds"
    extra_kind: str | None = None   # extra kind name, e.g. kind_dyn
    extra_iso:  str | None = None   # matching ISO_FORTRAN_ENV constant, e.g. REAL32

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        # Locate the @ccpp named module created by generate-meta-cap
        ccpp_module = None
        for inner_op in op.body.ops:
            if (
                isa(inner_op, builtin.ModuleOp)
                and inner_op.sym_name is not None
                and inner_op.sym_name.data == "ccpp"
            ):
                ccpp_module = inner_op
                break

        if ccpp_module is None:
            return

        # Collect unique real kind names in encounter order.
        # Use a dict as an ordered set (insertion-ordered since Python 3.7).
        kind_names: dict[str, None] = {}

        for table_prop_op in ccpp_module.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    # A real arg with a named kind qualifier (not a len= qualifier,
                    # and not a bare numeric kind literal e.g. `kind = 8` -- that's
                    # already valid, self-contained Fortran (`real(kind=8)`) with no
                    # ccpp_kinds dependency, so treating it as a symbolic name to
                    # declare/export would emit an invalid `public :: 8`).
                    if (
                        arg_op.arg_type.data == "real"
                        and arg_op.kind is not None
                        and "len=" not in arg_op.kind.data
                        and not arg_op.kind.data.isdigit()
                    ):
                        kind_names[arg_op.kind.data] = None

        if not kind_names:
            return

        # A metadata-declared kind_spec (a table's own [ccpp-table-properties]
        # `kind_spec = <module>:<kind_name>=>spec`) takes priority over the
        # hardcoded ISO_FORTRAN_ENV table below -- it's an explicit statement
        # of where this kind really comes from, matching real capgen-v1's own
        # precedence (metadata kind_spec / --kind-type over any built-in
        # default).
        meta_kind_specs = _collect_metadata_kind_specs(ccpp_module)

        # Build one ccpp.kind op per unique kind name.
        # Known kind names are mapped to their ISO_FORTRAN_ENV equivalents;
        # unrecognised kinds fall back to using the kind name as the value.
        # Both are still consulted for any kind name with no metadata
        # kind_spec, so every existing example's implicit kind_phys=REAL64
        # resolution is unchanged.
        _KIND_VALUES = dict(CCPP_KIND_TO_ISO)  # local copy — don't mutate the module-level dict
        if self.extra_kind and self.extra_iso:
            _KIND_VALUES[self.extra_kind] = self.extra_iso
        kind_ops = []
        for kind_name in kind_names:
            if kind_name in meta_kind_specs:
                module, spec = meta_kind_specs[kind_name]
                kind_ops.append(ccpp.KindOp(kind_name, spec, module))
            else:
                kind_ops.append(ccpp.KindOp(kind_name, _KIND_VALUES.get(kind_name, kind_name)))

        kinds_op = ccpp.KindsOp(kind_ops)
        Rewriter.insert_op(kinds_op, InsertPoint.at_start(ccpp_module.body.block))
