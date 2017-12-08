# -*- coding: utf-8 -*-
"""
Created on Wed Nov 16 12:44:40 2016

@author: kremin
"""

import numpy as np
import pdb
#import copy as copymodule
#import poscollider
#import posmovetable
#import posconstants as pc
#import matplotlib.pyplot as plt
#from posmodel import PosModel
#import posanticollision as apcoll
from posmodel import PosModel
import posconstants as pc

class anticolConsts:
    def _init_(self):
        pmod = PosModel()
        self.dt = self.angstep/pmod.axis[0].motor_to_shaft(pmod._motor_speed_cruise)
        del pmod
        self.phisafe = 144.
        self.tolerance = 2.
        self.angstep = 6#12.
        # em potential computation coefficients
        self.coeffcr = 1.0
        self.coeffca = 0.#100.0
        self.coeffn =  980.0
        self.coeffa = 1000.0
        self.rtol = 2*1.58
        
    def _check_for_collisions(self,tps,cur_poscollider,list_tables):
        # Store indices of colliding positioners
        #new_poscollider = poscollider.PosCollider()
        #new_poscollider.add_positioners(cur_poscollider.posmodels)
        # Loop over all possible collisions
        posmodel_index_iterable = range(len(cur_poscollider.posmodels))
        sweeps = [[] for i in posmodel_index_iterable]
        collision_index = [[] for i in posmodel_index_iterable]
        collision_type = [pc.case.I for i in posmodel_index_iterable]
        collision_step = [np.inf for i in posmodel_index_iterable]
        earliest_collision = [np.inf for i in posmodel_index_iterable]
        nontriv = 0
        for k in range(len(cur_poscollider.collidable_relations['A'])):
            A = cur_poscollider.collidable_relations['A'][k]
            B = cur_poscollider.collidable_relations['B'][k]
            tableA = list_tables[A].for_schedule
            obsTPA = tps[A]
            B_is_fixed = cur_poscollider.collidable_relations['B_is_fixed'][k]
            if B_is_fixed and A in range(len(list_tables)): # might want to replace 2nd test here with one where we look in tables for a specific positioner index
                these_sweeps = cur_poscollider.spacetime_collision_with_fixed(A, obsTPA, tableA)
            elif A in range(len(list_tables)) and B in range(len(list_tables)): # again, might want to look for specific indexes identifying which tables go with which positioners
                tableB = list_tables[B].for_schedule
                obsTPB = tps[B]    
                these_sweeps = cur_poscollider.spacetime_collision_between_positioners(A, obsTPA, tableA, B, obsTPB, tableB)
    
            if these_sweeps[0].collision_time <= earliest_collision[A]:
                nontriv += 1
                sweeps[A] = these_sweeps[0]
                earliest_collision[A] = these_sweeps[0].collision_time
                if B_is_fixed:
                    collision_index[A] = [A,None]
                else:
                    collision_index[A] = [A,B]
                collision_type[A] = these_sweeps[0].collision_case
                if these_sweeps[0].collision_time < np.inf:
                    collision_step[A] = self._get_index_of_collision(list_tables[A].for_schedule,these_sweeps[0].collision_time)
                    earliest_collision[A] = these_sweeps[0].collision_time
            for i in range(1,len(these_sweeps)):
                if these_sweeps[i].collision_time < earliest_collision[B]:
                    nontriv += 1
                    sweeps[B] = these_sweeps[i]
                    earliest_collision[B] = these_sweeps[i].collision_time
                    if B_is_fixed:
                        collision_index[B] = [A,None]
                    else:
                        collision_index[B] = [A,B]
                    collision_type[B] = these_sweeps[i].collision_case
                    collision_step[B] = self._get_index_of_collision(list_tables[B].for_schedule,these_sweeps[i].collision_time)
    
        collision_indices, collision_types, collision_steps = \
                    np.asarray(collision_index), np.asarray(collision_type), np.asarray(collision_step)
        collision_indices = collision_indices[collision_types != pc.case.I]
        collision_steps = collision_steps[collision_types != pc.case.I]
        collision_types = collision_types[collision_types != pc.case.I]
        
        collision_mask = np.ones(len(collision_indices)).astype(bool)
        for i in range(len(collision_indices)):
            for j in np.arange(i+1,len(collision_indices)):
                if collision_mask[i]:
                    if np.all(collision_indices[i] == collision_indices[j]):
                        collision_mask[j]=False
                    elif np.all(collision_indices[i] == list(reversed(collision_indices[j]))):
                        collision_mask[j]=False
    
        collision_indices = collision_indices[collision_mask]
        collision_types = collision_types[collision_mask]
        collision_steps = collision_steps[collision_mask]
        
        # return the earliest collision time and collision indices
        return collision_indices, collision_types, collision_steps
    
        
    
        
    
    def _get_index_of_collision(self,positioner_table, collision_time):
        upper_time_bounds = np.asarray(positioner_table['stats']['net_time'])
        lower_time_bounds = np.append([0.],upper_time_bounds[:-1])
        total_time = upper_time_bounds[-1]
        if collision_time == np.inf:
            print("Collision time infinite. Returing ind = None")
            return None
        elif collision_time > total_time:
            print("Collision time was later than the total move time for the position. Returnding ind = None")
            return None        
        else: 
            ind = None
            for i in range(positioner_table['nrows']):
                if upper_time_bounds[i] >= collision_time and lower_time_bounds[i] <= collision_time:
                    ind = i
            if ind == None:
                intervene("Inside get index of collision. Found ind was none?")
            return ind


    def _printindices(self,statement,step,indices):
        unique = self._unique_inds(indices)
        print(statement,step,'   at indices:    ',unique)
        
        
    def _unique_inds(self,indices):
        raveled = []    
        for val in np.ravel(indices):
            for va in np.ravel(val):
                if va != None:
                    raveled.append(va)
        return np.unique(np.asarray(raveled))






            
