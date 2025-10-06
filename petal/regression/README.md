# Regression Testing for Petal Module

This regression test suite uses a "golden master" approach to ensure that code refactoring does not introduce unintended behavior changes.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Common Usage Scenarios](#common-usage-scenarios)
- [Measuring Code Coverage](#measuring-code-coverage)
- [Understanding Test Results](#understanding-test-results)
- [Adding New Tests](#adding-new-tests)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Overview

### What is Regression Testing?

Regression testing verifies that code changes don't break existing functionality. This suite captures current behavior as "correct" baselines, then compares future test runs against those baselines to detect any behavioral changes.

**Golden Master Testing Strategy:**
1. **Baseline Creation**: Run tests once to capture current behavior
2. **Comparison**: After code changes, compare new results to baseline
3. **Verification**: Any differences indicate potential regressions

### Why Use This?

- ✅ **Safety net** during aggressive refactoring
- ✅ **Objective verification** that behavior hasn't changed
- ✅ **Documentation** of expected system behavior
- ✅ **Confidence** to make bold changes
- ✅ **Fast feedback** loop (~2-3 minutes for full suite)

### What's Tested?

The suite includes 12 comprehensive test scenarios:

1. **test_01_basic_moves** - All coordinate systems (posintTP, poslocTP, poslocXY, etc.)
2. **test_02_collision_scenarios** - Known collision cases with adjust/freeze modes
3. **test_03_edge_cases** - Theta hardstop, phi limits, boundary conditions
4. **test_04_state_management** - State persistence, updates, validation
5. **test_05_transform_chain** - Forward/reverse/roundtrip coordinate transforms
6. **test_06_scheduling_algorithms** - All anticollision × anneal mode combinations
7. **test_07_move_table_formats** - All 7 output formats (schedule, collider, hardware, etc.)
8. **test_08_complex_sequences** - Multi-move operations with corrections
9. **test_09_petal_level_coordinates** - Petal-level (ptlXY) and observatory-level (obsXY) coordinate systems
10. **test_10_backlash_compensation** - Automatic backlash compensation in move tables
11. **test_11_linear_phi_motor** - Zeno motor (linear phi motor) specific behavior
12. **test_12_disabled_positioner** - Handling of positioners with CTRL_ENABLED = False

---

## Prerequisites

### Environment Variables (Optional)

**The regression tests now work out-of-the-box with no environment setup required!**

The test suite includes a minimal `fp_settings_min/` directory and uses `test_logs_path/` for logs. However, you can override these defaults:

```bash
# Optional: Use custom fp_settings directory
export FP_SETTINGS_PATH=/path/to/fp_settings

# Optional: Use custom log directory
export POSITIONER_LOGS_PATH=/path/to/logs
```

To use the full `fp_settings` from SVN:
```bash
svn co https://desi.lbl.gov/svn/code/focalplane/fp_settings
export FP_SETTINGS_PATH=$PWD/fp_settings
```

**Default behavior** (no environment variables set):
- Uses `regression/fp_settings_min/` (30KB, self-contained)
- Logs to `regression/test_logs_path/`
- Command-line overrides: `--fp-settings-path` and `--positioner-logs-path`

### Required Python Packages

```bash
pip install numpy astropy pandas configobj Cython matplotlib
```

### Compile Cython Extensions

```bash
cd /path/to/plate-control-dev/petal
python setup.py build_ext --inplace
```

If you encounter issues (e.g., after switching Python versions), clean first:
```bash
python setup.py clean --all
python setup.py build_ext --inplace
```

### DOSlib Dependency

**You do NOT need to install DOSlib for regression testing.** The code gracefully handles its absence:
- `DOSlib.positioner_index` is wrapped in try/except with fallbacks
- `DOSlib.flags` is optional (you'll see a warning which can be ignored)
- `DOSlib.util` has a fallback implementation

You'll see these warnings during test runs (which are normal and can be ignored):
```
DOSlib.positioner_index module not available. (This may be ok for some environments.)
WARNING: DOSlib.flags not imported! Flags will not be set!
```

---

## Quick Start

### Step 1: Create Initial Baselines (Before Refactoring)

**⚠️ IMPORTANT: Only do this once, before you start refactoring!**

Baselines for tests 01-08 were created on 2-Oct-2025 to establish the unified code base ([commit 7b4a283](https://github.com/dkirkby/plate-control-dev/commit/7b4a283815557e02634694ca6ac308c4c185634f)). Tests 09-12 were added on 5-Oct-2025 to improve coverage. All baselines are committed to version control.

```bash
cd /path/to/plate-control-dev/petal
python -m regression.regression_test --mode baseline
```

This creates baseline JSON files in `regression/baselines/` that capture the current behavior as "correct."

**Expected output** (verbose petal module logging omitted for clarity):
```
======================================================================
Running 12 regression test(s)
Mode: BASELINE
Baseline directory: /path/to/petal/regression/baselines
======================================================================

Running test_01_basic_moves... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_02_collision_scenarios... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_03_edge_cases... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_04_state_management... 💾 BASELINE_SAVED
Running test_05_transform_chain... 💾 BASELINE_SAVED
Running test_06_scheduling_algorithms... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_07_move_table_formats... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_08_complex_sequences... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_09_petal_level_coordinates... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_10_backlash_compensation... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_11_linear_phi_motor... [... verbose logging ...] 💾 BASELINE_SAVED
Running test_12_disabled_positioner... [... verbose logging ...] 💾 BASELINE_SAVED

======================================================================
TEST SUMMARY
======================================================================
  BASELINE_SAVED      :  12 (100.0%)
```

**Note**: Each test generates extensive output from the petal module (state loading, collision checks, move execution, etc.). This is normal operation - focus on the final test status.

### Step 2: Commit Baselines to Git

```bash
git add regression/baselines/
git commit -m "Add regression test baselines before refactoring"
```

### Step 3: Verify Tests Pass on Current Code

```bash
python -m regression.regression_test --mode compare
```

All tests should pass on the first run after creating baselines.

### Step 4: Make Code Changes

Refactor, edit, improve the code as needed.

### Step 5: Verify No Regressions After Changes

```bash
python -m regression.regression_test --mode compare
```

**Success output** (verbose logging omitted):
```
======================================================================
Running 12 regression test(s)
Mode: COMPARE
Baseline directory: /path/to/petal/regression/baselines
======================================================================

Running test_01_basic_moves... [... verbose logging ...] ✓ PASS
Running test_02_collision_scenarios... [... verbose logging ...] ✓ PASS
Running test_03_edge_cases... [... verbose logging ...] ✓ PASS
Running test_04_state_management... ✓ PASS
Running test_05_transform_chain... ✓ PASS
Running test_06_scheduling_algorithms... [... verbose logging ...] ✓ PASS
Running test_07_move_table_formats... [... verbose logging ...] ✓ PASS
Running test_08_complex_sequences... [... verbose logging ...] ✓ PASS
Running test_09_petal_level_coordinates... [... verbose logging ...] ✓ PASS
Running test_10_backlash_compensation... [... verbose logging ...] ✓ PASS
Running test_11_linear_phi_motor... [... verbose logging ...] ✓ PASS
Running test_12_disabled_positioner... [... verbose logging ...] ✓ PASS

======================================================================
TEST SUMMARY
======================================================================
  PASS                :  12 (100.0%)
```

---

## Common Usage Scenarios

### Run All Tests (Compare to Baseline)

```bash
python -m regression.regression_test --mode compare
```

Exit code: `0` = all pass, `1` = some failed

### Run Specific Test

```bash
python -m regression.regression_test --mode compare --test test_01_basic_moves
```

### Run with Verbose Output

```bash
python -m regression.regression_test --mode compare --verbose
```

Shows detailed information about what's being tested in each scenario.

### Update Baseline After Intentional Change

If you've intentionally changed behavior (e.g., fixed a bug, improved an algorithm):

```bash
# Update specific test baseline
python -m regression.regression_test --mode update --test test_03_edge_cases

# Or recreate all baselines
python -m regression.regression_test --mode baseline
```

**⚠️ WARNING**: Only update baselines if the behavior change is intentional and verified to be correct!

### Use Custom Baseline Directory

```bash
python -m regression.regression_test --baseline-dir /path/to/custom/baselines --mode compare
```

### Integration with CI/CD

A GitHub Actions workflow is configured in `.github/workflows/regression-tests.yml` to automatically run regression tests on every push and pull request.

**What the workflow does:**
- Runs tests on Python 3.9.6 (currently used at LBL and KPNO), 3.11, and 3.13
- Compiles Cython extensions
- Executes all regression tests
- Measures code coverage (Python 3.11 only)
- Uploads coverage HTML report as an artifact

**Viewing CI results:**
- Check the "Actions" tab on GitHub to see test results
- Download coverage reports from successful runs (available for 30 days)

**Testing on the `regtest` branch:**
To test the workflow on your development branch before merging:

```bash
# Push your commits to the regtest branch
git push origin regtest

# View results at: https://github.com/YOUR_USERNAME/plate-control-dev/actions
```

The workflow is triggered automatically for the `regtest` branch, so you can verify that all tests pass before merging to `main`.

**Adding to your own workflow:**

```yaml
- name: Compile Cython extensions
  run: |
    cd petal
    python setup.py build_ext --inplace

- name: Run regression tests
  run: |
    cd petal
    # No environment setup needed - uses built-in fp_settings_min
    python -m regression.regression_test --mode compare
```

---

## Measuring Code Coverage

To measure how much of the petal module code is exercised by the regression tests:

### Quick Coverage Report

```bash
# Run tests with coverage measurement
coverage run -m regression.regression_test --mode compare

# View coverage report in terminal
coverage report

# Generate detailed HTML report
coverage html
open htmlcov/index.html
```

The `.coveragerc` file is already configured to:
- Measure coverage for petal module code only (excludes regression test code)
- Exclude collision_lookup_generator.py and collision_lookup_generator_subset.py which are obsolete
- Exclude petalcomm.py and petalsockcomm.py which require access to hardware
- Sort results by coverage percentage

### Coverage Report from 5-Oct-2025 (All 12 Tests)

```
Name                  Stmts   Miss  Cover
-----------------------------------------
replay.py               301    301     0%
posanimator.py          206    155    25%
petal.py               1689   1245    26%
posschedstats.py        338    244    28%
petaltransforms.py      228    127    44%
posschedulestage.py     454    241    47%
posschedule.py          796    369    54%
postransforms.py        259    103    60%
posstate.py             294    102    65%
posconstants.py         338    103    70%
posmovetable.py         463    135    71%
posmodel.py             371     56    85%
xy2tp.py                 96      7    93%
-----------------------------------------
TOTAL                  5833   3188    45%
```

**Coverage improvements from tests 09-12:**
- **test_09**: Added ptlXY and obsXY coordinate system coverage (postransforms.py: 53% → 60%)
- **test_10**: Verified backlash compensation paths (already covered by existing tests)
- **test_11**: Added Zeno motor (linear phi) coverage (posmodel.py: 80% → 85%, posmovetable.py: 66% → 71%, posschedulestage.py: 37% → 47%)
- **test_12**: Added disabled positioner handling (petal.py: 26%, posschedule.py: 53% → 54%)

- **Stmts**: Total lines of executable code
- **Miss**: Lines not executed during tests
- **Cover**: Percentage covered

---

## Understanding Test Results

### Test Passes (✓ PASS)

Output matches baseline exactly. Refactoring preserved behavior.

### Test Fails (✗ FAIL)

```
Running test_03_edge_cases... ✗ FAIL
  Signature mismatch!
  Expected: a1b2c3d4...
  Got:      e5f6g7h8...

  Data differences:
  - baseline['posintTP'][0]: 30.0
  + current['posintTP'][0]:  30.00001
```

**Investigate:**
1. Is this an intentional behavior change? → Update baseline
2. Is this a bug you introduced? → Fix the code
3. Is this non-determinism (random numbers, timestamps)? → Fix test to be deterministic

### New Baseline Created (🆕 NEW_BASELINE)

Baseline didn't exist, so one was created. This happens:
- First time running a test
- After deleting a baseline file

---

## Adding New Tests

### Structure of a Test Method

```python
def test_09_my_new_scenario(self):
    """Test description for documentation"""
    # 1. Setup
    ptl = self._create_petal()
    posid = self.test_posids[0]

    # 2. Execute operations
    ptl.request_move_posintTP(posid, 45.0, 120.0)
    ptl.schedule_moves(anticollision='adjust')
    ptl.send_and_execute_moves()

    # 3. Capture results (must be JSON-serializable)
    state = ptl.positioners[posid].state
    data = {
        'final_position': {
            'posintTP': list(state.posintTP()),
            'poslocTP': list(state.poslocTP()),
        },
        'some_calculation': my_calculation_result,
    }

    return data
```

### Requirements

1. **Test method name** must start with `test_` and match `test_\d{2}_.*` pattern
2. **Return value** must be JSON-serializable (dict, list, numbers, strings, booleans, None)
3. **Deterministic** - same inputs must produce same outputs every time
4. **Self-contained** - create fresh Petal instance, don't rely on state from other tests

### Register New Test

Add to `RegressionTestSuite.ALL_TESTS`:

```python
ALL_TESTS = [
    'test_01_basic_moves',
    'test_02_collision_scenarios',
    # ... existing tests ...
    'test_09_my_new_scenario',  # Your new test
]
```

### Create Baseline for New Test

```bash
python -m regression.regression_test --mode baseline --test test_09_my_new_scenario
```

---

## Troubleshooting

### "Required environment variables not set"

```bash
export POSITIONER_LOGS_PATH=/tmp/poslogs
export FP_SETTINGS_PATH=/path/to/fp_settings
```

### "ModuleNotFoundError: No module named 'poscollider'"

Cython extensions not compiled:
```bash
cd petal
python setup.py build_ext --inplace
```

If that doesn't work, clean first and retry:
```bash
python setup.py clean --all
python setup.py build_ext --inplace
```

### Tests Fail Immediately After Creating Baseline

This indicates non-deterministic behavior. Common causes:
- Random number generation without fixed seed
- Timestamps in test data
- System-dependent paths
- Floating-point operations with different rounding

### Test Fails After Refactoring

1. Run with `--verbose` to see detailed output:
   ```bash
   python -m regression.regression_test --mode compare --verbose --test test_XX
   ```

2. Check the diff shown in output - is the change intentional?

3. If intentional, update baseline:
   ```bash
   python -m regression.regression_test --mode update --test test_XX
   ```

### Verbose Petal Logging Obscures Test Results

This is expected. The petal module generates extensive logging:
```
Some parameters not provided to __init__, reading petal config.
Requests processed in 0.000 sec
schedule_moves called with anticollision = adjust
Penultimate collision check --> num colliding sweeps = 0
...
```

Focus on the final test status line: `✓ PASS` or `✗ FAIL`

### "PermissionError" or "OSError" on POSITIONER_LOGS_PATH

Ensure the directory exists and is writable:
```bash
mkdir -p /tmp/poslogs
chmod 755 /tmp/poslogs
```

---

## Best Practices

### Before Refactoring

1. ✅ Create baselines on clean, working code
2. ✅ Verify all tests pass: `python -m regression.regression_test --mode compare`
3. ✅ Commit baselines to git
4. ✅ Document what refactoring you're about to do

### During Refactoring

1. ✅ Run tests frequently after each significant change
2. ✅ Commit passing states: "Refactored X - regression tests: PASS"
3. ✅ If tests fail, investigate immediately (easier to debug small changes)
4. ✅ Only update baselines if behavior change is intentional and verified

### After Refactoring

1. ✅ Run full test suite: `python -m regression.regression_test --mode compare`
2. ✅ Check code coverage to identify untested areas
3. ✅ Consider adding new tests for edge cases discovered during refactoring
4. ✅ Document any intentional behavior changes

### General Guidelines

- **Never commit failing tests** - either fix the code or update the baseline
- **Don't update all baselines blindly** - investigate each failure individually
- **Keep baselines in version control** - they document expected behavior
- **Run tests before merging** - catch regressions before they reach main branch
- **Add tests for bugs** - when fixing a bug, add a test that would have caught it

### Baseline Update Workflow

When updating baselines after intentional changes:

```bash
# 1. Verify the change is correct
python -m regression.regression_test --mode compare --test test_XX --verbose

# 2. Review what changed - is this expected?
# (Look at the diff in the test output)

# 3. If expected, update baseline
python -m regression.regression_test --mode update --test test_XX

# 4. Verify updated baseline passes
python -m regression.regression_test --mode compare --test test_XX

# 5. Commit with descriptive message
git add regression/baselines/test_XX.json
git commit -m "Update test_XX baseline: improved collision detection algorithm"
```

---

## Test Suite Architecture

### File Organization

```
petal/
├── regression/
│   ├── __init__.py
│   ├── regression_test.py        # Main test suite
│   ├── baselines/                # Golden master JSON files
│   │   ├── test_01_basic_moves.json
│   │   ├── test_02_collision_scenarios.json
│   │   └── ... (12 total)
│   ├── fp_settings_min/          # Minimal config for self-contained testing
│   │   ├── pos_settings/         # 9 positioner configs (7 standard + 1 Zeno + 1 disabled)
│   │   ├── collision_settings/   # Collision parameters
│   │   ├── ptl_settings/         # Petal templates
│   │   └── fid_settings/         # Fiducial templates
│   ├── test_logs_path/           # Default log output directory
│   └── README.md                 # This file
├── petal.py                      # Code being tested
├── posmodel.py                   # Code being tested
└── ... (other petal module files)
```

### How It Works

1. **Test Execution**: Each test method exercises specific petal functionality
2. **Data Capture**: Test returns a data dictionary with all relevant outputs
3. **Serialization**: Data is serialized to JSON with deterministic ordering
4. **Hashing**: SHA256 hash computed for quick comparison
5. **Comparison**: Hash and full data compared against baseline
6. **Reporting**: Results displayed with clear PASS/FAIL status

### Baseline File Format

```json
{
  "timestamp": "2025-10-02T12:41:10.800382",
  "signature": "f685ae84e40be710ca62058fe8d055908caf507130cbf809723c71685c107356",
  "data": {
    "test_specific_key": "test_specific_value",
    "posintTP": [30.00005, 120.000034],
    "...": "..."
  }
}
```

- `timestamp`: When baseline was created (for reference only)
- `signature`: SHA256 hash of serialized data (for quick comparison)
- `data`: The actual test output being validated

---

## Command Reference

```bash
# Create baselines (do once before refactoring)
python -m regression.regression_test --mode baseline

# Compare against baselines (do frequently during refactoring)
python -m regression.regression_test --mode compare

# Run specific test
python -m regression.regression_test --mode compare --test test_01_basic_moves

# Update specific baseline after intentional change
python -m regression.regression_test --mode update --test test_03_edge_cases

# Verbose output (see what's being tested)
python -m regression.regression_test --mode compare --verbose

# Custom baseline directory
python -m regression.regression_test --baseline-dir /path/to/baselines --mode compare

# Measure code coverage
coverage run -m regression.regression_test --mode compare
coverage report

# Get help
python -m regression.regression_test --help
```

---

## Performance

- **Runtime**: ~3-4 minutes for all 12 tests
- **Per test**: ~10-30 seconds average (varies by test complexity)
- **Baseline size**: ~3-200 KB per test (12 files total ~1.2 MB)

Tests run sequentially to ensure deterministic execution order.

---

## Questions or Issues?

- Review this documentation
- Run with `--verbose` flag for detailed output
- Check troubleshooting section above
- Examine baseline JSON files to understand expected data structure
- Review test implementations in `regression_test.py`
