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
- When a C++-relevant item here resolves, remove it from this file
  entirely in the same sitting (full history lives in `BACKLOG.md`/
  `CHANGELOG.md` — nothing lingers here, open items only).
- When a new item lands in `BACKLOG.md` that bears on this same goal, add
  it here too, at whatever tier its priority warrants.
- IDs here must always match `BACKLOG.md`'s current ID for that item
  exactly.

Last synchronized with `BACKLOG.md`: 2026-10-08.

## Recommended near-term path

**1 → 2/3** is the highest-value sequence right now: the architectural
blocker and all cheap wins are done, so next is the `cxx-scheme`
end-to-end test gap, then the two most concrete remaining chost
limitations — without committing to Tier 2's large Phase C investment
until there's real pull for it.

## Tier 1 — close real gaps in the C++ host support that exists today

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

## Tier 2 — bigger downstream investment (EAMxx C++ bridge)

5. **`eamxx-phaseB-deviceptr`** — small, concrete: a `gpu_pointer_mode =
   deviceptr` host-meta property for zero-staging GPU pointer passing.
   Directly resolves `chost-gpu-memory` above — doing this closes two
   backlog items for the cost of one.
6. **`eamxx-suite-coverage-checker`** — cheap tooling (a diff script, no
   generator changes), catches a real class of silent coverage gaps.
   Worth doing opportunistically any time, independent of the phased
   work below.
7. **`eamxx-phaseA-variant-tag`** — moderate effort: a metadata `variant`
    tag so a scheme can declare separate CPU/GPU argument lists. A loose
    prerequisite for Phase C below.
8. **`eamxx-phaseC-printer`** — the big one: generate a whole C++
    `AtmosphereProcess` class, not just the BIND(C) layer. An order of
    magnitude more effort than everything above combined; only worth
    starting once the groundwork above has landed and real EAMxx
    integration demand is confirmed (this is a design proposal against a
    different repo's own integration need, not yet a committed plan).
