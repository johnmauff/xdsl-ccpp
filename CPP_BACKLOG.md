# C++ / Multi-Language Support Backlog

A priority-ordered **view into `BACKLOG.md`**, filtered and reordered
around a single goal: enabling real multi-language support in
xdsl_ccpp — both C++ as a host model (the "chost" BIND(C) cap) and C++ as
a scheme implementation. Use this file to decide what to pick up next
toward that goal; use `BACKLOG.md` for full detail on any item (file
paths, risk, archive pointers) and for everything not related to this
goal.

**This is a derived list, not a second source of truth.** Every item here
has a matching entry in `BACKLOG.md`'s own sections, carrying the same
stable ID — that entry is where the full file/rationale/history detail
lives. This file adds only two things BACKLOG.md's own ordering doesn't
give: a priority ranking specific to the multi-language goal, and a short
"why this matters for C++" note per item.

**Keeping this synchronized with `BACKLOG.md`** (manual, by design — no
tooling enforces this):
- When a C++-relevant item here resolves, changes scope, or gets
  renamed/re-prioritized in `BACKLOG.md`, update the corresponding line
  here in the same sitting.
- When a new item lands in `BACKLOG.md` that bears on this same goal, add
  it here too, at whatever tier its priority warrants.
- IDs here must always match `BACKLOG.md`'s current ID for that item
  exactly (see `BACKLOG.md`'s own Technical Debt section for the
  ID-stability policy — this file is exactly the kind of place a stale ID
  reference would otherwise go unnoticed).

Last synchronized with `BACKLOG.md`: 2026-10-08 (after `chost-rank3-bindc`
and both `chost-identity-collision`/`chost-dim-collision` resolved;
following `cpp-type-table-unify` and `cpp-dual-print-pipeline`;
`lang-neutral-expr-ir` (including Stage 3c, now fully done) resolved;
new `chost-real-width-fallback` item found during that work).

## Recommended near-term path

**1 → 2/3** is the highest-value sequence right now: Tier 1's
architectural blocker and all of Tier 2's cheap wins are done, so next is
the `cxx-scheme` end-to-end test gap, then the two most concrete
remaining chost limitations — without committing to Tier 4's large Phase
C investment until there's real pull for it.

## Tier 1 — foundational, blocks everything else in this direction

**`lang-neutral-expr-ir` — RESOLVED 2026-10-08**: the real architectural
blocker is fully done, including Stage 3c (`UnitConvertOp`'s own
deferred structured-conversion sub-item). A language-neutral expression
vocabulary (reused `arith`/`math` plus 7 new custom ops) exists, with
both a Fortran printer and a C++ expression printer (`expr_to_cpp_str`)
rendering the same IR tree in each language's own syntax — propagated to
all 3 files with real retrofit work (`constituent_cap.py`,
`cpp_interop.py`, `suite_cap.py`; `run_dispatch.py`/`lifecycle_cap.py`
audited and confirmed to need none). Stage 3c: a bare numeric real kind
(`kind = 8`/`4`) builds a real `arith` conversion tree at both of
`suite_cap.py`'s real call sites (`_apply_kind_and_unit_casts` and
`_apply_divergent_marshaling`); a named kind (e.g. `kind_phys`) stays on
the opaque-text path permanently, by design. See `BACKLOG.md`'s entry and
`CHANGELOG.md`'s "Stages 0-4"/"Stage 5"/"Stage 3c" writeups for full
detail, including a PR #115 Copilot review round (2 real findings, both
fixed); removed from the numbered list below (renumbered accordingly) —
this tier is now fully resolved.

## Tier 2 — cheap, low-risk wins directly in the C++ codepath

**`cpp-type-table-unify` — RESOLVED 2026-10-07**: `_chost_cpp_type`/
`_cpp_type` now both adapt onto one new shared `cpp_numeric_type`
decision table (`xdsl_ccpp/util/cpp_type_table.py`), with their three
real pre-existing quirks preserved as explicit, documented parameters/
overrides rather than silently unified away. Byte-identical output
confirmed (730 passed, 1 xfailed, zero FileCheck goldens touched), plus
new direct unit coverage neither function had before. See `BACKLOG.md`'s
entry and `CHANGELOG.md`'s resolution writeup for full detail; removed
from the numbered list below (renumbered accordingly) — this tier is
now fully resolved.

**`cpp-dual-print-pipeline` — RESOLVED 2026-10-05**: `ccpp_dsl.py` now
runs the pipeline once and prints both the `.F90` and C++ header output
from the same in-memory module (a new `ftn_and_cpp_header` pipeline
target), instead of two fully independent subprocess re-runs — ~2x
faster on a small example, verified byte-identical output. See
`BACKLOG.md`'s entry and `CHANGELOG.md`'s resolution writeup for full
detail; removed from the numbered list below (renumbered accordingly).

