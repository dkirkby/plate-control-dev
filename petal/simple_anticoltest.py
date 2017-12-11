import os

basepath = os.path.abspath('../')
logdir = os.path.abspath(os.path.join(basepath,'positioner_logs'))
allsetdir = os.path.abspath(os.path.join(basepath,'fp_settings'))
if 'HOME' not in os.environ.keys():
    os.environ['HOME'] = basepath
tempdir = os.environ.get('HOME') + os.path.sep + 'fp_temp_files' + os.path.sep
if not os.path.exists(logdir):
    os.makedirs(logdir)
    os.makedirs(os.path.join(logdir,'move_logs'))
    os.makedirs(os.path.join(logdir,'test_logs'))
    os.makedirs(os.path.join(logdir,'pos_logs'))
if not os.path.exists(allsetdir):
    os.makedirs(allsetdir)
if not os.path.exists(tempdir):
    os.makedirs(tempdir)
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
curnposs = 100#120  
#np_fil = 500
size_vals = np.asarray([100,200,300,400,500])
nrandtploops = 1#30
nloops = 1#4 # warning that the npos will go as ( ( nloop_iter + 1 ) * curnposs )!!!

def run_random_example(nposs):
    # hack
    #if nposs in size_vals:
    #    justload = True
    #elif nposs < 100:
    #    justload = False
    #else:
    #    nposs = size_vals[np.argmin(np.abs(size_vals-nposs))]
    #    justload = True
    justload = False    
    pos_locs = os.path.join(os.path.abspath(os.path.curdir),'positioner_locations.csv')
    locs = Table.read(pos_locs,format='ascii.csv')
    positioners = locs[((locs['type']!='NON')&(locs['type']!='OPT'))]

    postype = np.asarray(positioners['type'])#[:nposs])
    idnams = np.asarray(['temp'+str(i).zfill(4) for i in range(postype.size)])
    pos_idnams = idnams[postype=='POS'][:nposs].tolist()
    last_ind = np.where(idnams == pos_idnams[-1])[0][0]
    fid_idnams = idnams[((postype=='FIF')|(postype=='GIF'))][:last_ind].tolist()

    #files_exist = os.path.exists(os.path.join(logdir,'pos_logs','unit_temp0'+('%03d' % (nposs-1))+'_log_00000001.csv'))     
    os.system('rm ../positioner_logs/pos_logs/unit_temp0*')
    os.system('rm ../positioner_logs/fid_logs/unit_temp0*')
    os.system('rm ../fp_settings/pos_settings/unit_temp0*')
    os.system('rm ../fp_settings/fid_settings/unit_temp0*')
    curpetal = petal.Petal(petal_id='1',posids=pos_idnams,fidids=fid_idnams,simulator_on=True,verbose=True)  
       
    #if not files_exist:
    pit = 0
    for row in positioners:
        idnam,typ,xloc,yloc = row
        if pit == nposs:
            break
        if typ == 'POS':
            state = curpetal.posmodels[pit].state
            state.store('OFFSET_X',xloc)
            state.store('OFFSET_Y',yloc)
            state.store('OFFSET_T',0)
            state.store('OFFSET_P',0)
            state.write()  
            pit += 1
        elif typ == 'FIF' and typ == 'GIF':
            fidnam = idnams[int(idnam)]
            state = curpetal.fidstates[fidnam]
            state.store('OFFSET_X',xloc)
            state.store('OFFSET_Y',yloc)
            state.store('OFFSET_T',0)
            state.store('OFFSET_P',0)
            state.write()  
        else:
            print("The type didn't match fiducial or positioner!")

        
    #if not justload:
    collider = poscollider.PosCollider()
    collider.add_positioners(curpetal.posmodels)
    curpetal.collider = collider
    #xvals = np.array([curpetal.collider.posmodels[i].state.read('OFFSET_X') for i in range(len(curpetal.collider.posmodels))])
    #yvals = np.array([curpetal.collider.posmodels[i].state.read('OFFSET_Y') for i in range(len(curpetal.collider.posmodels))])
    #xv = xvals.reshape(xvals.shape[0],1)
    #xg = xv-xv.T
    #xg[np.diag_indices(xvals.shape[0])] = 99
    #xlocs = np.where(xg==0)
    #yv = yvals.reshape(yvals.shape[0],1)
    #yg = yv-yv.T
    #yg[np.diag_indices(yvals.shape[0])] = 99
    #ylocs = np.where(yg==0)    
    #pdb.set_trace()
    #pdb.set_trace()
    #keep_going = 'T'
    #while (keep_going.upper() == 'T' or keep_going.upper() == 'Y'):
    for i in range(nrandtploops): 
        if justload:
            rand2 = np.random.randint(low=0,high=19,size=1)[0]
            rand3 = np.random.randint(low=0,high=9,size=1)[0]
            tpstarts,tpfins = load_random_state('./tpsets/randomtpsets_nps-'+str(nposs)+'__'+str(rand2)+'.pkl',rand3)
        else:
            tpstarts = create_random_state_opt(collider,curpetal.posmodels,typ= 'posTP')
            tpfins = create_random_state_opt(collider,curpetal.posmodels,typ= 'obsTP')
            
        if len(tpstarts) != len(pos_idnams):
            print("ID names should be same length as generated tpstarts")
            pdb.set_trace()
        
        #commands = ['obsTP']*itternum#len(pos_idnams)
        request_dict = {}
        for itter,idn in enumerate(pos_idnams):
            curpetal.posmodels[itter].state.store('POS_T',tpstarts[itter][0])
            curpetal.posmodels[itter].state.store('POS_P',tpstarts[itter][1])
            curpetal.posmodels[itter].state.write()
            #request_dict[idn] = {'command':commands[itter],'target':tpfins[itter]}
            request_dict[idn] = {'command':'obsTP','target':tpfins[itter]}
        #pdb.set_trace()
        curpetal._clear_schedule()
        curpetal.request_targets(request_dict)
        
        stime = time.time()
        curpetal.schedule_moves(anticollision=True)
        print("Anticollision took: %0.2f seconds" %(time.time()-stime))
        #keep_going = str(input('\n\n\n\nKeep going? '))
    



def load_random_state(pkl_file,index):
    with open(pkl_file,'rb') as pklin:
        allsets = pkl.load(pklin)
    this_set = allsets[index]
    return this_set['tpstarts'],this_set['tpfins']

 
def create_random_state_opt(poscols,posmodels,typ= 'obsTP'):
    nattempts = 2000
    tp_obs = []
    tp_pos = []

    for i,posmod in enumerate(posmodels):
        pos_mins = [posmod.targetable_range_T[0],posmod.targetable_range_P[0]]
        pos_maxs = [posmod.targetable_range_T[1],posmod.targetable_range_P[1]]
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
    for i in range(nloops):
        run_random_example(curnposs*(i+1))
        
