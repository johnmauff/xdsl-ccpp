# rrtmgp_composite

A Python composite-scheme definition of CAM-SIMA's RRTMGP radiation
(see `composite_scheme_plan.md`): an exchangeable package with slots and
hooks, a CAM-SIMA host adapter, and a suite. Not meant to be compiled.

`meta/` is a metadata-only snapshot (no Fortran) of the schemes used by
atmospheric_physics' `test/test_suites/suite_rrtmgp.xml`, copied here as
`suite_rrtmgp.xml`, the flat reference suite. Source: ESCOMP/atmospheric_physics,
branch `xdsl-support`, commit `15b844d`, as checked out under CAM-SIMA's
`src/physics/ncar_ccpp`. `meta/` keeps that repository's directory layout;
refresh by re-copying the same files from a newer checkout.
