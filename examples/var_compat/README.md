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

**Naming note:** the investigation notes below (and elsewhere in this file)
reference generated subroutine names like `test_host_ccpp_physics_run` /
`VarCompatibility_ccpp_physics_run` -- this reflects the naming convention
at the time each note was written. Since the vocabulary-resolution
redesign's Stage 5 (`ccpp_cap_refactor_plan.md`), the six lifecycle
dispatchers use bare, capgen-v1-style names instead (`ccpp_register`/
`ccpp_init`/`ccpp_physics_timestep_init`/`ccpp_physics_run`/
`ccpp_physics_timestep_final`/`ccpp_final`) -- the module itself
(`test_host_ccpp_cap`/`VarCompatibility_ccpp_cap`) is still host-prefixed,
unchanged. Left as-is below rather than rewritten throughout, to preserve
each note as an accurate record of what was actually observed at the time.

## Other features this example carries, not addressed by this port

Nested-subcycle support has landed (see above), and the dummy-argument-name
collision, unit conversion, cross-scheme kind/unit divergence, and vertical
array flipping items below are all now implemented and verified against
this example's real generated output. Actually building it with gfortran for
the first time (rather than just inspecting generated text) surfaced two
more known issues:

- **Fixed — `module_rad_ddt.meta` was missing from this port's generation
  inputs (a port mistake, not an `xdsl_ccpp` code gap).** The real
  capgen-v1 source keeps `rad_lw`/`rad_sw`'s DDT type definitions
  (`ty_rad_lw`/`ty_rad_sw`) in their own separate file rather than bundled
  into a scheme's own `.meta` (unlike e.g. `examples/ddthost`'s
  `make_ddt.meta`, which declares its DDT type and the scheme that uses it
  in the same file) — but this port's `--scheme-files` list (in the
  Makefile and the three `tests/filecheck` goldens) never included
  `module_rad_ddt.meta`, so its DDT table definitions were never parsed at
  all. This silently caused two separate, real symptoms once actually
  compiled: the suite-cap module declared `fluxLW` as `type(ty_rad_lw)`
  without ever importing the module that defines it, and `rad_sw_run`'s
  `sfc_up_sw`/`sfc_down_sw` arguments (DDT-member standard_names) were
  silently dropped from the suite signature entirely, since the DDT-member
  matching machinery had no DDT definition to match against. Fixed by
  adding `module_rad_ddt.meta` to the Makefile's `CAPS_SCHEMES` and all
  three `var_compat-xml.mlir` RUN lines — confirmed both symptoms disappear
  with zero `xdsl_ccpp` code changes.
- **Fixed — the dynamic-count subcycle's loop bound
  (`num_subcycles_for_effr`) used to be emitted as the literal standard_name
  string instead of being resolved to the host's own local name
  (`num_subcycles`).** No scheme anywhere declares a matching arg of its own
  for this standard_name (unlike e.g. `scheme_order_in_suite`, which flows
  through the ordinary scheme-arg host-matching path because several schemes
  declare it as their own arg), so it never entered `suite_cap.py`'s
  `all_args` through any existing pathway — no other example in the repo uses
  a named, non-literal subcycle loop count, so this path was never exercised
  before. Fixed by a new `_synthesize_dynamic_loop_count_args` method in
  `suite_cap.py` that scans the suite's subcycle structure for dynamic loop
  counts with no scheme-arg match, resolves the host's own local name for the
  standard_name, and synthesizes a fresh host-matched argument for it — so it
  becomes a genuine, correctly-declared dummy argument the same way any other
  host-matched value does. Scoped to only the `_run` (physics) postfix that
  actually emits a do-loop using it. See `ccpp_cap_refactor_plan.md`'s
  backlog.
- **Fixed — the host-facing wrapper subroutine (generated by `ccpp_cap.py`'s
  `run_dispatch.py`, a separate code path from the suite-cap subroutine the
  fixes above live in) used to declare `scalar_var`/`tke_inout`/`tke2_inout`
  `intent(in)`, while the suite-cap subroutine it calls correctly declares
  them `intent(inout)`** — passing an `intent(in)` actual argument into an
  `intent(inout)` dummy argument is invalid Fortran. These three are
  ordinary scheme-declared inout scalars with no dedicated framework meaning
  of their own (no host match, not `ccpp_error_message`/`ccpp_error_code`,
  not a `ccpp_t` handle); `run_dispatch.py`'s copy-back logic only ever
  handled those three framework cases, so this case had no copy-back at all
  and the wrapper never learned the value needed echoing back. Fixed by a
  new `_get_suite_leading_inout_ret_info` helper (`cap_shared.py`) plus a
  matching dedup fix in `print_ftn.py`'s keyword-call printer (it needed to
  suppress a redundant `_out_N=` echo once the copy-back target is a
  variable already passed as an input — otherwise the same variable gets
  bound twice under two different keyword names, also invalid Fortran). See
  `ccpp_cap_refactor_plan.md`'s backlog.
