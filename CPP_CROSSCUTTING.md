# C++ Work: Cross-Cutting Backlog Items

Items in `BACKLOG.md` that are **not** C++ items (so they are not in
`CPP_BACKLOG.md`) but touch the same code or generated interfaces as the
C++ / multi-language work. The C++ backlog has its own owner; these items
are owned by the main backlog. Use this file to know where to coordinate.

Compiled 2026-10-27 from a review of `BACKLOG.md`. IDs match `BACKLOG.md`,
which holds the full detail for each item. Like `CPP_BACKLOG.md`, this is a
derived view: when an item here resolves or changes in `BACKLOG.md`, update
or remove it here too.

## Directly affects C++ work — coordinate before either side lands

### `suite-state-full-match` (L)
Rewrites `ccpp_suite_state` to match capgen-v1: an integer-enum
allocatable array with dedicated alloc/dealloc subroutines. This is the
variable at the centre of `chost-thread-safety`, whose preferred fix
(per-instance state slots via `_is_multi_instance_host` in `suite_cap.py`)
changes the same declaration.
- **Coordinate:** decide which lands first, or design the thread-safety
  fix around the new layout. Done separately, they conflict.

### `canonical-error-arg-order` (S code, M review)
Always put the error arguments last, as `errmsg, errflg`, in every
generated routine. Today a group routine takes them in the order and with
the names of its first scheme. Changes generated signatures in almost
every configuration.
- **C++ impact (not yet verified):** if the chost BIND(C) entry points and
  C++ headers (`cpp_interop.py`, `print_cpp_header.py`) take their
  signatures from the group routines, the C ABI changes too. The C++
  drivers in `examples/*/host_cpp/` call by position.
- **Check before landing:** whether the chost signatures change; if so,
  update the C++ drivers and C++ goldens in the same PR and tell the C++
  owner.

### Package caps — `composite-package-caps` and the `package-cap-*` follow-ons
Package caps (`--package-caps`, 2f/2g done) restructure suite caps. Making
them the default is deferred (user decision, 2026-10-23).
- **C++ impact:** no reference to package caps found in `cpp_interop.py`.
  No test combines `--bind-c` with `--package-caps`, or puts a
  `language = c++` scheme inside a package.
- **Check before the default switch:** the chost path and
  `cxx-scheme-no-e2e-test` must work with package caps.

## Affects the GPU-related C++ items

### `xdsl-upgrade` (S-M)
xDSL pin 0.56.1 → 0.74.0. Affects the whole codebase, `cpp_interop.py`
included, so it means merge churn for open C++ branches. It also brings
upstream `acc`/`omp` dialects, which could change how
`chost-gpu-memory` / `eamxx-phaseB-deviceptr` emit directives.
- **Coordinate:** timing with open C++ branches; design the GPU chost
  work with the post-upgrade dialects in mind.

### `gpu-conversion-residency` (S-M, after `xdsl-upgrade`)
Unit/kind conversion temporaries for device-resident arguments are built
on the host (`suite_cap.py`, ~L1060-1120), with no `!$acc`/`!$omp`
directive. A C++ host passing device pointers to a scheme that needs a
conversion would hit this.
- **C++ impact:** mention it as a known gap in the `chost-gpu-memory`
  design.

### `acc-meta-residency-check` (S)
Static check that each argument's `memory_space` in `.meta` matches the
routine's `!$acc present(...)`/`deviceptr(...)` clauses.
- **C++ impact:** close to the generation-time mismatch warning that
  `eamxx-phaseB-deviceptr` proposes, and to the optional `memory_space`
  derivation in `cxx-scheme-annotations`. Share the logic instead of
  building it two or three times.

### `gpu-ci` (M-L, blocked on a runner/hosting decision)
No CI runs generated OpenACC on a real GPU.
- **C++ impact:** any GPU chost work (`chost-gpu-memory`, Phase B) can
  only be checked by hand until this exists.

## Affects how C++ items are scoped

### `dup-meta-shadow-elim` and `direct-fortran-ingest`
Metadata generated from annotated Fortran (`!$ccpp` tags,
`fparser2_to_meta.py`, `ccpp_generate_meta`), plus suite XML
auto-generation from source analysis and directives.
- **C++ impact:**
  - It is the reason `eamxx-phaseA-variant-tag` is on hold (motivation to
    be revisited). It may change the design of `eamxx-phaseC-printer` too:
    generated metadata could carry the EAMxx field/tracer role and layout.
  - C++ schemes can't use `!$ccpp` tags, so they still need hand-written
    `.meta`. That gap is now its own C++ item, `cxx-scheme-annotations`.
    `direct-fortran-ingest`'s design should leave room for C++ sources.

## Minor — no action needed

- **`hle-vocab-retire`:** the chost path injects `ncol` automatically, and
  the legacy `horizontal_loop_extent` code path stays while `--legacy-mode`
  exists.
- **`generation-error-output`:** usability fix (legacy warnings tied to
  `--verbose`, plain `Error:` exits, quieter fparser2 warning). Applies to
  the chost path too, since it runs through the same passes.
