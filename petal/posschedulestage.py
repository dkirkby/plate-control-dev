import posconstants as pc
import posmovetable

class PosScheduleStage(object):
    """This class encapsulates the concept of a 'stage' of the fiber
    positioner motion. The typical usage would be either a direct stage from
    start to finish, or an intermediate stage, used for retraction, rotation,
    or extension.

        collider     ... instance of poscollider for this petal
        anneal_time  ... Time in seconds over which to spread out moves in this stage
                         to reduce overall power density consumed by the array. You
                         can also argue None if no annealing should be done.
        power_supply_map ... dict where key = power supply id, value = set of posids attached to that supply
    """
    def __init__(self, collider, anneal_time=3, power_supply_map={}, verbose=False):
        self.collider = collider # poscollider instance
        self.anneal_time = anneal_time
        self.move_tables = {} # keys: posids, values: posmovetable instances
        self.sweeps = {} # keys: posids, values: possweep instances
        self._power_supply_map = power_supply_map
        self._disabled = {posid for posid in self.collider.posids if not self.collider.posmodels[posid].is_enabled}
        self._start_posTP = {} # keys: posids, values: [theta,phi]
        self._final_posTP = {} # keys: posids, values: [theta,phi]
        self._true_dtdp = {} # keys: posids, values: [delta theta, delta phi]
    
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

    def anneal_power_density(self):
        """Adjusts move tables' internal timing, to reduce peak power consumption
        of the overall array.
        """
        if self.anneal_time == None:
            return
        table_data = {posid:self.move_table[posid].for_schedule() for posid in self.move_tables}
        orig_max_time = max({table['net_time'][-1] for table in table_data.values()})
        new_max_time = self.anneal_time if self.anneal_time > orig_max_time else orig_max_time
        for posids in self.power_supply_map.values():
            for posid,table in self.move_tables:
                # think about best way to scatter these
                # probably takes two passes
                #   1. calculate total power density vs time, and record contributions vs time for each positioner
                #   2. redistribute, positioner by positioner    
            
    def adjust_paths(self, colliding_positioners, iteration):
        """Alters move tables to avoid collisions.
        """
        # be sure not to alter any disabled positioners






##### OLD CODE, RETRIEVED FROM POSSCHEDULE.PY #######

    def _avoid_collisions_tweak(self,tables,collision_indices, collision_types,tpss,tpfs,step,maxtimes):
        '''Need function description.
        '''
        
        # PSEUDO-CODE, discuss with Joe
        # for each collision
            # if posA-to-posB, adjust posA and/or posB
            # if posA-to-fixed, adjust posA
            # recheck collisions with adjacent neighbors
                # if fixed, remove from collisions list
                # if not fixe move to bottom of collisions list and try tweaking next collision
                # if N tries have failed for this collision, and still no fix, revert to zeroth
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