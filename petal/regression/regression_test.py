#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Comprehensive Regression Test Suite for Plate Control Refactoring

This module implements a "golden master" testing strategy to ensure that
refactored code produces identical results to the original implementation.

The test suite includes a minimal fp_settings directory with all required
configuration files, so it can be run without any environment setup.

Usage:
    # Compare against baselines (uses built-in minimal fp_settings)
    python -m regression.regression_test --mode compare

    # Create initial baselines (run once before refactoring)
    python -m regression.regression_test --mode baseline

    # Run specific test
    python -m regression.regression_test --mode compare --test test_01_basic_moves

    # Update baselines after intentional behavior change
    python -m regression.regression_test --mode update --test test_03_edge_cases

    # Use custom fp_settings directory
    python -m regression.regression_test --mode compare --fp-settings-path /path/to/fp_settings

Environment Variables (optional):
    FP_SETTINGS_PATH - Path to fp_settings directory
                       (default: regression/fp_settings_min/)
    POSITIONER_LOGS_PATH - Path for log files
                           (default: regression/test_logs_path/)

For detailed documentation, see docs/README.md (REGRESSION_TESTING.md)
"""

import json
import hashlib
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import traceback
import argparse


def _setup_environment_for_tests():
    """
    Set up environment variables for regression testing.

    Priority order:
    1. Command line arguments (--fp-settings-path, --positioner-logs-path)
    2. Default values (fp_settings_min/, test_logs_path/)

    Any existing FP_SETTINGS_PATH or POSITIONER_LOGS_PATH environment variables
    are ignored with a warning.
    """
    # Get the regression directory
    regression_dir = Path(__file__).parent

    # Parse command line arguments early
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--fp-settings-path', type=str, default=None)
    parser.add_argument('--positioner-logs-path', type=str, default=None)
    args, _ = parser.parse_known_args()

    # Handle FP_SETTINGS_PATH
    if 'FP_SETTINGS_PATH' in os.environ:
        print("WARNING: Ignoring FP_SETTINGS_PATH environment variable.")
        print(f"         Was set to: {os.environ['FP_SETTINGS_PATH']}")

    if args.fp_settings_path:
        fp_settings_path = Path(args.fp_settings_path).resolve()
        print(f"Using fp_settings from command line: {fp_settings_path}")
    else:
        fp_settings_path = (regression_dir / 'fp_settings_min').resolve()
        print(f"Using default fp_settings: {fp_settings_path}")

    os.environ['FP_SETTINGS_PATH'] = str(fp_settings_path)

    # Handle POSITIONER_LOGS_PATH
    if 'POSITIONER_LOGS_PATH' in os.environ:
        print("WARNING: Ignoring POSITIONER_LOGS_PATH environment variable.")
        print(f"         Was set to: {os.environ['POSITIONER_LOGS_PATH']}")

    if args.positioner_logs_path:
        logs_path = Path(args.positioner_logs_path).resolve()
    else:
        logs_path = (regression_dir / 'test_logs_path').resolve()

    os.environ['POSITIONER_LOGS_PATH'] = str(logs_path)


# Set up environment before importing petal modules
_setup_environment_for_tests()

# Now check that required environment variables are set
required_env_vars = ['POSITIONER_LOGS_PATH', 'FP_SETTINGS_PATH']
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    print("\n" + "="*70)
    print("ERROR: Required environment variables not set:")
    for var in missing_vars:
        print(f"  {var}")
    print("\nThis should not happen - please report as a bug.")
    print("="*70 + "\n")
    sys.exit(1)

# Add parent directory to path for imports (to import petal modules)
_regression_dir = Path(__file__).parent
_petal_dir = _regression_dir.parent
sys.path.insert(0, str(_petal_dir))

import numpy as np
import petal
import posmodel
import posstate
import posmovetable
import posconstants as pc


class RegressionTestSuite:
    """
    Main regression test suite implementing golden master testing strategy.

    The approach is:
    1. Run representative scenarios through the system
    2. Capture all outputs and state
    3. Serialize to JSON and compute hash
    4. Compare against previously saved baseline
    """

    def __init__(self, baseline_dir=None, verbose=False):
        """
        Initialize regression test suite.

        Args:
            baseline_dir: Directory to store/load baseline files (default: regression/baselines)
            verbose: Print detailed output during test execution
        """
        if baseline_dir is None:
            baseline_dir = Path(__file__).parent / 'baselines'
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(exist_ok=True)
        self.verbose = verbose
        self.test_timestamp = datetime.now().isoformat()
        self.results = {}

        # Test configuration
        self.petal_id = 0
        self.petal_loc = 3
        self.test_posids = self._get_test_posids()

    def _get_test_posids(self) -> List[str]:
        """Get list of positioner IDs for testing"""
        # Use a small, representative subset for fast tests
        # Device locations 21-28, 33-34 (subset7b from harness)
        test_device_locs = {21, 22, 26, 27, 28, 33, 34}

        # Map device locations to posids
        # Use M0XXXX format where XXXX = device_loc * 100 + 1
        # This ensures unique posids that encode device location
        # These correspond to pre-existing static config files in fp_settings_min/pos_settings/
        return [f'M{loc*100+1:05d}' for loc in sorted(test_device_locs)]

    # ============================================================
    # TEST SCENARIOS
    # ============================================================

    def test_01_basic_moves(self) -> Dict:
        """Test basic movement commands in all coordinate systems"""
        if self.verbose:
            print("  Testing basic moves in all coordinate systems...")

        results = {}

        # Test each coordinate system
        coord_systems = {
            'posintTP': [(10.0, 90.0), (-15.0, 120.0), (0.0, 150.0)],
            'poslocTP': [(10.0, 90.0), (-15.0, 120.0), (0.0, 150.0)],
            'poslocXY': [(5.0, 3.0), (-2.0, 4.0), (0.0, 6.0)],
        }

        for coord_system, targets in coord_systems.items():
            if self.verbose:
                print(f"    Testing {coord_system}...")

            ptl = self._create_test_petal(
                simulator_on=True,
                anticollision='adjust',
                verbose=False
            )

            system_results = []
            for target in targets:
                # Create request for first positioner
                posid = self.test_posids[0]
                requests = {
                    posid: {
                        'command': coord_system,
                        'target': list(target),
                        'log_note': f'test_01_{coord_system}'
                    }
                }

                ptl.request_targets(requests)
                ptl.schedule_send_and_execute_moves(anticollision='adjust')

                # Capture state after move
                state = self._capture_petal_state(ptl)
                system_results.append({
                    'target': target,
                    'final_state': state
                })

            results[coord_system] = system_results

        return results

    def test_02_collision_scenarios(self) -> Dict:
        """Test known collision-inducing scenarios"""
        if self.verbose:
            print("  Testing collision scenarios...")

        results = {}

        # Test case 1: Two positioners moving toward collision
        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='adjust',
            verbose=False
        )

        if len(self.test_posids) >= 2:
            # Create opposing moves that would collide
            requests = {
                self.test_posids[0]: {
                    'command': 'posintTP',
                    'target': [30.0, 120.0],
                    'log_note': 'collision_test_pos0'
                },
                self.test_posids[1]: {
                    'command': 'posintTP',
                    'target': [-30.0, 120.0],
                    'log_note': 'collision_test_pos1'
                }
            }

            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision='adjust')

            results['opposing_moves_adjust'] = {
                'final_state': self._capture_petal_state(ptl),
                'schedule_stats': self._capture_schedule_stats(ptl)
            }

        # Test case 2: Same scenario with freeze mode
        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='freeze',
            verbose=False
        )

        if len(self.test_posids) >= 2:
            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision='freeze')

            results['opposing_moves_freeze'] = {
                'final_state': self._capture_petal_state(ptl),
                'schedule_stats': self._capture_schedule_stats(ptl)
            }

        return results

    def test_03_edge_cases(self) -> Dict:
        """Test boundary conditions and edge cases"""
        if self.verbose:
            print("  Testing edge cases...")

        results = {}

        # Test theta near hardstop
        ptl = self._create_test_petal(simulator_on=True, anticollision=None, verbose=False)
        posid = self.test_posids[0]

        # Move near theta hardstop (±180°)
        theta_cases = [
            ('near_positive_limit', 175.0),
            ('near_negative_limit', -175.0),
            ('wrap_around', 179.0),
        ]

        for case_name, theta in theta_cases:
            requests = {
                posid: {
                    'command': 'posintTP',
                    'target': [theta, 100.0],
                    'log_note': f'edge_case_{case_name}'
                }
            }
            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision=None)
            results[case_name] = self._capture_positioner_state(ptl, posid)

        # Test phi limits
        phi_cases = [
            ('phi_minimum', 0.0, 10.0),
            ('phi_maximum', 0.0, 180.0),
        ]

        for case_name, theta, phi in phi_cases:
            requests = {
                posid: {
                    'command': 'posintTP',
                    'target': [theta, phi],
                    'log_note': f'edge_case_{case_name}'
                }
            }
            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision=None)
            results[case_name] = self._capture_positioner_state(ptl, posid)

        return results

    def test_04_state_management(self) -> Dict:
        """Test state persistence and updates"""
        if self.verbose:
            print("  Testing state management...")

        results = {}
        posid = self.test_posids[0]

        # Create a state object
        state = posstate.PosState(
            unit_id=posid,
            device_type='pos',
            petal_id=self.petal_id,
            logging=False  # Don't log during test
        )

        # Store some values
        test_values = {
            'POS_T': 45.0,
            'POS_P': 90.0,
            'OFFSET_T': 0.5,
            'OFFSET_P': -0.3,
            'LENGTH_R1': 3.0,
            'LENGTH_R2': 3.0,
        }

        for key, val in test_values.items():
            state.store(key, val, register_if_altered=False)

        # Capture state
        results['stored_values'] = {
            key: state._val.get(key) for key in test_values.keys()
        }

        # Test state validation
        results['validation'] = {
            'has_required_keys': all(key in state._val for key in ['POS_T', 'POS_P']),
            'pos_t_in_range': -180 <= state._val['POS_T'] <= 180,
            'pos_p_in_range': -20 <= state._val['POS_P'] <= 200,
        }

        return results

    def test_05_transform_chain(self) -> Dict:
        """Test coordinate system transformations"""
        if self.verbose:
            print("  Testing coordinate transforms...")

        results = {}

        # Create a posmodel with transforms
        posid = self.test_posids[0]
        state = posstate.PosState(
            unit_id=posid,
            device_type='pos',
            petal_id=self.petal_id,
            logging=False
        )
        state.store('POS_T', 0.0, register_if_altered=False)
        state.store('POS_P', 90.0, register_if_altered=False)

        pm = posmodel.PosModel(state=state)
        trans = pm.trans

        # Test roundtrip transforms
        test_positions = [
            [0.0, 90.0],
            [45.0, 120.0],
            [-30.0, 150.0],
        ]

        for posintTP in test_positions:
            # Forward transforms
            poslocTP = trans.posintTP_to_poslocTP(posintTP)
            poslocXY = trans.posintTP_to_poslocXY(posintTP)

            # Reverse transforms
            back_from_locTP = trans.poslocTP_to_posintTP(poslocTP)
            back_from_locXY = trans.poslocXY_to_posintTP(poslocXY)

            results[f'posintTP_{posintTP[0]}_{posintTP[1]}'] = {
                'original': posintTP,
                'poslocTP': list(poslocTP) if hasattr(poslocTP, '__iter__') else poslocTP,
                'poslocXY': list(poslocXY) if hasattr(poslocXY, '__iter__') else poslocXY,
                'roundtrip_from_locTP': list(back_from_locTP) if hasattr(back_from_locTP, '__iter__') else back_from_locTP,
                'roundtrip_from_locXY': list(back_from_locXY) if hasattr(back_from_locXY, '__iter__') else back_from_locXY,
            }

        return results

    def test_06_scheduling_algorithms(self) -> Dict:
        """Test different scheduling modes"""
        if self.verbose:
            print("  Testing scheduling algorithms...")

        results = {}

        anticollision_modes = ['adjust', 'freeze', None]
        anneal_modes = ['filled', 'ramped']

        for ac_mode in anticollision_modes:
            for anneal_mode in anneal_modes:
                if self.verbose:
                    print(f"    Testing anticollision={ac_mode}, anneal={anneal_mode}")

                key = f'ac_{ac_mode}_anneal_{anneal_mode}'

                ptl = self._create_test_petal(
                    simulator_on=True,
                    anticollision=ac_mode,
                    anneal_mode=anneal_mode,
                    verbose=False
                )

                # Create move requests for multiple positioners
                requests = {}
                for i, posid in enumerate(self.test_posids[:3]):  # First 3 positioners
                    requests[posid] = {
                        'command': 'posintTP',
                        'target': [float(i * 15), 100.0 + i * 10],
                        'log_note': f'sched_test_{key}'
                    }

                ptl.request_targets(requests)
                ptl.schedule_send_and_execute_moves(anticollision=ac_mode)

                results[key] = {
                    'final_state': self._capture_petal_state(ptl),
                    'schedule_stats': self._capture_schedule_stats(ptl),
                }

        return results

    def test_07_move_table_formats(self) -> Dict:
        """Test all move table output formats"""
        if self.verbose:
            print("  Testing move table formats...")

        results = {}

        # Create a representative move table
        posid = self.test_posids[0]
        state = posstate.PosState(
            unit_id=posid,
            device_type='pos',
            petal_id=self.petal_id,
            logging=False
        )
        state.store('POS_T', 0.0, register_if_altered=False)
        state.store('POS_P', 90.0, register_if_altered=False)

        pm = posmodel.PosModel(state=state)

        # Create move table with multiple rows
        table = posmovetable.PosMoveTable(this_posmodel=pm, init_posintTP=[0.0, 90.0])
        table.set_move(0, pc.T, 30.0)
        table.set_move(0, pc.P, 20.0)
        table.set_postpause(0, 0.5)
        table.set_move(1, pc.T, -15.0)
        table.set_move(1, pc.P, 10.0)

        # Test all output formats
        format_methods = {
            'for_schedule': lambda: table.for_schedule(suppress_automoves=True),
            'for_collider': lambda: table.for_collider(suppress_automoves=True),
            'for_hardware': lambda: table.for_hardware(),
            'for_cleanup': lambda: table.for_cleanup(),
            'angles': lambda: table.angles(),
            'timing': lambda: table.timing(suppress_automoves=True),
        }

        for format_name, method in format_methods.items():
            try:
                output = method()
                results[format_name] = self._sanitize_table_output(output)
            except Exception as e:
                results[format_name] = {'error': str(e)}

        return results

    def test_08_complex_sequences(self) -> Dict:
        """Test multi-move sequences with corrections"""
        if self.verbose:
            print("  Testing complex sequences...")

        results = {}

        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='adjust',
            verbose=False
        )

        # Initial move
        posid = self.test_posids[0]
        requests = {
            posid: {
                'command': 'posintTP',
                'target': [30.0, 120.0],
                'log_note': 'sequence_move_1'
            }
        }
        ptl.request_targets(requests)
        ptl.schedule_send_and_execute_moves(anticollision='adjust')
        results['after_move_1'] = self._capture_positioner_state(ptl, posid)

        # Correction move
        requests = {
            posid: {
                'command': 'poslocdXdY',
                'target': [0.5, -0.3],
                'log_note': 'sequence_correction'
            }
        }
        ptl.request_targets(requests)
        ptl.schedule_send_and_execute_moves(anticollision='freeze')
        results['after_correction'] = self._capture_positioner_state(ptl, posid)

        # Final move
        requests = {
            posid: {
                'command': 'posintTP',
                'target': [-20.0, 150.0],
                'log_note': 'sequence_move_2'
            }
        }
        ptl.request_targets(requests)
        ptl.schedule_send_and_execute_moves(anticollision='adjust')
        results['after_move_2'] = self._capture_positioner_state(ptl, posid)

        return results

    def test_09_petal_level_coordinates(self) -> Dict:
        """Test petal-level and observer-level coordinate systems"""
        if self.verbose:
            print("  Testing petal-level coordinate systems...")

        results = {}

        # Test ptlXY coordinate system (petal-level Cartesian)
        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='adjust',
            verbose=False
        )

        posid = self.test_posids[0]

        # Test ptlXY moves
        # Note: ptlXY coordinates are petal-level positions in mm
        # Positioners have limited reach (~6mm), so targets must be near positioner center
        # For device_loc 21, center is approximately at ptlXY (44.86, 4.98)
        ptlXY_targets = [
            (45.0, 5.0),    # Near center
            (44.0, 4.0),    # Slightly offset
            (46.0, 6.0),    # Another offset
        ]

        ptlXY_results = []
        for target in ptlXY_targets:
            requests = {
                posid: {
                    'command': 'ptlXY',
                    'target': list(target),
                    'log_note': f'test_09_ptlXY_{target[0]}_{target[1]}'
                }
            }
            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision='adjust')

            ptlXY_results.append({
                'target': target,
                'final_state': self._capture_positioner_state(ptl, posid)
            })

        results['ptlXY_moves'] = ptlXY_results

        # Test obsXY coordinate system (observer-level global)
        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='adjust',
            verbose=False
        )

        # Note: obsXY coordinates are observatory-level global positions
        # These coordinates may be unreachable for this test positioner,
        # but the test still exercises the coordinate transform code paths
        obsXY_targets = [
            (45.0, 5.0),     # Similar to ptlXY for petal_loc=3
            (44.0, 4.0),
            (46.0, 6.0),
        ]

        obsXY_results = []
        for target in obsXY_targets:
            requests = {
                posid: {
                    'command': 'obsXY',
                    'target': list(target),
                    'log_note': f'test_09_obsXY_{target[0]}_{target[1]}'
                }
            }
            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision='adjust')

            obsXY_results.append({
                'target': target,
                'final_state': self._capture_positioner_state(ptl, posid)
            })

        results['obsXY_moves'] = obsXY_results

        # Test coordinate transform roundtrips for ptlXY and obsXY
        state = posstate.PosState(
            unit_id=posid,
            device_type='pos',
            petal_id=self.petal_id,
            logging=False
        )
        state.store('POS_T', 0.0, register_if_altered=False)
        state.store('POS_P', 90.0, register_if_altered=False)

        pm = posmodel.PosModel(state=state)
        trans = pm.trans

        # Test roundtrip transforms
        test_positions = [
            [0.0, 90.0],
            [30.0, 120.0],
            [-45.0, 100.0],
        ]

        transform_results = []
        for posintTP in test_positions:
            # Forward transforms to ptlXY and obsXY
            poslocTP = trans.posintTP_to_poslocTP(posintTP)
            ptlXY = trans.posintTP_to_ptlXY(posintTP)

            # For obsXY, we need to go through the petal transforms
            # Use the petal object's transforms
            poslocXY = trans.posintTP_to_poslocXY(posintTP)

            transform_results.append({
                'original_posintTP': posintTP,
                'poslocTP': list(poslocTP) if hasattr(poslocTP, '__iter__') else poslocTP,
                'ptlXY': list(ptlXY) if hasattr(ptlXY, '__iter__') else ptlXY,
                'poslocXY': list(poslocXY) if hasattr(poslocXY, '__iter__') else poslocXY,
            })

        results['transform_roundtrips'] = transform_results

        return results

    def test_10_backlash_compensation(self) -> Dict:
        """Test automatic backlash compensation moves"""
        if self.verbose:
            print("  Testing backlash compensation...")

        results = {}

        # Use posid M02101 which has ANTIBACKLASH_ON = True in its config
        posid = self.test_posids[0]  # M02101

        # Verify backlash settings from config
        state = posstate.PosState(
            unit_id=posid,
            device_type='pos',
            petal_id=self.petal_id,
            logging=False
        )

        # Record backlash configuration
        results['config'] = {
            'antibacklash_on': state._val.get('ANTIBACKLASH_ON'),
            'backlash': state._val.get('BACKLASH'),
            'antibacklash_final_move_dir_t': state._val.get('ANTIBACKLASH_FINAL_MOVE_DIR_T'),
            'antibacklash_final_move_dir_p': state._val.get('ANTIBACKLASH_FINAL_MOVE_DIR_P'),
        }

        # Create petal with backlash-enabled positioner
        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='adjust',
            verbose=False
        )

        # Test 1: Move that requires backlash compensation
        requests = {
            posid: {
                'command': 'posintTP',
                'target': [30.0, 120.0],
                'log_note': 'test_10_move_with_backlash'
            }
        }
        ptl.request_targets(requests)
        ptl.schedule_send_and_execute_moves(anticollision='adjust')

        results['move_1'] = {
            'target': [30.0, 120.0],
            'final_state': self._capture_positioner_state(ptl, posid),
        }

        # Test 2: Create a move table directly and check backlash generation
        pm = posmodel.PosModel(state=state)
        state.store('POS_T', 0.0, register_if_altered=False)
        state.store('POS_P', 90.0, register_if_altered=False)

        # Create move table with backlash enabled
        table = posmovetable.PosMoveTable(this_posmodel=pm, init_posintTP=[0.0, 90.0])

        # Add moves in both axes
        table.set_move(0, pc.T, 45.0)  # Move theta by 45 degrees
        table.set_move(0, pc.P, 30.0)  # Move phi by 30 degrees

        # Get hardware-ready format which includes backlash moves
        hardware_table = table.for_hardware()

        results['move_table_test'] = {
            'num_rows': len(table.rows),
            'should_antibacklash': table.should_antibacklash,
            'has_hardware_table': hardware_table is not None,
            'hardware_table_keys': list(hardware_table.keys()) if hardware_table else None,
        }

        # Test 3: Multiple sequential moves to verify backlash is applied
        ptl = self._create_test_petal(
            simulator_on=True,
            anticollision='adjust',
            verbose=False
        )

        move_sequence = [
            [15.0, 100.0],
            [-15.0, 110.0],
            [30.0, 95.0],
        ]

        sequence_results = []
        for target in move_sequence:
            requests = {
                posid: {
                    'command': 'posintTP',
                    'target': target,
                    'log_note': f'test_10_sequence_{target[0]}_{target[1]}'
                }
            }
            ptl.request_targets(requests)
            ptl.schedule_send_and_execute_moves(anticollision='adjust')

            sequence_results.append({
                'target': target,
                'final_state': self._capture_positioner_state(ptl, posid),
            })

        results['move_sequence'] = sequence_results

        # Test 4: Test with ANTIBACKLASH_ON = False for comparison
        # Modify state temporarily
        state_no_backlash = posstate.PosState(
            unit_id=posid,
            device_type='pos',
            petal_id=self.petal_id,
            logging=False
        )
        state_no_backlash.store('POS_T', 0.0, register_if_altered=False)
        state_no_backlash.store('POS_P', 90.0, register_if_altered=False)
        state_no_backlash.store('ANTIBACKLASH_ON', False, register_if_altered=False)

        pm_no_backlash = posmodel.PosModel(state=state_no_backlash)
        table_no_backlash = posmovetable.PosMoveTable(
            this_posmodel=pm_no_backlash,
            init_posintTP=[0.0, 90.0]
        )
        table_no_backlash.set_move(0, pc.T, 45.0)
        table_no_backlash.set_move(0, pc.P, 30.0)

        results['no_backlash_comparison'] = {
            'should_antibacklash': table_no_backlash.should_antibacklash,
            'num_rows': len(table_no_backlash.rows),
        }

        return results

    # ============================================================
    # HELPER METHODS - PETAL CREATION & STATE CAPTURE
    # ============================================================

    def _create_test_petal(self, **kwargs) -> petal.Petal:
        """
        Create a test petal instance with standard configuration.

        Args:
            **kwargs: Override default petal configuration
        """
        # Default configuration
        config = {
            'petal_id': self.petal_id,
            'petal_loc': self.petal_loc,
            'posids': self.test_posids,
            'fidids': {},
            'simulator_on': True,
            'db_commit_on': False,
            'local_commit_on': False,
            'local_log_on': False,
            'collider_file': None,
            'sched_stats_on': False,
            'anticollision': 'adjust',
            'verbose': False,
            'phi_limit_on': False,
            'save_debug': False,
            'anneal_mode': 'filled',
        }

        # Override with provided kwargs
        config.update(kwargs)

        # Create petal - it will load states from config files automatically
        return petal.Petal(**config)

    def _capture_petal_state(self, ptl: petal.Petal) -> Dict:
        """Capture complete petal state for comparison"""
        state = {
            'positioner_states': {},
            'has_schedule': hasattr(ptl, 'schedule') and ptl.schedule is not None,
        }

        # Capture each positioner's state
        for posid in ptl.posids:
            state['positioner_states'][posid] = self._capture_positioner_state(ptl, posid)

        return state

    def _capture_positioner_state(self, ptl: petal.Petal, posid: str) -> Dict:
        """Capture single positioner's state"""
        posmodel = ptl.posmodels[posid]

        return {
            'posintTP': list(posmodel.expected_current_posintTP),
            'poslocTP': list(posmodel.expected_current_poslocTP),
            'is_enabled': posmodel.is_enabled,
            'classified_as_retracted': posmodel.classified_as_retracted,
        }

    def _capture_schedule_stats(self, ptl: petal.Petal) -> Dict:
        """Capture scheduling statistics"""
        if not hasattr(ptl, 'schedule_stats') or not ptl.schedule_stats.is_enabled():
            return {}

        stats = ptl.schedule_stats
        return {
            'has_data': len(stats.cache) > 0,
            'cache_size': len(stats.cache),
        }

    def _sanitize_table_output(self, output: Dict) -> Dict:
        """Clean move table output for serialization"""
        if not isinstance(output, dict):
            return {'raw': str(output)}

        sanitized = {}
        for key, val in output.items():
            if isinstance(val, (list, tuple)):
                sanitized[key] = [self._sanitize_value(v) for v in val]
            else:
                sanitized[key] = self._sanitize_value(val)

        return sanitized

    def _sanitize_value(self, val: Any) -> Any:
        """Convert value to JSON-serializable format"""
        if isinstance(val, np.ndarray):
            return val.tolist()
        elif isinstance(val, (np.integer, np.floating)):
            return float(val)
        elif isinstance(val, (list, tuple)):
            return [self._sanitize_value(v) for v in val]
        elif isinstance(val, dict):
            return {k: self._sanitize_value(v) for k, v in val.items()}
        else:
            return val

    # ============================================================
    # SERIALIZATION & COMPARISON
    # ============================================================

    def _serialize_for_comparison(self, data: Any) -> str:
        """
        Convert data to stable, comparable JSON format.
        Handles numpy arrays and rounds floats to avoid floating point noise.
        """
        def clean(obj):
            if isinstance(obj, np.ndarray):
                return clean(obj.tolist())
            elif isinstance(obj, (np.integer, np.floating)):
                return round(float(obj), 6)
            elif isinstance(obj, dict):
                return {k: clean(v) for k, v in sorted(obj.items())}
            elif isinstance(obj, (list, tuple)):
                return [clean(item) for item in obj]
            elif isinstance(obj, float):
                return round(obj, 6)
            elif obj is None or isinstance(obj, (bool, str, int)):
                return obj
            else:
                # Fallback: convert to string
                return str(obj)

        cleaned = clean(data)
        return json.dumps(cleaned, sort_keys=True, indent=2)

    def _compute_signature(self, data_str: str) -> str:
        """Compute SHA256 hash of serialized data"""
        return hashlib.sha256(data_str.encode()).hexdigest()

    # ============================================================
    # BASELINE MANAGEMENT
    # ============================================================

    def save_baseline(self, test_name: str, data: Any) -> str:
        """Save test results as baseline"""
        baseline_file = self.baseline_dir / f"{test_name}.json"
        serialized = self._serialize_for_comparison(data)
        signature = self._compute_signature(serialized)

        baseline = {
            'timestamp': self.test_timestamp,
            'signature': signature,
            'data': json.loads(serialized),
        }

        with open(baseline_file, 'w') as f:
            json.dump(baseline, f, indent=2)

        return signature

    def load_baseline(self, test_name: str) -> Optional[Dict]:
        """Load baseline data for test"""
        baseline_file = self.baseline_dir / f"{test_name}.json"

        if not baseline_file.exists():
            return None

        with open(baseline_file) as f:
            return json.load(f)

    def compare_to_baseline(self, test_name: str, data: Any) -> Dict:
        """Compare current results to baseline"""
        baseline = self.load_baseline(test_name)

        if baseline is None:
            return {
                'status': 'NEW_BASELINE',
                'message': 'No baseline exists',
            }

        current_serialized = self._serialize_for_comparison(data)
        current_signature = self._compute_signature(current_serialized)
        baseline_signature = baseline['signature']

        if current_signature == baseline_signature:
            return {
                'status': 'PASS',
                'message': 'Results match baseline exactly',
            }
        else:
            # Compute detailed diff
            current_data = json.loads(current_serialized)
            diff = self._compute_diff(baseline['data'], current_data)

            return {
                'status': 'FAIL',
                'message': 'Results differ from baseline',
                'baseline_signature': baseline_signature[:12] + '...',
                'current_signature': current_signature[:12] + '...',
                'num_differences': len(diff),
                'first_differences': diff[:5],  # Show first 5
                'baseline_timestamp': baseline['timestamp'],
            }

    def _compute_diff(self, baseline: Any, current: Any, path: str = '') -> List[Dict]:
        """Recursively compute differences"""
        diffs = []

        if type(baseline) != type(current):
            diffs.append({
                'path': path or '(root)',
                'type': 'TYPE_MISMATCH',
                'baseline_type': type(baseline).__name__,
                'current_type': type(current).__name__,
            })
            return diffs

        if isinstance(baseline, dict):
            all_keys = set(baseline.keys()) | set(current.keys())
            for key in sorted(all_keys):
                new_path = f"{path}.{key}" if path else str(key)
                if key not in baseline:
                    diffs.append({'path': new_path, 'type': 'ADDED'})
                elif key not in current:
                    diffs.append({'path': new_path, 'type': 'REMOVED'})
                else:
                    diffs.extend(self._compute_diff(baseline[key], current[key], new_path))

        elif isinstance(baseline, (list, tuple)):
            if len(baseline) != len(current):
                diffs.append({
                    'path': path or '(root)',
                    'type': 'LENGTH_CHANGED',
                    'baseline_length': len(baseline),
                    'current_length': len(current),
                })

            for i, (b_item, c_item) in enumerate(zip(baseline, current)):
                new_path = f"{path}[{i}]" if path else f"[{i}]"
                diffs.extend(self._compute_diff(b_item, c_item, new_path))

        elif baseline != current:
            diffs.append({
                'path': path or '(root)',
                'type': 'VALUE_CHANGED',
                'baseline': baseline,
                'current': current,
            })

        return diffs

    # ============================================================
    # TEST RUNNER
    # ============================================================

    def get_all_test_methods(self) -> List[str]:
        """Get list of all test methods"""
        return sorted([
            method for method in dir(self)
            if method.startswith('test_') and callable(getattr(self, method))
        ])

    def run_test(self, test_name: str, mode: str) -> Dict:
        """
        Run a single test.

        Args:
            test_name: Name of test method (e.g., 'test_01_basic_moves')
            mode: 'baseline', 'compare', or 'update'

        Returns:
            Dictionary with test results
        """
        if not hasattr(self, test_name):
            return {
                'status': 'ERROR',
                'message': f'Test {test_name} not found',
            }

        try:
            # Run the test
            method = getattr(self, test_name)
            test_data = method()

            if mode == 'baseline' or mode == 'update':
                # Save as baseline
                signature = self.save_baseline(test_name, test_data)
                return {
                    'status': 'BASELINE_SAVED',
                    'message': f'Baseline saved',
                    'signature': signature[:12] + '...',
                }
            else:  # compare mode
                result = self.compare_to_baseline(test_name, test_data)
                if result['status'] == 'NEW_BASELINE':
                    # Auto-save if no baseline exists
                    signature = self.save_baseline(test_name, test_data)
                    result['signature'] = signature[:12] + '...'
                return result

        except Exception as e:
            return {
                'status': 'ERROR',
                'message': str(e),
                'traceback': traceback.format_exc(),
            }

    def run_all_tests(self, mode: str = 'compare', specific_test: Optional[str] = None) -> Dict[str, Dict]:
        """
        Run all regression tests.

        Args:
            mode: 'baseline', 'compare', or 'update'
            specific_test: If provided, run only this test

        Returns:
            Dictionary mapping test names to results
        """
        if specific_test:
            test_methods = [specific_test] if specific_test in self.get_all_test_methods() else []
        else:
            test_methods = self.get_all_test_methods()

        if not test_methods:
            print("No tests to run!")
            return {}

        print(f"\n{'='*70}")
        print(f"Running {len(test_methods)} regression test(s)")
        print(f"Mode: {mode.upper()}")
        print(f"Baseline directory: {self.baseline_dir}")
        print(f"{'='*70}\n")

        results = {}
        for test_name in test_methods:
            print(f"Running {test_name}...", end=' ', flush=True)

            result = self.run_test(test_name, mode)
            results[test_name] = result

            # Print status
            status_symbols = {
                'PASS': '✓',
                'FAIL': '✗',
                'BASELINE_SAVED': '💾',
                'NEW_BASELINE': '🆕',
                'ERROR': '⚠️',
            }
            symbol = status_symbols.get(result['status'], '?')
            print(f"{symbol} {result['status']}")

            # Print additional info for failures
            if result['status'] == 'FAIL':
                print(f"  └─ {result['num_differences']} difference(s) found")
                if self.verbose and 'first_differences' in result:
                    for diff in result['first_differences'][:3]:
                        print(f"     • {diff}")
            elif result['status'] == 'ERROR':
                print(f"  └─ {result['message']}")

        self._print_summary(results)
        return results

    def _print_summary(self, results: Dict[str, Dict]):
        """Print test summary"""
        print(f"\n{'='*70}")
        print("TEST SUMMARY")
        print(f"{'='*70}")

        status_counts = {}
        for result in results.values():
            status = result['status']
            status_counts[status] = status_counts.get(status, 0) + 1

        total = len(results)
        for status in sorted(status_counts.keys()):
            count = status_counts[status]
            pct = 100 * count / total if total > 0 else 0
            print(f"  {status:20s}: {count:3d} ({pct:5.1f}%)")

        # List failures
        failures = [name for name, result in results.items() if result['status'] == 'FAIL']
        if failures:
            print(f"\n{'='*70}")
            print(f"FAILED TESTS ({len(failures)})")
            print(f"{'='*70}")
            for name in failures:
                result = results[name]
                print(f"\n{name}:")
                print(f"  Baseline: {result.get('baseline_timestamp', 'unknown')}")
                print(f"  Differences: {result.get('num_differences', 0)}")
                if 'first_differences' in result:
                    print(f"  First differences:")
                    for diff in result['first_differences']:
                        print(f"    • {diff.get('path', '?')}: {diff.get('type', '?')}")


