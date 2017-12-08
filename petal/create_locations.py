import os

basepath = os.path.abspath('../')
logdir = os.path.abspath(os.path.join(basepath,'positioner_logs'))
allsetdir = os.path.abspath(os.path.join(basepath,'fp_settings'))
if not os.path.exists(logdir):
    os.makedirs(logdir)
    os.makedirs(os.path.join(logdir,'move_logs'))
    os.makedirs(os.path.join(logdir,'test_logs'))
    os.makedirs(os.path.join(logdir,'pos_logs'))
if not os.path.exists(allsetdir):
    os.makedirs(allsetdir)
if 'POSITIONER_LOGS_PATH' not in os.environ:
    os.environ['POSITIONER_LOGS_PATH'] = logdir
if 'PETAL_PATH' not in os.environ:
    os.environ['PETAL_PATH'] = basepath
if 'FP_SETTINGS_PATH' not in os.environ:
    os.environ['FP_SETTINGS_PATH'] = allsetdir
#if 'CURRENT_LOG_BASENAME' not in os.environ:
#    os.environ['CURRENT_LOG_BASENAME'] = logdir

import poscollider
import numpy as np
import posconstants as pc
import petal
import time
from astropy.table import Table
import pdb
import pickle as pkl

curnposs = 500  



def run_random_example(nposs):

    pos_locs = os.path.join(os.path.abspath(os.path.curdir),'positioner_locations.csv')
    locs = Table.read(pos_locs,format='ascii.csv')
    #np.random.shuffle(locs)
    positioners = locs[((locs['type']!='NON')|(locs['type']!='OPT'))]
    x0,y0 = positioners['x'], positioners['y']
    xy0 = [[],[]]
    tp0 = [[],[]]
    j = 0
    for typ in positioners['type']:
        if j == nposs:
            break
        xy0[0].append(x0[j])
        xy0[1].append(y0[j])
        tp0[0].append(0)
        tp0[1].append(0)
        if typ == 'POS':
            j+=1
        
    npos = len(xy0[0])
    postype = np.asarray(positioners['type'][:npos])
    idnams = np.asarray(['temp'+str(i).zfill(4) for i in range(npos)])
    pos_idnams = idnams[postype=='POS'].tolist()
    fid_idnams = idnams[((postype=='FIF')|(postype=='GIF'))].tolist()
    posarray = petal.Petal(petal_id='1',posids=pos_idnams,fidids=fid_idnams,simulator_on=True,verbose=True)
    for i in range(len(pos_idnams)):
        state = posarray.posmodels[i].state
        state.store('OFFSET_X',xy0[0][i])
        state.store('OFFSET_Y',xy0[1][i])
        state.store('OFFSET_T',tp0[0][i])
        state.store('OFFSET_P',tp0[1][i])
        state.write()

    collider = poscollider.PosCollider()
    collider.add_positioners(posarray.posmodels)
    tpsets = []
    for evenmoreuseless in range(20):
        for uselessitter in range(10):
            print(evenmoreuseless,uselessitter)
            tpstarts = create_random_state_opt(collider,posarray.posmodels,typ= 'posTP')
            tpfins = create_random_state_opt(collider,posarray.posmodels,typ= 'obsTP')
            tpsets.append({'tpstarts':tpstarts,'tpfins':tpfins})
            pdb.set_trace()
    #try:
    #    with open('./tpsets/randomtpsets_nps-'+str(nposs)+'__'+str(evenmoreuseless)+'.pkl','wb') as pklout:
    #        pkl.dump(tpsets,pklout)
    #except:
    #    pdb.set_trace()

  

def create_random_state_opt(poscols,posmodels,typ= 'obsTP'):
    nattempts = 2000
    tp_obs = []
    tp_pos = []

    for i,posmod in enumerate(posmodels):
        pos_mins = [posmod.targetable_range_T[0],posmod.targetable_range_P[0]]
        pos_maxs = [posmod.targetable_range_T[1],posmod.targetable_range_T[1]]
        theta_min,phi_min = posmod.trans.posTP_to_obsTP(pos_mins)
        theta_max,phi_max = posmod.trans.posTP_to_obsTP(pos_maxs)
        randthetas = np.random.randint(low=theta_min,high=theta_max,size=nattempts)
        randphis = np.random.randint(low=phi_min,high=phi_max,size=nattempts)
        
        avoid_thetaphi_collisions = True
        iterations = 0
        randtheta = randthetas[iterations]
        randphi = randphis[iterations]
        while avoid_thetaphi_collisions:
            if iterations > nattempts:
                print("Breaking because 2000 iterations were peformed unsuccessfully for index %d" %i)
                tp_obs.append([randtheta,phi_max])
                if typ == 'obsTP':
                    tp_pos.append(posmod.trans.obsTP_to_posTP([randtheta,phi_max]))
            avoid_thetaphi_collisions = False
            iterations += 1
            result_fixed = poscols.spatial_collision_with_fixed(i, [randtheta,randphi])
            if result_fixed != pc.case.I:
                avoid_thetaphi_collisions = True
                randtheta = randthetas[iterations]
                randphi = randphis[iterations]
                continue
            cur_ids = np.asarray(poscols.pos_neighbor_idxs[i])
            cur_collideable = cur_ids[cur_ids < i]
            for j in cur_collideable:
                result = poscols.spatial_collision_between_positioners(i, j, [randtheta,randphi],tp_obs[j])
                if result != pc.case.I:
                    avoid_thetaphi_collisions = True
                    randtheta = randthetas[iterations]
                    randphi = randphis[iterations]
                    break

        tp_obs.append([randtheta,randphi])          
        if typ == 'posTP':
            tp_pos.append(posmod.trans.obsTP_to_posTP([randtheta,randphi]))

    if typ == 'posTP':
        return tp_pos
    else:
        return tp_obs


    
if __name__ == '__main__':
    #import cProfile
    #cProfile.run('run_random_example(curnposs)')
    run_random_example(curnposs)
        
