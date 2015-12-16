import numpy as np
import PosMoveTable
import PosConstants as pc

class PosSchedule(object):
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

    def move_request(self, posmodel, Q, S):
        """Adds a request to the schedule for a given positioner to move to
        the target position (Q,S).
        """
        self.move_tables.append(posmovetable.PosMoveTable(posmodel))
        self._targt.append([Q,S])
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
            self._schedule_without_anticollision()
        else:
            self._schedule_with_anticollision()

    # internal methods
    def _schedule_without_anticollision(self):
        for i in range(len(self.move_tables)):
            if not(self._is_forced[i]):
                tbl = self.move_tables[i]

                # convert global (Q,S) into local theta,phi
                start_xy = tbl.posmodel.trans.QS_to_obsXY([self._start[0][i],self._start[1][i]])
                targt_xy = tbl.posmodel.trans.QS_to_obsXY([self._targt[0][i],self._targt[1][i]])
                start_shaft = tbl.posmodel.trans.obsXY_to_shaftTP(start_xy)
                targt_shaft = tbl.posmodel.trans.obsXY_to_shaftTP(targt_xy)
                start = tbl.posmodel.trans.shaftTP_to_obsTP(start_shaft)
                targt = tbl.posmodel.trans.shaftTP_to_obsTP(targt_shaft)

                # delta = finish - start
                dtdp = [0,0]
                dtdp = targt_obs - start_obs

                # set deltas and pauses into move table
                row = 0 # for the anti-collision, this would vary
                tbl.set_move     (row, pc.T, dtdp[0][i])
                tbl.set_move     (row, pc.P, dtdp[1][i])
                tbl.set_prepause (row, 0.0)
                tbl.set_postpause(row, 0,0)


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
        xy0 = [] # will store the (x,y) locations of the fiber positioners' centers
        t_range = [] # will store the (theta_min, theta_max) travel ranges
        p_range = [] # will store the (phi_min, phi_max) travel ranges
        for tbl in self.move_tables:
            R.append(  [tbl.posmodel.state.read('LENGTH_R1'), tbl.posmodel.state.read('LENGTH_R2')])
            tp0.append([tbl.posmodel.state.read('POLYN_T0' ), tbl.posmodel.state.read('POLYN_P0' )])
            xy0.append([tbl.posmodel.state.read('POLYN_X0' ), tbl.posmodel.state.read('POLYN_Y0' )])
            t_range.append(tbl.posmodel.targetable_range_T)
            p_range.append(tbl.posmodel.targetable_range_P)

        # transform start points and targets to the flattened xy coordinate system
        start_xy = [[0]*len(self._start) for i in range(2)]
        targt_xy = [[0]*len(self._targt) for i in range(2)]
        for i in range(len(self.move_tables)):
            tbl = self.move_tables[i]
            temp = tbl.posmodel.trans.QS_to_flatXY([self._start[0][i],self._start[1][i]])
            start_xy[0][i] = temp[0]
            start_xy[1][i] = temp[1]
            temp = tbl.posmodel.trans.QS_to_flatXY([self._targt[0][i],self._targt[1][i]])
            targt_xy[0][i] = temp[0]
            targt_xy[1][i] = temp[1]

        # anticollision algorithm goes here
        # (to-do)

        self._schedule_without_anticollision() # placeholder to be replaced with real code