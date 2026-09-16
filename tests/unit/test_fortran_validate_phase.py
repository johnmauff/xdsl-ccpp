"""Unit tests for ccppMain.validate_fortran_sources -- the production-path
wiring of the Fortran-vs-.meta cross-validation phase (fparser2_to_meta.py +
validate_fir.py + the same-stem/same-directory pairing convention from
ccpp_validate_source.py), with CPP preprocessing (fortran_preprocess.py)
applied before extraction.

Currently warn-only (see the plan that introduced this method / this
repo's capgen_v1_parity_backlog.md): mismatches are printed to stderr, never
raised, pending a full sweep across CAM-SIMA's real scheme tree.
"""

import pytest

pytest.importorskip("fparser", reason="fparser not installed")

from xdsl_ccpp.tools.ccpp_dsl import ccppMain


def _write_pair(tmp_path, name, meta_body, f90_body):
    meta_path = tmp_path / f"{name}.meta"
    f90_path = tmp_path / f"{name}.F90"
    meta_path.write_text(meta_body)
    f90_path.write_text(f90_body)
    return str(meta_path)


class TestNoMismatch:
    def test_matching_pair_prints_nothing(self, tmp_path, capsys):
        meta_path = _write_pair(
            tmp_path,
            "clean_scheme",
            """\
[ccpp-table-properties]
  name = clean_scheme
  type = scheme
[ccpp-arg-table]
  name = clean_scheme_run
  type = scheme
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
""",
            """\
module clean_scheme
contains
  subroutine clean_scheme_run(errflg)
    integer, intent(out) :: errflg
  end subroutine
end module
""",
        )
        m = ccppMain()
        m.options_db = {"scheme_files": [meta_path], "preproc_defs": []}
        m.validate_fortran_sources()
        captured = capsys.readouterr()
        assert captured.err == ""


class TestMismatchDetected:
    def test_type_mismatch_warned_not_raised(self, tmp_path, capsys):
        meta_path = _write_pair(
            tmp_path,
            "bad_scheme",
            """\
[ccpp-table-properties]
  name = bad_scheme
  type = scheme
[ccpp-arg-table]
  name = bad_scheme_run
  type = scheme
[ flag ]
  standard_name = some_flag
  units = 1
  dimensions = ()
  type = integer
  intent = out
""",
            """\
module bad_scheme
contains
  subroutine bad_scheme_run(flag)
    real, intent(out) :: flag
  end subroutine
end module
""",
        )
        m = ccppMain()
        m.options_db = {"scheme_files": [meta_path], "preproc_defs": []}
        m.validate_fortran_sources()  # must not raise
        captured = capsys.readouterr()
        assert "type mismatch" in captured.err


class TestPreprocDefsResolveCppGuardedSignature:
    def test_mismatch_without_defines_clean_with_defines(self, tmp_path, capsys):
        meta_path = _write_pair(
            tmp_path,
            "cpp_scheme",
            """\
[ccpp-table-properties]
  name = cpp_scheme
  type = scheme
[ccpp-arg-table]
  name = cpp_scheme_run
  type = scheme
[ temp ]
  standard_name = air_temperature
  units = K
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  type = real
  intent = inout
""",
            """\
module cpp_scheme
contains
  subroutine cpp_scheme_run(temp)
#ifdef SPMD
    real, intent(inout) :: temp(:,:)
#else
    real, intent(inout) :: temp(:)
#endif
  end subroutine
end module
""",
        )
        m = ccppMain()

        m.options_db = {"scheme_files": [meta_path], "preproc_defs": []}
        m.validate_fortran_sources()
        assert "rank mismatch" in capsys.readouterr().err

        m.options_db = {"scheme_files": [meta_path], "preproc_defs": ["SPMD"]}
        m.validate_fortran_sources()
        assert capsys.readouterr().err == ""


class TestGracefulSkips:
    def test_no_paired_f90_is_skipped(self, tmp_path, capsys):
        meta_path = tmp_path / "orphan.meta"
        meta_path.write_text(
            """\
[ccpp-table-properties]
  name = orphan
  type = scheme
[ccpp-arg-table]
  name = orphan_run
  type = scheme
[ errflg ]
  standard_name = ccpp_error_code
  units = 1
  dimensions = ()
  type = integer
  intent = out
"""
        )
        m = ccppMain()
        m.options_db = {"scheme_files": [str(meta_path)], "preproc_defs": []}
        m.validate_fortran_sources()  # must not raise, no .F90 present
        assert capsys.readouterr().err == ""

    def test_empty_scheme_files_is_a_noop(self, capsys):
        m = ccppMain()
        m.options_db = {"scheme_files": [], "preproc_defs": []}
        m.validate_fortran_sources()
        assert capsys.readouterr().err == ""

    def test_missing_scheme_files_key_is_a_noop(self, capsys):
        m = ccppMain()
        m.options_db = {}
        m.validate_fortran_sources()
        assert capsys.readouterr().err == ""
