# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [PETAL_v2.12] - 2026-02-14

### Added

- Support for linear theta motors that mirrors existing linear phi motor support.
- Regression tests for robots with a linear theta and both linear theta and phi motors.

### Changed

- CI tests use both numpy 1.25.2 and 2.x (KPNO uses 1.25 and some 1.26 but will eventually migrate to 2.x)

### Fixed

- Missing pytz import for regression test
- Rewrite some numpy expressions to work in both 1.25 and 2.x in postransforms
- Regression test now works when DOSlib is installed in the test environment

## [PETAL_v2.11] - 2025-10-07

### Added

- Extensive regression tests of code in the petal module. For details see [petal/regression/README.md](https://github.com/dkirkby/plate-control-dev/pull/7#issuecomment-3374488881). Tests are run automatically on pushes and pull-requests to the main branch.

### Changed

- Assume that a robot is not a linear phi when ZENO_MOTOR_P is undefined.
- Update cython build script and instructions to be compatible with python 3.13 where distutils is deprecated. Prefer setuptools instead.

### Fixed

- Ensure that logging works when stats are not enabled in posschedule.py.


## [PETAL_v2.10] - 2025-09-30

This is the starting point for a unified codebase managed on github that merges the separate
svn branches used on the LBL test stands (lbl) and on the mountain (kpnopetalv2).

The main changes are to:
- normalize white space and line endings
- resolve 20 merge conflicts documented [here](https://github.com/dkirkby/plate-control-dev/wiki/LBL_KPNO_diffs).
- remove superseded top-level dirs posfidfvc and xytest

The original LBL codebase is archived [here](https://github.com/dkirkby/plate-control-dev/releases/tag/lbl-ref).

The original KPNO codebase is archived [here](https://github.com/dkirkby/plate-control-dev/releases/tag/kpno-ref).

This unified codebase is released on github [here](https://github.com/dkirkby/plate-control-dev/releases/tag/PETAL_v2.10rc2).
