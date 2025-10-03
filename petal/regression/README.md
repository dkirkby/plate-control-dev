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

The suite includes 8 comprehensive test scenarios:

1. **test_01_basic_moves** - All coordinate systems (posintTP, poslocTP, poslocXY, etc.)
2. **test_02_collision_scenarios** - Known collision cases with adjust/freeze modes
3. **test_03_edge_cases** - Theta hardstop, phi limits, boundary conditions
4. **test_04_state_management** - State persistence, updates, validation
5. **test_05_transform_chain** - Forward/reverse/roundtrip coordinate transforms
6. **test_06_scheduling_algorithms** - All anticollision × anneal mode combinations
7. **test_07_move_table_formats** - All 7 output formats (schedule, collider, hardware, etc.)
8. **test_08_complex_sequences** - Multi-move operations with corrections

---

## Prerequisites

### Required Environment Variables

```bash
# Create log directory
mkdir -p /tmp/poslogs
export POSITIONER_LOGS_PATH=/tmp/poslogs

# Point to fp_settings directory
export FP_SETTINGS_PATH=/path/to/fp_settings
```

If `fp_settings` is not available:
```bash
svn co https://desi.lbl.gov/svn/code/focalplane/fp_settings
export FP_SETTINGS_PATH=$PWD/fp_settings
```

### Required Python Packages

```bash
pip install numpy astropy pandas configobj Cython
```

### Compile Cython Extensions

```bash
cd /path/to/plate-control-dev/petal
python setup.py build_ext --inplace clean --all
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

```bash
cd /path/to/plate-control-dev/petal
python -m regression.regression_test --mode baseline
```

This creates baseline JSON files in `regression/baselines/` that capture the current behavior as "correct."

**Expected output** (verbose petal module logging omitted for clarity):
```
======================================================================
Running 8 regression test(s)
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

======================================================================
TEST SUMMARY
======================================================================
  BASELINE_SAVED      :   8 (100.0%)
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
Running 8 regression test(s)
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

======================================================================
TEST SUMMARY
======================================================================
  PASS                :   8 (100.0%)
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

Add to your GitHub Actions workflow:

```yaml
- name: Run regression tests
  run: |
    cd petal
    export POSITIONER_LOGS_PATH=/tmp/poslogs
    export FP_SETTINGS_PATH=${{ github.workspace }}/fp_settings
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
- Show which specific lines weren't covered
- Sort results by coverage percentage

### Understanding Coverage Results

```
Name                 Stmts   Miss  Cover   Missing
--------------------------------------------------
petal.py              2888    450    84%   123-145, 234-267, ...
posmodel.py            312     45    86%   67-72, 145, ...
posstate.py            456     89    80%   234-245, 567, ...
posschedule.py         789    123    84%   456-478, 890, ...
...
--------------------------------------------------
TOTAL                 5234    789    85%
```

- **Stmts**: Total lines of executable code
- **Miss**: Lines not executed during tests
- **Cover**: Percentage covered
- **Missing**: Specific line numbers not covered

High coverage (>80%) indicates the regression tests exercise most of the code paths, providing confidence that refactoring won't break untested code.

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
python setup.py build_ext --inplace clean --all
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
│   ├── regression_test.py       # Main test suite
│   ├── baselines/                # Golden master JSON files
│   │   ├── test_01_basic_moves.json
│   │   ├── test_02_collision_scenarios.json
│   │   └── ... (8 total)
│   └── docs/
│       └── README.md             # This file
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

- **Runtime**: ~2-3 minutes for all 8 tests
- **Per test**: ~15-30 seconds average (varies by test complexity)
- **Baseline size**: ~50-200 KB per test (8 files total ~1 MB)

Tests run sequentially to ensure deterministic execution order.

---

## Questions or Issues?

- Review this documentation
- Run with `--verbose` flag for detailed output
- Check troubleshooting section above
- Examine baseline JSON files to understand expected data structure
- Review test implementations in `regression_test.py`