## Tier 3 — close real gaps in the C++ host support that exists today

**`chost-rank3-bindc` — RESOLVED 2026-10-07**: the plain `--bind-c` path
was non-functional for *every* array rank (not just "rank > 2" as
previously scoped), confirmed via real gfortran compilation and fixed by
declaring explicit shape + `target` instead of flat assumed-size,
resolving each dimension from a sibling scalar already in scope. Includes
a PR #112 Copilot review round (2 real findings, both fixed) and real
end-to-end gfortran compile verification. See `BACKLOG.md`'s entry and
`CHANGELOG.md`'s resolution writeup for full detail; removed from the
numbered list below (renumbered accordingly).

**`chost-identity-collision`/`chost-dim-collision` — RESOLVED 2026-10-07**:
`cpp_interop.py`'s `_chost_build_maps` resolved every chost argument's
identity and dimension shape via flat, global, unscoped scans across all
schemes — the same collision bug class `chost-rank3-bindc`'s PR #112
review already fixed once in `run_dispatch.py`. Fixed by scoping the scan
to exactly the schemes feeding one suite-cap function, keying a genuine
collision by each sibling's own `model_var_name` (new
`_suite_fn_groups_for`/`_chost_scan_scheme_phase_args`/
`_chost_resolve_scheme_arg_identities`). Both items fixed in one pass
(identical new scoping infrastructure needed for both), tracked as two
separate entries by deliberate choice. See `BACKLOG.md`'s entry and
`CHANGELOG.md`'s resolution writeup for full detail; removed from the
numbered list below (renumbered accordingly).

1. **`cxx-scheme-no-e2e-test`** — the *other* C++ direction (a Fortran
   host calling a C++ scheme implementation) has zero compiled
   end-to-end test, only static FileCheck fixtures. The cap-generation
   side is already done and verified correct — this is a real confidence
   gap, not a design gap.
2. **`chost-gpu-memory`** — no device-pointer contract for a C++ host
   driving GPU physics across the BIND(C) boundary. The most
   consequential of the "known limitations" for real HPC adoption of the
   chost path. Note: `chost-rank3-bindc`'s resolution confirmed `--bind-c`
   + `--directive acc/omp` together is still completely untested in this
   repo — relevant context for whoever picks this item up.
3. **`chost-column-major`** — C++ callers must manually match Fortran's
   column-major layout with no detection or alternative; a silent-wrong-
   numerical-result footgun, not an active failure.
4. **`chost-thread-safety`** — concurrent C++ threads race on the
   module-level `ccpp_suite_state` variable; safe today only because the
   one real driver is single-threaded. Lower urgency than 2/3 — no known
   real caller is multi-threaded yet.
5. **`chost-real-width-fallback`** — found 2026-10-08 during
   `lang-neutral-expr-ir` Stage 3c's work above: `cpp_interop.py`'s
   `_real_width_from_iso` silently defaults to 64-bit for any kind it
   can't resolve via the ISO-name map, including an unresolved bare-digit
   kind (a hypothetical `kind = 4` would be silently mis-widened).
   Latent only — no real fixture currently declares `kind = 4`. Fix:
   consult the new Fortran-side `real_kind_width` helper before falling
   back to 64. Low effort, low urgency.

## Tier 4 — bigger downstream investment (EAMxx C++ bridge)

6. **`eamxx-phaseB-deviceptr`** — small, concrete: a `gpu_pointer_mode =
   deviceptr` host-meta property for zero-staging GPU pointer passing.
   Directly resolves `chost-gpu-memory` above — doing this closes two
   backlog items for the cost of one.
7. **`eamxx-suite-coverage-checker`** — cheap tooling (a diff script, no
   generator changes), catches a real class of silent coverage gaps.
   Worth doing opportunistically any time, independent of the phased
   work below.
8. **`eamxx-phaseA-variant-tag`** — moderate effort: a metadata `variant`
    tag so a scheme can declare separate CPU/GPU argument lists. A loose
    prerequisite for Phase C below.
9. **`eamxx-phaseC-printer`** — the big one: generate a whole C++
    `AtmosphereProcess` class, not just the BIND(C) layer. An order of
    magnitude more effort than everything above combined; only worth
    starting once the groundwork above has landed and real EAMxx
    integration demand is confirmed (this is a design proposal against a
    different repo's own integration need, not yet a committed plan).
