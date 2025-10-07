# Regression Test Logs Directory

This directory is used as the default location for positioner logs during regression testing.

When running regression tests, the `POSITIONER_LOGS_PATH` environment variable is automatically set to this directory unless overridden via the `--positioner-logs-path` command line argument.

## Contents

During test runs, this directory may contain:
- `pos_logs/` - Positioner move logs
- `fid_logs/` - Fiducial logs
- `ptl_logs/` - Petal-level logs
- Other log and temporary files created by the test suite

## Git Tracking

This README.md file exists primarily to allow this directory to be tracked in git.
Log files generated during testing are temporary and should not be committed.
