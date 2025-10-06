# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [PETAL_v2.11] - Unreleased

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
