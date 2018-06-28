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
        self.verbose = verbose
        self._sweeps = {} # keys: posids, values: instances of PosSweep, corresponding to entries in self.move_tables
        self._proposed_move_tables = {}
        self._proposed_sweeps = {}
        self._power_supply_map = power_supply_map
        self._enabled = {posid for posid in self.collider.posids if self.collider.posmodels[posid].is_enabled}
        self._disabled = self.collider.posids.difference(self._enabled)
        self._frozen = {}
        self._start_posTP = {} # keys: posids, values: [theta,phi]
        self._final_posTP = {} # keys: posids, values: [theta,phi]
        self._true_dtdp = {} # keys: posids, values: [delta theta, delta phi]
        self._fixed_cases = {pc.case.PTL, pc.case.GFA} # collision case enumerations against fixed polygons
    
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

    def anneal_power_density(self, anneal_time=None):
        """Adjusts move tables' internal timing, to reduce peak power consumption
        of the overall array.
        
            anneal_time  ... Time in seconds over which to spread out moves in this stage
                             to reduce overall power density consumed by the array. You
                             can also argue None if no annealing should be done.
        """
        if anneal_time == None:
            return
        table_data = {posid:self.move_table[posid].for_schedule() for posid in self.move_tables}
        orig_max_time = max({table['net_time'][-1] for table in table_data.values()})
        new_max_time = anneal_time if anneal_time > orig_max_time else orig_max_time
        for posids_set in self._power_supply_map.values():
            for posid,table in self.move_tables:
                pass
                # think about best way to scatter these
                # write down some math on paper, to get a clean algorithm
                # probably takes two passes
                #   1. calculate total power density vs time, and record contributions vs time for each positioner
                #   2. redistribute, positioner by positioner    

    def equalize_table_times(self):
        """Makes all move tables in the stage have an equal total time length,
        by adding in post-pauses wherever necessary.
        """
        move_times = {}
        for posid,table in self.move_tables.items():
            postprocessed = table.for_schedule
            move_times[posid] = postprocessed['stats']['net_time'][-1]
        max_move_time = max(move_times.values())
        for posid,table in self.move_tables.items():
            equalizing_pause = max_move_time - move_times[posid]
            if equalizing_pause:
                idx = table.n_rows
                table.insert_new_row(idx)
                table.set_postpause(idx,equalizing_pause)
            
    def propose_path_adjustment(self, posid, method='freeze'):
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
            
        No new collision checking is performed by this method. So it is important 
        after receiving a new proposal, to re-check the positioner against all its neighbors
        and see both whether the original collision was solved, and also whether the
        proposal induces any new collisions.
        """
        if self._sweeps[posid].collision_case == pc.case.I:
            if self.verbose:
                print('Warning: no need to propose path adjustment for positioner ' + str(posid) +', it has no collision.') 
            return
        table = self.move_tables[posid].copy()
        sweep = self._sweeps[posid].copy()
        table_data = table.for_schedule()
        if method == 'pause':
            pass
        elif method in {'extend','retract'}:
            pass
        elif method in {'rot_ccw','rot_cw'}:
            pass
        elif method == 'freeze':
            for row_idx in reversed(range(table.n_rows)):
                if table_data['stats']['net_time'] >= sweep.collision_time:
                    table.delete_row(row_idx)
                else:
                    break
            if table.n_rows == 0:
                table.set_move(0,0,0)
        else:
            if self.verbose:
                print('Warning: invalid path adjustment method \'' + str(method) + '\' requested for positioner ' + str(posid) + '.')
            return
            
            # old stuff here below
            if any(dtdp) or wait:
                table.insert_new_row(0)
            if any(dtdp):
                targetable_TP = self.collider.posmodels[posid].trans.shaft_ranges('targetable')
                new_pos = [self._start_posTP[i] + dtdp[i] for i in [0,1]] # intentionally not using a postransforms method, because here I do NOT want to allow wrap around
                for i in [0,1]:
                    range_max = max(targetable_TP[i])
                    range_min = min(targetable_TP[i])
                    if new_pos[i] < range_min:
                        dtdp[i] = range_min - self.start_posTP[i]
                    elif new_pos[i] > range_max:
                        dtdp[i] = range_max - self.start_posTP[i]
                table.set_move(0,0,dtdp[0])
                table.set_move(0,1,dtdp[1])
            if wait:
                wait = max(0,wait) # just make sure no negative wait being asked for
                table.set_postpause(0,wait)
        
        
        pass
        # be sure not to alter any disabled positioners
        # for each collision
            # if posA-to-posB, adjust posA and/or posB
            # if posA-to-fixed, adjust posA
            # recheck collisions with adjacent neighbors
                # if fixed, remove from collisions list
                # if not fixe move to bottom of collisions list and try tweaking next collision
                # if N tries have failed for this collision, and still no fix, revert to zeroth

    def keep_adjustments(self):
        """Keep the proposed move tables as the permanent new ones.
        """
        pass

    def find_collisions(self, move_tables):
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
        self._sweeps.update(setless_sweeps_dict) # this should not be here -- it should be at a higher level, depending on context, since sometimes you only have proposed sweeps
        return setless_sweeps_dict

    def check_tables_for_collisions_and_freeze(self, move_tables):
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
        colliding_sweeps = self.find_collisions(move_tables)
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
                    del move_tables[pos_to_freeze] # is this sufficient cleanup? self.move_tables? what about sweeps?
                else:
                    compensating_pause = original_total_move_time - table_data['stats']['net_time'][n_rows-1]
                    new_postpause = table_data['postpause'][n_rows-1] + compensating_pause
                    move_tables[pos_to_freeze].set_postpause(n_rows-1,new_postpause)
                these_frozen.add(pos_to_freeze)
                neighbors_of_frozen.add(self.collider.pos_neighbors[pos_to_freeze])
            tables_to_recheck = {posid:move_tables[posid] for posid in these_frozen.union(neighbors_of_frozen) if posid in move_tables}
            colliding_sweeps = self.find_collisions(tables_to_recheck) # double-check to ensure the freezing truncation hasn't caused a follow-on collision
            all_frozen.add(these_frozen)
            n_iter += 1
        if n_iter >= max_iter:
            print('Warning: could not sufficiently arrest colliding positioners, after ' + str(n_iter) + ' iterations of freezing!')
        return all_frozen, colliding_sweeps





##### OLD CODE, RETRIEVED FROM POSSCHEDULE.PY #######

    def _avoid_collisions_tweak(self,tables,collision_indices, collision_types,tpss,tpfs,step,maxtimes):
        '''Need function description.
        '''
        
        
        altered_pos=[]
        for collision_indices_this,collision_type_this in zip(collision_indices,collision_types):
            posA,posB=collision_indices_this[0],collision_indices_this[1]
            print('Collision ',posA,posB,collision_type_this)
            altered_pos,altered_posB=[],[]
            if posA != None:
                ########################
                # Tweaks begin
                ########################
                tables,altered_posA,solved = self._tweak_sequence(tables,tpss,posA)
            if posB != None and not solved:
                tables,altered_posB,solved = self._tweak_sequence(tables,tpss,posB)
            altered_pos_t=set(altered_posA)|set(altered_posB)
            altered_pos.append(altered_pos_t[i] for i in range(len(altered_pos_t)))


        return tables, altered_pos

    def _tweak_sequence(self,tables,tpss,posid):
        altered_pos=[]
        tps_check,tables_check={},{}
        neighbours_and_me=self.collider.pos_neighbors[posid]
        neighbours_and_me.append(posid)
        solved=False
        tables[posid].set_prepause(0, 1) # 1s prepause
        for j in neighbours_and_me:
            tps_check[j]=tpss[j]
            tables_check[j]=tables[j]
        collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
        if len(collision_types_try)==0 :
            print('* Solved by pausing '+posid+' 1s!')
            altered_pos.append(posid)
            solved=True
        else:
            tables[posid].set_prepause(0, 0) # restore

        if not solved:
            tables=self._tweak_move_theta(tables,posid,45.)
            for j in neighbours_and_me:
                tps_check[j]=tpss[j]
                tables_check[j]=tables[j]
            collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
            if len(collision_types_try)==0 :
                print('* Solved by moving '+posid+' theta 45 degree!')
                altered_pos.append(posid)
                solved=True
            else:
                tables = self._tweak_move_theta_restore(tables,posid)

        if not solved:
            tables=self._tweak_move_theta(tables,posid,-45.)
            for j in neighbours_and_me:
                tps_check[j]=tpss[j]
                tables_check[j]=tables[j]
            collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
            if len(collision_types_try)==0 :
                print('* Solved by moving '+posid+' theta -45 degree!')
                altered_pos.append(posid)
                solved=True
            else:
                tables = self._tweak_move_theta_restore(tables,posid)

        if not solved:
            tables=self._tweak_move_theta_wait_back(tables,posid,45,0.5)
            for j in neighbours_and_me:
                tps_check[j]=tpss[j]
                tables_check[j]=tables[j]
            collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
            if len(collision_types_try)==0 :
                print('* Solved by moving '+posid+' theta 45 degree and wait 0.5s!')
                altered_pos.append(posid)
                solved=True
            else:
                tables = self._tweak_move_theta_wait_back_restore(tables,posid)

        if not solved:
            tables=self._tweak_move_theta_wait_back(tables,posid,-45,0.5)
            for j in neighbours_and_me:
                tps_check[j]=tpss[j]
                tables_check[j]=tables[j]
            collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
            if len(collision_types_try)==0 :
                print('* Solved by moving '+posid+' theta -45 degree and wait 0.5s!')
                altered_pos.append(posid)
                solved=True
            else:
                tables = self._tweak_move_theta_wait_back_restore(tables,posid)

        #tables=self._tweak_freeze(tables,posid)

        return tables, altered_pos, solved

    def _tweak_add_prepause(self,tables,posid,time):
        table = tables[posid]
        table.set_prepause(0, time)
        tables[posid] = table
        return tables

    def _tweak_move_theta(self,tables,posid,dT):
        table = tables[posid]
        nrows=len(table.rows)
        table.insert_new_row(0)
        table.insert_new_row(nrows+1)
        nrows=len(table.rows)
        table.set_move(0, pc.T, dT)
        table.set_move(nrows-1,pc.T,-dT)
        tables[posid] = table
        return tables

    def _tweak_move_theta_restore(self,tables,posid):
        table = tables[posid]
        nrows=len(table.rows)
        table.delete_row(nrows-1)
        table.delete_row(0)
        tables[posid] = table
        return tables

    def _tweak_move_phi(self,tables,posid,dP):
        table = tables[posid]
        nrows=len(table.rows)
        table.insert_new_row(0)
        table.insert_new_row(nrows+1)
        nrows=len(table.rows)
        table.set_move(0, pc.P, dP)
        table.set_move(nrows-1,pc.P,-dP)
        tables[posid] = table
        return tables
    
    def _tweak_move_theta_wait_back(self,tables,posid,dT,time):
        table = tables[posid]
        table.insert_new_row(0)
        table.insert_new_row(0)
        table.set_move(0, pc.T, dT)
        table.set_postpause(0, time)
        table.set_move(1, pc.T, -dT)
        return tables

    def _tweak_move_theta_wait_back_restore(self,tables,posid):
        table = tables[posid]
        table.delete_row(0)
        table.delete_row(0)
        return tables
    
    def _tweak_freeze(self,tables,posid):
        table=tables[posid]
        nrows=len(table.rows)
        for i in range(nrows):
            table.set_move(i, pc.T, 0.)
            table.set_move(i, pc.P, 0.)
        return tables

    def _tweak_move_theta_phi(self,tables,posid,dT,dP):
        pass