- **Fixed — two more real `run_dispatch.py` bugs, found after correcting
  `test_host_mod.meta`'s `type = host` → `type = module` typo (see
  `ccpp_cap_refactor_plan.md`'s backlog) still left `scalar_varA`/
  `scalar_varB`/`scalar_varC`/`num_subcycles` unresolved on the host-facing
  wrapper.**
  - *Bare-name collision.* `HostVariableMatchPass` correctly resolves
    `effr_pre`/`effr_post`/`effr_diag`'s own `scalar_var`-named args to their
    distinct `physics_state` DDT members (`scalar_varA`/`scalar_varB`/
    `scalar_varC`), but `run_dispatch.py`'s `local_to_host_info` map was keyed
    by each scheme's own un-renamed local name — since all three literally
    declare `scalar_var`, only the first-processed scheme's entry was ever
    kept, and the wrapper's own dummy args for `suite_cap.py`'s already-
    disambiguated `scalar_varA`/`scalar_varB`/`scalar_varC` had no matching
    key at all. Fixed by grouping host-matched args by bare local name,
    deduplicated by standard_name (mirroring `suite_cap.py`'s own `all_args`
    construction): a bare name with only one distinct standard_name keeps its
    simple key exactly as before, while a bare name genuinely shared by 2+
    distinct standard_names is instead keyed by each sibling's own
    host-matched canonical name — precisely what `suite_cap.py` renamed that
    sibling's dummy argument to.
  - *`num_subcycles` DDT-scan gap.* `num_subcycles` is a suite-level argument
    synthesized entirely by `suite_cap.py`'s `_synthesize_dynamic_loop_count_args`
    (see the loop-bound fix above) — it isn't declared in any scheme's own
    `.meta` at all. The fallback that resolves such a suite-level arg's
    standard_name only ever scanned `HOST`/`MODULE` tables, never `DDT`, so it
    could never discover that `num_subcycles` is really a `physics_state`
    member. Fixed by extending that scan to `DDT` tables too, and folding any
    such match into `local_to_host_info` as a DDT-member entry, so it resolves
    through the existing DDT-access-path machinery instead of falling back to
    a caller-block argument.

  With both fixed, `VarCompatibility_ccpp_physics_run`'s signature collapses
  to exactly `suite_name, suite_part, errmsg, errflg`. See
  `tests/unit/test_run_dispatch_host_wrapper_resolution.py` for direct
  regression coverage (sabotage-verified against both fixes independently)
  and `ccpp_cap_refactor_plan.md`'s backlog for the full writeup.

- **Fixed — `col_start`/`col_end` missing from `VarCompatibility_ccpp_physics_run`,
  found immediately after the fix above: `test_host.F90`'s hand-written call
  (which must not be modified) additionally passes `col_start`/`col_end` (6
  arguments total), 2 more than the signature above.** Diffing against real
  upstream capgen-v1 confirmed this example's schemes genuinely don't chunk
  by column — every one of them is dimensioned by the full
  `horizontal_dimension`, matching upstream's own design, not a porting
  omission. `col_start`/`col_end` only ever enter a suite callee's own
  signature via `suite_cap.py`'s `_classify_args`, which replaces a
  scheme-declared `horizontal_loop_extent` arg with synthetic `col_start`/
  `col_end` scalars — gated entirely on some scheme declaring
  `horizontal_loop_extent`. Since no scheme here does, `run_dispatch.py`'s
  per-suite-arg classification had nothing to discover, and the wrapper's own
  signature never picked them up either — this is true upstream too (its own
  `ccpp_physics_run` bundles `col_start`/`col_end` into a fixed,
  always-present framework argument list regardless of scheme content, a
  convention xdsl-ccpp doesn't otherwise have).

  **Fixed generically for every Fortran example**, not specially for
  `var_compat`: `run_dispatch.py`'s `_build_run_block_signature` now accepts
  `col_start`/`col_end` unconditionally whenever the host itself declares
  `horizontal_loop_begin`/`horizontal_loop_end` (every example's host
  metadata already does) and no suite here already supplied a
  `col_start`/`col_end`-equivalent under some other local name — mirroring
  how `errmsg`/`errflg` are already always present regardless of scheme
  content. Confirmed safe against every other example (`helloworld`,
  `capgen`, `ddthost`, `advection`, and the chost/bind-c examples): all of
  them already receive `col_start`/`col_end` via the pre-existing
  `horizontal_loop_extent`-driven path, and the new fallback correctly
  detects that and adds nothing extra, so their generated output is
  byte-identical. `VarCompatibility_ccpp_physics_run`'s signature is now
  exactly `suite_name, suite_part, col_start, col_end, errmsg, errflg` —
  matching `test_host.F90`'s existing call precisely, in both arity and
  argument order, with zero changes to any hand-written file.

  **One caveat this fix does not (and cannot, from the generator side)
  resolve:** `col_start`/`col_end` are accepted but genuinely unused inside
  `physics_run`'s body, since none of this example's schemes are
  chunk-aware. `test_host.F90` calls this suite part inside a 5-column
  chunking loop, so — if actually compiled and run — the suite executes
  redundantly once per chunk over the *entire* array each time, and
  `effr_calc.F90` has a real accumulation
  (`effrs_inout = effrs_inout + (10.0 / 6.0)`), so the redundant calls would
  over-increment it. That's an inherent mismatch between the driver's
  chunking assumption (modeled on `examples/advection`'s own driver
  convention) and this suite's genuinely unchunked design (matching
  upstream) — not a bug this fix claims to paper over. See
  `tests/unit/test_run_dispatch_col_bounds_fallback.py` for direct
  regression coverage (sabotage-verified, including a guard against
  double-inserting `col_start`/`col_end` for the already-working chunked
  examples) and `ccpp_cap_refactor_plan.md`'s backlog for the full writeup.

