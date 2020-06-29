import posconstants as pc
import posmovetable
import math

class PosScheduleStage(object):
    """This class encapsulates the concept of a 'stage' of the fiber
    positioner motion. The typical usage would be either a direct stage from
    start to finish, or an intermediate stage, used for retraction, rotation,
    or extension.

        collider         ... instance of poscollider for this petal
        stats            ... instance of posschedstats for this petal
        power_supply_map ... dict where key = power supply id, value = set of posids attached to that supply
    """
    def __init__(self, collider, stats, power_supply_map={}, verbose=False, printfunc=None):
        self.collider = collider # poscollider instance
        self.move_tables = {} # keys: posids, values: posmovetable instances
        self.start_posintTP = {} # keys: posids, values: initial positions at start of stage
        self.sweeps = {} # keys: posids, values: instances of PosSweep, corresponding to entries in self.move_tables
        self.colliding = set() # positioners currently known to have collisions
        self.stats = stats
        self._power_supply_map = power_supply_map
        self._theta_max_jog_A = 50 # deg, maximum distance to temporarily shift theta when doing path adjustments
        self._theta_max_jog_B = 20
        self._phi_max_jog_A = 45 # deg, maximum distance to temporarily shift phi when doing path adjustments
        self._phi_max_jog_B = 90
        self._max_jog = self._assign_max_jog_values() # collection of all the max jog options above
        self.sweep_continuity_check_stepsize = 4.0 # deg, see PosSweep.check_continuity function
        self.verbose = verbose
        self.printfunc = printfunc

    def initialize_move_tables(self, start_posintTP, dtdp):
        """Generates basic move tables for each positioner, starting at position
        start_tp and going to a position a distance dtdp away.

            start_posintTP  ... dict of starting [theta,phi] positions, keys are posids
            dtdp            ... dict of [delta theta, delta phi] from the starting position. keys are posids

        The user should take care that dtdp vectors have been generated using the
        canonical delta_posintTP function provided by PosTransforms module, with
        range_wrap_limits='targetable'. (The user should *not* generate dtdp by a
        simple vector subtraction or the like, since this would not correctly handle
        physical range limits of the fiber positioner.)
        """
        for posid in start_posintTP:
            posmodel = self.collider.posmodels[posid]
            final_posintTP = posmodel.trans.addto_posintTP(start_posintTP[posid], dtdp[posid], range_wrap_limits='targetable')
            true_dtdp = posmodel.trans.delta_posintTP(final_posintTP, start_posintTP[posid], range_wrap_limits='targetable')
            table = posmovetable.PosMoveTable(posmodel, start_posintTP[posid])
            table.set_move(0, pc.T, true_dtdp[0])
            table.set_move(0, pc.P, true_dtdp[1])
            table.set_prepause(0, 0.0)
            table.set_postpause(0, 0.0)
            self.move_tables[posid] = table
        self.start_posintTP = start_posintTP.copy()

    def is_not_empty(self):
        """Returns boolean whether the stage is empty of move_tables.
        """
        return not(not(self.move_tables))

    def add_table(self, move_table):
        """Directly adds a move table to the stage. If a move table representing
        same positioner already exists, then that table is extended.
        """
        this_posid = move_table.posid
        if move_table.posid in self.move_tables:
            self.move_tables[this_posid].extend(move_table)
        else:
            self.move_tables[this_posid] = move_table

    def anneal_tables(self, anneal_time=None):
        """Adjusts move table timing, to attempt to reduce peak power consumption
        of the overall array.

            anneal_time  ... Time in seconds over which to spread out moves in this stage
                             to reduce overall power density consumed by the array. You
                             can also argue None if no spreading should be done.

        If anneal_time is less than the time it takes to execute the longest move
        table, then that longer execution time will be used instead of anneal_time.
        """
        if anneal_time == None:
            return
        postprocessed = {posid:table.for_schedule() for posid,table in self.move_tables.items()}
        times = {posid:post['net_time'][-1] for posid,post in postprocessed.items()}
        orig_max_time = max(times.values())
        new_max_time = anneal_time if anneal_time > orig_max_time else orig_max_time
        supply_map = {supply: [p for p in posids if p in postprocessed]  # list type is intentional, so easy to check below for last element
                      for supply, posids in self._power_supply_map.items()}
        for posids in supply_map.values():
            group = []
            group_time = 0
            for posid in posids:
                group.append(posid)
                group_time += times[posid]
                if group_time > new_max_time or posid == posids[-1]:
                    n = len(group)
                    nominal_spacing = new_max_time / (n + 1)
                    center = 0
                    for i in range(n):
                        p = group[i]
                        center += nominal_spacing
                        start = center - times[p]/2
                        if start < 0:
                            start = 0
                        finish = start + times[p]
                        if finish > new_max_time:
                            start = new_max_time - times[p]
                        self.move_tables[p].set_prepause(0,start)
                    group = []
                    group_time = 0

    def equalize_table_times(self):
        """Makes all move tables in the stage have an equal total time length,
        by adding in post-pauses wherever necessary.
        """
        if not self.move_tables:
            return
        times = {}
        for posid,table in self.move_tables.items():
            postprocessed = table.for_schedule()
            times[posid] = postprocessed['net_time'][-1]
        max_time = max(times.values())
        for posid,table in self.move_tables.items():
            equalizing_pause = max_time - times[posid]
            if equalizing_pause:
                idx = table.n_rows
                table.insert_new_row(idx)
                table.set_postpause(idx,equalizing_pause)
                if self.sweeps: # because no collision checking is performed if anticollsion=None
                    if posid in self.sweeps.keys():
                        self.sweeps[posid].extend(self.collider.timestep, max_time)
        if self.verbose:
            self.printfunc(f'posschedulestage: move time after annealing = {max_time}')
        return max_time

    def adjust_path(self, posid, freezing='on'):
        """Adjusts move paths for posid to avoid collision. If the positioner
        has no collision, then no adjustment is made.

            posid    ... positioner to adjust. This method assumes that this posid
                         already has a move_table associated with it in the stage,
                         that find_collsions() has already been run, and the results
                         saved via store_collision_finding_results().

            freezing ... string with the following settings for when the "freeze"
                         method of collision resolution shall be applied:

                'on'     ... freeze positioner if the path adjustment options all fail to resolve collisions
                'off'    ... don't freeze, even if the path adjustment options all fail to resolve collisions
                'forced' ... only freeze, and *must* do so
                'forced_recursive' ... like 'forced', then closes any follow-on neighbor collisions

        Return value is a set containing the posids of any robot(s) whose move
        tables were adjusted in the course of the function call.

        With freezing == 'off' or 'on', the path adjustment algorithm goes through a
        series of options, trying adding various pauses and pre-moves to avoid collision.

        With freezing == 'on', then if all the adjustment options fail, the fallback
        is to attempt to "freeze" the positioner posid. This means its path is simply halted
        prior to the collision, and no attempt is made for it to reach its supposed final
        target. This may still fail, for example in the case where two robots are simultaneously
        sweeping through each other (rather than one simply striking another). In this case, one
        must use freezing == 'forced' if you want to freeze this posid anyway.

        With freezing == 'forced', we skip calculating the various path adjustment options,
        and instead go straight to freezing the positioner before it collides.
        
        With freezing == 'forced_recursive', it is just like 'forced', plus at the end
        we look for any follow-on collisions among neighbors (due to a neighbor continuing to
        move, or a new side-effect collision). These will be recursively searched out and
        resolved by more forced freezing. This is intended as the final adjustment method,
        to definitively prevent any collisions including side-effects.
        
        The timing of a neighbor's motion path may be adjusted as well by this
        function, but not the geometric path that the neighbor follows.

        Adjustments to neighbor's timing only go one level deep of neighborliness.
        In other words, a neighbor's neighbor will not be affected by this function.
        """
        stats_enabled = self.stats.is_enabled()
        if self.sweeps[posid].collision_case == pc.case.I:
            return set()
        elif self.sweeps[posid].collision_case in pc.case.fixed_cases:
            methods = ['freeze'] if freezing != 'off' else []
        elif freezing in {'forced','forced_recursive'}:
            methods = ['freeze']
        elif freezing == 'off':
            methods = pc.nonfreeze_adjustment_methods
        else:
            methods = pc.all_adjustment_methods
        adjusted = set()
        for method in methods:
            collision_neighbor = self.sweeps[posid].collision_neighbor
            proposed_tables = self._propose_path_adjustment(posid,method)
            colliding_sweeps, all_sweeps = self.find_collisions(proposed_tables)
            should_accept = not(colliding_sweeps) or freezing in {'forced','forced_recursive'}
            should_accept &= any(proposed_tables) # nothing to accept if no proposed tables were generated
            if should_accept:
                self.move_tables.update(proposed_tables)
                adjusted.update(proposed_tables.keys())
                
                # search for any side effect new collisions
                proposed = set(proposed_tables.keys())
                could_have_changed = {posid, collision_neighbor}
                for p in proposed:
                    could_have_changed.update(self.collider.pos_neighbors[p])
                could_have_changed -= proposed # saves a little time -- no need to recheck these
                tables_to_recheck = {p:self.move_tables[p] for p in could_have_changed if p in self.move_tables}
                col_recheck, all_recheck = self.find_collisions(tables_to_recheck)
                col_to_store = {p:s for p,s in col_recheck.items() if p in tables_to_recheck.keys()}
                all_to_store = {p:s for p,s in all_recheck.items() if p in tables_to_recheck.keys()}
                col_to_store.update({p:s for p,s in colliding_sweeps.items() if p in proposed})
                all_to_store.update({p:s for p,s in all_sweeps.items() if p in proposed})
                
                # determine if collision was resolved (for statistics tracking)
                if stats_enabled:
                    old_collision_id = self._collision_id(posid,collision_neighbor)
                    if posid in col_to_store:
                        new_collision_id = self._collision_id(posid,col_to_store[posid].collision_neighbor)
                        collision_resolved = new_collision_id != old_collision_id
                    else:
                        collision_resolved = True
                    if collision_resolved:
                        self.stats.add_collisions_resolved(method, {old_collision_id})

                # store results
                old_colliding = self.colliding # note how sequence here emphasizes that this must occur before store_collision_finding_results(), which affects self.colliding. in a perfect world, I would re-factor functionally to remove the state-dependence [JHS]                
                self.store_collision_finding_results(col_to_store, all_to_store)
                if method == 'freeze':
                    self.sweeps[posid].register_as_frozen() # needs to occur after storing results above
                    adjusted.add(posid)
               
                # recursively-forced freezing
                if freezing == 'forced_recursive':
                    newly_colliding = set(col_to_store.keys()).difference(old_colliding)
                    remainder = newly_colliding
                    if collision_neighbor in self.colliding:
                        remainder.add(collision_neighbor)
                    if newly_colliding:
                        self.printfunc('Note: adjust_path(' + str(posid) + ', freezing=\'' + str(freezing) + '\') introduced new collisions for ' + str(newly_colliding))
                    for p in sorted(remainder): # sort is for repeatabiity (since 'remainder' is an unordered set, and so path adjustments would otherwise get processed in variable order from run to run)
                        freeze_is_possible = False # starting assumption for this pos
                        if p in self.move_tables: # does p have any move_table to be frozen?
                            if not self.move_tables[p].is_motionless: # does that table have any contents inside to be frozen?
                                freeze_is_possible = True
                        if freeze_is_possible: 
                            recursed_newly_frozen = self.adjust_path(p,freezing='forced_recursive') # recursively close out any side-effect new collisions
                            adjusted.update(recursed_newly_frozen) 
                        else:
                            self.printfunc(' --> no further freezing possible on ' + str(p) + ' --- already motionless')
                        verified = p not in self.colliding
                        self.printfunc(' --> recursive forced freeze attempted on ' + str(p) + '. Verified now non-collidng? ' + str(verified))
                break # note indentation level of this return statement is essential. it breaks out of the methods for loop. do not remove again!
        return adjusted

    def find_collisions(self, move_tables):
        """Identifies any collisions that would be induced by executing a collection
        of move tables.

            move_tables   ... dict with keys = posids, values = PosMoveTable instances.

        Two items are returned. They are both dicts with keys = posids, values = PosSweep
        instances (see poscollider.py).

          1st dict: Only contains sweeps for positioners that collide. It will be
                    empty if there are no collisions. These sweeps may indicate
                    collision with another positioner or with a fixed boundary. This
                    information is given internally within each sweep instance.

          2nd dict: Contains all sweeps that were generated during this function call.

        For any pair of positioners that collide, the returned collisions dict will contain
        separate sweeps for each of the pair. These two sweeps are giving you information
        about the same collision event, but from the perspectives of the two different
        positioners. In other words, if there is an entry for posid 'M00001', colliding with
        neighbor 'M00002', then the dict will also contain an entry for posid 'M00002',
        colliding with neighbor 'M0001'.

        If positioner A collides with a fixed boundary, or with a disabled neighbor
        positioner B, then the returned collisions dict only contains the sweep of A.

        If a positioner has collisions with multiple other postioners / fixed boundaries,
        then only the first collision event in time is included in the returned collisions
        dict.

        In the rare event of a three-way exactly simultaneous collision between three
        moving positioners, then all three of those positioners' sweeps would still
        appear in the return dictionary.
        """
        already_checked = {posid:set() for posid in self.collider.posids}
        colliding_sweeps = {posid:set() for posid in self.collider.posids}
        all_sweeps = {}
        for posid in move_tables:
            table_A = move_tables[posid]
            for neighbor in self.collider.pos_neighbors[posid]:
                if neighbor not in already_checked[posid]:
                    table_B = move_tables[neighbor] if neighbor in move_tables else self._get_or_generate_table(neighbor)
                    pospos_sweeps = self.collider.spacetime_collision_between_positioners(posid, table_A.init_poslocTP, table_A.for_collider(), neighbor, table_B.init_poslocTP, table_B.for_collider())
                    all_sweeps.update({posid:pospos_sweeps[0], neighbor:pospos_sweeps[1]})
                    for sweep in pospos_sweeps:
                        if sweep.collision_case != pc.case.I:
                            colliding_sweeps[sweep.posid].add(sweep)
                    already_checked[posid].add(neighbor)
                    already_checked[neighbor].add(posid)
            for fixed_neighbor in self.collider.fixed_neighbor_cases[posid]:
                posfix_sweep = self.collider.spacetime_collision_with_fixed(posid, table_A.init_poslocTP, table_A.for_collider())[0] # index 0 to immediately retrieve from the one-element list this function returns
                all_sweeps.update({posid:posfix_sweep}) # don't worry --- if pospos colliding sweep takes precedence, this will be appropriately replaced again below
                if posfix_sweep.collision_case != pc.case.I:
                    colliding_sweeps[posid].add(posfix_sweep)
        multiple_collisions = {posid for posid in colliding_sweeps if len(colliding_sweeps[posid]) > 1}
        for posid in multiple_collisions:
            first_collision_time = math.inf
            for sweep in colliding_sweeps[posid]:
                if sweep.collision_time < first_collision_time:
                    first_sweep = sweep
                    first_collision_time = sweep.collision_time
            colliding_sweeps[posid] = {first_sweep}
        colliding_sweeps = {posid:colliding_sweeps[posid].pop() for posid in colliding_sweeps if colliding_sweeps[posid]} # remove set structure from elements, and remove empty elements
        all_sweeps.update(colliding_sweeps)
        return colliding_sweeps, all_sweeps

    def store_collision_finding_results(self, colliding_sweeps, all_sweeps):
        """Stores sweep data as-generated by find_collisions method.
        """
        self.sweeps.update(all_sweeps)
        all_checked = {posid for posid in all_sweeps}
        now_colliding = {posid for posid in colliding_sweeps}
        now_not_colliding = all_checked.difference(now_colliding)
        self.colliding = self.colliding.union(now_colliding)
        self.colliding = self.colliding.difference(now_not_colliding)
        # check for special case of lingering incorrect colliding status (no move table therefore wasn't registered as resolved)
        no_table_but_in_colliding = {posid for posid in self.colliding if posid not in self.move_tables}
        for posid in no_table_but_in_colliding:
            n = self.sweeps[posid].collision_neighbor
            if n and self.sweeps[n].collision_neighbor != posid: # i.e., neighbor thinks this collision has been resolved
                self.sweeps[posid].clear_collision()
                self.colliding.remove(posid)
                if posid in colliding_sweeps:
                    colliding_sweeps.pop(posid)
        if self.stats.is_enabled():
            found = {self._collision_id(posid, sweep.collision_neighbor) for posid, sweep in colliding_sweeps.items()}
            self.stats.add_collisions_found(found)
            
    def sweeps_continuity_check(self):
        """Returns set of posids for any whose sweeps were found to be discontinous.
        """
        discontinuous = {}
        for p,s in self.sweeps.items():
            if not s.check_continuity(self.sweep_continuity_check_stepsize, self.collider.posmodels[p]):
                discontinuous.add(p)
        return discontinuous

    def _propose_path_adjustment(self, posid, method='freeze'):
        """Generates a proposed alternate move table for the positioner posid
        The alternate table is meant to attempt to avoid collision.

          posid  ... The positioner to propose a path adjustment for.

          method ... The type of adjustment to make. Valid selections are:

             'pause'     ... Pre-delay is added to the positioner's move table in this
                             stage, to wait for the neighbor to possibly move out of the way.

             'extend_X'    ... Positioner phi arm is first extended out, in an attempt to open
                               a clear path for neighbor.

             'retract_X'   ... Positioner phi arm is first retracted in, in an attempt to open
                               a clear path for neighbor.

             'rot_ccw_X'   ... Positioner theta axis is first rotated ccw, in an attempt to
                               open a clear path for neighbor.

             'rot_cw_X'    ... Positioner theta axis is first rotated cw, in an attempt to
                               open a clear path for neighbor.

             'repel_ccw_X' ... Positioner theta axis is first rotated ccw, while simultaneously
                               the neighbor axis is rotated the opposite direction (cw).

             'repel_cw_X'  ... Positioner theta axis is first rotated cw, while simultaneously
                               the neighbor axis is rotated the opposite direction (ccw).

             'freeze'      ... Positioner is halted prior to the collision, and no attempt
                               is made for its final target.

        The subscript 'X' in many of the adjustment methods above refers to the
        size of the maximum distance jog step to attempt, labeled 'A', 'B', etc.

        The return value is a dict of proposed new move tables. Key = posid, value =
        new move table. If no change is proposed, the dict is empty. If the proposal
        includes changing both the argued positioner and its neighbor, than they will
        both have tables in the dict.

        No positioner or neighbor will be changed if it is disabled, or if it has
        already been "frozen".

        No new collision checking is performed by this method. So it is important
        after receiving a new proposal, to re-check for collisions against all the
        neighbors of all the proposed new move tables.
        """
        no_collision = self.sweeps[posid].collision_case == pc.case.I
        fixed_collision = self.sweeps[posid].collision_case in pc.case.fixed_cases
        already_frozen = self.sweeps[posid].is_frozen
        not_enabled = not(self.collider.posmodels[posid].is_enabled)
        unmoving_neighbor = self.sweeps[posid].collision_neighbor not in self.move_tables
        if no_collision or (fixed_collision and method != 'freeze') or already_frozen or not_enabled or (unmoving_neighbor and method != 'freeze'):
            return {}
        
        # table that will be adjusted
        tables = {posid: self._get_or_generate_table(posid,should_copy=True)}
        tables_data = {}
        if method == 'freeze' or 'repel' in method:
            tables_data[posid] = tables[posid].for_schedule()
        
        # freeze method
        if method == 'freeze':
            for row_idx in reversed(range(tables[posid].n_rows)):
                net_time = tables_data[posid]['net_time'][row_idx]
                collision_time = self.sweeps[posid].collision_time
                if math.fmod(net_time, self.collider.timestep): # i.e., if not exactly matching a quantized timestep (almost always the case)
                    collision_time -= self.collider.timestep # handles coarseness of discrete time by treating the collision time as one timestep earlier in the sweep
                if net_time >= collision_time:
                    if self.verbose:
                        self.printfunc("net time, collision_time " + str(net_time) + ' ' + str(collision_time))
                    tables[posid].delete_row(row_idx)
                else:
                    break
            if tables[posid].n_rows == 0:
                tables[posid].set_move(0,0,0)
            return tables
        
        # get neighbor table
        neighbor = self.sweeps[posid].collision_neighbor
        posmodels = {posid:self.collider.posmodels[posid], neighbor:self.collider.posmodels[neighbor]}
        neighbor_can_move = posmodels[neighbor].is_enabled and not self.sweeps[neighbor].is_frozen
        if neighbor_can_move:
            tables[neighbor] = self._get_or_generate_table(neighbor,should_copy=True)
            tables_data[neighbor] = tables[neighbor].for_schedule()
            for neighbor_clearance_time in tables_data[neighbor]['net_time']:
                if neighbor_clearance_time > self.sweeps[posid].collision_time:
                    break
            neighbor_clearance_time += pc.num_timesteps_clearance_margin * self.collider.timestep
        elif method == 'pause':
            return {} # no point in pausing if neighbor never moves
            
        # pause method
        if method == 'pause':
            tables[posid].insert_new_row(0)
            tables[posid].set_prepause(0,neighbor_clearance_time)
            return {posid:tables[posid]} # exclude neighbor here, since nothing being done to it
        
        # retract, rot, extend, repel methods: calculate jog distances
        max_abs_jog = abs(self._max_jog[method])
        jogs = {} # will hold distance(s) to move away from target and then back toward target
        jog_times = {} # will hold corresponding move time for each jog
        if 'extend' in method or 'retract' in method:
            axis = pc.P
            limits = posmodels[posid].targetable_range_P
            if 'retract' in method:
                limits[1] = min(limits[1], self.collider.Ei_phi) # note deeper retraction than Eo, to give better chance of avoidance
                direction = +1
            else:
                direction = -1
            jogs[posid] = self._range_limited_jog(nominal=max_abs_jog, direction=direction, start=tables[posid].init_posintTP[1], limits=limits)
        elif 'rot' in method:
            axis = pc.T
            direction = +1 if 'ccw' in method else -1
            jogs[posid] = self._range_limited_jog(nominal=max_abs_jog, direction=direction, start=tables[posid].init_posintTP[0], limits=posmodels[posid].targetable_range_T)
        elif 'repel' in method:
            axis = pc.T
            for p,t in tables.items():
                start = t.init_posintTP[0]
                limits = posmodels[p].targetable_range_T
                direction = 1 if p == posid else -1 # neighbor repels from primary
                if 'cw' in method:
                    direction *= -1
                if direction > 0:
                    furthest_existing_excursion = max(tables_data[p]['net_dT'] + [0]) # zero element prevents accidentally adding margin (if all net_dT < 0) that temporally might not exist when you hoped it would
                    limits[1] -= furthest_existing_excursion
                else:
                    furthest_existing_excursion = min(tables_data[p]['net_dT'] + [0]) # zero element prevents accidentally adding margin (if all net_dT > 0) that temporally might not exist when you hoped it would
                    limits[0] -= furthest_existing_excursion # minus sign here is correct, since furthest_existing_excursion <= 0
                jogs[p] = self._range_limited_jog(nominal=max_abs_jog, direction=direction, start=start, limits=limits)
        else:
            self.printfunc('Error: unknown path adjustment method \'' + str(method) + '\'')
            return {}
        for p in jogs:
            jog_times[p] = posmodels[p].true_move(axisid=axis, distance=jogs[p], allow_cruise=True, limits=None, init_posintTP=None)['move_time']     
        
        # apply jogs and associated pauses to tables
        if 'repel' in method:
            if neighbor in tables:
                jog_times_diff = jog_times[neighbor] - jog_times[posid]
                wait_for_neighbor_to_jog = max(jog_times_diff,0)
                wait_for_posid_to_jog = max(-jog_times_diff,0)
            for p,t in tables.items():
                t.insert_new_row(0)
                t.set_move(0, axis, jogs[p])
                if p == posid:
                    t.set_postpause(0,wait_for_neighbor_to_jog + neighbor_clearance_time)
                else:
                    t.set_postpause(0,wait_for_posid_to_jog)
                t.set_move(t.n_rows, axis, -jogs[p]) # note how this is happening in a new final row
        else:
            tables[posid].insert_new_row(0)
            tables[posid].insert_new_row(0)
            tables[posid].set_move(0,axis,jogs[posid])
            tables[posid].set_postpause(0,neighbor_clearance_time)
            tables[posid].set_move(1,axis,-jogs[posid])
            if neighbor in tables:
                tables[neighbor].insert_new_row(0)
                tables[neighbor].set_prepause(0,jog_times[posid])   
        return tables
    
    @staticmethod
    def _range_limited_jog(nominal, direction, start, limits):
        """Returns a range-limited jog distance.
            nominal   ... nominal jog distance, prior to applying range limits
            direction ... +1 means counter-clockwise, -1 means clockwise
            start     ... starting angle position
            limits    ... 2-element list or tuple stating max and min accessible angles
        """
        if direction >= 0:
            limited = min(start + nominal, max(limits))
        else:
            limited = max(start - nominal, min(limits))
        return limited - start

    def _get_or_generate_table(self, posid, should_copy=False):
        """Fetches move table for posid from self.move_tables. If no such table
        exists, generates a new one. The should_copy flag allows you to request
        that the returned table be a duplicate of the original table (not a pointer
        to it.)
        """
        if posid in self.move_tables:
            table = self.move_tables[posid]
            if should_copy:
                table = table.copy()
        else:
            start = self.start_posintTP[posid] if posid in self.start_posintTP else None
            table = posmovetable.PosMoveTable(self.collider.posmodels[posid], start)
            table.insert_new_row(0)
        return table

    def _assign_max_jog_values(self):
        """Makes convenience dict containing theta and phi max jog values for
        all adjustment methods.
        """
        max_jogs = {}
        for method in pc.nonfreeze_adjustment_methods:
            if '_A' in method:
                if 'extend' in method or 'retract' in method:
                    max_jogs[method] = self._phi_max_jog_A
                else:
                    max_jogs[method] = self._theta_max_jog_A
            else:
                if 'extend' in method or 'retract' in method:
                    max_jogs[method] = self._phi_max_jog_B
                else:
                    max_jogs[method] = self._theta_max_jog_B
        return max_jogs

    @staticmethod
    def _collision_id(A,B):
        """Returns an id string combining string A and string B. The returned
        string will be the same regardless of whether A or B is argued first.
        """
        s = sorted({str(A),str(B)})
        return s[0] + '-' + s[1]