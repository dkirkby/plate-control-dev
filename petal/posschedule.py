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

    def request_target(self, pos, uvtype, u, v):
        """Adds a request to the schedule for a given positioner to move to
        the target position (u,v) in the coordinate system cs. A schedule can
        only contain one target request per positioner at a time.
                pos ... posid or posmodel
            uv_type ... string, 'qs', 'xy', 'dqds', or 'dxdy'
                  u ... float, value of q, x, dq, or dx
                  v ... float, value of s, y, ds, or dy
        """
        posmodel = get_model_for_pos(pos)
        already_requested = [p['posmodel'] for p in self.requests]
        if posmodel in already_requested:
            print('cannot request more than one target per positioner in a given schedule')
            return
        current_position = posmodel.expected_current_position
        if uv_type == 'qs' or uv_type == 'dqds':
            start_uv = [current_position['Q'],current_position['S']]
            start_flatxy = posmodel.trans.QS_to_flatXY(start_uv)
        elif uv_type == 'xy' or uv_type == 'dxdy':
            start_uv = [current_position['obsX'],current_position['obsY']]
            start_flatxy = posmodel.trans.obsXY_to_flatXY(start_uv)
        else:
            print('bad uv_type for target request')
            return
        if uv_type == 'qs':
            targt_flatxy = posmodel.trans.QS_to_flatXY([u,v])
        elif uv_type == 'xy':
            dudv = posmodel.trans.delta_obsXY([u,v],start_uv)

        elif uv_type == 'dqds':

        elif uv_type == 'dxdy':

        else:

            return
        partial_abs_request = {'posmodel':posmodel, 'command':coordsys, 'cmd_val1':u, 'cmd_val2':v}
        self.request_delta(pos,coordsys,dudv[0],dudv[1],partial_abs_request,start_uv)

    def request_delta(self, pos, coordsys, du, dv, start_upartial_abs_request=None,start_uv=None):
        """Adds a request to the schedule for a given positioner to move to
        the target a distance (du,dv) away in the coordinate system cs. A schedule
        can only contain one request per positioner at a time.
                pos ... posid or posmodel
           coordsys ... string, 'qs' or 'xy'
                 du ... float, dq value or dx value
                 dv ... float, ds value or dy value
        """


        if not(known_start_uv):
            current_position = posmodel.expected_current_position
            if coordsys == 'qs':
                start_uv = [current_position['Q'],current_position['S']]
            elif coordsys == 'xy':
                start_uv = [current_position['obsX'],current_position['obsY']]
        if coordsys == 'qs':
            targt_uv = posmodel.trans.addto_QS(start_uv,[du,dv])
            start_flatxy = posmodel.trans.QS_to_flatXY(start_xy)
            targt_flatxy = posmodel.trans.QS_to_flatXY(start_xy)
            command = 'dqds'
        elif coordsys == 'xy':
            start_xy =
            targt_xy = posmodel.trans.addto_obsXY(start_xy,[du,dv])
            start_flatxy = posmodel.trans.obsXY_to_flatXY(start_xy)
            targt_flatxy = posmodel.trans.obsXY_to_flatXY(start_xy)
            command = 'dxdy'
        else:
            print('bad coordinate system for move request')
            return
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