- **Fixed — a real `ifx` compile failure, found only by an actual
  standards-strict compiler (gfortran silently accepted the offending
  Fortran, and every FileCheck golden matched it byte-for-byte — this
  survived undetected until an actual build was tried):**
  ```
  error #5192: Lead underscore not allowed
            num_subcycles=phys_state%num_subcycles, _out_0=ccpp_tmp_0, ...
  error #6784: The number of actual arguments cannot be greater than the
               number of dummy arguments.
  error #6627: This is an actual argument keyword name, and not a dummy
               argument name.   [_OUT_0]
  ```
  Root cause, one layer deeper than either symptom: `run_dispatch.py`'s
  `_build_run_dispatch_chain` had no copy-back branch at all for a suite
  callee's own leading `intent(inout)` **scalar** return value when it's
  host-matched to a DDT member (`scalar_var`/`tke_inout`/`tke2_inout`,
  resolved to `phys_state%scalar_var` etc.) rather than a plain
  caller-block argument or plain host/cap-owned module variable — every
  existing branch (`block_arg_map`/`host_var_map`/`cap_var_map`) missed it.
  With no `CopyOp` consumer at all, `print_ftn.py`'s own "untracked call
  result" fallback took over: it invents a throwaway `ccpp_tmp_N` local for
  the value and, in the **plain positional-call path**, prints it as a
  genuine *extra positional argument* — a real arity mismatch that also
  silently shifts every later argument (including `errmsg`/`errflg`) into
  the wrong dummy-argument slot. In the **keyword-call path** (used
  whenever any of the suite's own inputs is optional, so Fortran correctly
  forwards `OPTIONAL` absence status — `var_compat`'s radiation group has
  several optional array args), the same untracked value additionally got
  a synthetic `_out_{i}` placeholder keyword name from a separate list
  comprehension that only recognized `errmsg`/`errflg` by type — invalid
  Fortran on two counts: the leading underscore, and the resulting arity
  mismatch.

  **Fixed with two complementary changes:** (1) a new copy-back branch
  reuses the exact same `HostVarRefOp` already built as the argument's own
  *input* reference as the copy-back target too — functionally a no-op
  (Fortran already reflects the update through the same aliased
  reference), but it gives the result a real `CopyOp` consumer, so it never
  reaches the untracked-call-result fallback at all; this alone fixes the
  positional-call arity bug and eliminates the dead `ccpp_tmp_N`
  declaration entirely, not just its use. (2) The keyword-call path's
  result-name construction was moved after, and now reuses, the same
  leading-inout/trailing-alloc classification the copy-back loop already
  uses, computing each output position's real callee dummy-argument name
  instead of a synthetic placeholder — belt-and-suspenders alongside (1),
  and the only thing needed for positions (1) doesn't cover (a genuine
  trailing alloc-region scalar with no operand-side entry at all, which
  legitimately does need its own real keyword name printed).

  Confirmed via the real `Makefile` path: `test_host_ccpp_physics_run`'s
  call to `var_compatibility_suite_suite_radiation` now has exactly the
  right argument count with no `_out_N`/`ccpp_tmp_N` anywhere. See
  `tests/unit/test_run_dispatch_kw_call_result_names.py` for direct
  regression coverage (sabotage-verified against both the positional- and
  keyword-call symptoms independently) and `ccpp_cap_refactor_plan.md`'s
  backlog for the full writeup.

