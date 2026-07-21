# advection_flat_host

A deliberately minimal companion to `examples/advection`, built specifically to test
xdsl-ccpp's OpenACC data-movement generation without the DDT-member reference-resolution
gap that `advection` hits (see `ccpp_cap_refactor_plan.md`'s GPU/OpenACC backlog).

## Why this exists, and how it differs from `advection`

`cld_liq`/`cld_ice`/`apply_constituent_tendencies`/`const_indices` are reused here
byte-for-byte from `examples/advection` — the scheme physics doesn't care whether its
arguments are host-matched to a DDT member or a plain host variable, that's purely a
host-side concern. The only thing that changed is the host: `temp`/`qv`/`ps` are declared
here as plain `flat_host_mod` module variables instead of members of a `physics_state` DDT.

This matters because `GPUCcppCapPass` currently has no support at all for DDT-member host
references (confirmed while building the original `advection` GPU scenario — the
classification logic works fine, but the directive-insertion side never finds a DDT
member's `HostVarRefOp` and silently skips it). Testing against a real DDT would have
conflated that gap with the one this example is actually meant to exercise.

## What this example demonstrates today

- `temp`: `memory_space = device` on both `cld_liq_run` and `cld_ice_run`, host side left
  undeclared. Both schemes agree — the compatible-union / cross-function hoisting path.
- `qv`: host side (`flat_host_mod.meta`) declares `memory_space = device`. `cld_liq_run`
  also declares `memory_space = device` (→ wants `present`). `cld_ice_run` leaves it
  undeclared (→ wants `update`). Two schemes in the *same group* genuinely disagree about
  the same host variable's residency.

Generating this suite through `generate-gpu-ccpp-cap` shows the actual gap concretely:
`_analyze_one_suite` processes `present_vars` before `update_vars` when building lifetimes,
so `update` silently wins for `qv` — `cld_liq`'s `present` classification is discarded with
no error, and the emitted code brackets *both* schemes' calls with a single `update self`/
`update device` pair spanning the whole group call, not scoped to either scheme
individually. `cld_liq_run`'s own `!$acc parallel loop present(qv,...)` is then asserting
residency the surrounding cap-generated code never actually establishes for it specifically.

This is the real, reproducible target for Phase 7's GPU/OpenACC (b)/(c) work: per-scheme-call
clause routing and conflict detection, not per-suite/per-group.

## Building and verifying (CPU only)

```
make caps    # regenerate the CCPP caps (requires xdsl-ccpp / ccpp_xdsl on PATH)
make check   # build and run the verification driver
```

`test_flat_host_integration.F90` runs the full lifecycle once (register → initialize →
timestep_initial → run → timestep_final → finalize) and checks two things using only
`temp`/`qv` (the data the host itself owns — the generated cap's own scratch/tendency
arrays are private to it and not observable from the driver):

1. `errflg` stays `0` after every lifecycle call.
2. Level 1 is initialized well below `tcld` (both `cld_liq`/`cld_ice`'s trigger condition)
   and every other level well above it — so a real run should show `qv` decrease and
   `temp` increase at level 1 (condensation/freezing with latent heat release) while every
   other level is untouched. This confirms data actually flows from the host arrays into
   the schemes and back, not just that nothing crashed.

**Scope note:** this Makefile is CPU-only — it does not build the OpenACC (`ARCH=GPU`)
path `advection`'s/`kessler`'s Makefiles support. `temp`/`qv`'s `memory_space=device`
annotations are inert without a `--directive acc`/`omp` pass invocation; this target
exists to confirm the example is otherwise a correct, complete, buildable CCPP host,
independent of the (b)/(c) GPU work it was built to test. Not yet wired into CI.
