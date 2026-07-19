# Multi-Instance Support

**Status: implemented.** This document previously described multi-instance
`ccpp_t` support as a future plan; it has since shipped. Kept as a short
reference to where the implementation and its tests live, rather than
deleted outright, since the design choices below (standard name, type
source, instance cap) are otherwise not written down anywhere else.

## What's implemented

- **`ccpp_t` handle**: a host `.meta` variable of `type = ccpp_t` is
  recognized by `host_var_match_pass.py` (matching on
  `CCPP_T_INSTANCE_STD_NAME = "ccpp_t_instance"`, defined in
  `xdsl_ccpp/util/ccpp_conventions.py`) and recorded as a `ccpp.ccpp_handle`
  op (`CcppHandleOp` in `xdsl_ccpp/dialects/ccpp.py`).
- **Type source**: xdsl-ccpp does not define its own `ccpp_t` — generated
  code depends on the framework's type via `use ccpp_types, only: ccpp_t`
  (see `xdsl_ccpp/backend/print_ftn.py`).
- **Threading**: the handle is threaded through every generated lifecycle
  and run subroutine signature (`suite_cap.py`, `ccpp_cap.py`,
  `lifecycle_cap.py`, `run_dispatch.py`, `print_ftn.py`).
- **Per-instance state**: the module-level `initialized` scalar became
  `ccpp_suite_state`, a `character(len=16), dimension(<num_instances>)`
  array indexed by `ccpp_data%ccpp_instance`, tracking a state string
  (`'uninitialized'` / `'initialized'` / `'in_time_step'`) rather than a
  plain boolean.
- **Instance cap**: configurable via `--num-instances`, but only on the
  low-level `xdsl_ccpp.frontend.ccpp_xml` frontend module (see
  DEVELOPERS.md's "Running the Pipeline Manually" for how to compose it with
  `ccpp_opt` by hand) — **not** on the main `ccpp_xdsl` driver
  (`xdsl_ccpp/tools/ccpp_dsl.py`), which doesn't expose this flag at all
  (confirmed 2026-07-19: `ccpp_xdsl --help` has no `--num-instances`/instance
  option, and passing it to `ccpp_xdsl` fails with "unrecognized arguments").
  The value is embedded as the `ccpp.num_instances` IR attribute either way;
  defaults to `CCPP_NUM_INSTANCES = 200` (`xdsl_ccpp/util/ccpp_conventions.py`)
  when not passed. That file's own `# TODO: expose via --num-instances CLI
  argument` comment (directly above the constant) is accurate, not stale —
  it's specifically about wiring this into the `ccpp_xdsl` driver, which
  hasn't happened yet.

## Where to look

- Unit tests: `tests/unit/test_ccpp_t_threading.py`
- End-to-end golden output: `tests/filecheck/examples/end_to_end/helloworld-ccpp-t.mlir`
  (generated from `examples/helloworld/hello_world_host_ccpp_t.meta`)
