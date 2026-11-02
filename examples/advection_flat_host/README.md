# advection_flat_host

A deliberately minimal companion to `examples/advection`, built specifically to test
xdsl-ccpp's OpenACC data-movement generation without the DDT-member reference-resolution
gap that `advection` hits (see `CHANGELOG.md`'s GPU/OpenACC backlog).

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
- `qv`: host side (`flat_host_mod.meta`) declares `memory_space = device`, and both
  `cld_liq_run` and `cld_ice_run` declare `memory_space = device` (→ `present`). The cap
  makes the host variable resident itself (`present()` alone allocates nothing), so `qv`
  stays on the device through both schemes.

Until 2026-11-02 `cld_ice_run`'s `qv` lacked `memory_space = device` here (a copy slip;
`examples/advection`'s `cld_ice.meta` always had it), so the two schemes disagreed and the
cap wrapped `cld_ice_run` in `!$acc update self(qv)` / `!$acc update device(qv)`. Since
`cld_ice_run`'s kernel uses `qv` with `present(qv)`, that trailing `update device` overwrote
its device result with the stale host copy. The Fortran-vs-`.meta` check
(`acc-derive-memory-space`) now flags such a contradiction. The routing for schemes that
genuinely disagree (one uses a variable on the device, another on the host) is covered by the
synthetic conflict fixtures in `tests/unit/test_gpu_directives.py`.
A plain-CPU generate/build/test (no `--directive`) is unaffected either way, since
`memory_space` is inert without a `--directive acc`/`omp` pass invocation.

This was the real, reproducible target for Phase 7's GPU/OpenACC (b)/(c) work — both are now
done: (c) (turning a silent conflict into a hard error) and (b) (true per-scheme-call clause
routing, so `qv` actually compiles correctly instead of raising) — see
`CHANGELOG.md`'s GPU/OpenACC backlog for the full design history. The multi-group
`ccpp_physics_run` discovery gap (a separate, orthogonal bug affecting every var kind
`GPUCcppCapPass` still handles) remains deferred, unexercised by this single-group example.

## Building and verifying (CPU only)

From the repository root:

```bash
cmake -S . -B build
cmake --build build --target advection_flat.exe
ctest --test-dir build -R advection_flat --output-on-failure
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

**Scope note:** this example's own CMake target is CPU-only by default — it shares the
`ARCH` cache variable with `advection`/`kessler` (see the top-level README's "GPU build"
section for `-DARCH=GPU` usage), but `temp`/`qv`'s `memory_space=device` annotations are
inert without a `--directive acc`/`omp` pass invocation regardless of `ARCH`; this target
exists to confirm the example is otherwise a correct, complete, buildable CCPP host,
independent of the (b)/(c) GPU work it was built to test. `ctest_advection_flat_host_integration`
is wired into the CMake CI workflow's matrix.