apc = anticolConsts()


def cos(x):
    return np.cos(np.deg2rad(x))
    
    
    
def sin(x):
    return np.sin(np.deg2rad(x))
    
    
def rhoxyto(r12,xt,yt,xo,yo):
    xdiff = xt - xo 
    ydiff = yt - yo
    return np.sqrt(xdiff*xdiff + ydiff*ydiff)
    

def intervene(string=''):
    if apc.dosomethingdebug:
        print(string)
        pdb.set_trace()
    else:
        print('Entered intervene. ',string, '  Continueing on')


    
def run_animation(tables, collider, tpss):
    sweeps = [[] for i in range(len(collider.posmodels))]
    earliest_collision = [np.inf for i in range(len(collider.posmodels))]
    for k in range(len(collider.collidable_relations['A'])):
        A = collider.collidable_relations['A'][k]
        B = collider.collidable_relations['B'][k]
        tableA = tables[A].for_schedule
        obsTPA = tpss[A]
        B_is_fixed = collider.collidable_relations['B_is_fixed'][k]
        if B_is_fixed and A in range(len(tables)): # might want to replace 2nd test here with one where we look in tables for a specific positioner index
            these_sweeps = collider.spacetime_collision_with_fixed(A, obsTPA, tableA)
        elif A in range(len(tables)) and B in range(len(tables)): # again, might want to look for specific indexes identifying which tables go with which positioners
            tableB = tables[B].for_schedule
            obsTPB = tpss[B]    
            these_sweeps = collider.spacetime_collision_between_positioners(A, obsTPA, tableA, B, obsTPB, tableB)
        for i in range(len(these_sweeps)):
            AorB = A if i == 0 else B
            if these_sweeps[i].collision_time <= earliest_collision[AorB]:
                sweeps[AorB] = these_sweeps[i]
                earliest_collision[AorB] = these_sweeps[i].collision_time

    collider.animate(sweeps)        
    collision_indices, collision_types, collision_steps = apc._check_for_collisions(tpss,collider,tables)
    apc._printindices('Collisions after that animation ','',collision_indices)
    
  

    
    
    