- **Milestone: `examples/var_compat` builds and runs with `ifx` for the
  first time** — the fix above closed the last real compile blocker. The
  actual run then hit a real *runtime* mismatch (`test_host.F90`'s own
  `check_suite()` compares `ccpp_physics_suite_variables`'s output against
  hardcoded expected counts):
  ```
  ERROR: Found 16 input variable names for suite, var_compatibility_suite, should be 18
  ERROR: Found 15 output variable names for suite, var_compatibility_suite, should be 14
  ERROR: Found 21 required variable names for suite, var_compatibility_suite, should be 22
  ```
  **Fixed — three independent gaps in `ccpp_cap.py`'s `_build_suite_variables_fn`,**
  none previously exercised by any other example:
  1. **Spurious extra output.** `effr_calc`'s `ncl_out`
     (`cloud_liquid_number_concentration`) is `optional`, `intent = out`,
     and no host `.meta` anywhere declares a match for it — it resolves to
     a throwaway cap-owned scratch variable (`lc_ncl_out`) that never
     reaches the host in either direction, but was being listed as a real
     output anyway (declared intent alone drove the old logic). Fixed by
     excluding an *optional*, unmatched, `CapScratch`-classified arg whose
     standard_name isn't a recognized framework array (`ccpp_constituents`
     and friends still correctly appear) — **and** only when host files were
     actually supplied to this run in the first place (a scheme-only
     FileCheck invocation with no `--host-files` at all makes *every*
     scheme var look unmatched, which isn't the same fact) — **and** only
     for genuinely-optional args (a *mandatory* unmatched `CapScratch` arg,
     like `examples/advection`'s own `tendency_of_cloud_liquid_dry_mixing_ratio`,
     represents a real suite requirement, not something silently absent).
  2. **Two missing inputs.** `num_subcycles_for_effr` is a suite-level
     dynamic subcycle loop count synthesized directly by `suite_cap.py`'s
     `_synthesize_dynamic_loop_count_args` — it never becomes a real
     scheme-table `ArgumentOp` anywhere, so the scheme-table scan had
     nothing to discover. Fixed by scanning the suite's own subcycle
     structure directly for non-literal loop counts.
  3. **The other missing input.** `flag_indicating_cloud_microphysics_has_ice`
     is referenced only inside `test_host_data.meta`'s own
     `active = (flag_indicating_cloud_microphysics_has_ice)` conditional-presence
     expressions on the `effri`/`nci` DDT members — never itself a scheme
     argument. `active` is a real `ArgumentOp` property but no pass
     currently evaluates it as a conditional (see the "opt_arg's dead
     `active` property" backlog item); the flag it names is still a
     genuine host requirement regardless. Fixed by scanning every
     `active =` expression module-wide for referenced standard_names —
     scoped to modules with exactly one suite (`examples/capgen` generates
     two suites from one invocation sharing a host file with this same
     `active =` pattern; without the single-suite scope, the referenced
     name leaked into both suites' lists even though only one actually
     uses it).

  All three confirmed via the real `Makefile` path: `ccpp_physics_suite_variables`
  now reports exactly 18 input / 14 output / 22 required variables, matching
  `test_var_compat_host_integration.F90`'s hardcoded expected lists exactly
  (content, not just counts). See `tests/unit/test_suite_variables_gaps.py`
  for direct regression coverage (sabotage-verified against all three fixes
  independently, plus the guard tests for the two false-positive traps found
  along the way) and `ccpp_cap_refactor_plan.md`'s backlog for the full
  writeup.

- **Fixed — a real runtime failure, found by actually running the built
  executable:**
  ```
  ERROR in initialize of var_compatibility_suite: ERROR: effr_pre_init() needs to be called first
  ```
  Root cause, in a third code path from every fix above (none of which touch
  lifecycle — init/finalize/timestep — dispatch): `effr_pre_init`/
  `effr_calc_init`/`effr_post_init`/`effr_diag_init` all share one
  `intent(inout)` `scheme_order` scalar (`scheme_order_in_suite`) that
  `HostVariableMatchPass` correctly resolves to a DDT member,
  `phys_state%scheme_order` — `test_host_data.F90` initializes it to `1`
  before `physics_initialize` runs, and each scheme's own `_init` checks it
  against its expected call position, then increments it, relying on
  Fortran's pass-by-reference semantics to thread the running count across
  the whole call sequence. `lifecycle_cap.py`'s `_generate_lifecycle_fn`
  (covering init/finalize/timestep dispatch, separate from
  `run_dispatch.py`'s "_run" dispatch) only ever checked whether a
  standard_name was a plain `MODULE`-table variable — it had **no
  DDT-member resolution branch at all**. A DDT-member match fell through to
  the same fallback used for genuinely unmatched args: a fresh,
  uninitialized local (`lc_scheme_order`), silently discarding the host's
  real initial value.

  **Fixed** by teaching `_generate_lifecycle_fn` the same DDT-member
  resolution `run_dispatch.py` already has, reusing `cap_shared.py`'s
  existing DDT-resolution helpers rather than duplicating them. Confirmed
  via the real `Makefile` path: `test_host_ccpp_physics_initialize`'s call
  to `var_compatibility_suite_suite_initialize` now passes
  `phys_state%scheme_order` directly, with no `lc_scheme_order` anywhere.
  No other example was affected — this gap was never exercised by any other
  example's lifecycle dispatch. See
  `tests/unit/test_lifecycle_ddt_member_resolution.py` for direct
  regression coverage (sabotage-verified) and `ccpp_cap_refactor_plan.md`'s
  backlog for the full writeup.

- **Fixed — a hand-written-file bug, found once `ifx` actually built the
  example successfully: `gfortran` refused to compile
  `test_var_compat_host_integration.F90` at all**, on all three of its
  string-array constructors (`test_invars1`/`test_outvars1`/`test_reqvars1`):
  ```
  Error: Different CHARACTER lengths (58/59) in array constructor at (1)
  ```
  Confirmed by diffing directly against upstream capgen-v1's own
  `test_var_compatibility_integration.F90`: upstream is perfectly
  consistent — all 54 string literals across the three arrays are exactly
  58 characters, uniformly (Fortran array constructors require every
  element to share one length; `gfortran` enforces this strictly, `ifx`
  apparently pads/truncates silently instead). The ported version had 30 of
  54 entries off by ±1–3 characters — a padding-count slip introduced when
  the array literals were reflowed/reformatted during the port, not an
  upstream issue and not a design problem with the data itself (every
  variable name was already correct).

  **Fixed, per explicit user authorization to touch this specific
  hand-written file for this specific issue** — every string literal
  re-padded to exactly 58 characters, matching upstream exactly. Verified
  programmatically both ways: all 54 entries now uniformly 58 characters,
  and every identifier's stripped text is byte-identical to before across
  all three arrays, in the same order — only trailing whitespace changed.

- **Fixed — a real `gfortran` runtime crash, found by actually running the
  built executable:**
  ```
  At line 184 of file examples/var_compat/var_compatibility_suite_cap.F90
  Fortran runtime error: Attempting to allocate already allocated variable 'effrr_in_unit_conv'
  ```
  Root cause, in `print_ftn.py` (the Fortran backend, a different layer
  from every fix above): each "forward" conversion op (`CCPPKindCastOp`/
  `CCPPUnitConvertOp`/`CCPPVerticalFlipOp`/`CCPPRowMajorConvertOp` —
  allocates a local temp, converts into it) is paired with a "write-back"
  op that writes the temp back to the host and deallocates it — but the
  deallocate only ever happened inside the write-back case. `effrr_in`
  (consumed by `effr_calc_run`) is pure `intent(in)`, so it has no
  write-back at all — nothing ever deallocated its conversion temp. That's
  invisible for a subroutine called only once (Fortran auto-deallocates
  non-`SAVE` locals on return), but `var_compatibility_suite_suite_radiation`
  calls `effr_calc_run` inside a nested 3-level subcycle loop
  (`do ccpp_loop_cnt0 = 1, 2` / `do ccpp_loop_cnt = 1, 2`) — the same temp gets
  allocated a second time within the same subroutine invocation, before
  Fortran ever gets a chance to deallocate it.

  **Fixed** by printing a guarded deallocate
  (`if (allocated(x)) deallocate(x)` — the same pattern `CCPPSafeDeallocOp` already uses
  elsewhere in this file) immediately before every `allocate(...)`
  statement all four of these op cases print, independent of whether a
  write-back exists — safe for pure `intent(in)` values, and a no-op on
  first entry so it doesn't change behavior for the ordinary, non-looped
  case either. Confirmed via the real `Makefile` path: every conversion
  temp in `var_compatibility_suite_suite_radiation` (`effrr_in_unit_conv`,
  `effrr_in_vert_flip`, `effrs_inout_kind_cast`, etc.) now has a guard
  immediately before its `allocate`. This is a generator-wide fix, not
  var_compat-specific: `examples/helloworld`'s own `ccpp_t` variant golden
  also legitimately changed (same guard, same reason) and was regenerated;
  no other example was affected. See
  `tests/unit/test_print_ftn_conversion_temp_dealloc.py` for direct
  regression coverage (sabotage-verified, covering three of the four
  affected op cases) and `ccpp_cap_refactor_plan.md`'s backlog for the full
  writeup.

  Confirmed via the real `Makefile` path that `make check` then reported a
  real numeric mismatch (see the `col_start`/`col_end` slicing fix below,
  which resolves it) rather than a build/link failure.

- **Fixed — the `col_start`/`col_end` chunking-correctness gap flagged above
  as unresolvable from the generator side turned out to be a real,
  fixable generator bug, found by actually running capgen-v1's own
  generator on this same example and diffing its output against
  xdsl-ccpp's:**
  ```
  Error: max diff of            effrs from expected value exceeds tolerance:    0.6000000E-04 >    0.5300000E-09
   Answers are not correct!
  ```
  capgen-v1 slices every host-array reference passed into a suite-part call
  by `col_start:col_end`
  (e.g. `phys_state%effrr(col_start:col_end, pver:1:-1)`) and recomputes any
  `horizontal_dimension`-standard_name scalar as `col_end - col_start + 1`
  (e.g. `ncol=(col_end - col_start + 1)`), so a chunked call only ever
  touches its own column window.
  xdsl-ccpp did neither: `test_host_ccpp_physics_run` accepted `col_start`/
  `col_end` (the fix above) but called `var_compatibility_suite_suite_radiation`
  with the whole, unsliced host array and the host's raw, full column count
  every time — so each of `test_host.F90`'s 3 chunked driver calls
  redundantly reprocessed the *entire* array, and `effrs_inout`'s real
  `+=` accumulation (the only non-idempotent operation among this suite's
  schemes) over-accumulated by exactly 3x (90 µm actual increase vs. 30 µm
  correct/expected — the reported `0.6000000E-04` diff is exactly that 60 µm
  excess). Every other checked value happened to be idempotent under
  repetition (constant overwrites, `min`/`max` clamps, or never touched by
  the scheme body at all), which is why only `effrs` surfaced a failure.

  Traced to three independent, precisely-located bugs, all in
  `run_dispatch.py`:
  1. `_build_run_block_signature`'s host-driven col_start/col_end fallback
     (the fix above) registered them into `union_non_host_args` (so the
     wrapper's own signature accepts them) but never into
     `non_host_std_to_canonical` — the dict `_build_run_dispatch_chain`'s
     already-existing `ArraySectionOp`-slicing logic actually looks up, so
     that logic's own guard always saw nothing and skipped slicing
     unconditionally.
  2. A scheme-declared scalar arg whose own `standard_name` is
     `horizontal_dimension` (var_compat's own `ncol`, matching
     `rad_lw`/`rad_sw`/`effr_calc`) was passed the host's raw, full column
     count through the ordinary host-var-reference path, with nothing
     recomputing it as `col_end - col_start + 1`.
  3. A pre-existing, previously-unreachable bug in the same
     `ArraySectionOp` block required at least 2 resolved dimensions before
     slicing anything — silently skipping any genuinely 1-D
     `horizontal_dimension`-only host array (var_compat's own `fluxLW`,
     `sfc_up_sw`, `sfc_down_sw`), which would otherwise have regressed
     those checked values from correct-but-redundant to actively wrong
     (only ever writing the first chunk's columns) once (1) started
     slicing their 2-D siblings correctly.

  **Fixed** by (a) also registering the canonical `col_start`/`col_end`
  mapping in the same fallback block, (b) recomputing a
  `horizontal_dimension`-standard_name scalar via the same
  `alloc`/`load`/`sub`/`add-one`/`store` op sequence `suite_cap.py`'s own
  `_build_ncol_compute_ops` already uses for this exact computation, and
  (c) relaxing the 2-dimension requirement to accept a single resolved
  dimension. No changes needed to `suite_cap.py`'s `_classify_args` (that's
  `advection`'s separate, already-correct legacy `horizontal_loop_extent`
  mechanism — confirmed untouched and unaffected), `print_ftn.py` (temp
  allocation sizes already derive from whatever shape the sliced actual
  argument has), the suite callee's own Fortran signature (Fortran
  assumed-shape dummies adapt automatically to a sliced actual argument), or
  the existing `optional`/`target` handling (confirmed orthogonal).

  Confirmed via the real `Makefile` path: `test_host_ccpp_physics_run`'s
  call now reads
  `effrr_inout=phys_state%effrr(col_start:col_end, 1:pver)`, `ncol=ncol`
  with `ncol = col_end - col_start + 1` computed just above, and
  `fluxLW=phys_state%fluxLW(col_start:col_end)` /
  `sfc_up_sw=phys_state%fluxSW%sfc_up_sw(col_start:col_end)` /
  `sfc_down_sw=phys_state%fluxSW%sfc_down_sw(col_start:col_end)` — matching
  capgen-v1's own generated shape. Affects every example whose host declares
  `horizontal_loop_begin`/`horizontal_loop_end` and whose schemes rely on the
  `horizontal_dimension`-only fallback rather than `horizontal_loop_extent`
  (`var_compat`, `helloworld`, and the synthetic `array-layout-reshape`
  FileCheck fixture); every `horizontal_loop_extent`-based example
  (`advection`, `capgen`, `ddthost`, and the chost/bind-c examples) is
  confirmed unaffected — their existing mechanism is a separate, untouched
  code path. See `tests/unit/test_run_dispatch_col_bounds_fallback.py` for
  direct regression coverage (sabotage-verified against all three fixes
  independently, including the pre-existing `advection`-style
  no-double-insert guard) and `ccpp_cap_refactor_plan.md`'s backlog for the
  full writeup.

  **Follow-up — a real `gfortran` compile error, found immediately on the
  first real build attempt of this fix:**
  ```
  Error: Symbol 'ncol' at (1) has no IMPLICIT type
  ```
  Root cause, in `print_ftn.py` (a different layer from the fix above):
  the recomputed `ncol` local (a genuinely new `memref.AllocaOp`) is
  necessarily constructed nested inside the suite_name/suite_part dispatch
  chain's `scf.IfOp`s — it can only be computed once `col_start`/`col_end`
  are known to belong to the matching suite/part, same as every other
  per-suite value in this function. But `print_ftn.py`'s local-alloca
  declaration collector only ever scanned the function body's own top-level
  ops (`bdy.block.ops`), not recursively into nested regions — so the
  assignment (`ncol = col_end - col_start + 1`) and its use in the call were
  both printed correctly, but the corresponding `integer :: ncol`
  declaration was silently dropped. The very next code block in the same
  file (declaring `CCPPKindCastOp`/`CCPPUnitConvertOp` temporaries) already
  had to solve this identical problem for a different op type, and already
  does it correctly via `bdy.block.walk()` — this alloca-declaration
  collector was simply never updated to match, since no prior code path
  needed a genuinely new local alloca'd from inside this specific nested
  dispatch chain.

  **Fixed** by changing that one collector from `bdy.block.ops` to
  `bdy.block.walk()`, matching the existing, already-proven pattern used
  two blocks below in the same function. Purely additive — every
  previously-found top-level alloca is still found (a walk includes the
  top level), so no existing declaration is gained or lost; only
  previously-invisible nested ones (this `ncol` case) are now also declared.
  Confirmed via the real `Makefile` path: `test_host_ccpp_physics_run` now
  declares `integer :: ncol` immediately after `errflg`. Full unit +
  FileCheck suites re-run clean afterward (500 passed, same 1 pre-existing
  xfail and 1 pre-existing unrelated failure as before this whole fix) —
  no other example's generated output changed, confirming no other example
  currently constructs a nested alloca of this kind. See the new
  `test_ncol_local_is_declared` test in
  `tests/unit/test_run_dispatch_col_bounds_fallback.py` (sabotage-verified)
  for direct regression coverage.

  **Confirmed** by an actual `gfortran` build-and-run: `make check` now
  reports PASS, including a correct `effrs` value — CI is green for
  `var_compat`, closing out the original numeric-mismatch report end to end.

- **Fixed — a known, pre-existing, previously-undetected gap in the same
  `ArraySectionOp` slicing machinery, found while auditing what the
  `col_start`/`col_end` fix above did and didn't cover:** `effr_calc`'s
  optional, unmatched output `ncl_out` (`cloud_liquid_number_concentration`)
  has no host-side match anywhere in this port's metadata, so it falls back
  to a cap-owned scratch buffer (`lc_ncl_out`), sized to the full host
  column count and dimensioned by `horizontal_dimension`/
  `vertical_layer_dimension` like any other array arg — a `CapVar`-sourced
  argument, a different `ArgSourceKind` than the `Host`/`DdtMember` case the
  earlier fix covered. Its own slicing gate was still keyed entirely to the
  legacy `horizontal_loop_extent` name, and even where that legacy gate did
  fire (`examples/advection`'s own `tendency_of_cloud_liquid_dry_mixing_ratio`),
  it only ever built a single-dimension section — so `lc_ncl_out` was never
  sliced by `col_start`/`col_end` at all under the newer convention: every
  chunked call would write only the first chunk's columns, leaving every
  later chunk's columns stale/uninitialized for any host that actually read
  it (this test's own doesn't, which is why it stayed invisible).

  **Fixed** by splitting the `CapVar` branch in two: the existing
  `horizontal_loop_extent` case is left completely untouched (still exactly
  one dimension, matching `advection`'s already-correct, already-verified
  output byte-for-byte), and a new `horizontal_dimension` case reuses the
  same multi-dimension resolution loop the `Host`/`DdtMember` branch already
  has, extended to cap-owned buffers. Confirmed via the real generator path:
  the call now reads `ncl_out=lc_ncl_out(col_start:col_end, 1:pver)`.
  Confirmed unaffected: `advection` and `capgen`'s goldens (which do exercise
  the legacy-convention `CapVar` path) are byte-identical; only `var_compat`'s
  two goldens changed. See `TestCapVarSlicedWhenRankTwo` in
  `tests/unit/test_run_dispatch_col_bounds_fallback.py` (sabotage-verified,
  plus a guard confirming the already-covered `Host`/`DdtMember` slicing in
  the same call is undisturbed) for direct regression coverage.

- **Fixed — the generated `test_host_ccpp_cap.F90` failed to compile with
  "Error in opening the compiled module file" for `ccpp_constituent_prop_mod`
  and `ccpp_scheme_utils`.** Not an `xdsl_ccpp` code gap: every generated
  ccpp-cap module unconditionally emits a `<Host>_model_const_properties()`
  entry point (part of the mandatory CCPP host-facing API, not something
  scheme-specific — this example declares no constituents of its own), and
  that entry point's `use ccpp_constituent_prop_mod`/`use ccpp_scheme_utils`
  need real Fortran module files to compile against. Those two modules are
  part of the real CCPP framework library, not `xdsl_ccpp`'s job to
  generate — every other example that's actually been compiled
  (`examples/advection`, `examples/advection_flat_host`,
  `examples/constadv`, `examples/constprop`) carries its own small, fully
  generic stub implementation of both and wires them into its own Makefile;
  this port's Makefile simply never got the same two files. Fixed by
  copying the (byte-identical across all four of those examples) stub files
  in as `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` and adding
  them to `SRCS` right after `GEN_KINDS`, ahead of everything that uses
  them, matching the existing ordering convention already used for
  `module_rad_ddt.F90`.

- **Vertical array flipping (`top_at_one`) — implemented.** `effr_calc`'s
  `effrr_in`/`effrs_inout` and `effr_diag`'s `effrr_in` declare
  `top_at_one = True`; `effr_pre`/`effr_post`/`effrs_calc` don't declare it
  at all. No host file in this port declares an explicit vertical-convention
  counterpart to compare against, so the schemes that don't declare it
  define the shared, "not flipped" representation, and any scheme that does
  declare it needs a flip — reusing the exact same cross-scheme divergence
  detection and per-call marshaling built for the kind/unit fix above
  (`suite_cap.py`'s `divergent_std_keys`/`generateSchemeSubroutineCallOps`),
  plus a new `VerticalFlipOp`/`VerticalFlipWriteBackOp` pair
  (`xdsl_ccpp/dialects/ccpp_utils.py`) modeled directly on the existing
  `KindCastOp`/`KindWriteBackOp`, reversing an array section along whichever
  dimension its own `dim_names` says is vertical rather than converting a
  value. `effrs_inout`'s real case chains all three kinds of per-call
  marshaling on the same argument at once (kind cast, then unit convert,
  then vertical flip), with the write-back correctly unwinding in the
  opposite order. `top_at_one` is now a recognized metadata attribute
  (`ArgumentOp.KNOWN_PROPS`) instead of silently dropped with an
  unrecognised-key warning. See
  `tests/unit/test_suite_vertical_flip_marshaling.py` for direct regression
  coverage. Note: this specific example's own scheme arithmetic on the
  flipped variables is uniform across vertical levels (confirmed by reading
  `effr_calc.F90`/`effr_diag.F90`), so its own numeric answer-check can't
  independently distinguish a correct flip from a no-op one — verification
  here is about correct, valid generated Fortran syntax and correct
  call-site placement, not an independent numeric proof from this
  particular test.
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

```bash
cmake -S . -B build   # from the repo root
cmake --build build --target var_compatibility_host_integration
ctest --test-dir build -R var_compat --output-on-failure
```

(This example originally built and ran via a hand-written Makefile; see the
"Confirmed by an actual `gfortran` build-and-run" bullet above for how that
first full PASS was reached, including the runtime variable-count mismatch
and `col_start`/`col_end` unused-chunking questions raised along the way —
both resolved by the time CI went green. The Makefile itself has since been
removed in favor of the CMake build shown above.)
