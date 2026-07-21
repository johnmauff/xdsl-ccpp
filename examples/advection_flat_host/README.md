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

Generating this suite through `generate-gpu-ccpp-cap` (`--directive acc`) shows the actual
gap concretely: `cld_liq` wants `present(qv)`, `cld_ice` wants `update self`/`update device`,
and today's per-*suite*-group granularity has no way to satisfy both at once. As of the (c)
fix, `_analyze_one_suite` detects this and raises a `ValueError` naming `qv` and both
conflicting schemes, instead of the prior behavior (`update` silently winning — `cld_liq`'s
`present` classification discarded with no error, emitting a single `update self`/`update
device` pair around the whole group call that `cld_liq_run`'s own
`!$acc parallel loop present(qv,...)` would then be asserting residency for that the
surrounding code never actually established). `make caps`/`make check` (no `--directive`)
are unaffected — this only fires when generating with `--directive acc`/`omp`.

This is the real, reproducible target for Phase 7's GPU/OpenACC (b)/(c) work. (c) — turning
the silent conflict into a hard error — is done; (b) — true per-scheme-call clause routing,
so `qv` compiles correctly with each scheme getting its own directive instead of raising at
all — remains unimplemented (see `ccpp_cap_refactor_plan.md`'s GPU/OpenACC backlog).

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
independent of the (b)/(c) GPU work it was built to test. This `check` target is wired
into CI's compile-tests workflow matrix.
