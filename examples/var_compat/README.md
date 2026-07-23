# var_compat

Ported from NCAR/ccpp-framework's `feature/capgen-v1` branch,
`end-to-end-tests/var_compat`. This example exists to exercise real,
non-synthetic **nested `<subcycle>` support**.

## The capability this example exercises

`var_compatibility_suite.xml`'s `radiation` group nests `<subcycle>` three
levels deep in one branch (a dynamic-count subcycle containing two nested
`loop="2"` subcycles), plus two sibling subcycles that share the same
dynamic-count standard_name (`num_subcycles_for_effr`):

```xml
<subcycle loop="num_subcycles_for_effr">
  <scheme>effr_pre</scheme>
  <subcycle loop="2">
    <subcycle loop="2">
      <scheme>effr_calc</scheme>
    </subcycle>
  </subcycle>
  <scheme>effr_post</scheme>
</subcycle>
<subcycle loop="num_subcycles_for_effr">
  <scheme>effrs_calc</scheme>
</subcycle>
```

xdsl-ccpp originally rejected nested subcycles outright (a deliberate,
documented restriction at three separate entry points: the XML parser, IR
reconstruction, and the Python suite-authoring DSL) — this example was
ported specifically to prove that gap with a real, non-synthetic suite, and
then to serve as the test vehicle for closing it. **Recursive nested-subcycle
support has since been implemented** against this exact example (XML
parsing, IR reconstruction, scheme enumeration, and Fortran do-loop codegen
all handle arbitrary nesting depth now), and `make caps`-equivalent
generation succeeds end-to-end for this suite. See
`tests/filecheck/examples/{frontend,completed_ir,end_to_end}/var_compat-xml.mlir`
for the regression coverage, and `ccpp_cap_refactor_plan.md`'s backlog for
the full history, including two real bugs (a duplicate and a missing
Fortran variable declaration) this work found and fixed along the way.

## Other features this example carries, not addressed by this port

Nested-subcycle support has landed (see above) and `make caps`-equivalent
generation now succeeds end-to-end for this suite (confirmed by running
`python3 -m xdsl_ccpp.tools.ccpp_dsl` directly against these files). Even so,
don't expect this example to be fully numerically correct, or even
compilable, on every variable — a few of its real capgen-v1 features are
separate, already-tracked backlog items, not part of the nested-subcycle
work:

- **Vertical array flipping (`top_at_one`)** — `effr_calc`'s `effrr_in`/
  `effrs_inout` and `effr_diag`'s `effrr_in` declare `top_at_one = True`.
  Confirmed completely unimplemented in xdsl_ccpp today (zero references
  anywhere) — generation emits an "unrecognised key" warning and silently
  ignores it, not a crash, but numerically incomplete for those variables
  specifically.
- **Kind conversion (`kind_phys` vs `kind = 8`) — confirmed working.**
  `effr_calc`'s `effrs_inout` declares `kind = 8` while every other
  occurrence of the same standard_name uses `kind_phys`. Confirmed by
  actually running generation: it's detected, warned about, and handled —
  the generated `var_compatibility_suite_suite_radiation` allocates a
  `real(kind=8)` cast temporary, casts in before the call sequence, and
  casts back out afterward.
