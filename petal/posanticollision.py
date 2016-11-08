# -*- coding: utf-8 -*-
"""
Currently a very basic anticollision code that will
vastly improve over time with future updates.
@author: Anthony Kremin
@institution: University of Michigan
@email: kremin[at]umich.edu
"""
import numpy as np
import pdb

import poscollider
import posmovetable
import posconstants as pc


def run_anticol(x,y,t,t2,p,p2,posmodels, method = 'RRE', avoidance='zeroth_order', verbose=False):
    '''
        Wrapper function to run the specified version of anticollision,
        if available.
    '''
    if method == 'RRE':
        return run_RRE_anticol(x,y,t,t2,p,p2,posmodels,method,avoidance,verbose)
    else:
        print("RRE is all that is available currently. Continuing with RRE")
        return run_RRE_anticol(x,y,t,t2,p,p2,posmodels,method,avoidance,verbose)




def run_RRE_anticol(x,y,t,t2,p,p2,posmodels,method, avoidance, verbose):
    # Create a poscollider instance to check collisions in movetable
    pos_collider = poscollider.PosCollider()
    pos_collider.add_positioners(posmodels)
    
    # Define the phi angle to move in order to ensure that it's "tucked in"
    p_in = np.asarray(p).clip(min=96)

    # Generate complete movetables under RRE method
    tables = []    
    for i,cur_posmodel in enumerate(posmodels):
        current_table = create_table(t[i],t2[i],p[i],p_in[i],p2[i],cur_posmodel,method)
        # jhs -- we should have a table.store_orig_command() method here
        # ajk -- for now I implemented  ^ in the posschedule call after this posanticollision returns
        tables.append(current_table)

    # Check for collisions
    earliest_collision, collision_indices, collision_types = check_for_collisions(t,p,pos_collider,tables)
    if verbose:
        print('Collisions at indices:    ',np.unique(collision_indices))
    # Set max number of anticollision correction iterations, then intiate loop
    max_iterations = 10
    iterations = 0

    while len(collision_indices) > 0:
        iterations += 1
        # Correct Collisions
        tables = correct_collisions(tables,posmodels,collision_indices,collision_types, avoidance)
        # Check for collisions
        earliest_collision, collision_indices, collision_types = check_for_collisions(t,p,pos_collider,tables)                
        if verbose:
            print('Collisions at indices:    ',np.unique(collision_indices))
        # Give up and stop trying if we exceed max iterations. Currently eturns instead of throwing error
        if iterations > max_iterations:
            print("Iterations for collision avoidance has exceeded %d attempts. Quitting Execution" % max_iterations)
            break
    # return the output tables
    return tables
            







def create_table(theta_start,theta_final, phi_start, phi_inner, phi_final, current_positioner_model, method = 'RRE'):
    '''
        Wrapper function to call the appropriate version of the movetable generation code specified by 'method,'
        if it's available.
    '''
    if method == 'RRE':
        return create_table_RRE(theta_start,theta_final, phi_start, phi_inner, phi_final, current_positioner_model)
    else:
        print("Currently RRE is all we have. Using that method.")
        return create_table_RRE(theta_start,theta_final, phi_start, phi_inner, phi_final, current_positioner_model)



