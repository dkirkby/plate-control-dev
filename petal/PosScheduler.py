import numpy as np
import PosMoveTable

class PosScheduler(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.

    Note that the schedule may contain multiple move tables for the same positioner,
    under the assumption that another module (i.e. PosArrayMaster) will generally be
    the one which merges any such tables in sequence, before sending off to the hardware.
    """

    def __init__(self):
        self.move_tables = []
        self._start = []
        self._targt = []
        self._is_forced = []

    def move_request(self, posmodel, P, Q):
        """Adds a request to the scheduler for a given positioner to move to
        the target position (P,Q).
        """
        self.move_tables.append(PosMoveTable.PosMoveTable(posmodel))
        self._targt.append([P,Q])
        self._is_forced_dtdp.append(False)

    def expert_move_request(self, move_table):
        """Adds an externally-constructed move table to the schedule. The move
        table will be skipped by the scheduling algorithm. Also, if there
        is ANY such table in a given schedule, then the anti-collision algorithm
        will NOT be used. Generally, this method should only be used for internal
        calls by an expert user.
        """
        self.move_tables.append(move_table)
        self._targt.append([float('nan'),float('nan')])
        self._is_forced.append(True)

    def schedule_moves(self, anticollision=True):
        """Executes the scheduling algorithm upon the stored list of move requests.
        Note that if there are any forced relative (dtheta,dphi) moves in the requests
        list, then this forces that the whole schedule be done with no anticollision.
        """
        self._start = [[0]*len(self.move_tables) for i in range(2)]
        for i in range(len(self.move_tables)):
            if self._is_forced[i]:
                self._start[0][i] = float('nan')
                self._start[1][i] = float('nan')
            else:
                current_position = self.move_tables[i].posmodel.expected_current_position
                self._start[0][i] = current_position['Q']
                self._start[1][i] = current_position['S']
        if not(anticollision) or any(self._is_forced):
            self.move_tables = self._schedule_without_anticollision()
        else:
            self.move_tables = self._schedule_with_anticollision()

    # internal methods
    def _schedule_without_anticollision(self):
        i = 0
        for tbl in self.move_tables:
            # convert global (Q,S) into local theta,phi
            start = np.transpose(np.array(self._start[i]))
            targt = np.transpose(np.array(self._targt[i]))
            start = tbl.posmodel.trans.QS_to_obsTP(start)
            targt = tbl.posmodel.trans.QS_to_obsTP(targt)

            # delta = finish - start
            dtdp_obs = targt - start

            # set deltas and pauses into move table
            if not(self._is_forced[i]):
                row = 0 # for the anti-collision, this would vary
                tbl.set_move     (row, tbl.posmodel.T, dtdp_obs[0,i])
                tbl.set_move     (row, tbl.posmodel.P, dtdp_obs[1,i])
                tbl.set_prepause (row, 0.0)
                tbl.set_postpause(row, 0,0)

            i += 1

        return move_tables

    def _schedule_with_anticollision(self):
        # gather the general envelopes and keep-out zones (see DESI-0899, same for all positioners)
        Ei = 6.800 # [mm] inner clear rotation envelope
        Eo = 9.990 # [mm] outer clear rotation envelope
        P2 = [] # (to-do) polygonal type II keepout zone
        P3 = [] # (to-do) polygonal type III keepout zone

        # gather the location-specific keep-out zones (varies by positioner)
        P4 = [] # will store a list of additional polygonal keepout zones due to nearby hardware (GFA), or petal seam, or dead neighbor positioner. if none, that entry is an empty list, so length still matches the # of move_tables
        for tbl in self.move_tables:
            P4.append([]) # (to-do)

        # gather the kinematics calibration data
        R = [] # will store arm lengths for theta and phi
        tp0 = [] # will store the (theta,phi) permanent offsets (e.g., theta clocking angle of mounting, phi clocking angle of construction)
        PQ0 = [] # will store the (P,Q) locations of the fiber positioners' centers
        t_range = [] # will store the (theta_min, theta_max) travel ranges
        p_range = [] # will store the (phi_min, phi_max) travel ranges
        for tbl in self.move_tables:
            R.append(  [tbl.posmodel.state.kv['LENGTH_R1'], tbl.posmodel.state.kv['LENGTH_R2']])
            tp0.append([tbl.posmodel.state.kv['POLYN_T0' ], tbl.posmodel.state.kv['POLYN_P0' ]])
            PQ0.append([tbl.posmodel.state.kv['POLYN_Q0' ], tbl.posmodel.state.kv['POLYN_S0' ]]) # changing the P,Q to Q,S??
            t_range.append(tbl.posmodel.targetable_range_T)
            p_range.append(tbl.posmodel.targetable_range_P)

        # anticollision algorithm goes here

        move_tables = self._schedule_without_anticollision() # placeholder to be replaced with real code
        return move_tables