def main():
    """Main entry point for regression test suite"""
    # Ensure we don't write to database during tests
    if 'DOS_POSMOVE_WRITE_TO_DB' in os.environ:
        print("WARNING: DOS_POSMOVE_WRITE_TO_DB is set. Unsetting to prevent DB writes during testing.")
        del os.environ['DOS_POSMOVE_WRITE_TO_DB']

    parser = argparse.ArgumentParser(
        description='Regression test suite for plate control refactoring',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create initial baselines
  python regression_test.py --mode baseline

  # Compare against baselines (uses built-in minimal fp_settings by default)
  python regression_test.py --mode compare

  # Run specific test
  python regression_test.py --mode compare --test test_01_basic_moves

  # Update specific baseline after intentional change
  python regression_test.py --mode update --test test_03_edge_cases

  # Verbose output
  python regression_test.py --mode compare --verbose

  # Use custom fp_settings directory
  python regression_test.py --mode compare --fp-settings-path /path/to/fp_settings
        """
    )

    parser.add_argument(
        '--mode',
        choices=['baseline', 'compare', 'update'],
        default='compare',
        help='baseline: save current behavior; compare: check against baseline; update: update specific baseline'
    )

    parser.add_argument(
        '--test',
        type=str,
        help='Run only this specific test (e.g., test_01_basic_moves)'
    )

    parser.add_argument(
        '--baseline-dir',
        type=str,
        default=None,
        help='Directory to store/load baseline files (default: regression/baselines)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed output during test execution'
    )

    parser.add_argument(
        '--fp-settings-path',
        type=str,
        default=None,
        help='Path to fp_settings directory (default: regression/fp_settings_min/)'
    )

    parser.add_argument(
        '--positioner-logs-path',
        type=str,
        default=None,
        help='Path to positioner logs directory (default: regression/test_logs_path/)'
    )

    args = parser.parse_args()

    # Create and run test suite
    suite = RegressionTestSuite(
        baseline_dir=args.baseline_dir,
        verbose=args.verbose
    )

    results = suite.run_all_tests(
        mode=args.mode,
        specific_test=args.test
    )

    # Exit with error code if any tests failed
    failures = sum(1 for r in results.values() if r['status'] in ['FAIL', 'ERROR'])
    sys.exit(0 if failures == 0 else 1)


if __name__ == '__main__':
    main()
