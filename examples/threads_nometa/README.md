# threads_nometa

**dup-meta-shadow-elim (BACKLOG.md) demonstration.** This is the tag-based
twin of `examples/threads` — identical functionality, identical host/
suite/driver files, but `thread_scheme.F90` carries
`standard_name`/`units`/`long_name`/`dim_names` as `!$ccpp [name] key =
value` comment tags instead of a hand-maintained `thread_scheme.meta`.
No `.meta` for the **scheme** is committed to this directory at all; it's
generated into the build tree from the tagged source at CMake configure
time (see this directory's own `CMakeLists.txt` for the mechanism and its
one known limitation). `data.meta`/`test_host.meta` (host/control
metadata, describing arbitrary module-level state rather than subroutine
arguments) **are** committed, same as in `examples/threads` — nothing
built so far generates host `.meta`; that's a structurally different
extraction problem Phases 1-4 never attempted, not an oversight here.

Verified directly, not assumed: the regenerated `.meta` is semantically
identical to `examples/threads`' own hand-authored `thread_scheme.meta`
— `compare_modules()` between the two reports zero mismatches.

## Line-count comparison (this example specifically)

| | `.F90` | `.meta` | Total maintained |
|---|---|---|---|
| `examples/threads` (original) | 51 | 39 | **90** |
| `examples/threads_nometa` (this one) | 71 | 0 (generated, not committed) | **71** |

A ~21% reduction for this one small, 4-argument scheme. That understates
the real payoff on purpose: the fixed overhead of `.meta`'s own
structural boilerplate (table/arg-table headers, `type =`/`dimensions =`
lines) is proportionally large for a tiny scheme like this one, while
each `!$ccpp` tag line added here is pure extra text with no offsetting
savings at this scale. The real corpus this backlog item targets
(`NCAR/atmospheric_physics`, 36,431 real `.meta` lines) has the same
small, fixed per-argument tag overhead but vastly more of the mechanical
content tags eliminate — see `CHANGELOG.md`'s `dup-meta-shadow-elim`
entries for the full-corpus numbers (45.6% fully derivable, 14.9% mixed,
7.4% structural — all eliminable as hand-maintained text; only the
irreducible ~32% moves into tags).

## Files

| File | Description |
|------|-------------|
| `test_host.meta` | Control table + host table — unchanged from `examples/threads`, out of scope for tagging (Phases 1-4 cover scheme `.meta` only) |
| `data.meta`/`data.F90` | `thread_type` DDT + host array — unchanged, same reason |
| `thread_scheme.F90` | The scheme, now carrying `!$ccpp` tags; **no `thread_scheme.meta` committed** |
| `suite_thread_suite.xml` | Suite definition — unchanged, references the scheme by name only |
| `main.F90` | Driver — unchanged |
