# Why capgen-v1 and xdsl_ccpp assign different constituent indices

**Status: root-caused and confirmed, 2026-09-15. Not a bug in xdsl_ccpp. No
action needed on this side.** Documented here because it's easy to
re-encounter (as a "why isn't this bit-for-bit?" surprise in a future
Dropsonde comparison) and the investigation to re-derive this took a while.

## Symptom

Comparing a capgen-v1 build against an xdsl_ccpp build of the same suite
(e.g. `gw_cam7_se`) with Dropsonde shows that a given physical constituent
lands at a *different* index in the shared `ccpp_constituents` (`const`)
array on each side. Example from `gw_cam7_se`'s Dropsonde constituent map
(41 species; both builds pull from the byte-identical IC file):

```
cam q(:,:, 1) mass_number_concentration_of_cloud_liquid_...  <-> sima q(:,:,36) ...
cam q(:,:,27) water_vapor_mixing_ratio_...                   <-> sima q(:,:,18) ...
```

Same 41 species, same set, on both sides -- just a full scramble of
positions, not a shift or a missing/extra species. This shows up as a tiny
(~1 ULP, ~1e-13 to ~1e-11 absolute) numerical difference in any scheme that
sums over the whole constituent dimension in a loop order that depends on
array position (e.g. `geopotential_temp.F90`'s water-species summation) --
see `dropsonde_out/gw_cam7_after_fix/report.txt` for a worked example. It is
**not** related to the intent-merge bug or the `ConstituentSyncOp`
staleness bug fixed elsewhere this session -- this is a separate,
independent, and benign phenomenon.

## Suites affected

Only suites that register constituents **dynamically at runtime** (i.e. via
a `_register`-phase scheme with an `allocatable, intent(out)` array of
`ccpp_constituent_properties_t`, populated by scanning the IC file for
`cnst_*` variables -- see `initialize_constituents.F90`). `gw_cam7_se` is
the concrete example (41 dynamically-discovered species).

Suites with only **statically-declared** (`advected = .true.` in scheme
metadata) constituents are NOT affected -- `rk_stratiform` (3 species:
`q_wv`/`cldliq`/`cldice`, all fixed/static) came back **byte-for-byte
identical** between capgen and xdsl_ccpp after the `ConstituentSyncOp`
pointer-alias fix. This is explained below.

## Root cause

Both generators register constituents through the same shared runtime
object, `ccpp_model_constituents_t` (`ccpp_constituent_prop_mod.F90` --
nearly identical copies live in `ccpp_framework/src/` for capgen and
`xdsl_ccpp/framework_src/` for xdsl_ccpp; the only diff between them is an
unrelated default-value fix).

Registration itself (`%new_field()` -> `hash_table%add_hash_key()`) does
**not** determine the final array index. The final index is assigned later,
in `%lock_table()` (`ccp_model_const_table_lock`, same file), which walks
the internal **hash table via an iterator** (`ccpp_hash_iterator_t`) and
packs constituents into `const_metadata(:)`/`vars_layer(:,:,:)` in
**hash-bucket order**, not insertion order:

```fortran
! ccp_model_const_table_lock:
num_vars = this%hash_table%num_values()
allocate(this%const_metadata(num_vars), ...)
call hiter%initialize(this%hash_table)
do
  ...
  hval => hiter%value()
  ...
  call hiter%next()
end do
```

The hash table's bucket count is derived from a `num_elements` sizing hint
passed to `%initialize_table(num_elements)` *before* any registration
happens (`tbl_size = int(log2(num_elements * 10)) + 1`, i.e. a power-of-two
bucket count). **This is where capgen-v1 and xdsl_ccpp disagree**, in how
they compute that hint for a suite with dynamic constituents:

- **capgen-v1** (`ccpp_framework/scripts/constituents.py`, feeding the
  `cam_ccpp_register_constituents` it generates via `host_cap.py`):
  ```fortran
  num_consts = size(host_constituents, 1)
  num_suite_consts = suite_gw_cam7_se_constituents_num_consts(...)   ! STATIC/fixed-advected count ONLY
  num_consts = num_consts + num_suite_consts
  call cam_constituents_obj%initialize_table(num_consts)             ! = 0 + 1 = 1 for gw_cam7_se
  ```
  `num_suite_consts` comes from `add_constituent_vars`'s static
  scan of scheme metadata (`advected = .true.` declarations) -- it has
  no way to know about, and never queries, the size of the *dynamically*
  populated `gw_cam7_se_dynamic_constituents` module array (41 entries),
  even though that array is already populated by the time this runs.
  This looks like a genuine oversight in real capgen-v1's own
  `constituents.py`, not something specific to this project's usage of it.

- **xdsl_ccpp** (`xdsl_ccpp/transforms/constituent_cap.py`,
  `_generate_constituent_api`'s `register_constituents` body):
  ```fortran
  lc_num_consts = size(host_constituents)
  if (allocated(lc_constituents)) lc_num_consts = lc_num_consts + size(lc_constituents)   ! dynamic array, correctly included
  lc_num_consts = lc_num_consts + 1   ! n_fixed
  call cam_constituents_obj%initialize_table(lc_num_consts)          ! = 0 + 41 + 1 = 42 for gw_cam7_se
  ```

A hash table sized for capacity 1 vs. capacity 42 buckets the *same 41
string keys* into completely different bucket layouts, so `lock_table`'s
final packed order differs -- even though the actual registration content,
the IC file, and the set of species are all identical. Both builds are
internally self-consistent and correct; this is purely an artifact of an
under-sized hash table hint on the capgen-v1 side, not a data or logic bug
on either side.

### Why `rk_stratiform` (and any all-static suite) is unaffected

For a suite with zero dynamically-registered constituents, both
generators compute the *same* `num_consts`/`lc_num_consts` (just the
static/fixed-advected count, e.g. 3 for `rk_stratiform`), so both get the
identical hash table size, identical bucket layout, and identical final
order. This is exactly what was observed: `rk_stratiform` matched
byte-for-byte, `gw_cam7_se` didn't.

## How this was confirmed

1. Added a temporary `write(iulog,*)` debug print inside
   `initialize_constituents_register`'s `pio_inq_varname` scan loop in the
   *shared* scheme source
   (`src/physics/ncar_ccpp/test/test_schemes/initialize_constituents.F90`,
   a git submodule at `xdsl-ccpp.cam-sima`'s `src/physics/ncar_ccpp`).
   Rebuilt both the `gw_cam7.dropsonde-capgen` and `gw_cam7.dropsonde-xdsl`
   debug cases under `/glade/derecho/scratch/dennis/dropsonde_cases/`, ran
   Dropsonde (which drives both binaries), then read the resulting
   `atm.log.*` files in each case's `run/` directory.
   - Result: **identical** alphabetical scan order on both sides
     (`cnst_CFC11, cnst_CFC12, ..., cnst_soa_a2`), 41 entries, ruling out
     any difference in how the IC file itself is read.
   - (First attempt used bare `write(6,*)`, which never showed up anywhere
     -- CAM-SIMA's log redirection uses the `iulog` logical unit, not raw
     unit 6, from very early in `cam_comp_init`. `use cam_logfile, only:
     iulog` is required for a print in this kind of early-init scheme code
     to actually land in `atm.log`.)
   - The debug print was reverted after use; both cases were rebuilt clean
     afterward.
2. Independently corroborated via an *existing* diagnostic: generated
   `physics_read_data` (from `src/data/write_init_files.py`, shared
   generator-agnostic script) prints `"Constituent <std_name> default value
   not configured..."` while looping `do constituent_idx = 1,
   num_advected_vars` and indexing `field_data_ptr(:,:,constituent_idx)` --
   i.e. this loop variable *is* the real, final registry slot. Its printed
   order in `atm.log` differed between the two builds and matched
   Dropsonde's own constituent map, confirming Dropsonde's report reflects
   real runtime state (not a tooling artifact).
3. Read `ccp_model_const_table_lock`'s source directly (both copies) and
   confirmed the hash-bucket-iteration mechanism, then read the
   `num_consts`/`lc_num_consts` computation in both `host_cap.py`/
   `constituents.py` (capgen) and `constituent_cap.py` (xdsl_ccpp)
   side-by-side generated output for `gw_cam7_se`'s
   `cam_ccpp_register_constituents`, confirming the `1` vs `42` sizing
   discrepancy directly in the generated Fortran.

## If picking this back up later

- This is **not** on the punch list for xdsl_ccpp itself -- xdsl_ccpp's own
  sizing computation is the *correct* one; there's nothing to fix here on
  this side.
- If bit-for-bit parity with capgen-v1 across dynamic-constituent suites
  ever becomes a hard requirement (it currently isn't -- the only observed
  effect is ~1 ULP floating-point noise from summation-order differences,
  well within `ncdata_check`'s `min_difference` tolerance), the only way to
  actually reproduce it would be to make xdsl_ccpp's `initialize_table()`
  sizing hint *deliberately* match capgen-v1's (undersized) one for a given
  suite -- which would mean intentionally replicating an upstream
  capgen-v1 oversight. Not recommended; flagging only for completeness.
- A cleaner long-term fix, if this ever matters to the real
  `ccpp-framework` project (upstream, not this repo), would be for
  capgen-v1's `constituents.py` to include the dynamic array's `size(...)`
  when computing `num_consts` for `initialize_table()`, matching what
  xdsl_ccpp already does. That's an upstream `ccpp-framework` change, not
  an `xdsl-ccpp.cam-sima` one.
- Relevant debug case pairs (built, DEBUG=TRUE/NTASKS=1) still exist at
  `/glade/derecho/scratch/dennis/dropsonde_cases/` for `gw_cam7` and
  `rk_stratiform`, capgen and xdsl sides of each -- reusable for further
  probing without a fresh case build.
