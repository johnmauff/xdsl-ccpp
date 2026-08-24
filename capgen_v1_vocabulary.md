# capgen-v1's reserved CCPP vocabulary

No single consolidated listing of this exists anywhere. `ccpp-framework-fresh/doc/migration.md`
covers most of it, but scattered across several sections framed as migration guidance (old
ccpp-prebuild/ccpp-capgen → capgen deltas), not as a flat reference — and its own §3.1 control-
variable table turns out to be stale (see the correction below). This doc is the missing flat
listing: every CCPP standard name (and metadata-schema keyword) real capgen-v1's own framework
code — not physics-domain names like `air_temperature`, which are just opaque strings to the
framework — treats specially. Compiled 2026-08-21 by reading the actual source at
`ccpp-framework-fresh/capgen/`, not by trusting the doc. Every entry below is a real `file:line`
citation into that checkout; anything in `doc/migration.md` that source didn't confirm is called
out explicitly rather than repeated with unwarranted confidence.

This is about capgen-v1's own vocabulary, not xdsl-ccpp's port of it — no line-by-line "does
xdsl-ccpp implement this" column. Where this session's own work already established xdsl-ccpp's
status for a given item (from `ccpp_cap_refactor_plan.md`'s vocabulary-gap entries, task #11 and
its splits #68/#69), a short parenthetical says so; treat those as pointers, not the point of
this document.

## Correction to `doc/migration.md` §3.1

Its prose says "every host's `type=control` table must declare" 7 required variables, but its
own table lists only 6 rows — missing `group_name`. Confirmed real and required directly in
source (`ccpp_capgen.py:689`, part of the same required-list as the other 6). The listing below
uses the source, not the doc.

Also: two things this project's own examples treat as if they were reserved capgen-v1
vocabulary are **not**, per this sweep — flagged inline where relevant, since porting a naming
*choice* as if it were a framework *requirement* is an easy trap:
- `suite_lifecycle` is not a reserved scheme name. `<init>`/`<final>` SDF tags wrap an arbitrary
  scheme name chosen by the SDF author (`suite_xml.py:89-97`); `suite_lifecycle` is just the name
  this project's own ported examples happen to use for that scheme.
- `dynamic_constituents_for_*` is not framework vocabulary either — it's an ordinary,
  example-specific standard name coined for `examples/advection`'s own constituent output
  variables, meaningless to the framework itself.

## 1. Required `type=control` standard names

A closed set — enforced in `ccpp_capgen.py:733-856` (`_validate_required_control_vars`); any
other variable declared in a `type=control` table is a hard parse-time error
(`ccpp_capgen.py:837-848`).

| Standard name                | Fortran type | Purpose                                          |
|-------------------------------|--------------|---------------------------------------------------|
| `suite_name`                  | character    | Drives suite dispatch                              |
| `group_name`                  | character    | Drives per-group `select case` inside `ccpp_physics_*` (missing from `doc/migration.md`'s own table) |
| `horizontal_loop_begin`       | integer      | Lower chunk-bound                                  |
| `horizontal_loop_end`         | integer      | Upper chunk-bound                                  |
| `number_of_physics_threads`   | integer      | Physics-internal thread budget (pass 1 if unused)  |
| `ccpp_error_code`              | integer      | Error flag                                         |
| `ccpp_error_message`           | character    | Error message                                      |

`ccpp_capgen.py:688-694`.

Paired-optional — declare **both** members of a pair or **neither**; declaring exactly one is a
hard error (`ccpp_capgen.py:725-730,806-824`):

| Pair                                       | Purpose                                                  |
|---------------------------------------------|-----------------------------------------------------------|
| `instance_number` / `number_of_instances`   | Multi-instance API                                        |
| `thread_number` / `number_of_threads`       | Multi-threading API (count carried for API symmetry — the framework itself only consumes it at register/init time, per the comment at `ccpp_capgen.py:716-720`) |

(xdsl-ccpp mirrors the `instance_number`/`number_of_instances` pair; the `thread_number`/
`number_of_threads` pair is task #69's own scoped gap.)

## 2. Dimension standard names

From `generator/suite_resolver.py`:

- `horizontal_dimension` — the only accepted horizontal-loop dimension name
  (`_HORIZ_LOOP_DIMS`, `suite_resolver.py:85-87,92`).
- `horizontal_loop_extent` — rejected outright at parse time
  (`_FORBIDDEN_DIMENSION_NAMES`, `ccpp_capgen.py:592-596`, checked in `_check_no_loop_dimensions`)
  unless `--legacy-mode` rewrites it first (§3 below).
- `vertical_layer_dimension`, `vertical_interface_dimension` — `_VDIM_STDS`
  (`suite_resolver.py:97-100`), consulted by the vertical-flip transform when host and scheme
  disagree on `top_at_one`.
- `ccpp_constant_one` — the only accepted non-integer literal as a range dimension's lower bound
  (`suite_resolver.py:113`).

Equivalence between these base names is **always on**, unconditionally — no flag gates it. The
two GFS-specific collapses in §4 are the only ones gated behind an opt-in flag.

## 3. Legacy renames (`--legacy-mode`)

Full `_LEGACY_NAME_MAP`, `metadata/legacy_compat.py:61-73` — confirmed no other entries exist:

| Legacy name                  | Canonical replacement |
|-------------------------------|------------------------|
| `horizontal_loop_extent`      | `horizontal_dimension` |
| `number_of_openmp_threads`    | `number_of_threads`    |

(xdsl-ccpp mirrors the first via `CCPP_DEPRECATED_STD_NAMES`; the second is task #11/#69's own
scoped gap — noted there as coupled to, not independent of, the `thread_number` mechanism in §5.)

## 4. GFS dim aliases (`--gfs-dim-aliases`)

Full `_DIM_ALIAS_MAP`, `metadata/dim_aliases.py:78-89` — confirmed no other entries exist. Only
collapsed at dim-*identity comparison* time (never renamed, never merged as a standalone
variable):

| Alias                                                  | Canonical representative     |
|----------------------------------------------------------|-------------------------------|
| `adjusted_vertical_layer_dimension_for_radiation`         | `vertical_layer_dimension`    |
| `vertical_composition_dimension`                          | `vertical_layer_dimension`    |

(xdsl-ccpp implements this as of 2026-08-24, gated behind its own `--gfs-dim-aliases` flag —
task #68.)

## 5. Registered scalar-index dimensions

Full `SCALAR_INDEX_DIMS`, `metadata/registered_dimensions.py:135-149` — confirmed no other
entries exist. A leaf (scheme-bound) variable must never declare one of these; only a container
DDT-instance variable may (hard parse-time error otherwise):

| Count dimension        | Substituted scalar index |
|--------------------------|----------------------------|
| `number_of_instances`    | `instance_number`          |
| `number_of_threads`      | `thread_number`            |

(xdsl-ccpp implements the first pair as two hardcoded constants + logic spread across 8 files,
not as a general table like this one — task #69's own scoped gap covers generalizing it and
adding the second pair.)

## 6. Error/status vocabulary

`ccpp_error_code`, `ccpp_error_message` — see §1; no other error-specific reserved names found
anywhere in the sweep.

## 7. Constituent vocabulary

From `generator/suite_resolver.py` unless noted:

| Standard name                              | Meaning                                                        | Source |
|----------------------------------------------|------------------------------------------------------------------|--------|
| `ccpp_constituent_properties_t`               | Type marker recognized as a register-phase constituent-output arg | `suite_resolver.py:119` (also `host_constituents.py:42`, `suite_cap.py:63`) |
| `ccpp_model_constituents_object`              | Host-exposed constituent object (opt-in)                          | `suite_resolver.py:124` |
| `ccpp_constituents`                           | Base constituent array                                            | `suite_resolver.py:130` |
| `ccpp_constituent_tendencies`                 | Constituent tendency array                                        | `suite_resolver.py:131` |
| `ccpp_constituent_properties`                 | Constituent properties array                                      | `suite_resolver.py:132` |
| `number_of_ccpp_constituents`                 | Constituent count (also usable as a dimension, §1167 of `doc/migration.md`) | `suite_resolver.py:133` |
| `ccpp_constituent_minimum_values`             | Per-constituent floor values                                      | `suite_resolver.py:134` |
| `tendency_of_<x>` / `index_of_<x>`            | Standard-name *prefixes*, not full names — `index_of_<x>` gets SHA1-mangled past 63 characters | `suite_resolver.py:135-136,148-184` |

Not standard names, but part of the same convention:
- `ccpp_model_constituents_obj` — the per-instance Fortran local variable name (not a standard
  name) — `suite_resolver.py:203`.
- `ccpp_host_constituents` — the fixed host-wide module name every suite cap `use`s —
  `suite_resolver.py:221`.
- `default_value`, `min_value`, `mixing_ratio_type`, `water_species` — per-variable metadata
  *attributes* (not standard names) consumed by the `--legacy-auto-clone-constituents` shim —
  `metadata/auto_clone_constituents.py:100-103`.

## 8. SDF-structural vocabulary

No reserved scheme or table *names* exist at this level — `<init>`/`<final>` are generic SDF
tags wrapping an arbitrary, author-chosen scheme name (`suite_xml.py:89-97`; see the correction
at the top of this doc). No dedicated subcycle-loop-count standard name exists either — a
`<subcycle loop="...">` bound is resolved exactly like any other scheme-declared standard name,
per `suite_resolver.py`'s ordinary loop-context handling.

## 9. Generator-owned locals (never declared by a host)

`suite_resolver.py:1447-1452`:

- `ccpp_loop_counter`
- `ccpp_loop_extent`

Both resolve to generated do-loop locals, in scope only inside a `<subcycle>` block body.

## 10. Metadata-schema keywords (not standard names)

Distinct from everything above: these are reserved *keys* in the `.meta` file schema itself, not
CCPP standard names.

- **Table types** (`type = ...` on a `[ccpp-table-properties]` block): `scheme`, `host`,
  `control`, `suite`, `ddt` — `VALID_TABLE_TYPES`, `metadata_table.py:110`. (`doc/migration.md`
  never mentions `suite` as a distinct 5th table type — worth checking separately whether it's
  used differently than the doc implies, if that ever becomes relevant.)
- **Table-header keys**: `name`, `type`, `module_name`, `source_path`, `dependencies`,
  `dependencies_path`, `kind_spec` — `metadata_table.py:1003-1050`.
- **Per-variable attribute keys**: `standard_name`, `long_name`, `units`, `dimensions`, `type`,
  `kind`, `intent`, `optional`, `active`, `protected`, `allocatable`, `top_at_one` —
  `metadata_table.py:492-497`; the boolean-typed subset is `optional`, `protected`, `allocatable`
  (`metadata_table.py:485`).
