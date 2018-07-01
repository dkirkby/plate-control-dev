import posconstants as pc
import posschedulestage

class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    
        petal  ... Instance of Petal that this schedule applies to.
        
        log    ... Instance of PosSchedStats in which to register scheduling statistics.
                   If log=None, then no statistics are logged.
    """

    def __init__(self, petal, stats=None, verbose=True):
        self.petal = petal
        self.stats = stats
        self.verbose = verbose
        self.printfunc = self.petal.printfunc
        self.requests = {} # keys: posids, values: target request dictionaries
        self.max_path_adjustment_passes = 3 # max number of times to go through the set of colliding positioners and try to adjust each of their paths to avoid collisions. After this many passes, it defaults to freezing any that still collide
        self.stage_order = ['direct','retract','rotate','extend','expert']
        self.RRE_stage_order = ['retract','rotate','extend']
        self.stages = {name:posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map) for name in self.stage_order}
        self.anneal_time = {'direct':3, 'retract':3, 'rotate':3, 'extend':3, 'expert':3} # times in seconds, see comments in PosScheduleStage
        self.move_tables = {}

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
        posmodel = self.petal.posmodels[posid]
        if self.already_requested(posid):
            if self.verbose:
                self.printfunc(str(posid) + ': target request denied. Cannot request more than one target per positioner in a given schedule.')
            return
        if self._deny_request_because_disabled(posmodel):
            if self.verbose:
                self.printfunc(str(posid) + ': target request denied. Positioner is disabled.')
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
                self.printfunc(str(posid) + ': target request denied. Bad uv_type "' + str(uv_type) + '".')
            return
        if unreachable:
            if self.verbose:
                self.printfunc(str(posid) + ': target request denied. Target not reachable: ' + str(uv_type) + ' = (' + format(u,'.3f') + ',' + format(v,'.3f') + ')')
            return
        targt_obsTP = posmodel.trans.posTP_to_obsTP(targt_posTP)
        if self._deny_request_because_target_interference(posmodel,targt_obsTP):
            if self.verbose:
                self.printfunc(str(posid) + ': target request denied. Target interferes with a neighbor\'s existing target.')
            return
        if self._deny_request_because_out_of_bounds(posmodel,targt_obsTP):
            if self.verbose:
                self.printfunc(str(posid) + ': target request denied. Target exceeds a fixed boundary.')
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

    def schedule_moves(self, anticollision='freeze'):
        """Executes the scheduling algorithm upon the stored list of move requests.

        A single move table is generated for each positioner that has a request
        registered. The resulting tables are stored in the move_tables list.
        
        There are three options for anticollision behavior during scheduling:
           
          None      ... No collisions are searched for. Expert use only.
           
          'freeze'  ... Collisions are searched for. If found, the colliding
                                   positioner is frozen at its original position. This
                                   setting is suitable for small correction moves.
           
          'adjust'  ... Collisions are searched for. If found, the motion paths
                                   of colliding positioners are adjusted to attempt to
                                   avoid each other. If this fails, the colliding positioner
                                   is frozen at its original position. This setting is
                                   suitable for gross retargeting moves.

        If there were ANY pre-existing move tables in the list (for example, hard-
        stop seeking tables directly added by an expert user or expert function),
        then the requests list is ignored. The only changes to move tables are
        for power density annealing. Furthermore, if anticollision='adjust',
        then it reverts to 'freeze' instead. An argument of anticollision=None
        remains as-is.
        """
        if not self.requests and not self.stages['expert'].is_not_empty():
            if self.verbose:
                self.printfunc('No requests nor existing move tables found. No move scheduling performed.')
            return
        if self.stages['expert'].is_not_empty():
            self._schedule_expert_tables(anticollision)
        else:
            if anticollision == 'adjust':
                self._schedule_requests_with_path_adjustments() # there is only one possible anticollision method for this scheduling method
            else:
                self._schedule_requests_with_no_path_adjustments(anticollision)
        for name in self.stage_order:
            self.stages[name].equalize_table_times()
            for posid,table in self.stages[name].move_tables:
                if posid in self.move_tables:
                    self.move_tables[posid].extend(table)
                else:
                    self.move_tables[posid] = table
        if self.requests:
            for posid,table in self.move_tables.items():
                req = self.requests.pop(posid)
                table.store_orig_command(0,req['command'],req['cmd_val1'],req['cmd_val2']) # keep the original commands with move tables
                table.log_note += (' ' if table.log_note else '') + req['log_note'] # keep the original log notes with move tables
        if self.petal.animator_on:
            for name in self.stage_order:
                stage = self.stages[name]
                if stage.is_not_empty():
                    self.collider.add_mobile_to_animator(self.petal.animator_total_time, stage.sweeps)
                    self.petal.animator_total_time += max({sweep.time[-1] for sweep in stage.sweeps})
                
    def already_requested(self, posid):
        """Returns boolean whether a request has already been registered in the
        schedule for the argued positioner.
        """
        return posid in self.requests           

    def expert_add_table(self, move_table):
        """Adds an externally-constructed move table to the schedule. Only simple
        freezing is available as an anticollision method for such externally-made
        tables. If any tables have been added by this method, then any target requests
        will be ignored upon scheduling. Generally, this method should only be used
        by an expert user.
        """
        if self._deny_request_because_disabled(move_table.posmodel):
            if self.verbose:
                self.printfunc(str(move_table.posmodel.posid) + ': move table addition to schedule denied. Positioner is disabled.')
            return
        self.stages['expert'].add_table(move_table)

    def _schedule_expert_tables(self, anticollision):
        """Gathers data from expert-added move tables and populates the 'expert'
        stage. Any move requests are ignored.
        """
        should_freeze = not(not(anticollision))
        self._direct_stage_conditioning(self.stages['expert'], self.anneal_time['expert'], should_freeze)

    def _schedule_requests_with_no_path_adjustments(self, anticollision):
        """Gathers data from requests dictionary and populates the 'direct'
        stage with direct motions from start to finish. The positioners are given no
        path adjustments to avoid each other.
        """
        start_posTP = {}
        desired_final_posTP = {}
        dtdp = {}
        for posid,request in self.requests.items():
            start_posTP[posid] = request['start_posTP']
            desired_final_posTP[posid] = request['targt_posTP']
            trans = self.petal.posmodels[posid].trans
            dtdp[posid] = trans.delta_posTP(desired_final_posTP[posid], start_posTP[posid], range_wrap_limits='targetable')
        stage = self.stages['direct']
        stage.initialize_move_tables(start_posTP, dtdp)
        should_freeze = not(not(anticollision)) # double-negative syntax is to be compatible with various False/None/'' negative values
        self._direct_stage_conditioning(stage, self.anneal_time['direct'], should_freeze)
        
    def _direct_stage_conditioning(self, stage, anneal_time, should_freeze):
        """Applies annealing and possibly freezing to a 'direct' or 'expert' stage.
        
            stage         ... instance of PosScheduleStage, needs to already have its move tables initialized
            anneal_time   ... time in seconds, for annealing
            should_freeze ... boolean, says whether to check for collisions and freeze
        """
        stage.anneal_tables(anneal_time)
        if should_freeze:
            colliding_sweeps, all_sweeps = stage.find_collisions(stage.move_tables)
            stage.store_collision_finding_results(colliding_sweeps, all_sweeps)
            for posid in colliding_sweeps:
                if posid in stage.colliding: # re-check, since earlier path adjustments in loop may have already resolved this posid's collision
                    stage.adjust_path(posid, freezing='forced')
        
    def _schedule_requests_with_path_adjustments(self):
        """Gathers data from requests dictionary and populates the 'retract',
        'rotate', and 'extend' stages with motion paths from start to finish.
        The move tables may include adjustments of paths to avoid collisions.
        """
        start_posTP = {name:{} for name in self.RRE_stage_order}
        desired_final_posTP = {name:{} for name in self.RRE_stage_order}
        dtdp = {name:{} for name in self.RRE_stage_order}
        for posid,request in self.requests.items():
            # Some care is taken here to use only delta and add functions provided by PosTransforms,
            # to ensure that range wrap limits are always safely handled from stage to stage.
            posmodel = self.petal.posmodels[posid]
            trans = posmodel.trans
            start_posTP['retract'][posid] = request['start_posTP']
            desired_final_posTP['retract'][posid] = [request['start_posTP'][pc.T], self.collider.Eo_phi] # Ei would also be safe, but unnecessary in most cases. Costs more time and power to get to.
            desired_final_posTP['rotate'][posid]  = [request['targt_posTP'][pc.T], self.collider.Eo_phi] # Ei would also be safe, but unnecessary in most cases. Costs more time and power to get to.
            desired_final_posTP['extend'][posid]  = request['targt_posTP']
            dtdp['retract'][posid]       = trans.delta_posTP(desired_final_posTP['retract'][posid], start_posTP['retract'][posid], range_wrap_limits='targetable')
            start_posTP['rotate'][posid] = trans.addto_posTP(        start_posTP['retract'][posid],        dtdp['retract'][posid], range_wrap_limits='targetable')
            dtdp['rotate'][posid]        = trans.delta_posTP(desired_final_posTP['rotate'][posid],  start_posTP['rotate'][posid],  range_wrap_limits='targetable')
            start_posTP['extend'][posid] = trans.addto_posTP(        start_posTP['rotate'][posid],         dtdp['rotate'][posid],  range_wrap_limits='targetable')
            dtdp['extend'][posid]        = trans.delta_posTP(desired_final_posTP['extend'][posid],  start_posTP['extend'][posid],  range_wrap_limits='targetable')
        for name in self.RRE_stage_order:
            stage = self.stage[name]
            stage.initialize_move_tables(start_posTP[name], dtdp[name])
            stage.anneal_tables(self.anneal_time[name])
            colliding_sweeps, all_sweeps = stage.find_collisions(stage.move_tables)
            stage.store_collision_finding_results(colliding_sweeps, all_sweeps)
            attempts_remaining = self.max_path_adjustment_passes
            while stage.colliding and attempts_remaining:
                for posid in stage.colliding:
                    stage.adjust_path(posid)
                attempts_remaining -= 1
            
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
            neighbor_posmodel = self.petal.posmodels[neighbor]
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