- **Unit conversion — table entries added, plus a real cross-scheme
  marshaling bug found and fixed.** `effr_pre`'s `effrr_inout` (units `m`)
  vs `effr_calc`'s `effrr_in` (units `um`), same standard_name — and several
  others in this suite (`km`/`m`, `j kg-1`/`m2 s-2`, `m+2 s-2`/`m2 s-2`).
  `UNIT_CONVERSIONS` (`xdsl_ccpp/util/ccpp_conventions.py`) now has entries
  for all of these; `m+2 s-2`/`m2 s-2` turned out to be the identical unit
  written two ways, fixed via a `normalize_units` tweak rather than a real
  conversion factor.

  Regenerating this example's real output after adding those entries
  surfaced something bigger: two standard_names here are declared with
  genuinely different units or kind by *different schemes*, not just
  different from the host. `effr_pre`/`effr_post` declare the rain-particle
  radius (`effective_radius_of_stratiform_cloud_rain_particle`) in meters,
  matching the host; `effr_calc`/`effr_diag` declare the *same*
  standard_name in micrometers. `effrs_calc` declares the snow-particle
  radius in meters/`kind_phys`, matching the host; `effr_calc` declares the
  *same* standard_name in micrometers/`kind = 8`. `suite_cap.py` used to
  build one combined suite-level dummy argument per standard_name, convert
  it once against the host based on whichever scheme's declaration happened
  to be first in scheme order, and pass that same converted value to every
  other scheme sharing the name — so `effr_calc`/`effr_diag` were silently
  receiving the rain-particle radius still in raw meters (off by a factor of
  a million, no warning at all), and `effrs_calc` was silently receiving the
  snow-particle radius already converted to micrometers/`kind = 8` for
  `effr_calc`'s benefit, when its own declaration needed no conversion at
  all.

  **Fixed**: `_build_arg_tables` now flags a standard_name as divergent when
  two or more schemes sharing it disagree on kind or units with each other.
  For a divergent standard_name, the suite-level dummy argument stays in the
  host's own native representation for the whole function body, and
  `generateSchemeSubroutineCallOps` independently marshals *each individual
  call* to that call's own scheme's already-known mismatch against the host
  (detected per-scheme, completely independently, by
  `HostVariableMatchPass` all along) — converting immediately before the
  call and writing back immediately after, reusing the same
  `KindCastOp`/`UnitConvertOp`/`KindWriteBackOp`/`UnitWriteBackOp` already
  used for the ordinary case. Every non-divergent standard_name is
  completely unaffected. See
  `tests/unit/test_suite_cross_scheme_unit_kind.py` for direct regression
  coverage and `ccpp_cap_refactor_plan.md`'s backlog for the full writeup.
- **Dummy-argument-name collision — found here, fixed in `suite_cap.py`,
  unrelated to subcycling, and not a `.meta`-authoring mistake.**
  `effr_pre`/`effr_calc`/`effr_post`/`effr_diag` each independently use the
  bare Fortran name `scalar_var` for four different, unrelated
  standard_names (`scalar_variable_for_testing_a`/plain/`_b`/`_c`) —
  correct, idiomatic CCPP metadata: a scheme's local arg name is private and
  arbitrary by design, only `standard_name` needs to be consistent.
  `test_host_data.meta` (this example's own real host metadata) gives all
  four standard_names distinct, collision-free local names of its own
  (`scalar_var`/`scalar_varA`/`scalar_varB`/`scalar_varC`) precisely so a
  generated cap can use the host's name instead of each scheme's.
  `suite_cap.py`'s signature construction now detects the collision and
  falls back to the host-matched canonical name (`model_var_name`) for just
  the colliding entries — every non-colliding arg elsewhere keeps its
  original name, unchanged. The data wiring was fixed alongside the printed
  name: each colliding scheme's own value is now tracked by argument
  position (not by the colliding bare name) so every scheme call still
  receives its own correct value. This requires the `generate-host-match`
  pass to run — which the production `ccpp_xdsl` tool always does whenever
  host files are supplied, so `make caps`/`run`/`check` below need no special
  invocation. See `tests/unit/test_suite_arg_name_collision.py` for direct
  regression coverage and `ccpp_cap_refactor_plan.md`'s backlog for the full
  writeup. This is the same general *class* of bug as the `ccpp_loop_cnt`
  duplicate-declaration bug this work found and fixed (two unrelated things
  independently choosing the same bare name, with no de-duplication step),
  but a different, unrelated site — it has nothing to do with subcycling and
  would occur in any suite with this naming pattern.

## Adaptations made during porting (not present in the upstream capgen-v1 files)

- `effr_pre.F90`'s Fortran module was renamed from `mod_effr_pre` to
  `effr_pre`, and the corresponding `module_name = mod_effr_pre` attribute
  was dropped from `effr_pre.meta`. `module_rad_ddt.F90`'s module was
  similarly renamed from `mod_rad_ddt` to `module_rad_ddt` (and both
  `module_name = mod_rad_ddt` attributes dropped from
  `module_rad_ddt.meta`). xdsl-ccpp's `.meta` parser does not support a
  `module_name` override on `[ccpp-table-properties]` (only `name`/`type`/
  `dependencies`/`relative_path`/`array_layout`/`language`) — it assumes the
  Fortran module name matches the table/file name, which these two files'
  real capgen-v1 content didn't. Purely a naming change; no behavior change.
- Several `.meta` files use a bracket-without-surrounding-space argument
  style (e.g. `[effrr_in]` rather than `[ effrr_in ]`), which xdsl-ccpp's
  line-oriented `.meta` parser doesn't accept (it uses the presence of a
  surrounding space to distinguish an argument-name bracket from a
  `[ccpp-table-properties]`/`[ccpp-arg-table]` header). Normalized to the
  spaced form everywhere it appeared — a whitespace-only change, no
  standard_names/types/attributes/structure altered.