def check_for_collisions_deprecated(tps,cur_poscollider,list_tables):
    # Use pre-made collision detection tools in poscollider class
    earliest_collision = np.ones(len(cur_poscollider.posmodels))*np.inf
    # Store indices of colliding positioners
    collision_index = []
    collision_type = []
    collision_step = []
    # Loop over all possible collisions
    for k in range(len(cur_poscollider.collidable_relations['A'])):
        # Get indices of current potential collision
        A = cur_poscollider.collidable_relations['A'][k]
        B = cur_poscollider.collidable_relations['B'][k]

        # Get the movetables for each of the positioners
        tableA = list_tables[A].for_schedule

        B_is_fixed = cur_poscollider.collidable_relations['B_is_fixed'][k]
        # might want to replace 2nd test here with one where we look in tables 
        # for a specific positioner index
        if B_is_fixed: 
            these_sweeps = cur_poscollider.spacetime_collision_with_fixed(A, tps[A], tableA)
        # again, might want to look for specific indexes identifying which tables \
        # go with which positioners
        else: 
            tableB = list_tables[B].for_schedule
            these_sweeps = cur_poscollider.spacetime_collision_between_positioners(A, tps[A], tableA, B, tps[B], tableB)
        # Find the earliest collision if multiple are found
        if len(these_sweeps)>0 and these_sweeps[0].collision_time < earliest_collision[A]:
            earliest_collision[A] = these_sweeps[0].collision_time
            collision_step.append(apc._get_index_of_collision(list_tables[A].for_schedule, these_sweeps[0].collision_time))
            collision_index.append([A,B])
            collision_type.append(these_sweeps[0].collision_case)
        min_sweep = min(these_sweeps[1:],key=sweep_collisiontime_key,default=None)
        if min_sweep != None and min_sweep.collision_time < earliest_collision[B]:
            earliest_collision[B] = min_sweep.collision_time
            collision_step.append(apc._get_index_of_collision(list_tables[B].for_schedule, min_sweep.collision_time))
            collision_index.append([A,B])
            collision_type.append(min_sweep.collision_case)

    collision_indices, collision_types, collision_steps = \
                np.asarray(collision_index), np.asarray(collision_type), np.asarray(collision_step)
    collision_mask = np.ones(len(collision_indices)).astype(bool)
    for i in range(len(collision_indices)):
        for j in np.arange(i+1,len(collision_indices)):
            if collision_mask[i]:
                if np.all(collision_indices[i] == collision_indices[j]):
                    collision_mask[j]=False
                elif np.all(collision_indices[i] == list(reversed(collision_indices[j]))):
                    collision_mask[j]=False

    if len(collision_mask)>0 and len(collision_indices)>0:
        collision_mask[collision_indices is None] = False
    collision_indices = collision_indices[collision_mask]
    collision_types = collision_types[collision_mask]
    collision_steps = collision_steps[collision_mask]
    # return the earliest collision time and collision indices
    return collision_indices, collision_types, collision_steps
    
    
    
def single_interaction_collision_check(pos_collider,ind_changing, tp_changing, \
                table_changing, ind_nochange, tp_nochange, table_nochange):
    test_sweep = pos_collider.spacetime_collision_between_positioners(ind_changing, \
                tp_changing, table_changing, ind_nochange, tp_nochange, table_nochange)
    min_sweep = min(test_sweep,key=sweep_collisiontime_key)
    if min_sweep.collision_time < np.inf:
        return min_sweep.collision_time, min_sweep.collision_case
    else:
        #intervene("Inside single interation collision check. Found infinite sweeptime.")
        return np.inf, None
        

def row_movetime(row):
    return row.data['move_time'] + row.data['prepause'] + row.data['postpause']
    
def row_movetime_fromschedule(row):
    return row.data['move_time'] + row.data['prepause'] + row.data['postpause']
    
def sweep_collisiontime_key(sweep):
    return sweep.collision_time
    



