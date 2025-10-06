# Minimal FP Settings for Regression Testing

This directory contains a minimal version of the `fp_settings` directory required to run the regression test suite.

## Purpose

The regression tests need configuration files to function, but don't require the full `fp_settings` directory (which contains thousands of files and is ~150MB). This minimal version provides only the essential template files needed for testing, making the test suite:

- **Self-contained** - No external dependencies or environment setup required
- **Fast** - Small footprint for quick test runs
- **Portable** - Can be version controlled and distributed with the code

## Contents

The directory contains the minimum required subdirectories and DEFAULT configuration templates:

```
fp_settings_min/
├── README.md                                   (this file)
├── pos_settings/
│   ├── _unit_settings_DEFAULT.conf            (8.0K - positioner template)
│   ├── unit_M02101.conf                        (2.1K - test positioner, device_loc 21, backlash enabled)
│   ├── unit_M02201.conf                        (2.1K - test positioner, device_loc 22)
│   ├── unit_M02601.conf                        (2.1K - test positioner, device_loc 26)
│   ├── unit_M02701.conf                        (2.1K - test positioner, device_loc 27)
│   ├── unit_M02801.conf                        (2.1K - test positioner, device_loc 28)
│   ├── unit_M03301.conf                        (2.1K - test positioner, device_loc 33)
│   ├── unit_M03401.conf                        (2.1K - test positioner, device_loc 34)
│   └── unit_M03501.conf                        (2.2K - Zeno motor positioner, device_loc 35)
├── collision_settings/
│   └── _collision_settings_DEFAULT.conf       (4.0K - collision parameters)
├── ptl_settings/
│   └── _unit_settings_DEFAULT.conf            (1.1K - petal template)
├── fid_settings/
│   └── _unit_settings_DEFAULT.conf            (2.3K - fiducial template)
├── hwsetups/
│   └── .gitkeep                                (placeholder for git tracking)
├── test_settings/
│   └── .gitkeep                                (placeholder for git tracking)
└── other_settings/
    └── .gitkeep                                (placeholder for git tracking)
```

**Total size: ~30KB** (compared to ~150MB for full fp_settings)

**Note**: The `.gitkeep` files in `hwsetups/`, `test_settings/`, and `other_settings/` exist solely to ensure these directories are tracked by git (git doesn't track empty directories). These directories must exist for `posconstants.py` to work properly.

## How It Works

When regression tests run:

1. **Static configuration**: The 8 pre-configured positioner files (`unit_M02101.conf` through `unit_M03501.conf`) are loaded directly - no files are created or modified during test execution
2. **Read-only access**: The entire `fp_settings_min/` directory can be accessed read-only; the regression tests only read configuration, never write to it
3. **Complete structure**: All required subdirectories exist (tracked via `.gitkeep` files), so no directory creation is needed

## Usage

The regression test suite automatically uses this directory by default:

```bash
# Uses fp_settings_min/ automatically
python -m regression.regression_test --mode compare

# Override with custom fp_settings if needed
python -m regression.regression_test --mode compare --fp-settings-path /path/to/full/fp_settings
```

## Comparison with Full fp_settings

| Component | Full fp_settings | fp_settings_min |
|-----------|-----------------|-----------------|
| **Size** | ~150MB | ~30KB |
| **pos_settings/** | ~12,000 unit files | 1 DEFAULT template + 8 `unit_M0XXXX.conf` files |
| **fid_settings/** | ~300 unit files | 1 DEFAULT template |
| **ptl_settings/** | ~20 unit files | 1 DEFAULT template |
| **collision_settings/** | Multiple configs | 1 DEFAULT config |
| **Use case** | Production/full testing | Regression testing |

## Maintenance

When updating the regression tests:

- **DO** update the DEFAULT templates if calibration parameter formats change
- **DO** update the static `unit_M0XXXX.conf` files if test requirements change
- **DO** add new required subdirectories if the code starts using them
- **DON'T** add production-specific settings or data files beyond what's needed for testing

## Version Control

This directory and all its contents are tracked in git. The regression tests access this directory read-only and do not create or modify any files during execution.
