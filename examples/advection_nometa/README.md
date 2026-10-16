# advection_nometa

**dup-meta-shadow-elim (BACKLOG.md) demonstration, Phase 7.** This is the
tag-based twin of `examples/advection` — identical functionality,
identical host/suite/driver files, but all 5 real scheme `.F90` files
(`const_indices`, `cld_liq`, `apply_constituent_tendencies`, `cld_ice`,
`cld_shadow`) carry `standard_name`/`units`/`long_name`/`dim_names`/
`advected`/`constituent`/`state_variable`/`protected`/`default_value` as
`!$ccpp [name] key = value` comment tags instead of hand-maintained
`.meta` files. `memory_space = device` is never tagged on any argument —
it's mechanically derived from each scheme's own real `!$acc
present(...)` clauses (Phase 2), exactly as it already is in
`examples/advection` itself. No `.meta` for any **scheme** is committed
to this directory at all; all 5 are generated together, into the build
tree, from the tagged sources at CMake configure time (see this
directory's own `CMakeLists.txt` for the mechanism and its one known
limitation). `test_host_data.meta`/`test_host_mod.meta`/`test_host.meta`
(host/control metadata, describing arbitrary module-level state rather
than subroutine arguments) **are** committed, same as in
`examples/advection` — a structurally different extraction problem never
attempted by this effort, not an oversight here.

`dlc_liq.F90`/`.meta` (a deliberate register-phase-violation
negative-test fixture, not part of `cld_suite`) is out of scope for this
demonstration and is not duplicated here — see `examples/advection`'s
own README for what it tests.

Verified directly, not assumed: each scheme's regenerated `.meta` is
semantically identical to `examples/advection`'s own hand-authored
`.meta` for that scheme — `compare_modules()` between the two reports
zero mismatches, for all 5 schemes.

## Line-count comparison (this example specifically)

| Scheme | `examples/advection` (`.F90` + `.meta`) | `examples/advection_nometa` (`.F90` only) |
|---|---|---|
| `const_indices` | 94 + 108 = 202 | 145 |
| `cld_liq` | 112 + 142 = 254 | 171 |
| `apply_constituent_tendencies` | 39 + 36 = 75 | 61 |
| `cld_ice` | 139 + 150 = 289 | 203 |
| `cld_shadow` | 41 + 46 = 87 | 65 |
| **Total** | **907** | **645** |

A ~29% reduction across this suite's 5 real schemes — a noticeably
bigger payoff than `examples/threads_nometa`'s own ~21% (a single
4-argument scheme), consistent with this backlog item's own corpus-wide
finding: the fixed, per-argument `!$ccpp` tag overhead stays small and
constant while the mechanical content it eliminates (type/kind/intent/
dimension-count/structural boilerplate) scales with how many arguments
and entry points a real scheme actually has.

## Files

| File | Description |
|------|-------------|
| `test_host.meta` | Control table + host table — unchanged from `examples/advection`, out of scope for tagging |
| `test_host_data.meta`/`test_host_data.F90` | Host state data — unchanged, same reason |
| `test_host_mod.meta`/`test_host_mod.F90` | Host state module — unchanged, same reason |
| `const_indices.F90` | Scheme, now carrying `!$ccpp` tags; **no `const_indices.meta` committed** |
| `cld_liq.F90` | Scheme, now carrying `!$ccpp` tags; **no `cld_liq.meta` committed** |
| `apply_constituent_tendencies.F90` | Scheme, now carrying `!$ccpp` tags; **no `apply_constituent_tendencies.meta` committed** |
| `cld_ice.F90` | Scheme, now carrying `!$ccpp` tags; **no `cld_ice.meta` committed** |
| `cld_shadow.F90` | Scheme, now carrying `!$ccpp` tags; **no `cld_shadow.meta` committed** |
| `cld_suite.xml` | Suite definition — unchanged, references schemes by name only |
| `test_advection_host_integration.F90` | Driver — unchanged |
