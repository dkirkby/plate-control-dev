import posmovetable
import posconstants as pc
import posanticollision as anticollision

class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.

    Note that the schedule may contain multiple move tables for the same positioner,
    under the assumption that another module (i.e. Petal) will generally be
    the one which merges any such tables in sequence, before sending off to the hardware.
    
    Initialize with the petal object this schedule applies to.
    """

    def __init__(self, petal):
        self.petal = petal
        self.move_tables = []
        self.requests = []

    def request_target(self, pos, uv_type, u, v, log_note=''):
        """Adds a request to the schedule for a given positioner to move to the
        target position (u,v) or by the target distance (du,dv) in the coordinate
        system indicated by uv_type.

                pos ... posid or posmodel
            uv_type ... string, 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
                  u ... float, value of q, dq, x, dx, t, or dt
                  v ... float, value of s, ds, y, dy, p, or dp
           log_note ... optional string to store alongside the requested move in the log data

        A schedule can only contain one target request per positioner at a time.
        """
        posmodel = self.petal.get_model_for_pos(pos)
        if self.already_requested(posmodel):
            print('cannot request more than one target per positioner in a given schedule')
            return
        current_position = posmodel.expected_current_position
        start_posTP = [current_position['posT'],current_position['posP']]
        if uv_type == 'QS':
            (targt_posTP,unreachable) = posmodel.trans.QS_to_posTP([u,v])
        elif uv_type == 'obsXY':
            (targt_posTP,unreachable) = posmodel.trans.obsXY_to_posTP([u,v])
        elif uv_type == 'posXY':
            (targt_posTP,unreachable) = posmodel.trans.posXY_to_posTP([u,v])
        elif uv_type == 'obsTP':
            targt_posTP = posmodel.trans.obsTP_to_posTP([u,v])
        elif uv_type == 'posTP':
            targt_posTP = [u,v]
        elif uv_type == 'dQdS':
            start_uv = [current_position['Q'],current_position['S']]
            targt_uv = posmodel.trans.addto_QS(start_uv,[u,v])
            (targt_posTP,unreachable) = posmodel.trans.QS_to_posTP(targt_uv)
        elif uv_type == 'dXdY':
            start_uv = [current_position['posX'],current_position['posY']]
            targt_uv = posmodel.trans.addto_posXY(start_uv,[u,v])
            (targt_posTP,unreachable) = posmodel.trans.posXY_to_posTP(targt_uv)
        elif uv_type == 'dTdP':
            targt_posTP = posmodel.trans.addto_posTP(start_posTP,[u,v],range_wrap_limits='none')
        else:
            print('bad uv_type "' + str(uv_type) + '" for target request')
            return
        new_request = {'start_posTP' : start_posTP,
                       'targt_posTP' : targt_posTP,
                          'posmodel' : posmodel,
                           'command' : uv_type,
                          'cmd_val1' : u,
                          'cmd_val2' : v,
                          'log_note' : log_note}
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
            self._schedule_with_anticollision()
        else:
            self._schedule_without_anticollision()

    def total_dtdp(self, pos):
        """Return as-scheduled total move distance for positioner identified by pos.
        Returns [dt,dp].
        """
        posmodel = self.petal.get_model_for_pos(pos)
        dtdp = [0,0]
        for tbl in self.move_tables:
            if tbl.posmodel == posmodel:
                postprocessed = tbl.full_table
                dtdp = [postprocessed['stats']['net_dT'][-1], postprocessed['stats']['net_dP'][-1]]
                break
        return dtdp

    def total_scheduled_time(self):
        """Return as-scheduled total time for all moves and pauses to complete for
        all positioners.
        """
        time = 0
        for tbl in self.move_tables:
            postprocessed = tbl.full_table
            tbl_time = postprocessed['stats']['net_time'][-1]
            if tbl_time > time:
                time = tbl_time

    def already_requested(self, pos):
        """Returns boolean whether a request has already been registered in the
        schedule for the argued positioner.
        """
        posmodel = self.petal.get_model_for_pos(pos)
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
                if self.move_tables[i].posmodel.posid == self.move_tables[j].posmodel.posid:
                    extend_list.append(self.move_tables.pop(j))
                else:
                    j += 1
            for e in extend_list:
                self.move_tables[i].extend(e)
            i += 1

    def _schedule_without_anticollision(self):
        while(self.requests):
            req = self.requests.pop(0)
            posmodel = req['posmodel']
            table = posmovetable.PosMoveTable(posmodel)
            dtdp = posmodel.trans.delta_posTP(req['targt_posTP'], req['start_posTP'], range_wrap_limits='targetable')
            table.set_move(0, pc.T, dtdp[0])
            table.set_move(0, pc.P, dtdp[1])
            table.set_prepause (0, 0.0)
            table.set_postpause(0, 0.0)
            table.store_orig_command(0, req['command'], req['cmd_val1'], req['cmd_val2'])
            table.log_note += (' ' if table.log_note else '') + req['log_note']
            self.move_tables.append(table)

    def _schedule_with_anticollision(self):
        """
           Currently just a very naive anticollision that
           stops the positioner from moving if it will collide.
           Those positioners do not recieve their request location.
        """
        verbose = False
        if verbose:
            print("You ARE doing anticollisions")
            print("Number of requests: "+str(len(self.requests)))

        xabs = []; yabs = []; tstarts = []; pstarts = []; ttargs = []; ptargs = []; posmodels = []
        log_notes = {}
        for request in self.requests:
            posmodel = request['posmodel']
            xabs.append(posmodel.state.read('OFFSET_X'))
            yabs.append(posmodel.state.read('OFFSET_Y'))
            ttarg,ptarg = posmodel.trans.posTP_to_obsTP(request['targt_posTP'][:])
            tstart,pstart = posmodel.trans.posTP_to_obsTP(request['start_posTP'][:])
            tstarts.append(tstart)
            pstarts.append(pstart)
            ptargs.append(ptarg)
            ttargs.append(ttarg)
            posmodels.append(posmodel)
            log_notes[posmodel] = request['log_note']

        method = 'RRE'
        avoidance_technique = 'zeroth_order'
        self.move_tables = anticollision.run_anticol(xabs,yabs,tstarts,ttargs,pstarts,ptargs,posmodels,method,avoidance_technique,verbose)
        
        for table in self.move_tables:
            table.log_note += (' ' if table.log_note else '') + log_notes[table.posmodel]
