import os
import os

basepath = os.path.abspath('../')
logdir = os.path.abspath(os.path.join(basepath,'positioner_logs'))
allsetdir = os.path.abspath(os.path.join(basepath,'fp_settings'))
outputsdir = os.path.abspath(os.path.join(basepath,'outputs'))
figdir = os.path.abspath(os.path.join(basepath,'figures'))
if 'HOME' not in os.environ.keys():
    os.environ['HOME'] = basepath
tempdir = os.environ.get('HOME') + os.path.sep + 'fp_temp_files' + os.path.sep
if not os.path.exists(logdir):
    os.makedirs(logdir)
    os.makedirs(os.path.join(logdir,'move_logs'))
    os.makedirs(os.path.join(logdir,'test_logs'))
    os.makedirs(os.path.join(logdir,'pos_logs'))
for direct in [allsetdir,tempdir,outputsdir,figdir]:
    if not os.path.exists(direct):
        os.makedirs(direct)

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
curnposs = 20
#np_fil = 500
size_vals = np.asarray([100,200,300,400,500])
nrandtploops = 1#30
nloops = 1#4 # warning that the npos will go as ( ( nloop_iter + 1 ) * curnposs )!!!

def run_random_example(nposs):
    #files_exist = os.path.exists(os.path.join(logdir,'pos_logs','unit_temp0'+('%03d' % (nposs-1))+'_log_00000001.csv'))
    if os.sys.platform == 'win32' or os.sys.platform == 'win64':
        delcom = 'del'
    else:
        delcom = 'rm'
    for subdir in ['pos_logs','fid_logs']:
        try:
            os.system('{} {}'.format(delcom, os.path.join(logdir, subdir, 'unit_temp0*')))
        except:
            pass
    for subdir in ['pos_settings','fid_settings']:
        try:
            os.system('{} {}'.format(delcom, os.path.join(allsetdir, subdir, 'unit_temp0*')))
        except:
            pass

    justload = False
    platenum = 3
    pos_locs = os.path.join(allsetdir,'positioner_locations_0530v12.csv')
    positioners = Table.read(pos_locs,format='ascii.csv',header_start=2,data_start=3)
    #positioners = locs[((locs['device_type']=='POS')|(locs['device_type']=='FIF')|(locs['type']=='GIF'))]

    postype = np.asarray(positioners['device_type'])#[:nposs])
    last_posid = positioners['device_location_id'][postype == 'POS'][:nposs][-1]
    last_ind = np.where(positioners['device_location_id'] == last_posid)[0][0]
    cutlist_positioners = positioners[:(last_ind+1)]
    del postype,last_posid,last_ind

    temproot = 'temp{}'.format(platenum)
    idnams = np.asarray(['{}{:03d}'.format(temproot,int(nam)) for nam in cutlist_positioners['device_location_id']])
    cutpostype = cutlist_positioners['device_type']
    pos_idnams = idnams[cutpostype=='POS']
    fid_idnams = idnams[((cutpostype=='FIF')|(cutpostype=='GIF'))]

    curpetal = petal.Petal(petal_id=str(platenum),posids=pos_idnams.tolist(),fidids=fid_idnams.tolist(),simulator_on=True,verbose=True)
       
    #if not files_exist:
    pit = 0
    for row in positioners:
        if pit == nposs:
            break
        idnam, typ, xloc, yloc, zloc, qloc, rloc, sloc = row
        if typ == 'POS':
            model = curpetal.posmodels[pit]
            transform = model.trans
            x_off,y_off = transform.QS_to_obsXY([float(qloc),float(sloc)])
            #print(x_off,x_off-float(xloc),y_off,y_off-float(yloc))
            state = model.state
            state.store('OFFSET_X',xloc)
            state.store('OFFSET_Y',yloc)
            state.store('OFFSET_T',0)
            state.store('OFFSET_P',0)
            state.write()  
            pit += 1
        elif typ == 'FIF' or typ == 'GIF':
            fidid = '{}{:03d}'.format(temproot,int(idnam))
            state = curpetal.fidstates[fidid]
            state.store('Q',float(qloc))
            state.store('S',float(sloc))
            state.write()  
        else:
            print("Type {} didn't match fiducial or positioner!".format(typ))

    #collider = poscollider.PosCollider()
    #collider.add_positioners(curpetal.posmodels)
    #curpetal.collider = collider

    for i in range(nrandtploops): 
        if justload:
            rand2 = np.random.randint(low=0,high=19,size=1)[0]
            rand3 = np.random.randint(low=0,high=9,size=1)[0]
            tpstarts,tpfins = load_random_state('./tpsets/randomtpsets_nps-'+str(nposs)+'__'+str(rand2)+'.pkl',rand3)
        else:
            tpstarts = create_random_state_opt(curpetal.collider,curpetal.posmodels,typ= 'posTP')
            tpfins = create_random_state_opt(curpetal.collider,curpetal.posmodels,typ= 'obsTP')
            
        if len(tpstarts) != len(pos_idnams):
            print("ID names should be same length as generated tpstarts")
            pdb.set_trace()
        
        #commands = ['obsTP']*itternum#len(pos_idnams)
        request_dict = {}
        for itter,idn in enumerate(pos_idnams):
            state = curpetal.posmodels[itter].state
            state.store('POS_T',tpstarts[itter][0])
            state.store('POS_P',tpstarts[itter][1])
            state.write()
            #request_dict[idn] = {'command':commands[itter],'target':tpfins[itter]}
            request_dict[idn] = {'command':'obsTP','target':tpfins[itter]}
        #pdb.set_trace()
        print(pos_idnams,fid_idnams)
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
                if typ == 'posTP':
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
        
        
def animate_table(curpetal,tps):
    '''
        Find what positioners collide, and who they collide with
        Inputs:
            tps:  list or numpy array of theta,phi pairs that specify the location
                    of every positioner
            cur_poscollider:  poscollider object used to find the actual collisions
            list_tables:   list of all the movetables

        Outputs:
           All 3 are numpy arrays giving information about every collision that occurs.
            collision_indices: list index which identifies the positioners that collide
                                this has 2 indices in a pair [*,*] if 2 positioners collided
                                or [*,None] if colliding with a wall of fiducial.
            collision_types:   Type of collision as specified in the pc class
    '''
    collider = curpetal.collider
    list_tables = list(curpetal.schedule.move_tables)
    posmodel_index_iterable = range(len(collider.posmodels))
    sweeps = [[] for i in posmodel_index_iterable]
    earliest_collision = [np.inf for i in posmodel_index_iterable]
    nontriv = 0
    colrelations = collider.collidable_relations
    for A, B, B_is_fixed in zip(colrelations['A'], colrelations['B'], colrelations['B_is_fixed']):
        tableA = list_tables[A].for_schedule
        obsTPA = tps[A]
        if B_is_fixed and A in range(len(
                list_tables)):  ## might want to replace 2nd test here with one where we look in tables for a specific positioner index
            these_sweeps = collider.spacetime_collision_with_fixed(A, obsTPA, tableA)
        elif A in range(len(list_tables)) and B in range(len(
                list_tables)):  ## again, might want to look for specific indexes identifying which tables go with which positioners
            tableB = list_tables[B].for_schedule
            obsTPB = tps[B]
            these_sweeps = collider.spacetime_collision_between_positioners(A, obsTPA, tableA, B, obsTPB,
                                                                                 tableB)
        if these_sweeps[0].collision_time <= earliest_collision[A]:
            nontriv += 1
            sweeps[A] = these_sweeps[0]
            earliest_collision[A] = these_sweeps[0].collision_time
            if these_sweeps[0].collision_time < np.inf:
                earliest_collision[A] = these_sweeps[0].collision_time
        for i in range(1, len(these_sweeps)):
            if these_sweeps[i].collision_time < earliest_collision[B]:
                nontriv += 1
                sweeps[B] = these_sweeps[i]
                earliest_collision[B] = these_sweeps[i].collision_time

    ## return the earliest collision time and collision indices
    return sweeps

if __name__ == '__main__':
    #import cProfile
    #cProfile.run('run_random_example(curnposs)')
    for loopitter in range(nloops):
        run_random_example(curnposs)
        
