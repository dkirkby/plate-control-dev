# plate-control-dev

[![Regression Tests](https://github.com/dkirkby/plate-control-dev/actions/workflows/regression-tests.yml/badge.svg)](https://github.com/dkirkby/plate-control-dev/actions/workflows/regression-tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

Control software for the [DESI](https://www.desi.lbl.gov/) focal plane fiber positioners. This package commands ~5000 robotic positioners that place optical fibers at precise locations on the telescope focal plane to capture spectra of astronomical targets.

## Status

This codebase is actively maintained and deployed at Kitt Peak National Observatory (KPNO). It is currently undergoing refactoring to improve maintainability, with a regression test suite guarding against unintended behavior changes. The unified GitHub repository (since v2.10) merges the previously separate LBL and KPNO SVN branches.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Repository Structure

```
plate-control-dev/
  petal/          Core control system for a single petal (~500 positioners)
  pecs/           Petal Engineer Control System (calibration, recovery, sequencing)
  bin/            Command-line entry points
```

### petal/

The core library. Key modules:

| Module | Purpose |
|--------|---------|
| `petal.py` | Top-level petal controller: scheduling, collision detection, move execution |
| `posmodel.py` | Software model of a single two-axis positioner |
| `posstate.py` | Persistent positioner state stored as `.conf` files |
| `posmovetable.py` | Move table generation, backlash compensation, speed ramping |
| `posschedule.py` | Anti-collision scheduling (adjust, freeze, retract-rotate-extend) |
| `postransforms.py` | Coordinate transformations and forward/inverse kinematics |
| `petaltransforms.py` | Petal-level and observatory-level coordinate transforms |
| `poscollider.pyx` | Cython-optimized collision detection |

### pecs/

Higher-level scripts for calibration, Fiber View Camera (FVC) operations, positioner recovery, and move sequencing. Requires a running DESI Observing System (DOS) instance.

## Prerequisites

- **Python** 3.9 or later
- **Cython** (to compile the collision detection extension)
- **NumPy**, **Astropy**, **pandas**, **configobj**, **matplotlib**
- **DOSlib** (optional; only required for hardware communication and PECS scripts)

## Setup

### 1. Environment variables

For standalone development and testing, you will need to define some environment variables, e.g.
```bash
export POSITIONER_LOGS_PATH=/tmp/poslogs        # log output directory
export FP_SETTINGS_PATH=/path/to/fp_settings    # configuration data
```

The `fp_settings` directory contains positioner configurations and collision lookup tables. The production version of this directory is maintained in SVN:
```bash
svn co https://desi.lbl.gov/svn/code/focalplane/fp_settings
```
There is also a small alternate directory used for regression testing within this package at `petal/regression/fp_settings_min/`.

### 2. Compile Cython extensions

```bash
cd petal
python setup.py build_ext --inplace
```

If you hit issues (e.g. after switching Python versions), clean first:

```bash
python setup.py clean --all
python setup.py build_ext --inplace
```

## Testing

The regression test suite uses a golden-master approach: tests capture outputs and compare them against stored baselines.

```bash
cd petal

# Run all tests against baselines
python -m regression.regression_test --mode compare

# Run a single test
python -m regression.regression_test --mode compare --test test_01_basic_moves

# Verbose output
python -m regression.regression_test --mode compare --verbose
```

Tests cover basic moves, collision scheduling, coordinate transforms, backlash compensation, edge cases, and special motor types. See [petal/regression/README.md](petal/regression/README.md) for details.

### Code coverage

```bash
cd petal
coverage run -m regression.regression_test --mode compare
coverage report
coverage html   # generates htmlcov/index.html
```

## Deployment

The target platforms are the LBL test stands and the DESI online system at KPNO. Neither of these uses git or github for deployment (or wants to have the full history of commits).

Instead, we deploy from github via a tarfile associated with a tagged release. This can then either be used directly, or committed to SVN (which is used for most online packages).

There is a minor complication with sending code to svn from git via a tarfile: executable bits are not preserved, for two reasons. The first issue is that the github auto-generated source tarball does not preserve executable bits. The solution is to automatically create a suitable tarball using `git archive` with a github action triggered by publishing a release. The second issue is that `svn commit` does not propagate filesystem executable bits. Since the files with this bit set all match `pecs/*.py` we can propagate the bits manually using:
```bash
find pecs -name '*.py' -exec svn propset svn:executable ON {} +
```
Note that this should not be necessary in an existing SVN repo where these properties are already set.

## How It Works

### Coordinate Systems

Positioner positions flow through a chain of coordinate systems:

```
posintTP (theta, phi)  -->  poslocXY (local mm)  -->  ptlXY (petal mm)  -->  obsXY (observatory)
```

Each positioner has two arms (theta and phi) whose lengths and offsets are stored in calibration data. `PosTransforms` handles forward and inverse kinematics for individual positioners; `PetalTransforms` maps between petal-level and observatory-level frames.

### Move Execution Flow

1. **Request targets** via `petal.request_targets()` in any supported coordinate system.
2. **Generate move tables** (`PosMoveTable`) that quantize paths into discrete motor steps.
3. **Schedule moves** (`PosSchedule`) with anti-collision checks using progressively more aggressive strategies: direct placement, debounce, retract-rotate-extend (RRE), and expert override.
4. **Send and execute** move tables to hardware (or simulator).

### Collision Detection

The Cython-optimized `poscollider` module checks for physical interference between neighboring positioners. It uses pre-computed collision lookup tables and time-quantized sweep paths to detect and resolve conflicts at scheduling time.

### Simulator Mode

Setting `simulator_on=True` when constructing a `Petal` bypasses hardware communication, allowing algorithm development and testing without physical positioners.

## Contributing

Development happens on feature branches merged to `main` via pull requests. The CI workflow runs the regression test suite across multiple Python and NumPy versions on every push and PR.

When refactoring:
- Run regression tests frequently and investigate failures immediately.
- Only update baselines (`--mode update`) for intentional behavior changes.
- Commit passing states with clear messages.
