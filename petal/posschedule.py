import posmovetable
import posconstants as pc
import posschedulestage
from collections import OrderedDict

class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    
        petal             ... Instance of Petal that this schedule applies to.
        animate           ... Whether to automatically generate animations of the scheduled moves.
    """

    def __init__(self, petal, animate=False, verbose=True):
        self.petal = petal
        self.verbose = verbose
        self.requests = {} # keys: posids, values: target request dictionaries
        self.move_tables = {} # keys: posids, values: instances of PosMoveTable
        self.max_path_adjustment_iterations = 3 # number of times to attempt move path adjustments to avoid collisions

    @property
    def collider(self):
        return self.petal.collider
        
    def request_target(self, posid, uv_type, u, v, log_note=''):
        """Adds a request to the schedule for a given positioner to move to the
        target position (u,v) or by the target distance (du,dv) in the coordinate
        system indicated by uv_type.

              posid ... string, unique id of positioner
            uv_type ... string, 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
                  u ... float, value of q, dq, x, dx, t, or dt
                  v ... float, value of s, ds, y, dy, p, or dp
           log_note ... optional string to store alongside the requested move in the log data

        A schedule can only contain one target request per positioner at a time.
        """
        posmodel = self.petal.posmodel(posid)
        if self.already_requested(posid):
            if self.verbose:
                print(str(posid) + ': target request denied. Cannot request more than one target per positioner in a given schedule.')
            return
        if self._deny_request_because_disabled(posmodel):
            if self.verbose:
                print(str(posid) + ': target request denied. Positioner is disabled.')
            return
        current_position = posmodel.expected_current_position
        start_posTP = [current_position['posT'],current_position['posP']]
        lims = 'targetable'
        if uv_type == 'QS':
            (targt_posTP,unreachable) = posmodel.trans.QS_to_posTP([u,v],lims)
        elif uv_type == 'obsXY':
            (targt_posTP,unreachable) = posmodel.trans.obsXY_to_posTP([u,v],lims)
        elif uv_type == 'posXY':
            (targt_posTP,unreachable) = posmodel.trans.posXY_to_posTP([u,v],lims)
        elif uv_type == 'obsTP':
            targt_posTP = posmodel.trans.obsTP_to_posTP([u,v])
        elif uv_type == 'posTP':
            targt_posTP = [u,v]
        elif uv_type == 'dQdS':
            start_uv = [current_position['Q'],current_position['S']]
            targt_uv = posmodel.trans.addto_QS(start_uv,[u,v])
            (targt_posTP,unreachable) = posmodel.trans.QS_to_posTP(targt_uv,lims)
        elif uv_type == 'dXdY':
            start_uv = [current_position['posX'],current_position['posY']]
            targt_uv = posmodel.trans.addto_posXY(start_uv,[u,v])
            (targt_posTP,unreachable) = posmodel.trans.posXY_to_posTP(targt_uv,lims)
        elif uv_type == 'dTdP':
            targt_posTP = posmodel.trans.addto_posTP(start_posTP,[u,v],lims)
        else:
            if self.verbose:
                print(str(posid) + ': target request denied. Bad uv_type "' + str(uv_type) + '".')
            return
        if unreachable:
            if self.verbose:
                print(str(posid) + ': target request denied. Target not reachable: ' + str(uv_type) + ' = (' + format(u,'.3f') + ',' + format(v,'.3f') + ')')
            return
        targt_obsTP = posmodel.trans.posTP_to_obsTP(targt_posTP)
        if self._deny_request_because_target_interference(posmodel,targt_obsTP):
            if self.verbose:
                print(str(posid) + ': target request denied. Target interferes with a neighbor\'s existing target.')
            return
        if self._deny_request_because_out_of_bounds(posmodel,targt_obsTP):
            if self.verbose:
                print(str(posid) + ': target request denied. Target exceeds a fixed boundary.')
            return
        new_request = {'start_posTP' : start_posTP,
                       'targt_posTP' : targt_posTP,
                          'posmodel' : posmodel,
                             'posid' : posid,
                           'command' : uv_type,
                          'cmd_val1' : u,
                          'cmd_val2' : v,
                          'log_note' : log_note}
        self.requests[posid] = new_request

    def schedule_moves(self, anticollision='detect_and_freeze'):
        """Executes the scheduling algorithm upon the stored list of move requests.

        A single move table is generated for each positioner that has a request
        registered. The resulting tables are stored in the move_tables list.
        
        There are three options for anticollision behavior during scheduling:
           
          'none'               ... No collisions are searched for. Expert use only.
           
          'detect_and_freeze'  ... Collisions are searched for. If found, the colliding
                                   positioner is frozen at its original position. This
                                   setting is suitable for small correction moves.
           
          'detect_and_adjust'  ... Collisions are searched for. If found, the motion paths
                                   of colliding positioners are adjusted to attempt to
                                   avoid each other. If this fails, the colliding positioner
                                   is frozen at its original position. This setting is
                                   suitable for gross retargeting moves.

        If there were ANY pre-existing move tables in the list, then no new
        scheduling is done. Any new requests are ignored. Furthermore, if
        anticollision='detect_and_adjust', then it reverts to 'detect_and_freeze'
        instead. (An argument of anticollision='none' remains as-is.)
        """
        if anticollision not in {'none','detect_and_freeze','detect_and_adjust'}:
            if self.verbose:
                print('Bad anticollision option \'' + str(anticollision) + '\' was argued. No move scheduling performed.')
            return
        if self.move_tables:
            anticollision = 'detect_and_freeze' if anticollision == 'detect_and_adjust' else anticollision
        else:
            if anticollision == 'none' or anticollision == 'detect_and_freeze':
                self.schedule_with_no_path_adjustments()
            elif anticollision == 'detect_and_adjust':
                self.schedule_with_path_adjustments()
            for posid,table in self.move_tables.items():
                req = self.requests.pop(posid)
                table.store_orig_command(0,req['command'],req['cmd_val1'],req['cmd_val2']) # keep the original commands with move tables
                table.log_note += (' ' if table.log_note else '') + req['log_note'] # keep the original log notes with move tables
        if anticollision != 'none':
            self._check_tables_for_collisions_and_freeze()
        if self.animate:
            # I think I should break this up a bit:
            #   make generation of pngs happen inside posschedulestage instances
            #   high-level user "start animation capture", "finish animation capture" functions
            #   during this period, stages are spitting back png filenames into a list
            #   at the end of this period, the single mp4 file is made from however many pngs
            sweeps = self._merge_sweeps_from_stages(stages)
            savedir = pc.dirs['fp_temp_files']
            vidname = pc.filename_timestamp_str_now() + '_schedule_anim.mp4'
            self.collider.animate(sweeps,savedir,vidname)
                
    def already_requested(self, posid):
        """Returns boolean whether a request has already been registered in the
        schedule for the argued positioner.
        """
        return posid in self.requests           

    def expert_add_table(self, move_table):
        """Adds an externally-constructed move table to the schedule. If there
        is ANY such table in a given schedule, then the anti-collision algorithm
        will NOT be used. Generally, this method should only be used for internal
        calls by an expert user.
        """
        if self._deny_request_because_disabled(move_table.posmodel):
            return
        this_posid = move_table.posid
        if move_table.posid in self.move_tables:
            self.move_tables[this_posid].extend(move_table)
        else:
            self.move_tables[this_posid] = move_table

    def _check_tables_for_collisions_and_freeze(self, posids):
        """Checks for collision of all the argued posids against their neighbors,
        both other positioners and fixed boundaries.
        
        In case of a predicted collision, the colliding positioner is instead
        frozen in place at a point before the collision would have occurred.
        
        In the case where it is two neighboring positioners who would collide, then
        we always select to freeze the one that has its phi arm further extended.
        This provides a greater likelihood that at least one of the two (the less
        extended positioner) can still get its phi arm tucked in.
        """
        colliding_positioners = self._find_collisions(self.move_tables)
        n_iter = 0
        max_iter = 5
        while colliding_positioners and n_iter < max_iter:
            # decide which of pair to freeze
            # identify which row in its move table it would collide
            # truncate the move table ~5 (?) deg before collision would have occurred
            # make a dict of move_tables of all neighbors of frozen positioners
            colliding_positioners = self._find_collisions(neighbor_tables_of_frozen) # double-check to ensure the truncation hasn't caused a follow-on collision
            n_iter += 1
        if n_iter >= max_iter:
            print('Error: could not sufficiently arrest colliding positioners, after ' + str(n_iter) + ' of freezing!')

    def _schedule_with_no_path_adjustments(self, posids):
        """Gathers data from requests dictionary for the argued posids, and populates
        self.move_tables with direct motions from start to finish. These positioners
        are given no path adjustments to avoid each other.
        """
        start_tp = {}
        final_tp = {}
        for posid,request in self.requests.items():
            start_tp[posid] = request['start_posTP']
            final_tp[posid] = request['targt_posTP']
        stage = posschedulestage.PosScheduleStage(self.collider, anneal_time=3, verbose=self.verbose)
        stage.initialize_move_tables(start_tp, final_tp)
        stage.anneal_power_density()
        self.move_tables = stage.move_tables
        
    def _schedule_with_path_adjustments(self, posids):
        """Gathers data from requests dictionary for the argued posids, and populates
        self.move_tables with motion paths from start to finish. These include
        adjustments of paths to avoid collisions.
        
        For positioners that have not been given specific move requests, but
        which are not disabled, these get start/finish positions assigned to them that
        match their current position. This causes them to be included as candidates
        for path adjustment (so that they can be temporarily moved out of the path of
        other positioners if necessary, and then returned to their original location).
        
        Disabled positioners are still checked for collisions, but of course are not
        allowed to move out of the way.
        """
        stage_names = ['retract','rotate','extend']
        start_posTP = {name:{} for name in stage_names}
        desired_final_posTP = {name:{} for name in stage_names}
        dtdp = {name:{} for name in stage_names}
        for posid,request in self.requests.items():
            # some care is taken to use only delta and add functions provided by PosTransforms, to ensure that range wrap limits are always properly handled from stage to stage
            posmodel = self.collider.posmodels[posid]
            trans = posmodel.trans
            start_posTP['retract'][posid] = request['start_posTP']
            desired_final_posTP['retract'][posid] = [request['start_posTP'][pc.T], self.collider.Ei_phi]
            desired_final_posTP['rotate'][posid]  = [request['targt_posTP'][pc.T], self.collider.Ei_phi]
            desired_final_posTP['extend'][posid]  = request['targt_posTP']
            dtdp['retract'][posid]       = trans.delta_posTP(desired_final_posTP['retract'][posid], start_posTP['retract'][posid], range_wrap_limits='targetable')
            start_posTP['rotate'][posid] = trans.addto_posTP(        start_posTP['retract'][posid],        dtdp['retract'][posid], range_wrap_limits='targetable')
            dtdp['rotate'][posid]        = trans.delta_posTP(desired_final_posTP['rotate'][posid],  start_posTP['rotate'][posid],  range_wrap_limits='targetable')
            start_posTP['extend'][posid] = trans.addto_posTP(        start_posTP['rotate'][posid],         dtdp['rotate'][posid],  range_wrap_limits='targetable')
            dtdp['extend'][posid]        = trans.delta_posTP(desired_final_posTP['extend'][posid],  start_posTP['extend'][posid],  range_wrap_limits='targetable')                
        enabled_but_not_requested = [posmodel.posid for posmodel in self.collider.posmodels.values() if posmodel.is_enabled and not posmodel.posid in self.requests]
        for posid in enabled_but_not_requested:
            current_posTP = self.collider.posmodels[posid].expected_current_posTP
            for name in stage_names:
                start_posTP[name][posid] = current_posTP
                desired_final_posTP[name][posid] = current_posTP
        stages = OrderedDict.fromkeys(stage_names)
        # processing of these three stages is a good candidate for multiple processes, to get performance improvement (not multiple threads, due to the GIL)
        stages['retract'] = posschedulestage.PosScheduleStage(self.collider, anneal_time=3, verbose=self.verbose)
        stages['rotate']  = posschedulestage.PosScheduleStage(self.collider, anneal_time=3, verbose=self.verbose)
        stages['extend']  = posschedulestage.PosScheduleStage(self.collider, anneal_time=3, verbose=self.verbose)
        for name,stage in stages.items():
            stage.initialize_move_tables(start_posTP[name], dtdp[name])
            stage.anneal_power_density()
            colliding_positioners = self._find_collisions(stage.move_tables)
            n_iter = 0
            while colliding_positioners and n_iter < self.max_path_adjustment_iterations:
                stage.adjust_paths(colliding_positioners, n_iter)
                colliding_move_tables = {posid:stage.move_tables[posid] for posid in colliding_positioners}
                colliding_positioners = self._find_collisions(colliding_move_tables)
                n_iter += 1
        self.move_tables = self._merge_move_tables_from_stages(stages)
        motionless = {table.posid for table in self.move_tables if table.is_motionless}
        for posid in motionless:
            del self.move_tables[posid]

    def _find_collisions(self, move_tables):
        """Identifies collisions in the argued dict, keys = posids, values = PosMoveTable instances.
        
        Returns a dict with keys = posids, values = PosSweep instances (see poscollider.py)
            
        The return dict only contains sweeps for positioners that collide, and will be
        empty if there are no collisions.
        
        Note that for any pair of positioners that collide, the return dict will
        contain sweeps for each of them. The two sweeps are both giving you information
        about the same collision event, but from the perspectives of the two different
        positioners. In other words, if there is an entry for posid 'M00001', colliding with
        neighbor 'M00002', then the dict will also contain an entry for posid 'M00002',
        colliding with neighbor 'M0001'.
        
        If a positioner has collisions with multiple other postioners or fixed boundaries,
        then only the collision that occurs first is included in the return dict.
        """
        already_checked = {posid:set() for posid in self.collider.posids}
        colliding_sweeps = {posid:set() for posid in move_tables}
        for posid in move_tables:
            table_A = move_tables[posid]
            init_obsTP_A = table_A.posmodel.trans.posTP_to_obsTP(table_A.init_posTP)
            for neighbor in self.collider.pos_neighbors[posid]:
                if neighbor not in already_checked[posid]:
                    table_B = move_tables[neighbor] if neighbor in move_tables else table_B = posmovetable.PosMoveTable(self.collider.posmodels[neighbor])
                    init_obsTP_B = table_B.posmodel.trans.posTP_to_obsTP(table_B.init_posTP)
                    pospos_sweeps = self.collider.spacetime_collision_between_positioners(posid, init_obsTP_A, tableA, neighbor, init_obsTP_B, tableB)
                    for sweep in pospos_sweeps:
                        if sweep.collision_case != pc.case.I:
                            colliding_sweeps[sweep.posid].add(sweep)
                    already_checked[posid].add(neighbor)
                    already_checked[neighbor].add(posid)
            for fixed_neighbor in self.collider.fixed_neighbor_cases[posid]:
                posfix_sweeps = self.collider.spacetime_collision_with_fixed(posid, init_obsTP_A, table_A)
                if posfix_sweep.collision_case != pc.case.I:
                    colliding_sweeps[posid].add(posfix_sweeps[0]) # index 0 to retrieve from the one-element list
        # for any positioner that has > 1 collision, return the first collision only
        # and convert return data from dict of sets to dict of sweeps

    def _merge_move_tables_from_stages(self,stages):
        """Collects move tables from an ordered dict of PosScheduleStage instances.
        For each positioner, merges move tables from the stages. This is done
        in the order of the dict. Fills in any intermediate time gaps
        between stages with discrete pause events, so that all positioners have
        matching scheduled move times for all stages and overall. Returns a dict
        of move_tables, with keys = posids.
        """
        move_tables = {}
        for stage in stages.values():
            move_times = {}
            for posid,table in stage.move_tables.items():
                postprocessed = table.for_schedule
                move_times[posid] = postprocessed['stats']['net_time'][-1]
            max_move_time = max(move_times.values())
            for posid,table in stage.move_tables.items():
                equalizing_pause = max_move_time - move_times[posid]
                if equalizing_pause:
                    idx = table.n_rows
                    table.insert_new_row(idx)
                    table.set_postpause(idx,equalizing_pause)
                if posid in move_tables:
                    move_tables[posid].extend(table)
                else:
                    move_tables[posid] = table
        return move_tables
    
    def _deny_request_because_disabled(self, posmodel):
        """This is a special function specifically because there is a bit of care we need to
        consistently take with regard to post-move cleanup, if a request is going to be denied.
        """
        enabled = posmodel.is_enabled
        if enabled == False:  # this is specifically NOT worded as "if not enabled:", because here we actually do not want a value of None to pass the test, in case the parameter field 'CTRL_ENABLED' has not yet been implemented in the positioner's .conf file
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            return True
        return False
    
    def _deny_request_because_target_interference(self, posmodel, target_obsTP):
        """Checks for case where a target request is definitively unreachable due to
        incompatibility with already-existing neighbor targets.
        """
        posid = posmodel.posid
        target_interference = False
        neighbors_with_requests = [neighbor for neighbor in self.collider.pos_neighbors[posid] if neighbor in self.requests]
        for neighbor in neighbors_with_requests:
            neighbor_posmodel = self.collider.posmodels[neighbor]
            neighbor_target_posTP = self.requests[neighbor]['targt_posTP']
            neighbor_target_obsTP = neighbor_posmodel.trans.posTP_to_obsTP(neighbor_target_posTP)
            if self.collider.spatial_collision_between_positioners(self, posid, neighbor, target_obsTP, neighbor_target_obsTP):
                target_interference = True
                break
        if target_interference:
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            return True
        return False
    
    def _deny_request_because_out_of_bounds(self, posmodel, target_obsTP):
        """Checks for case where a target request is definitively unreachable due to
        being beyond a fixed petal or GFA boundary.
        """
        out_of_bounds = self.collider.spatial_collision_with_fixed(posmodel.posid, target_obsTP)
        if out_of_bounds:
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            return True
        return False