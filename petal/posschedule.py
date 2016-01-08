import numpy as np
import posmovetable
import posconstants as pc

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
        self.requests = []

    def request_target(self, pos, coordsys, u, v):
        """Adds a request to the schedule for a given positioner to move to
        the target position (u,v) in the coordinate system cs. A schedule can
        only contain one target request per positioner at a time.
                pos ... posid or posmodel
           coordsys ... string, 'qs' or 'xy'
                  u ... float, q value or x value
                  v ... float, s value or y value
        """
        posmodel = get_model_for_pos(pos)
        current_position = posmodel.expected_current_position
        start_qs = [current_position['q'],current_position['s']]
        if coordsys == 'qs':
            targt_qs = [u,v]
        elif coordsys == 'xy':
            targt_qs = posmodel.trans.obsXY_to_QS([u,v])
        else:
            print('bad coordinate system for move request')
            return
        dq = targt_qs[0] - start_qs[0]
        ds = targt_qs[1] - start_qs[1]
        partial_abs_request = {'posmodel':posmodel, 'command':coordsys, 'cmd_val1':u, 'cmd_val2':v}
        self.request_delta(pos,coordsys,dq,ds,partial_abs_request)

    def request_delta(self, pos, coordsys, du, dv, partial_abs_request=None):
        """Adds a request to the schedule for a given positioner to move to
        the target a distance (du,dv) away in the coordinate system cs. A schedule
        can only contain one request per positioner at a time.
                pos ... posid or posmodel
           coordsys ... string, 'qs' or 'xy'
                 du ... float, dq value or dx value
                 dv ... float, ds value or dy value
        """
        already_requested = [p['posmodel'] for p in self.requests]
        posmodel = get_model_for_pos(pos)
        if posmodel in already_requested:
            print('cannot request more than one target per positioner in a given schedule')
            return
        current_position = posmodel.expected_current_position
        if coordsys == 'qs':
            start_qs = [current_position['q'],current_position['s']]
            targt_qs = [start_qs[0] + du, start_qs[1] + dv]
            command = 'dqds'
        elif coordsys == 'xy':
            start_xy = [current_position['x'],current_position['y']]
            targt_xy = [start_xy[0] + du, start_xy[1] + dv]
            start_qs = posmodel.trans.obsXY_to_QS(start_xy)
            targt_qs = posmodel.trans.obsXY_to_QS(targt_xy)
            command = 'dxdy'
        else:
            print('bad coordinate system for move request')
            return
        start_flatxy = posmodel.trans.QS_to_flatXY(start_qs)
        targt_flatxy = posmodel.trans.QS_to_flatXY(targt_qs)
        if partial_abs_request:
            new_request = partial_abs_request
        else:
            new_request = {'posmodel':posmodel, 'command':command, 'cmd_val1':du, 'cmd_val2':dv}
        new_request['start_flatxy'] = start_flatxy
        new_request['targt_flatxy'] = targt_flatxy
        self.requests.append(new_request)

    def expert_add_table(self, move_table):
        """Adds an externally-constructed move table to the schedule. If there
        is ANY such table in a given schedule, then the anti-collision algorithm
        will NOT be used. Generally, this method should only be used for internal
        calls by an expert user.
        """
        self.move_tables.append(move_table)
        self._merge_tables_for_each_pos()

    def schedule_moves(self, anticollision=True):
        """Executes the scheduling algorithm upon the stored list of move requests.

        A single move table is generated for each positioner that has at least one
        request. These are stored in the move_tables list. If anticollision is true,
        then the algorithm is run when generating the move tables.

        If there were ANY pre-existing move tables in the list, then ALL the target
        requests are ignored.
        """
        if self.move_tables:
            return
        elif anticollision:
            self.move_tables = self._schedule_without_anticollision()
        else:
            self.move_tables = self._schedule_with_anticollision()

    def total_dTdP(self, posid):
        #NEEDED?
        """Return as-scheduled total move distance for positioner identified by posid.
        Returns [dT,dP].
        """
        dTdP = [0,0]
        for tbl in self.move_tables:
            if tbl.posmodel.state.read('SERIAL_ID') == posid:
                postprocessed = tbl.for_cleanup
                dTdP = [sum(postprocessed['dT']),sum(postprocessed['dP'])]
                break
        return dTdP

    def get_model_for_pos(self, pos):
        """Returns the posmodel object corresponding to a posid, or if the argument
        is a posmodel, just returns itself.
        """
        if isinstance(pos, posmodel.Posmodel):
            return pos.posid
        else:
            return pos

    # internal methods
    def _merge_tables_for_each_pos(self):
        """In each case where one positioner has multiple tables, they are merged in sequence
        into a single table.
        """
        i = 0
        while i < len(self.move_tables):
            j = i + 1
            extend_list = []
            while j < len(self.move_tables):
                if self.move_tables[i].posmodel.state.read('SERIAL_ID') == self.move_tables[j].posmodel.state.read('SERIAL_ID'):
                    extend_list.append(self.move_tables.pop(j))
                else:
                    j += 1
            for e in extend_list:
                self.move_tables[i].extend(e)
            i += 1

    def _schedule_without_anticollision(self):
        for req in self.requests:
            posmodel = req['posmodel']
            table = posmovetable.PosMoveTable(posmodel)
            (start_shaft,reachable) = posmodel.trans.flatXY_to_shaftTP(req['start_flatxy'])
            (targt_shaft,reachable) = posmodel.trans.flatXY_to_shaftTP(req['targt_flatxy'])
            dtdp = [0,0]
            dtdp[0] = targt_shaft[0] - start_shaft[0]
            dtdp[1] = targt_shaft[1] - start_shaft[1]
            row = 0
            table.set_move(row, pc.T, dtdp[0][i])
            table.set_move(row, pc.P, dtdp[1][i])
            table.set_prepause (row, 0.0)
            table.set_postpause(row, 0.0)
            table.store_orig_command
            self.move_tables.append(table)

    def _schedule_with_anticollision(self):
        """
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

        # anticollision algorithm goes here
        # (to-do)
        """
        self._schedule_without_anticollision() # placeholder to be replaced with real code