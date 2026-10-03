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

Last synchronized with `BACKLOG.md`: 2026-09-30 (after `TDB-002`/`TDB-003`
resolved and the backlog's `TDB-NNN` ID-scheme cleanup).

## Recommended near-term path

**1 → 2/3 → 4/5 → 8** is the highest-value sequence right now: it fixes
the actual architectural blocker first, costs little for the next two,
then closes the two most concrete existing-feature gaps — without
committing to Tier 4's large Phase C investment until there's real pull
for it.

## Tier 1 — foundational, blocks everything else in this direction

1. **`lang-neutral-expr-ir`** — the real architectural blocker. Statement
   *shape* is typed IR now (both the constituent-API and chost-cap
   conversions proved the pattern), but expression *content* is still raw
   Fortran text baked into every op at construction time. No
   second-language (C++) printer is achievable at all until this lands,
   regardless of what else gets done first.

## Tier 2 — cheap, low-risk wins directly in the C++ codepath

2. **`cpp-type-table-unify`** — small, bounded cleanup of the two
   independently-evolved C++ type-mapping tables (`_chost_cpp_type`/
   `_cpp_type`). Pure maintenance-drift risk today; worth doing before the
   expression-IR work (Tier 1) grows the vocabulary further and makes a
   later unification harder.
3. **`cpp-dual-print-pipeline`** — efficiency win: one pipeline run
   instead of two. Now unblocked since `CHostCapOp`'s full payload is
   typed IR rather than raw text; small, mechanical change.

## Tier 3 — close real gaps in the C++ host support that exists today

4. **`chost-rank3-bindc`** — a suspected real array-rank mismatch bug,
   still unverified against a real Fortran compiler. `g++`/real-compiler
   access on Derecho is now confirmed working (used throughout the chost
   cap's own Stage 3 verification) — this is actually resolvable now, not
   just theoretical.
5. **`cxx-scheme-no-e2e-test`** — the *other* C++ direction (a Fortran
   host calling a C++ scheme implementation) has zero compiled
   end-to-end test, only static FileCheck fixtures. The cap-generation
   side is already done and verified correct — this is a real confidence
   gap, not a design gap.
6. **`chost-gpu-memory`** — no device-pointer contract for a C++ host
   driving GPU physics across the BIND(C) boundary. The most
   consequential of the "known limitations" for real HPC adoption of the
   chost path.
7. **`chost-column-major`** — C++ callers must manually match Fortran's
   column-major layout with no detection or alternative; a silent-wrong-
   numerical-result footgun, not an active failure.
8. **`chost-thread-safety`** — concurrent C++ threads race on the
   module-level `ccpp_suite_state` variable; safe today only because the
   one real driver is single-threaded. Lower urgency than 6/7 — no known
   real caller is multi-threaded yet.

## Tier 4 — bigger downstream investment (EAMxx C++ bridge)

9. **`eamxx-phaseB-deviceptr`** — small, concrete: a `gpu_pointer_mode =
   deviceptr` host-meta property for zero-staging GPU pointer passing.
   Directly resolves `chost-gpu-memory` above — doing this closes two
   backlog items for the cost of one.
10. **`eamxx-suite-coverage-checker`** — cheap tooling (a diff script, no
    generator changes), catches a real class of silent coverage gaps.
    Worth doing opportunistically any time, independent of the phased
    work below.
11. **`eamxx-phaseA-variant-tag`** — moderate effort: a metadata `variant`
    tag so a scheme can declare separate CPU/GPU argument lists. A loose
    prerequisite for Phase C below.
12. **`eamxx-phaseC-printer`** — the big one: generate a whole C++
    `AtmosphereProcess` class, not just the BIND(C) layer. An order of
    magnitude more effort than everything above combined; only worth
    starting once the groundwork above has landed and real EAMxx
    integration demand is confirmed (this is a design proposal against a
    different repo's own integration need, not yet a committed plan).