def check_for_collisions(thetas,phis,cur_poscollider,list_tables):
    # Use pre-made collision detection tools in poscollider class
    earliest_collision = np.ones(len(cur_poscollider.posmodels))*np.inf
    # Store indices of colliding positioners
    collision_index = []
    collision_type = []
    # Loop over all possible collisions
    for k in range(len(cur_poscollider.collidable_relations['A'])):
        # Get indices of current potential collision
        A = cur_poscollider.collidable_relations['A'][k]
        B = cur_poscollider.collidable_relations['B'][k]
        if type(A) != int or type(B) != int:
            continue
        # Get the movetables for each of the positioners
        tableA = list_tables[A].full_table
        tableB = list_tables[B].full_table

        B_is_fixed = cur_poscollider.collidable_relations['B_is_fixed'][k]
        if B_is_fixed and A in range(len(list_tables)): # might want to replace 2nd test here with one where we look in tables for a specific positioner index
            these_sweeps = cur_poscollider.spacetime_collision_with_fixed(A, [thetas[A],phis[A]], tableA)
        elif A in range(len(list_tables)) and B in range(len(list_tables)): # again, might want to look for specific indexes identifying which tables go with which positioners
            these_sweeps = cur_poscollider.spacetime_collision_between_positioners(A, [thetas[A],phis[A]], tableA, B, [thetas[B],phis[B]], tableB)
        # Find the earliest collision if multiple are found
        for i in range(len(these_sweeps)):
            if i == 0:
                AorB = A
            else:
                AorB = B
            if these_sweeps[i].collision_time <= earliest_collision[AorB] and not np.isinf(these_sweeps[i].collision_time):
                #sweeps[AorB] = these_sweeps[i]
                earliest_collision[AorB] = these_sweeps[i].collision_time
                collision_index.append([A,B])
                collision_type.append(these_sweeps[i].collision_case)
    # return the earliest collision time and collision indices
    return earliest_collision, np.asarray(collision_index), np.asarray(collision_type)
    
    
    
    
    
def correct_collisions(tables,posmodels,collision_indices,collision_types,avoidance_type='zeroth_order'):
    '''
        Wrapper function for correcting collisions. Calls the function 
        specified by 'avoidance_type' if it exists. 
    '''
    if avoidance_type == 'zeroth_order':
        return correct_collisions_zerothorder(tables,posmodels,collision_indices)
    else:
        print("Currently zeroth order is all we have. Executing that.")
        return correct_collisions_zerothorder(tables,posmodels,collision_indices)
        
        
        
        

def create_table_RRE(theta_start,theta_final, phi_start, phi_inner, phi_final, current_positioner_model):
    # Get a table class instantiation
    table = posmovetable.PosMoveTable(current_positioner_model)
    
    # Find the theta and phi movements for the retract move
    dtdp = current_positioner_model.trans.delta_obsTP([theta_start,phi_start],[theta_start,phi_inner], range_wrap_limits='targetable')
    table.set_move(0, pc.T, dtdp[0])
    table.set_move(0, pc.P, dtdp[1])
    table.set_prepause (0, 0.0)
    table.set_postpause(0, 0.0)
    
    # Find the theta and phi movements for the theta movement inside the safety envelope
    dtdp = current_positioner_model.trans.delta_obsTP([theta_start,phi_inner],[theta_final,phi_inner], range_wrap_limits='targetable')
    table.set_move(1, pc.T, dtdp[0]) 
    table.set_move(1, pc.P, dtdp[1]) 
    table.set_prepause (1, 0.0)
    table.set_postpause(1, 0.0)
    
    # Find the theta and phi movements for the phi extension movement
    dtdp = current_positioner_model.trans.delta_obsTP([theta_final,phi_inner],[theta_final,phi_final], range_wrap_limits='targetable')
    table.set_move(2, pc.T, dtdp[0])
    table.set_move(2, pc.P, dtdp[1])
    table.set_prepause (2, 0.0)
    table.set_postpause(2, 0.0)
    
    # return this positioners rre movetable
    return table


    
    
    
    
    
def correct_collisions_zerothorder(tables,posmodels,collision_indices):
    # Get a unique list of all indices causing problems
    unique_indices = np.unique(collision_indices)
    
    nrows = np.max([len(table.rows) for table in tables])

    max_times = np.zeros(nrows)     
    for table in tables:
        for i in range(len(table.rows)):
            time = table.rows[i].data['move_time'] + table.rows[i].data['prepause'] + table.rows[i].data['postpause']
            if time > max_times[i]:
                max_times[i] = time
            
    # For the colliding indices, simply don't move them
    for index in unique_indices:
        table = posmovetable.PosMoveTable(posmodels[index])
        for ind in range(len(tables[index].rows)):
            table.set_move(ind, pc.T, 0.)
            table.set_move(ind, pc.P, 0.)
            table.set_prepause (ind, max_times[ind])
            table.set_postpause(ind, 0.0)
        tables[index] = table
    return tables
