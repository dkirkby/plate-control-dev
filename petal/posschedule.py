import numpy as np
import posmovetable
import posarraymaster
import posconstants as pc

class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.

    Note that the schedule may contain multiple move tables for the same positioner,
    under the assumption that another module (i.e. PosArrayMaster) will generally be
    the one which merges any such tables in sequence, before sending off to the hardware.
    """

    def __init__(self, posarray):
        if isinstance(posarray, posarraymaster.PosArrayMaster):
            self.posarray = posarray
        else:
            print('bad posarray')
        self.move_tables = []
        self.requests = []

    def request_target(self, pos, uv_type, u, v):
        """Adds a request to the schedule for a given positioner to move to the
        target position (u,v) or by the target distance (du,dv) in the coordinate
        system indicated by uv_type.

                pos ... posid or posmodel
            uv_type ... string, 'qs', 'xy', 'dqds', or 'dxdy'
                  u ... float, value of q, x, dq, or dx
                  v ... float, value of s, y, ds, or dy

        A schedule can only contain one target request per positioner at a time.
        """
        uv_type = uv_type.lower()
        pos = self.posarray.get_model_for_pos(pos)
        if self.already_requested(pos):
            print('cannot request more than one target per positioner in a given schedule')
            return
        current_position = pos.expected_current_position
        if uv_type == 'qs' or uv_type == 'dqds':
            start_uv = [current_position['Q'],current_position['S']]
            start_flatxy = pos.trans.QS_to_flatXY(start_uv)
        elif uv_type == 'xy' or uv_type == 'dxdy':
            start_uv = [current_position['obsX'],current_position['obsY']]
            start_flatxy = pos.trans.obsXY_to_flatXY(start_uv)
        else:
            print('bad uv_type for target request')
            return
        if uv_type == 'qs':
            targt_flatxy = pos.trans.QS_to_flatXY([u,v])
        elif uv_type == 'xy':
            targt_flatxy = pos.trans.obsXY_to_flatXY([u,v])
        elif uv_type == 'dqds':
            targt_uv = pos.trans.addto_QS(start_uv,[u,v])
            targt_flatxy = pos.trans.QS_to_flatXY(targt_uv)
        elif uv_type == 'dxdy':
            targt_uv = pos.trans.addto_obsXY(start_uv,[u,v])
            targt_flatxy = pos.trans.obsXY_to_flatXY(targt_uv)
        new_request = {'start_flatxy' : start_flatxy,
                       'targt_flatxy' : targt_flatxy,
                           'posmodel' : pos,
                            'command' : uv_type,
                           'cmd_val1' : u,
                           'cmd_val2' : v}
        self.requests.append(new_request)

    def add_table(self, move_table):
        """Adds an externally-constructed move table to the schedule. If there
        is ANY such table in a given schedule, then the anti-collision algorithm
        will NOT be used. Generally, this method should only be used for internal
        calls by an expert user.
        """
        self.move_tables.append(move_table)
        self._merge_tables_for_each_pos()

    def schedule_moves(self, anticollision=True):
        """Executes the scheduling algorithm upon the stored list of move requests.

        A single move table is generated for each positioner that has a request
        registered. The resulting tables are stored in the move_tables list. If the
        anticollision argument is true, then the anticollision algorithm is run when
        generating the move tables.

        If there were ANY pre-existing move tables in the list, then ALL the target
        requests are ignored, and the anticollision algorithm is NOT performed.
        """
        if self.move_tables:
            return
        elif anticollision:
            self.move_tables = self._schedule_without_anticollision()
        else:
            self.move_tables = self._schedule_with_anticollision()

    def total_dtdp(self, pos):
        """Return as-scheduled total move distance for positioner identified by posid.
        Returns [dt,dp].
        """
        pos = self.posarray.get_model_for_pos(pos)
        dtdp = [0,0]
        for tbl in self.move_tables:
            if tbl.posmodel == pos:
                postprocessed = tbl.full_table
                dtdp = [postprocessed['stats']['net_dT'][-1], postprocessed['stats']['net_dP'][-1]]
                break
        return dtdp

    def already_requested(self, pos):
        """Returns boolean whether a request has already been registered in the
        schedule for the argued positioner.
        """
        posmodel = self.posarray.get_model_for_pos(pos)
        already_requested_list = [p['posmodel'] for p in self.requests]
        was_already_requested = posmodel in already_requested_list
        return was_already_requested

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
            dtdp = posmodel.trans.delta_shaftTP(targt_shaft, start_shaft, range_wrap_limits='targetable')
            table.set_move(0, pc.T, dtdp[0])
            table.set_move(0, pc.P, dtdp[1])
            table.set_prepause (0, 0.0)
            table.set_postpause(0, 0.0)
            table.store_orig_command(0, req['command'], req['cmd_val1'], req['cmd_val2'])
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