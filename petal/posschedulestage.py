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
    def __init__(self, collider, power_supply_map={}, verbose=False):
        self.collider = collider # poscollider instance
        self.move_tables = {} # keys: posids, values: posmovetable instances
        self.sweeps = {} # keys: posids, values: instances of PosSweep, corresponding to entries in self.move_tables
        self.colliding = set() # positioners currently known to have collisions
        self.frozen = set()
        self.verbose = verbose
        self._power_supply_map = power_supply_map
        self._enabled = {posid for posid in self.collider.posids if self.collider.posmodels[posid].is_enabled}
        self._disabled = self.collider.posids.difference(self._enabled)
        self._start_posTP = {} # keys: posids, values: [theta,phi]
        self._final_posTP = {} # keys: posids, values: [theta,phi]
        self._true_dtdp = {} # keys: posids, values: [delta theta, delta phi]
        self._fixed_cases = {pc.case.PTL, pc.case.GFA} # collision case enumerations against fixed polygons
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
        self._start_posTP = start_posTP
        for posid in self._start_posTP:
            posmodel = self.collider.posmodels[posid]
            self._final_posTP[posid] = posmodel.trans.addto_posTP(self._start_posTP[posid], dtdp[posid], range_wrap_limits='targetable')
            self._true_dtdp[posid] = posmodel.trans.delta_posTP(self._final_posTP[posid], self.start_posTP[posid], range_wrap_limits='targetable')
            table = posmovetable.PosMoveTable(posmodel, self._start_posTP[posid])
            table.set_move(0, pc.T, self._true_dtdp[posid][0])
            table.set_move(0, pc.P, self._true_dtdp[posid][1])
            table.set_prepause(0, 0.0)
            table.set_postpause(0, 0.0)
            self.move_tables[posid] = table

    def is_not_empty(self):
        """Returns boolean whether the stage is empty of move_tables.
        """
        return len(self.move_tables) == 0
        
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
        postprocessed = {posid:self.move_table[posid].for_schedule for posid in self.move_tables}
        times = {posid:postprocessed[posid]['stats']['net_time'][-1] for posid in postprocessed}
        orig_max_time = max(times.values())
        new_max_time = anneal_time if anneal_time > orig_max_time else orig_max_time
        for posids in list(self._power_supply_map.values()):
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
        times = {}
        for posid,table in self.move_tables.items():
            postprocessed = table.for_schedule
            times[posid] = postprocessed['stats']['net_time'][-1]
        max_time = max(times.values())
        for posid,table in self.move_tables.items():
            equalizing_pause = max_time - times[posid]
            if equalizing_pause:
                idx = table.n_rows
                table.insert_new_row(idx)
                table.set_postpause(idx,equalizing_pause)

    def adjust_path(self, posid, force_freezing=False):
        """Adjusts move paths for posid to avoid collision.
        
        The timing of a neighbor's motion path may be adjusted as well by this
        function, but not the geometric path it follows.
        
        Adjustments to neighbor's timing only go one level deep of neighborliness.
        In other words, a neighbor's far neighbor (one that is not also neighbor
        of posid) will not be affected by this function.
        
        Normally, the path adjustment algorithm goes through a series of options,
        trying adding various pauses and pre-moves to avoid collision. If these
        all fail, then the fallback is to "freeze" posid. This means the positioner's
        path is simply halted prior to the collision, and no attempt is made for
        it to reach its supposed final target.
        
        The force_freezing boolean argument allows you to skip calculating the
        various adjustment options, and instead go straight to a forced freeze.
        """
        methods = ['freeze'] if force_freezing else ['pause','extend','retract','rot_ccw','rot_cw','freeze']
        for method in methods:
            proposed_tables = self._propose_path_adjustment(posid,method)
            colliding_sweeps, all_sweeps = self.find_collisions(proposed_tables, store_results=False)
            if not colliding_sweeps:
                self.move_tables.update(proposed_tables)
                self.sweeps.update(all_sweeps)
                for posid in all_sweeps:
                    self.colliding.remove(posid)
                    if method == 'freeze':
                        self.frozen.add(posid)
                return
        if self.verbose():
            print('Error: adjust_path() failed to prevent all collisions.')

    def find_collisions(self, move_tables, store_results=False):
        """Identifies any collisions that would be induced by executing a collection
        of move tables.
        
            move_tables   ... dict with keys = posids, values = PosMoveTable instances.
            
            store_results ... boolean, saying whether the results of this collision finding
                              should automatically be stored into the stage's persistent
                              data. (False is especially useful when making proposed changes
                              during anticollision algorithm, in case we're not sure yet
                              whether to keep the proposed change.)
        
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
        colliding_sweeps = {posid:set() for posid in move_tables}
        all_sweeps = {}
        for posid in move_tables:
            table_A = move_tables[posid]
            init_obsTP_A = table_A.posmodel.trans.posTP_to_obsTP(table_A.init_posTP)
            for neighbor in self.collider.pos_neighbors[posid]:
                if neighbor not in already_checked[posid]:
                    table_B = move_tables[neighbor] if neighbor in move_tables else posmovetable.PosMoveTable(self.collider.posmodels[neighbor]) # generation of fixed table if necessary, for a non-moving neighbor
                    init_obsTP_B = table_B.posmodel.trans.posTP_to_obsTP(table_B.init_posTP)
                    pospos_sweeps = self.collider.spacetime_collision_between_positioners(posid, init_obsTP_A, table_A, neighbor, init_obsTP_B, table_B)
                    all_sweeps.update({posid:pospos_sweeps[0], neighbor:pospos_sweeps[1]})
                    for sweep in pospos_sweeps:
                        if sweep.collision_case != pc.case.I:
                            colliding_sweeps[sweep.posid].add(sweep)
                    already_checked[posid].add(neighbor)
                    already_checked[neighbor].add(posid)
            for fixed_neighbor in self.collider.fixed_neighbor_cases[posid]:
                posfix_sweep = self.collider.spacetime_collision_with_fixed(posid, init_obsTP_A, table_A)[0] # index 0 to immediately retrieve from the one-element list this function returns
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
        colliding_sweeps = {posid:colliding_sweeps[posid].pop() for posid in colliding_sweeps} # remove set structure from elements
        all_sweeps.update(colliding_sweeps)
        if store_results:
            self.sweeps.update(all_sweeps)
            all_checked = {posid for posid in all_sweeps}
            now_colliding = {posid for posid in colliding_sweeps}
            now_not_colliding = all_checked.difference(now_colliding)
            self.colliding.add(now_colliding)
            self.colliding.difference(now_not_colliding)
        return colliding_sweeps, all_sweeps
   
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
        
        No new collision checking is performed by this method. So it is important 
        after receiving a new proposal, to re-check for collisions against all the
        neighbors of all the proposed new move tables.
        """
        no_collision = self.sweeps[posid].collision_case == pc.case.I
        fixed_collision = self.sweeps[posid].collision_case in {pc.case.PTL, pc.case.GFA}
        if no_collision or (method == 'pause' and fixed_collision):
            return {posid:self.move_tables[posid]} # unchanged move table
        table = self.move_tables[posid].copy()
        if method == 'freeze':    
            table_data = table.for_schedule
            for row_idx in reversed(range(table.n_rows)):
                if table_data['stats']['net_time'] >= self.sweep[posid].collision_time:
                    table.delete_row(row_idx)
                else:
                    break
            if table.n_rows == 0:
                table.set_move(0,0,0)
            return {posid:table}
        neighbor = self.sweeps[posid].collision_neighbor
        neighbor_table_data = self.move_tables[neighbor].for_schedule
        for neighbor_clearance_time in neighbor_table_data['stats']['net_time']:
            if neighbor_clearance_time > self.sweeps[posid].collision_time:
                break
        if method == 'pause':
            table.insert_new_row(0)
            table.set_prepause(0,neighbor_clearance_time)
            return {posid:table}
        else:
            posmodel = self.collider.posmodels[posid]
            if method in {'extend','retract'}:
                start = self._start_posTP[posid][1]
                speed = posmodel.abs_shaft_speed_cruise_P
                targetable_range = posmodel.targetable_range_P
                if method == 'retract':
                    limit = min(start + self._phi_max_jog, max(targetable_range), self.collider.Ei_phi)
                else:
                    limit = max(start - self._phi_max_jog, min(targetable_range))
                axis = pc.P
            else:
                start = self._start_posTP[posid][0]
                speed = posmodel.abs_shaft_speed_cruise_T
                targetable_range = posmodel.targetable_range_T
                if method == 'rot_ccw':
                    limit = min(start + self._theta_max_jog, max(targetable_range))
                else:
                    limit = max(start - self._theta_max_jog, min(targetable_range))
                axis = pc.T
            distance = limit - start
            move_time = abs(distance / speed)
            neighbor_table = self.move_tables[neighbor].copy()
            neighbor_table.insert_new_row(0)
            neighbor_table.set_prepause(0,move_time)
            table.insert_new_row(0)
            table.insert_new_row(0)
            table.set_move(0,axis,distance)
            table.set_postpause(0,neighbor_clearance_time)
            table.set_move(1,axis,-distance)
            return {posid:table, neighbor:neighbor_table}