- `test_host.meta`'s `type = control` (used for capgen-v1's own `test_host`
  control table) isn't a recognized xdsl-ccpp table type (only `scheme`/
  `module`/`ddt`/`host`) — changed to `type = host`, matching every other
  xdsl-ccpp example's host-control table. Also dropped `suite_name`/
  `group_name`/`thread_num`/`nthreads`/`nphys_threads` (capgen-v1's own
  framework threads these as extra dispatch args — see the `chunked_data`/
  `instances` backlog items for the related, separate multi-threaded-dispatch
  capability gap) and added the `suite_info` DDT stub table, matching
  examples/advection's test_host.meta exactly.
- `test_host.F90`'s `test_host` driver was rewritten to call xdsl-ccpp's
  actual generated cap function names/signatures (`test_host_ccpp_physics_register`/
  `_initialize`/`_timestep_initial`/`_run`/`_timestep_final`/`_finalize`,
  matching examples/advection's own driver) instead of capgen-v1's own
  framework's `ccpp_register`/`ccpp_init`/`ccpp_physics_init`/... naming and
  `thread_num`/`nthreads`/`nphys_threads`-bearing call signature. Same
  register → initialize → per-timestep(run over `col_start`/`col_end`
  chunks) → finalize structure as the real test, just calling the
  cap functions this project's generator actually produces.
- `test_var_compat_host_integration.F90` is adapted from capgen-v1's
  `test_var_compatibility_integration.F90` (same `test_prog`/`suite_info`/
  `cm`/`cs` harness, same expected suite input/output/required variable
  lists), restructured to match examples/advection's driver shape and with
  its `'var_compat: TEST PASSED'`/`'var_compat: TEST FAILED'` print line
  added for consistency with every other example in this repo.

## Schemes

| Scheme | Entry points | Description |
|--------|-------------|-------------|
| `effr_pre` | `_init`, `_run` | Pre-processes rain effective radius before the nested subcycle |
| `effr_calc` | `_init`, `_run` | Effective-radius calculation, called inside a 3-level-deep nested subcycle |
| `effr_post` | `_init`, `_run` | Post-processes rain effective radius after the nested subcycle |
| `effrs_calc` | `_run` | Snow effective-radius calculation, in its own sibling dynamic-count subcycle |
| `effr_diag` | `_init`, `_run` | Diagnostic pass over rain effective radius |
| `rad_lw` | `_run` | Longwave radiation fluxes (DDT-typed array argument, `ty_rad_lw`) |
| `rad_sw` | `_run` | Shortwave radiation fluxes (per-member real array arguments) |

## Files

| File | Description |
|------|-------------|
| `var_compatibility_suite.xml` | Suite definition (the nested-subcycle structure under test) |
| `effr_pre.meta`/`.F90` | Metadata + source for `effr_pre` |
| `effr_calc.meta`/`.F90` | Metadata + source for `effr_calc` |
| `effr_post.meta`/`.F90` | Metadata + source for `effr_post` |
| `effrs_calc.meta`/`.F90` | Metadata + source for `effrs_calc` |
| `effr_diag.meta`/`.F90` | Metadata + source for `effr_diag` |
| `rad_lw.meta`/`.F90` | Metadata + source for `rad_lw` |
| `rad_sw.meta`/`.F90` | Metadata + source for `rad_sw` |
| `module_rad_ddt.meta`/`.F90` | `ty_rad_lw`/`ty_rad_sw` DDT definitions |
| `test_host_data.meta`/`.F90` | Host DDT metadata + source (`physics_state`) |
| `test_host_mod.meta`/`.F90` | Host module metadata + source |
| `test_host.meta`/`.F90` | Host control metadata + source (`test_host`/`suite_info`) |
| `test_var_compat_host_integration.F90` | Test driver program |

## Running with ccpp_xdsl

```
make caps   # generate the suite/ccpp/kinds caps
make run    # build and run
make check  # build, run, and verify pass/fail
```
