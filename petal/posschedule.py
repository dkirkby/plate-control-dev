import posconstants as pc
import posschedulestage
import time
import math


class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.

        petal   ... Instance of Petal that this schedule applies to.

        stats   ... Instance of PosSchedStats in which to register scheduling statistics.
                    If stats=None, then no statistics are logged.

        verbose ... Control verbosity at stdout.
    """

    def __init__(self, petal, stats=None, verbose=True, redundant_collision_checking=False):
        self.petal = petal
        self.stats = stats
        if stats:
            schedule_id = pc.filename_timestamp_str()
            self.stats.register_new_schedule(schedule_id, len(self.petal.posids))
        self.verbose = verbose
        self.redundant_collision_checking = redundant_collision_checking # only for debugging use, adds a redundant layer of final collision checks, costs time
        self.printfunc = self.petal.printfunc
        self.requests = {} # keys: posids, values: target request dictionaries
        self.stage_order = ['direct','retract','rotate','extend','expert']
        self.RRE_stage_order = ['retract','rotate','extend']
        self.stages = {name:posschedulestage.PosScheduleStage(self.collider, power_supply_map=self.petal.power_supply_map, stats=self.stats, verbose=self.verbose, printfunc=self.printfunc) for name in self.stage_order}
        self.anneal_time = {'direct':1.0, 'retract':2.0, 'rotate':2.0, 'extend':2.0, 'expert':3} # times in seconds, see comments in PosScheduleStage
        self.should_anneal = True # overriding flag, allowing you to turn off all move time annealing
        self.should_check_petal_boundaries = True # allows you to turn off petal-specific boundary checks for non-petal systems (such as positioner test stands)
        self.move_tables = {}

    @property
    def collider(self):
        return self.petal.collider

    def request_target(self, posid, uv_type, u, v, log_note=''):
        """Adds a request to the schedule for a given positioner to move to the
        target position (u,v) or by the target distance (du,dv) in the
        coordinate system indicated by uv_type.

              posid ... string, unique id of positioner
            uv_type ... string, 'QS'/'dQdS', 'poslocXY',
                        'posintTP'/'dTdP'
                  u ... float, value of q, dq, x, dx, t, or dt
                  v ... float, value of s, ds, y, dy, p, or dp
           log_note ... optional string to store alongside the requested move
                        in the log data

        A schedule can only contain 1 target request per positioner at a time.

        Return value is True if the request was accepted and False if denied.
        """
        if self.stats:
            timer_start = time.clock()
            self.stats.add_request()
        posmodel = self.petal.posmodels[posid]
        trans = posmodel.trans
        if self.already_requested(posid):
            self.petal.pos_flags[posid] |= self.petal.multi_request_bit
            if self.verbose:
                self.printfunc(
                    f'{posid}: target request denied. Cannot request more than'
                    f'one target per positioner in a given schedule.')
            return False
        if self._deny_request_because_disabled(posmodel):
            if self.verbose:
                self.printfunc(
                    f'{posid}: target request denied. Positioner is disabled.')
            return False
        current_position = posmodel.expected_current_position
        start_posintTP = current_position['posintTP']
        lims = 'targetable'
        unreachable = False
        if uv_type == 'QS':
            targt_posintTP, unreachable = trans.QS_to_posintTP([u, v], lims)
        elif uv_type == 'dQdS':
            start_uv = current_position['QS']
            targt_uv = posmodel.trans.addto_QS(start_uv, [u, v])
            targt_posintTP, unreachable = trans.QS_to_posintTP(targt_uv, lims)
        elif uv_type == 'poslocXY':
            targt_posintTP, unreachable = trans.poslocXY_to_posintTP(
                [u, v], lims)
            if self.verbose:  # debug
                targt_poslocTP, _ = trans.poslocXY_to_poslocTP(
                    [u, v], lims)
                if unreachable:
                    self.printfunc(
                        f'{posid} unreachable, target poslocXY = {[u, v]}, '
                        f'lims = {lims}, '
                        f'targt_posintTP = {targt_posintTP}, '
                        f'unreachable = {unreachable}, '
                        f'targt_poslocTP = {targt_poslocTP}, '
                        f'targetable_range_T = {posmodel.targetable_range_T}, '
                        f'targetable_range_P = {posmodel.targetable_range_P}, '
                        f"offset_T = {trans.getval('OFFSET_T')}, "
                        f"offset_P = {trans.getval('OFFSET_P')}")
        elif uv_type == 'obsdXdY':
            # global cs5 projected xy, as returned by platemaker
            start_uv = current_position['obsXY']
            targt_uv = posmodel.trans.addto_XY(start_uv, [u, v])
            targt_posintTP, unreachable = posmodel.trans.obsXY_to_posintTP(
                targt_uv, lims)
        elif uv_type == 'poslocdXdY':
            # in poslocXY coordinates in local tangent plane, not global cs5
            start_uv = current_position['poslocXY']
            targt_uv = posmodel.trans.addto_XY(start_uv, [u, v])
            targt_posintTP, unreachable = posmodel.trans.poslocXY_to_posintTP(
                targt_uv, lims)
        elif uv_type == 'posintTP':
            targt_posintTP = [u, v]
        elif uv_type == 'dTdP':
            targt_posintTP = trans.addto_posintTP(start_posintTP, [u, v], lims)
        elif uv_type == 'obsXY':
            targt_posintTP, unreachable = trans.obsXY_to_posintTP([u, v], lims)
        elif uv_type == 'ptlXY':
            targt_posintTP, unreachable = trans.ptlXY_to_posintTP([u, v], lims)
        elif uv_type == 'poslocTP':
            targt_posintTP = trans.poslocTP_to_posintTP([u, v])
        else:
            if self.verbose:
                self.printfunc(
                    f'{posid}: target request denied. Bad uv_type: {uv_type}')
            return False
        if unreachable:
            self.petal.pos_flags[posid] |= self.petal.unreachable_targ_bit
            if self.verbose:
                self.printfunc(f'{posid}: target request denied. Target not '
                               f'reachable: {uv_type}, ({u:.3f}, {v:.3f})')

            return False
        if self._deny_request_because_limit(posmodel, targt_posintTP):
            if self.verbose:
                self.printfunc(f'{posid}: target request denied. Target '
                               "exceeds expert radial limit.")
            return False
        targt_poslocTP = trans.posintTP_to_poslocTP(targt_posintTP)
        if self._deny_request_because_target_interference(
                posmodel, targt_poslocTP):
            if self.verbose:
                self.printfunc(f'{posid}: target request denied. Target '
                               "interferes with a neighbor's existing target.")
            return False
        if (self.should_check_petal_boundaries
            and self._deny_request_because_out_of_bounds(
                posmodel, targt_poslocTP)):
            if self.verbose:
                self.printfunc(f'{posid}: target request denied. Target '
                               f'exceeds a fixed boundary.')
            return False
        new_request = {'start_posintTP': start_posintTP,
                       'targt_posintTP': targt_posintTP,
                       'posmodel': posmodel,
                       'posid': posid,
                       'command': uv_type,
                       'cmd_val1': u,
                       'cmd_val2': v,
                       'log_note': log_note}
        self.requests[posid] = new_request
        if self.stats:
            self.stats.add_requesting_time(time.clock() - timer_start)
            self.stats.add_request_accepted()
        return True

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
        if self.stats:
            timer_start = time.clock()
        if not self.requests and not self.stages['expert'].is_not_empty():
            if self.verbose:
                self.printfunc('No requests nor existing move tables found. No move scheduling performed.')
            return
        if self.stats:
            self.stats.set_scheduling_method(str(anticollision))
        if self.stages['expert'].is_not_empty():
            self._schedule_expert_tables(anticollision)
        else:
            self._fill_enabled_but_nonmoving_with_dummy_requests()
            if anticollision == 'adjust':
                self._schedule_requests_with_path_adjustments() # there is only one possible anticollision method for this scheduling method
            else:
                self._schedule_requests_with_no_path_adjustments(anticollision)
        if self.redundant_collision_checking:
            for name in self.stage_order:
                colliding_sweeps, all_sweeps = self.stages[name].find_collisions(self.stages[name].move_tables)
                self.printfunc('stage: ' + format(name.upper(),'>7s') + ', final check --> num colliding sweeps = ' + str(len(colliding_sweeps)) + ' (should always be zero)')
                if self.stats:
                    self.stats.add_redundant_collision_check(name,len(colliding_sweeps))
        for name in self.stage_order:
            if self.stages[name].is_not_empty() and self.verbose:
                self.printfunc('equalizing, comparing table for ' + name)
            self.stages[name].equalize_table_times()
            for posid,table in self.stages[name].move_tables.items():
                if posid in self.move_tables:
                    self.move_tables[posid].extend(table)
                else:
                    self.move_tables[posid] = table
                if self.verbose:
                    stage_sweep = self.stages[name].sweeps[posid] # quantized sweep after path adjustments
                    self._table_matches_quantized_sweep(table, stage_sweep) # prints a message if unmatched
        empties = {posid for posid,table in self.move_tables.items() if not table}
        motionless = {posid for posid,table in self.move_tables.items() if table.is_motionless}
        for posid in empties | motionless:
            del self.move_tables[posid]
        for posid,table in self.move_tables.items():                
            if posid in self.requests:
                req = self.requests.pop(posid)
                table.store_orig_command(0,req['command'],req['cmd_val1'],req['cmd_val2']) # keep the original commands with move tables
                log_note_addendum = req['log_note'] # keep the original log notes with move tables
                if self.stats:
                    if self._table_matches_original_request(table,req):
                        self.stats.add_table_matching_request()
            else:
                self.printfunc('Error: ' + str(posid) + ' has a move table despite no request.')
                table.display()
            table.log_note += (' ' if table.log_note else '') + log_note_addendum
        if self.petal.animator_on:
            for name in self.stage_order:
                stage = self.stages[name]
                if stage.is_not_empty():
                    self.collider.add_mobile_to_animator(self.petal.animator_total_time, stage.sweeps)
                    self.petal.animator_total_time += max({sweep.time[-1] for sweep in stage.sweeps.values()})
        if self.stats:
            self.stats.add_scheduling_time(time.clock() - timer_start)
            self.stats.set_num_move_tables(len(self.move_tables))
            net_times = {table.for_schedule()['net_time'][-1] for table in self.move_tables.values()}
            self.stats.set_max_table_time(max(net_times))
            stage_start_time = 0
            num_moving = {} # key is time, value is number of positioners moving at that time
            for name in self.stage_order:
                stage = self.stages[name]
                if stage.is_not_empty():
                    if stage.sweeps:
                        for sweep in stage.sweeps.values():
                            for i in range(len(sweep.time)):
                                this_time = sweep.time[i] + stage_start_time
                                if this_time not in num_moving:
                                    num_moving[this_time] = 0
                                if sweep.is_moving(i):
                                    num_moving[this_time] += 1
                        stage_start_time = max(num_moving.keys())
            self.stats.add_num_moving_data(num_moving)

    def _table_matches_quantized_sweep(self, move_table, sweep):
        """Takes as input a "for_schedule()" move table and a quantized sweep,
        and then cross-checks whether their total rotations (theta and phi)
        match. Returns a boolean.
        """
        tol = pc.schedule_checking_numeric_angular_tol
        table = move_table.for_schedule()
        end_tp_sweep = [sweep.theta(-1), sweep.phi(-1)]
        end_tp_table = [table['net_dT'][-1] + sweep.theta(0), table['net_dP'][-1] + sweep.phi(0)]
        endpos_diff = [end_tp_sweep[i] - end_tp_table[i] for i in range(2)]
        if abs(endpos_diff[0]) > tol or abs(endpos_diff[1]) > tol:
            self.printfunc(f'table and sweep not matched: {sweep.posid} end_tp: check={end_tp_sweep}, move={end_tp_table}')
            return False
        return True
    
    def _table_matches_original_request(self, move_table, request):
        """Input a move table and check whether the total motion matches request.
        Returns a boolean.
        """
        tol = pc.schedule_checking_numeric_angular_tol
        table = move_table.for_schedule()
        dtdp_request = [request['targt_posintTP'][i] - request['start_posintTP'][i] for i in range(2)]
        dtdp_table = [table['net_dT'][-1], table['net_dP'][-1]]
        diff = [dtdp_request[i] - dtdp_table[i] for i in range(2)]
        diff_abs = [abs(x) for x in diff]
        for i in range(len(diff_abs)):
            if diff_abs[i] > 180:
                diff_abs[i] -= 360
        if diff_abs[0] > tol or diff_abs[1] > tol:
            return False
        return True

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
        if self.stats:
            timer_start = time.clock()
        if self._deny_request_because_disabled(move_table.posmodel):
            if self.verbose:
                self.printfunc(str(move_table.posmodel.posid) + ': move table addition to schedule denied. Positioner is disabled.')
            return
        self.stages['expert'].add_table(move_table)
        if self.stats:
            self.stats.add_expert_table_time(time.clock() - timer_start)

    def _schedule_expert_tables(self, anticollision):
        """Gathers data from expert-added move tables and populates the 'expert'
        stage. Any move requests are ignored.
        """
        should_freeze = not(not(anticollision))
        self._direct_stage_conditioning(self.stages['expert'], self.anneal_time['expert'], should_freeze)

    def _schedule_requests_with_no_path_adjustments(self, anticollision):
        """Gathers data from requests dictionary and populates the 'direct'
        stage with direct motions from start to finish. The positioners are
        given no path adjustments to avoid each other.
        """
        start_posintTP = {}
        desired_final_posintTP = {}
        dtdp = {}
        for posid, request in self.requests.items():
            start_posintTP[posid] = request['start_posintTP']
            desired_final_posintTP[posid] = request['targt_posintTP']
            trans = self.petal.posmodels[posid].trans
            dtdp[posid] = trans.delta_posintTP(desired_final_posintTP[posid],
                                               start_posintTP[posid],
                                               range_wrap_limits='targetable')
        stage = self.stages['direct']
        stage.initialize_move_tables(start_posintTP, dtdp)
        # double-negative syntax is to be compatible with various
        # False/None/'' negative values
        should_freeze = not(not(anticollision))
        self._direct_stage_conditioning(
            stage, self.anneal_time['direct'], should_freeze)

    def _direct_stage_conditioning(self, stage, anneal_time, should_freeze):
        """Applies annealing and possibly freezing to a 'direct' or 'expert' stage.

            stage         ... instance of PosScheduleStage, needs to already have its move tables initialized
            anneal_time   ... time in seconds, for annealing
            should_freeze ... boolean, says whether to check for collisions and freeze
        """
        if self.should_anneal:
            stage.anneal_tables(anneal_time)
        if should_freeze or self.stats:
            if self.verbose:
                self.printfunc(f'schedule finding collisions: {len(stage.move_tables)}')
                self.printfunc('Posschedule first move table: \n' + str(list(stage.move_tables.values())[0].for_collider()))
            colliding_sweeps, all_sweeps = stage.find_collisions(stage.move_tables)
            stage.store_collision_finding_results(colliding_sweeps, all_sweeps)
        if should_freeze:
            if self.verbose:
                self.printfunc("initial stage.colliding: " + str(stage.colliding))
            adjustment_performed = False
            for posid in sorted(stage.colliding.copy()): # sort is for repeatability (since stage.colliding is an unordered set, and so path adjustments would otherwise get processed in variable order from run to run). the copy() call is redundant with sorted(), but left there for the sake of clarity, that need to be looping on a copy of *some* kind
                if posid in stage.colliding: # re-check, since earlier path adjustments in loop may have already resolved this posid's collision
                    newly_frozen = stage.adjust_path(posid, freezing='forced_recursive')
                    adjustment_performed = True
                    for p in newly_frozen:
                        self.petal.pos_flags[p] |= self.petal.frozen_anticol_bit # Mark as frozen by anticollision
                    if self.verbose:
                        self.printfunc("remaining stage.colliding " + str(stage.colliding))
            if self.stats and adjustment_performed:
                self.stats.add_to_num_adjustment_iters(1)

    def _schedule_requests_with_path_adjustments(self):
        """Gathers data from requests dictionary and populates the 'retract',
        'rotate', and 'extend' stages with motion paths from start to finish.
        The move tables may include adjustments of paths to avoid collisions.
        """
        start_posintTP = {name: {} for name in self.RRE_stage_order}
        desired_final_posintTP = {name: {} for name in self.RRE_stage_order}
        dtdp = {name: {} for name in self.RRE_stage_order}
        for posid, request in self.requests.items():
            # Some care is taken here to use only delta and add functions
            # provided by PosTransforms to ensure that range wrap limits are
            # always safely handled from stage to stage.
            posmodel = self.petal.posmodels[posid]
            trans = posmodel.trans
            start_posintTP['retract'][posid] = request['start_posintTP']
            starting_phi = start_posintTP['retract'][posid][pc.P]
            if starting_phi > self.collider.Eo_phi or request['start_posintTP'] == request['targt_posintTP']:
                retracted_phi = starting_phi
            else:
                retracted_phi = self.collider.Eo_phi # Ei would also be safe, but unnecessary in most cases. Costs more time and power to get to.
            desired_final_posintTP['retract'][posid] = [request['start_posintTP'][pc.T], retracted_phi]
            desired_final_posintTP['rotate'][posid] = [request['targt_posintTP'][pc.T], retracted_phi]
            desired_final_posintTP['extend'][posid] = request['targt_posintTP']
            def calc_dtdp(name, posid):
                tp_start = start_posintTP[name][posid]
                tp_final = desired_final_posintTP[name][posid]
                return trans.delta_posintTP(tp_final, tp_start, range_wrap_limits='targetable')
            def calc_next_tp(last_name, posid):
                last_tp = start_posintTP[last_name][posid]
                this_dtdp = dtdp[last_name][posid]
                return trans.addto_posintTP(last_tp, this_dtdp, range_wrap_limits='targetable')
            dtdp['retract'][posid] = calc_dtdp('retract',posid)
            start_posintTP['rotate'][posid] = calc_next_tp('retract',posid)
            dtdp['rotate'][posid] = calc_dtdp('rotate',posid)
            start_posintTP['extend'][posid] = calc_next_tp('rotate',posid)
            dtdp['extend'][posid] = calc_dtdp('extend',posid)
        for name in self.RRE_stage_order:
            stage = self.stages[name]
            stage.initialize_move_tables(start_posintTP[name], dtdp[name])
            if self.should_anneal:
                stage.anneal_tables(self.anneal_time[name])
            if self.verbose:
                self.printfunc(f'posschedule: finding collisions for {len(stage.move_tables)} positioners, trying {name}')
                self.printfunc('Posschedule first move table: \n' + str(list(stage.move_tables.values())[0].for_collider()))
            colliding_sweeps, all_sweeps = stage.find_collisions(stage.move_tables)
            stage.store_collision_finding_results(colliding_sweeps, all_sweeps)
            attempts_sequence = ['off','on','forced','forced_recursive'] # these are used as freezing arg to adjust_path()
            while stage.colliding and attempts_sequence:
                freezing = attempts_sequence.pop(0)
                for posid in sorted(stage.colliding.copy()): # sort is for repeatability (since stage.colliding is an unordered set, and so path adjustments would otherwise get processed in variable order from run to run). the copy() call is redundant with sorted(), but left there for the sake of clarity, that need to be looping on a copy of *some* kind
                    if posid in stage.colliding: # because it may have been resolved already when a *neighbor* got previously adjusted
                        newly_frozen = stage.adjust_path(posid, freezing)
                        for p in newly_frozen:
                            self.petal.pos_flags[p] |= self.petal.frozen_anticol_bit # Mark as frozen by anticollision
                            if name != self.RRE_stage_order[-1]: # i.e. some next stage exists
                                # must set next stage to begin from the newly-frozen position
                                frozen_table_data = stage.move_tables[p].for_schedule()
                                frozen_t = start_posintTP[name][p][pc.T] + frozen_table_data['net_dT'][-1]
                                frozen_p = start_posintTP[name][p][pc.P] + frozen_table_data['net_dP'][-1]
                                next_stage_idx = self.RRE_stage_order.index(name) + 1
                                next_name = self.RRE_stage_order[next_stage_idx]
                                start_posintTP[next_name][p] = [frozen_t,frozen_p]
                                dtdp[next_name][p] = calc_dtdp(next_name, p)
                if self.stats:
                    self.stats.add_to_num_adjustment_iters(1)
            if stage.colliding:
                self.printfunc('Error: During ' + name.upper() + ' stage of move scheduling (see PosSchedule.py), the positioners ' + str([posid for posid in stage.colliding]) + ' had collision(s) that were NOT resolved. This means there is a bug somewhere in the code that needs to be found and fixed. If this move is executed on hardware, these two positioners will collide!')
                self.printfunc('The move table(s) for these are:')
                for posid in stage.colliding:
                    for n in self.RRE_stage_order:
                        stage_str = str(posid) + ': ' + n.upper()
                        if posid in self.stages[n].move_tables:
                            self.printfunc(stage_str)
                            self.stages[n].move_tables[posid].display(self.printfunc)
                        elif n == name:
                            self.printfunc(stage_str + ' --> no move table found')
                if self.stats:
                    sorted_colliding = sorted(stage.colliding) # just for human ease of reading the values
                    colliding_tables = {posid:stage.move_tables[posid] for posid in sorted_colliding}
                    colliding_sweeps = {posid:stage.sweeps[posid] for posid in sorted_colliding}
                    self.stats.add_unresolved_colliding_at_stage(name, sorted_colliding, colliding_tables, colliding_sweeps)

    def _fill_enabled_but_nonmoving_with_dummy_requests(self):
        enabled = set(self.petal.all_enabled_posids())
        requested = set(self.requests.keys())
        enabled_but_not_requested = enabled - requested
        for posid in enabled_but_not_requested:
            posmodel = self.petal.posmodels[posid]
            current_posintTP = posmodel.expected_current_posintTP
            new_request = {'start_posintTP': current_posintTP,
                           'targt_posintTP': current_posintTP,
                           'posmodel': posmodel,
                           'posid': posid,
                           'command': '(autogenerated)',
                           'cmd_val1': 0,
                           'cmd_val2': 0,
                           'log_note': 'generated by path adjustment scheduler for enabled but untargeted positioner'}
            self.requests[posid] = new_request            

    def _deny_request_because_disabled(self, posmodel):
        """This is a special function specifically because there is a bit of care we need to
        consistently take with regard to post-move cleanup, if a request is going to be denied.
        """
        enabled = posmodel.is_enabled
        if enabled == False:  # this is specifically NOT worded as "if not enabled:", because here we actually do not want a value of None to pass the test, in case the parameter field 'CTRL_ENABLED' has not yet been implemented in the positioner's .conf file
            self.petal.pos_flags[posmodel.posid] |= self.petal.ctrl_disabled_bit
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            return True
        return False

    def _deny_request_because_target_interference(self, posmodel,
                                                  target_poslocTP):
        """Checks for case where a target request is definitively unreachable
        due to incompatibility with already-existing neighbor targets.
        """
        posid = posmodel.posid
        target_interference = False
        neighbors_with_requests = [
            neighbor for neighbor in self.collider.pos_neighbors[posid]
            if neighbor in self.requests]
        for neighbor in neighbors_with_requests:
            neighbor_posmodel = self.petal.posmodels[neighbor]
            neighbor_target_posintTP = \
                self.requests[neighbor]['targt_posintTP']
            neighbor_target_poslocTP = \
                neighbor_posmodel.trans.posintTP_to_poslocTP(
                    neighbor_target_posintTP)
            if self.collider.spatial_collision_between_positioners(
                    posid, neighbor, target_poslocTP,
                    neighbor_target_poslocTP):
                target_interference = True
                break
        if target_interference:
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            self.petal.pos_flags[posmodel.posid] |= self.petal.overlap_targ_bit
            return True
        return False

    def _deny_request_because_out_of_bounds(self, posmodel, target_poslocTP):
        """Checks for case where a target request is definitively unreachable
        due to being beyond a fixed petal or GFA boundary.
        """
        out_of_bounds = self.collider.spatial_collision_with_fixed(
            posmodel.posid, target_poslocTP)
        if out_of_bounds:
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            self.petal.pos_flags[posmodel.posid] |= \
                self.petal.restricted_targ_bit
            return True
        return False

    def _deny_request_because_limit(self, posmodel, target_posintTP):
        '''
        Check for cases where target exceeds radial limit set by experts.
        Useful to avoid needed to worry about anticollision.
        '''
        if self.petal.limit_radius:
            poslocXY = posmodel.trans.posintTP_to_poslocXY(target_posintTP)
            if math.sqrt(poslocXY[0]**2 + poslocXY[1]**2) > self.petal.limit_radius:
                posmodel.clear_postmove_cleanup_cmds_without_executing()
                self.petal.pos_flags[posmodel.posid] |= self.petal.exceeded_lims_bit
                return True
        return False
