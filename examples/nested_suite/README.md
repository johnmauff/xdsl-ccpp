# nested_suite

Ported from NCAR/ccpp-framework's `feature/capgen-v1` branch,
`end-to-end-tests/nested_suite`. This example exists to exercise real,
non-synthetic **cross-file suite composition** and **suite-level
`<init>`/`<final>` scheme hooks** — the two features introduced by the
SDF v2.0 schema bump, confirmed against the real upstream Python source
(`capgen/metadata/parse_tools/xml_tools.py`'s `expand_nested_suites`,
`capgen/generator/suite_resolver.py`'s suite-level `<init>`/`<final>`
resolution) rather than guessed from the schema alone.

## The capabilities this example exercises

### `<nested_suite>` cross-file composition

`main_suite.xml` splices in groups/schemes from four other suite XML files,
at both suite level and group level, recursively (2 levels deep in one
branch):

```xml
<suite name="main_suite" version="2.0">
  <init>suite_lifecycle</init>
  <group name="radiation1">
    <subcycle loop="num_subcycles_for_effr">
      <scheme>effr_pre</scheme>
      <subcycle loop="2"><subcycle loop="2"><scheme>effr_calc</scheme></subcycle></subcycle>
      <scheme>effr_post</scheme>
    </subcycle>
    <nested_suite name="radiation2_suite" group="effrs_calc" file="radiation2_suite.xml"/>
  </group>
  <nested_suite name="radiation4_suite" group="rad_lw_group" file="radiation4_suite.xml"/>
  <nested_suite name="radiation3_suite" file="radiation3_suite.xml"/>
  <final>suite_lifecycle</final>
</suite>
```

`radiation2_suite.xml`'s own `effrs_calc` group (an `effrs_calc` subcycle
plus an `effr_diag` scheme call) is declared inside `<group
name="radiation1">`, so it splices in unwrapped, merging directly into
`radiation1`'s own sequence. `radiation4_suite.xml`'s `rad_lw_group` is
referenced at the *suite* level, so it becomes a brand-new top-level group
of that name. `radiation3_suite.xml` is referenced with no `group=` at all,
so its own `rad_sw_group` (itself pulled in from a *second* file,
`radiation3_subsuite.xml`, one level deeper) carries straight through. The
expanded suite ends up with exactly three groups — `radiation1`,
`rad_lw_group`, `rad_sw_group` — matching
`test_nested_suite_integration.F90`'s own hardcoded `test_parts1` exactly.

xdsl-ccpp previously had no support for `<nested_suite>` at all — the
frontend parser only ever read one file and only recognized `<group>`
children, silently ignoring anything else. **Fixed** with a pure XML-tree
preprocessing pass (`ccpp_xml.py`'s `_expand_nested_suites`/
`_replace_nested_suite`/`_load_nested_suite_reference`), run once, entirely
before any group/scheme/subcycle object is built — mirroring capgen-v1's
own `expand_nested_suites` closely, including its more subtle rules
(suite-level `<nested_suite>` with a named `group=` gets its content
re-wrapped in a fresh group; relative `file=` paths always resolve against
the *original top-level* suite file's own directory, not whichever file a
given reference happens to live in). Because expansion happens before any
object exists, nothing downstream (the IR, `suite_cap.py`, `cap_shared.py`,
`suite_variable_model.py`) needed to change at all. See
`tests/unit/test_nested_suite_expansion.py` for direct regression coverage
(sabotage-verified) and `ccpp_cap_refactor_plan.md`'s backlog for the full
history.

### Suite-level `<init>`/`<final>` scheme hooks

