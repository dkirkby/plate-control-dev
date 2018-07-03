import posconstants as pc
import posmovetable

class PosScheduleStage(object):
    """This class encapsulates the concept of a 'stage' of the fiber
    positioner motion. The typical usage would be either a direct stage from
    start to finish, or an intermediate stage, used for retraction, rotation,
    or extension.

        collider         ... instance of poscollider for this petal
        power_supply_map ... dict where key = power supply id, value = set of posids attached to that supply
    """
    def __init__(self, collider, power_supply_map={}):
        self.collider = collider # poscollider instance
        self.move_tables = {} # keys: posids, values: posmovetable instances
        self.sweeps = {} # keys: posids, values: instances of PosSweep, corresponding to entries in self.move_tables
        self.colliding = set() # positioners currently known to have collisions
        self._power_supply_map = power_supply_map
        self._theta_max_jog = 90 # deg, maximum distance to temporarily shift theta when doing path adjustments
        self._phi_max_jog = 60 # deg, maximum distance to temporarily shift phi when doing path adjustments
    
    def initialize_move_tables(self, start_posTP, dtdp):
        """Generates basic move tables for each positioner, starting at position
        start_tp and going to a position a distance dtdp away.
        
            start_posTP  ... dict of starting [theta,phi] positions, keys are posids
            dtdp         ... dict of [delta theta, delta phi] from the starting position. keys are posids
        
        The user should take care that dtdp vectors have been generated using the
        canonical delta_posTP function provided by PosTransforms module, with
        range_wrap_limits='targetable'. (The user should *not* generate dtdp by a
        simple vector subtraction or the like, since this would not correctly handle
        physical range limits of the fiber positioner.)
        """
        for posid in start_posTP:
            posmodel = self.collider.posmodels[posid]
            final_posTP = posmodel.trans.addto_posTP(start_posTP[posid], dtdp[posid], range_wrap_limits='targetable')
            true_dtdp = posmodel.trans.delta_posTP(final_posTP, start_posTP[posid], range_wrap_limits='targetable')
            table = posmovetable.PosMoveTable(posmodel, start_posTP[posid])
            table.set_move(0, pc.T, true_dtdp[0])
            table.set_move(0, pc.P, true_dtdp[1])
            table.set_prepause(0, 0.0)
            table.set_postpause(0, 0.0)
            self.move_tables[posid] = table

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
        
        If spread_time is less than the time it takes to execute the longest move
        table, then that longer execution time will be used instead of spread_time.
        """
        if anneal_time == None:
            return
        postprocessed = {posid:table.for_schedule() for posid,table in self.move_tables.items()}
        times = {posid:post['net_time'][-1] for posid,post in postprocessed.items()}
        orig_max_time = max(times.values())
        new_max_time = anneal_time if anneal_time > orig_max_time else orig_max_time
        supply_map = {supply:[p for p in posids if p in postprocessed] for supply,posids in self._power_supply_map.items()} # list type is intentional, so easy to check below for last element
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
                'forced' ... 
                
        With freezing == 'off' or 'on', the path adjustment algorithm goes through a
        series of options, trying adding various pauses and pre-moves to avoid collision.
        
        With freezing == 'on', then if all the adjustment options fail, the fallback
        is to "freeze" the positioner posid. This means its path is simply halted prior
        to the collision, and no attempt is made for it to reach its supposed final target.
        
        With freezing == 'forced', we skip calculating the various path adjustment options,
        and instead go straight to freezing the positioner before it collides.

        The timing of a neighbor's motion path may be adjusted as well by this
        function, but not the geometric path that the neighbor follows.
        
        Adjustments to neighbor's timing only go one level deep of neighborliness.
        In other words, a neighbor's neighbor will not be affected by this function.
        """
        if self.sweeps[posid].collision_case == pc.case.I:
            return
        methods = ['freeze'] if freezing == 'forced' else ['pause','extend','retract','rot_ccw','rot_cw']
        if freezing == 'on':
            methods.append('freeze')
        for method in methods:
            proposed_tables = self._propose_path_adjustment(posid,method)
            colliding_sweeps, all_sweeps = self.find_collisions(proposed_tables)
            if not(colliding_sweeps): # i.e., the proposed tables should be accepted
                self.move_tables.update(proposed_tables)
                self.store_collision_finding_results(colliding_sweeps, all_sweeps)
                if method == 'freeze':
                    self.sweeps[posid].register_as_frozen()
                return

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
            init_obsTP_A = table_A.posmodel.trans.posTP_to_obsTP(table_A.init_posTP)
            for neighbor in self.collider.pos_neighbors[posid]:
                if neighbor not in already_checked[posid]:
                    table_B = move_tables[neighbor] if neighbor in move_tables else posmovetable.PosMoveTable(self.collider.posmodels[neighbor]) # generation of fixed table if necessary, for a non-moving neighbor
                    init_obsTP_B = table_B.posmodel.trans.posTP_to_obsTP(table_B.init_posTP)
                    pospos_sweeps = self.collider.spacetime_collision_between_positioners(posid, init_obsTP_A, table_A.for_collider(), neighbor, init_obsTP_B, table_B.for_collider())
                    all_sweeps.update({posid:pospos_sweeps[0], neighbor:pospos_sweeps[1]})
                    for sweep in pospos_sweeps:
                        if sweep.collision_case != pc.case.I:
                            colliding_sweeps[sweep.posid].add(sweep)
                    already_checked[posid].add(neighbor)
                    already_checked[neighbor].add(posid)
            for fixed_neighbor in self.collider.fixed_neighbor_cases[posid]:
                posfix_sweep = self.collider.spacetime_collision_with_fixed(posid, init_obsTP_A, table_A.for_collider())[0] # index 0 to immediately retrieve from the one-element list this function returns
                all_sweeps.update({posid:posfix_sweep})
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
        self.colliding.union(now_colliding)
        self.colliding.difference(now_not_colliding)

    def _propose_path_adjustment(self, posid, method='freeze'):
        """Generates a proposed alternate move table for the positioner posid
        The alternate table is meant to attempt to avoid collision.
        
          posid  ... The positioner to propose a path adjustment for.
            
          method ... The type of adjustment to make. Valid selections are:
              
             'pause'   ... Pre-delay is added to the positioner's move table in this
                           stage, to wait for the neighbor to possibly move out of the way.
            
             'extend'  ... Positioner phi arm is first extended out, in an attempt to open
                           a clear path for neighbor.
             
             'retract' ... Positioner phi arm is first retracted in, in an attempt to open
                           a clear path for neighbor.
             
             'rot_ccw' ... Positioner theta axis is first rotated ccw, in an attempt to
                           open a clear path for neighbor.
             
             'rot_cw'  ... Positioner theta axis is first rotated cw, in an attempt to
                           open a clear path for neighbor.

             'freeze'  ... Positioner is halted prior to the collision, and no attempt
                           is made for its final target.
        
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
        fixed_collision = self.sweeps[posid].collision_case in {pc.case.PTL, pc.case.GFA}
        already_frozen = self.sweeps[posid].is_frozen()
        not_enabled = not(self.collider.posmodels[posid].is_enabled())
        if no_collision or (method == 'pause' and fixed_collision) or already_frozen or not_enabled:
            return {posid:self.move_tables[posid]} # unchanged move table
        table = self.move_tables[posid].copy()
        if method == 'freeze':    
            table_data = table.for_schedule()
            for row_idx in reversed(range(table.n_rows)):
                if table_data['net_time'][row_idx] >= self.sweep[posid].collision_time:
                    table.delete_row(row_idx)
                else:
                    break
            if table.n_rows == 0:
                table.set_move(0,0,0)
            return {posid:table}
        if not fixed_collision:
            neighbor = self.sweeps[posid].collision_neighbor
            neighbor_table_data = self.move_tables[neighbor].for_schedule
            for neighbor_clearance_time in neighbor_table_data['net_time']:
                if neighbor_clearance_time > self.sweeps[posid].collision_time:
                    break
        else:
            neighbor_clearance_time = 0
        if method == 'pause':
            table.insert_new_row(0)
            table.set_prepause(0,neighbor_clearance_time)
            return {posid:table}
        else:
            tables = {posid:table}
            posmodel = self.collider.posmodels[posid]
            if method in {'extend','retract'}:
                start = self.sweeps[posid].phi(0)
                speed = posmodel.abs_shaft_speed_cruise_P
                targetable_range = posmodel.targetable_range_P
                if method == 'retract':
                    limit = min(start + self._phi_max_jog, max(targetable_range), self.collider.Ei_phi) # deeper retraction than Eo, to give better chance of avoidance
                else:
                    limit = max(start - self._phi_max_jog, min(targetable_range))
                axis = pc.P
            else:
                start = self.sweeps[posid].theta(0)
                speed = posmodel.abs_shaft_speed_cruise_T
                targetable_range = posmodel.targetable_range_T
                if method == 'rot_ccw':
                    limit = min(start + self._theta_max_jog, max(targetable_range))
                else:
                    limit = max(start - self._theta_max_jog, min(targetable_range))
                axis = pc.T
            distance = limit - start
            move_time = abs(distance / speed)
            if not fixed_collision:
                if self.collider.posmodels[neighbor].is_enabled() and not self.sweeps[neighbor].is_frozen():
                    neighbor_table = self.move_tables[neighbor].copy()
                    neighbor_table.insert_new_row(0)
                    neighbor_table.set_prepause(0,move_time)
                    tables[neighbor] = neighbor_table
            table.insert_new_row(0)
            table.insert_new_row(0)
            table.set_move(0,axis,distance)
            table.set_postpause(0,neighbor_clearance_time)
            table.set_move(1,axis,-distance)
            return tables