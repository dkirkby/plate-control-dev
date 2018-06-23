import posmovetable
import posconstants as pc
import posschedulestage
from collections import OrderedDict

class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    
        petal             ... Instance of Petal that this schedule applies to.
    """

    def __init__(self, petal, verbose=True):
        self.petal = petal
        self.verbose = verbose
        self.requests = {} # keys: posids, values: target request dictionaries
        self.move_tables = {} # keys: posids, values: instances of PosMoveTable
        self._sweeps = {} # keys: posids, values: instances of PosSweep, corresponding to entries in self.move_tables
        self.max_path_adjustment_iterations = 3 # number of times to attempt move path adjustments to avoid collisions
        self.min_freeze_clearance = 5 # degrees, how early to truncate a move table to avoid collision via "freezing"
        self.anneal_time = {'direct':3, 'retract':3, 'rotate':3, 'extend':3} # times in seconds, see comments in PosScheduleStage

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

        If there were ANY pre-existing move tables in the list (for example, hard-
        stop seeking tables directly added by an expert user or expert function),
        then the requests list is ignored. The only changes to move tables are
        for power density annealing. Furthermore, if anticollision='detect_and_adjust',
        then it reverts to 'detect_and_freeze' instead. An argument of anticollision='none'
        remains as-is.
        """
        if anticollision not in {'none','detect_and_freeze','detect_and_adjust'}:
            if self.verbose:
                print('Bad anticollision option \'' + str(anticollision) + '\' was argued. No move scheduling performed.')
            return
        if self.move_tables:
            anticollision = 'detect_and_freeze' if anticollision == 'detect_and_adjust' else anticollision
            self._schedule_existing_tables()
        else:
            if anticollision == 'none' or anticollision == 'detect_and_freeze':
                self._schedule_with_no_path_adjustments()
            elif anticollision == 'detect_and_adjust':
                self._schedule_with_path_adjustments()
            for posid,table in self.move_tables.items():
                req = self.requests.pop(posid)
                table.store_orig_command(0,req['command'],req['cmd_val1'],req['cmd_val2']) # keep the original commands with move tables
                table.log_note += (' ' if table.log_note else '') + req['log_note'] # keep the original log notes with move tables
        if anticollision == 'none':
            frozen_posids = set()
        else:
            frozen_posids, still_colliding_sweeps = self._check_tables_for_collisions_and_freeze(self.move_tables)            
        if self.petal.animator_on:
            self.collider.add_mobile_to_animator(self.petal.animator_total_time, self._sweeps, frozen_posids)
            self.petal.animator_total_time += max({sweep.time[-1] for sweep in self._sweeps})
                
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

    def _schedule_existing_tables(self):
        """Gathers data from exisitn move tables and applies power annealing.
        Any requests are ignored.
        """
        stage = posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map, verbose=self.verbose)
        stage.move_tables = self.move_tables
        stage.anneal_power_density(self.anneal_time['direct'])
        self.move_tables = stage.move_tables

    def _schedule_with_no_path_adjustments(self):
        """Gathers data from requests dictionary and populates self.move_tables
        with direct motions from start to finish. The positioners are given no
        path adjustments to avoid each other.
        """
        start_posTP = {}
        desired_final_posTP = {}
        dtdp = {}
        for posid,request in self.requests.items():
            start_posTP[posid] = request['start_posTP']
            desired_final_posTP[posid] = request['targt_posTP']
            trans = self.collider.posmodels[posid].trans
            dtdp[posid] = trans.delta_posTP(desired_final_posTP[posid], start_posTP[posid], range_wrap_limits='targetable')
        stage = posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map, verbose=self.verbose)
        stage.initialize_move_tables(start_posTP, dtdp)
        stage.anneal_power_density(self.anneal_time['direct'])
        self.move_tables = stage.move_tables
        
    def _schedule_with_path_adjustments(self):
        """Gathers data from requests dictionary and populates self.move_tables
        with motion paths from start to finish. The move tables may include
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
        stages['retract'] = posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map, verbose=self.verbose)
        stages['rotate']  = posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map, verbose=self.verbose)
        stages['extend']  = posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map, verbose=self.verbose)
        for name,stage in stages.items():
            stage.initialize_move_tables(start_posTP[name], dtdp[name])
            stage.anneal_power_density(self.anneal_time[name])
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
        """Identifies any collisions that would be induced by executing a collection
        of move tables.
        
            move_tables ... dict with keys = posids, values = PosMoveTable instances.
        
        Return:
            
            dict with keys = posids, values = PosSweep instances (see poscollider.py)
            
        The return dict only contains sweeps for positioners that collide. It will be
        empty if there are no collisions. These sweeps may indicate collision with
        another positioner or with a fixed boundary. This information is given internally
        within each sweep instance.
        
        For any pair of positioners that collide, the return dict will contain separate
        sweeps for each of them. These two sweeps are giving you information about the
        same collision event, but from the perspectives of the two different
        positioners. In other words, if there is an entry for posid 'M00001', colliding with
        neighbor 'M00002', then the dict will also contain an entry for posid 'M00002',
        colliding with neighbor 'M0001'.
        
        If positioner A collides with a fixed boundary, or with a disabled neighbor
        positioner B, then the return dict only contains the sweep of A.
        
        If a positioner has collisions with multiple other postioners / fixed boundaries,
        then only the first collision event in time is included in the return dict.
        
        In the rare event of a three-way exactly simultaneous collision between three
        moving positioners, then all three of those positioners' sweeps would still
        appear in the return dictionary.
        """
        already_checked = {posid:set() for posid in self.collider.posids}
        colliding_sweeps = {posid:set() for posid in move_tables}
        for posid in move_tables:
            table_A = move_tables[posid]
            init_obsTP_A = table_A.posmodel.trans.posTP_to_obsTP(table_A.init_posTP)
            for neighbor in self.collider.pos_neighbors[posid]:
                if neighbor not in already_checked[posid]:
                    table_B = move_tables[neighbor] if neighbor in move_tables else posmovetable.PosMoveTable(self.collider.posmodels[neighbor]) # generation of fixed table if necessary, for a non-moving neighbor
                    init_obsTP_B = table_B.posmodel.trans.posTP_to_obsTP(table_B.init_posTP)
                    pospos_sweeps = self.collider.spacetime_collision_between_positioners(posid, init_obsTP_A, table_A, neighbor, init_obsTP_B, table_B)
                    self._sweeps.update({posid:pospos_sweeps[0], neighbor:pospos_sweeps[1]})
                    for sweep in pospos_sweeps:
                        if sweep.collision_case != pc.case.I:
                            colliding_sweeps[sweep.posid].add(sweep)
                    already_checked[posid].add(neighbor)
                    already_checked[neighbor].add(posid)
            for fixed_neighbor in self.collider.fixed_neighbor_cases[posid]:
                posfix_sweep = self.collider.spacetime_collision_with_fixed(posid, init_obsTP_A, table_A)[0] # index 0 to immediately retrieve from the one-element list this function returns
                if posfix_sweep.collision_case != pc.case.I:
                    colliding_sweeps[posid].add(posfix_sweep)
        multiple_collisions = {posid for posid in colliding_sweeps if len(colliding_sweeps[posid]) > 1}
        for posid in multiple_collisions:
            first_collision_time = float('inf')
            for sweep in colliding_sweeps[posid]:
                if sweep.collision_time < first_collision_time:
                    first_sweep = sweep
                    first_collision_time = sweep.collision_time
            colliding_sweeps[posid] = {first_sweep}
        setless_sweeps_dict = {posid:colliding_sweeps[posid].pop() for posid in colliding_sweeps}
        self._sweeps.update(setless_sweeps_dict)
        return setless_sweeps_dict

    def _check_tables_for_collisions_and_freeze(self, move_tables):
        """Checks for possible collisions caused by all the argued move tables.        
        In case of a predicted collision, the colliding positioner is instead
        frozen in place at a point before the collision would have occurred.
        
        In the case where it is two neighboring positioners who would collide, then
        we select which of the two to freeze according to:
            
            1. If one positioner achieves its intended target prior to the collision,
               then we freeze the other one.
            2. Otherwise, we freeze the positioner that has its phi arm further extended.
               (This provides a greater likelihood that at least one of the two (the less
               extended positioner) can still get its phi arm tucked in.)
            3. In the rare event of equal phi extension at the moment of collision,
               then the choice of which to freeze is arbitrary.
        
        The argued dict move_tables will have its contents modified directly by
        this function, to achieve freezing. The total time to execute the move table
        is kept the same as the original, by addition of a compensating postpause. In cases
        where freezing requires that the positioner not move at all, those tables will be
        deleted from the dict.
        
        Return values are:
            
            all_frozen       ... set of all the posids that had their move tables frozen by this function
            colliding_sweeps ... dict of any remaining unresolved sweeps that have collisions, keys = posids
            
        In general, it is an error for colliding_sweeps to be anything other than
        empty. (It means the freezing algorithm did not work.)
        """
        fixed_cases = {pc.case.PTL, pc.case.GFA}
        n_iter = 0
        max_iter = 6 # Since max number of neighbors is six, could never need more than this # of iterations.
        all_frozen = set()
        colliding_sweeps = self._find_collisions(move_tables)
        while colliding_sweeps and n_iter < max_iter:
            these_frozen = set()
            neighbors_of_frozen = set()
            for posid,sweep_A in colliding_sweeps:
                if sweep_A.collision_case in fixed_cases or sweep_A.collision_neighbor not in move_tables:
                    pos_to_freeze = posid
                else:
                    sweep_B = colliding_sweeps[sweep_A.collision_neighbor]
                    if sweep_A.is_final_position(sweep_A.collision_idx):
                        pos_to_freeze = sweep_A.posid
                    elif sweep_B.is_final_position(sweep_B.collisiono_idx):
                        pos_to_freeze = sweep_B.posid
                    else:
                        phi_A = sweep_A.phi(sweep_A.collision_idx)
                        phi_B = sweep_B.phi(sweep_B.collision_idx)
                        pos_to_freeze = posid if phi_A > phi_B else sweep_B.posid
                sweep_to_freeze = colliding_sweeps[pos_to_freeze]
                table_data = move_tables[pos_to_freeze].for_schedule()
                original_total_move_time = table_data['stats']['net_time'][-1]
                for row_idx in reversed(range(move_tables[pos_to_freeze].n_rows)):
                    if table_data['stats']['net_time'] >= sweep_to_freeze.collision_time:
                        move_tables[pos_to_freeze].delete_row(row_idx)
                    else:
                        break
                n_rows = move_tables[pos_to_freeze].n_rows
                if n_rows == 0:
                    del move_tables[pos_to_freeze]
                else:
                    compensating_pause = original_total_move_time - table_data['stats']['net_time'][n_rows-1]
                    new_postpause = table_data['postpause'][n_rows-1] + compensating_pause
                    move_tables[pos_to_freeze].set_postpause(n_rows-1,new_postpause)
                these_frozen.add(pos_to_freeze)
                neighbors_of_frozen.add(self.collider.pos_neighbors[pos_to_freeze])
            tables_to_recheck = {posid:move_tables[posid] for posid in these_frozen.union(neighbors_of_frozen) if posid in move_tables}
            colliding_sweeps = self._find_collisions(tables_to_recheck) # double-check to ensure the freezing truncation hasn't caused a follow-on collision
            all_frozen.add(these_frozen)
            n_iter += 1
        if n_iter >= max_iter:
            print('Warning: could not sufficiently arrest colliding positioners, after ' + str(n_iter) + ' iterations of freezing!')
        return all_frozen, colliding_sweeps

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