`suite_lifecycle.F90` is a minimal scheme with *only* `_init`/`_final`
entry points (no `_run`), incrementing a shared `lifecycle_counter`.
Declared as direct children of `<suite>` (not inside any group), these run
once per suite lifecycle rather than once per group. This example's own
pass condition (`test_host_mod.F90`'s `compare_data()`) checks
`lifecycle_counter == 2` — one increment from init, one from final — a
clean, direct signal for this feature specifically, independent of the
radiation/effr numerics inherited from `var_compat`.

xdsl-ccpp had no concept of a suite-level lifecycle hook at all. **Fixed**
across three layers: the frontend parses `<init>`/`<final>` into
`XMLSuite.init_scheme`/`final_scheme`; two new optional properties on
`ccpp.SuiteOp` (and its IR-reconstruction mirror in `ccpp_descriptors.py`)
carry the scheme name through; `suite_cap.py`'s `_build_suite_lifecycle_call_ops`
resolves the named scheme's own `_init`/`_final` phase (note: `_final`, not
this codebase's own group-scheme `_finalize` convention — confirmed against
`suite_lifecycle.F90`'s actual subroutine names) against its
`HostVariableMatchPass`-annotated host match, and emits exactly one guarded
call inside the suite's own `_suite_initialize`/`_suite_finalize` bodies —
after the ordinary per-scheme calls, before the suite-state transition,
mirroring capgen-v1's own placement. A suite declaring neither hook is
completely unaffected (confirmed: every existing example's generated output
is byte-identical). See `tests/unit/test_suite_lifecycle_hooks.py` for
direct regression coverage (sabotage-verified) and
`ccpp_cap_refactor_plan.md`'s backlog for the full history.

## Adaptations made during porting (not present in the upstream capgen-v1 files)

Both of this example's own new capabilities generated correctly against the
real upstream files on the first generation attempt — no generator bugs
were found porting this example (unlike `var_compat`, which surfaced
several). The adaptations below are the same small, mechanical category
`var_compat`'s own port already established:

- `effr_pre.F90`/`module_rad_ddt.F90` module renames (`mod_effr_pre` →
  `effr_pre`, `mod_rad_ddt` → `module_rad_ddt`, and the corresponding
  `module_name` attribute drops from the `.meta` files) — reused
  `var_compat`'s own already-fixed copies of these files directly, since
  the underlying scheme/DDT content is otherwise identical.
- `test_host_mod.meta`'s `type = host` isn't the correct xdsl-ccpp type for
  a plain Fortran data module (as opposed to the host control/dispatch
  table, `test_host.meta`, which genuinely is `type = host`) — changed to
  `type = module`, matching `var_compat`'s own identical adaptation for the
  same file shape.
- `test_host.meta`/`test_host_data.F90`/`test_host_data.meta`: reused
  `var_compat`'s own already-adapted copies directly (byte-identical
  content needed — the host control API surface and `physics_state` DDT
  shape don't differ between the two examples).
- `test_host.F90` (the driver): reused `var_compat`'s own copy completely
  unmodified — it already loops generically over however many suite parts
  a suite declares (`do index = 1, size(test_suites(sind)%suite_parts)`),
  so it works for this example's three parts with zero changes.
- **Not needed here, unlike `var_compat`**: the `.meta` argument-bracket
  tight-vs-spaced normalization — every occurrence in this example's own
  upstream files uses the tight `[name]` form, accepted directly now that
  the bracket-spacing parser fix has landed.
- `test_nested_suite_integration.F90` adapted from capgen-v1's own
  `test_nested_suite_integration.F90` (same `test_prog`/`suite_info`/
  `cm`/`cs` harness as every other example), with its
  `'nested_suite: TEST PASSED'`/`'nested_suite: TEST FAILED'` print line
  added for consistency with every other example in this repo.

## Verification status

Confirmed via the real `Makefile` path (`make -f examples/nested_suite/Makefile
caps`): generation completes cleanly, `main_suite_cap.F90` produces exactly
the three expected group subroutines (`main_suite_suite_radiation1`,
`main_suite_suite_rad_lw_group`, `main_suite_suite_rad_sw_group`), the
`col_start`/`col_end` column-chunk slicing already fixed for `var_compat`
carries over correctly with zero extra work
(`phys_state%effrr(col_start:col_end, 1:pver)`,
`phys_state%fluxLW(col_start:col_end)`), and the suite-level `<init>`/
`<final>` calls appear exactly where expected
(`main_suite_suite_initialize`/`main_suite_suite_finalize`, each with a
correct `use suite_lifecycle, only: ...` stub and a correctly host-matched
`lifecycle_counter` reference). Full unit + FileCheck suite green throughout
(525 passed, same 1 pre-existing xfail and 1 pre-existing unrelated failure
as before this work).

**Not yet verified:** an actual `gfortran`/`ifx` build-and-run — this
laptop has no Fortran compiler. `make check` needs to be run on real
hardware to confirm `lifecycle_counter == 2` and the inherited
radiation/effr numeric checks all pass.

## Files

| File | Description |
|------|-------------|
| `main_suite.xml` | Top-level suite: `<init>`/`<final>` hooks, one real group, three `<nested_suite>` references |
| `radiation2_suite.xml` | Referenced by `main_suite.xml`'s `radiation1` group (group-level splice, unwrapped) |
| `radiation3_suite.xml` | Referenced by `main_suite.xml` at suite level with no `group=` (whole-suite splice) |
| `radiation3_subsuite.xml` | Referenced by `radiation3_suite.xml` — the 2nd level of nesting |
| `radiation4_suite.xml` | Referenced by `main_suite.xml` at suite level with `group=` (fresh-group-wrapped splice) |
| `suite_lifecycle.meta`/`.F90` | The suite-level `<init>`/`<final>` hook scheme (init/final-only, increments `lifecycle_counter`) |
| `effr_pre`/`effr_calc`/`effr_post`/`effrs_calc`/`effr_diag`/`rad_lw`/`rad_sw`/`module_rad_ddt` | Reused from `var_compat` (same schemes, same DDT) |
| `test_host_mod.meta`/`.F90`, `test_host_data.meta`/`.F90`, `test_host.meta`/`.F90` | Host model, data DDT, and control/dispatch driver |
| `test_nested_suite_integration.F90` | Integration test: expects 3 suite parts, checks `lifecycle_counter == 2` plus inherited radiation numerics |
