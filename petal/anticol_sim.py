## Need os so that we can define all the environment variables appropriately prior to loading focalplane-specific code
import os

## Define pythonically all the locations for the desi files
basepath = os.path.abspath('../')
logdir = os.path.abspath(os.path.join(basepath,'positioner_logs'))
allsetdir = os.path.abspath(os.path.join(basepath,'fp_settings'))
outputsdir = os.path.abspath(os.path.join(basepath,'outputs'))
figdir = os.path.abspath(os.path.join(basepath,'figures'))

## Define the locations in the environment so other modules can find them
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

import numpy as np
import posconstants as pc
import petal
import time
from astropy.table import Table
import pdb
import pickle as pkl

################
## Parameters ##
################
## How many positioners would you like to use?
curnposs = 20
## How many times should this run iteratively with new positions?
nloops = 1
## Whether to delete the old temporary files with the same names that will be generated upon execution of this script
delete_prev_tempfiles = True


def run_random_example(nposs,deltemps=False):
    '''
    Main calling function that generates random locations for positioners in true petal locations
    in a formation that is tightly packed such that anticollision is necessary

    The code creates initial and final tp positioners for the positioners and runs the schduling code to generate
    movetables that get the positioners from beginning to end without collisions (using anticollision where necessary)

    :param nposs: Number of positioners to 'load into the petal'
    :param deltemps: Whether to delete the old temporary positioner configurations files before regenerating them,
        as opposed to overwriting them
    '''
    ## If we want ot cleanup old files before writing new ones, lets tell code how the system deletes the files and
    ## then delete them if they exist
    if delete_prev_tempfiles:
        files_exist = os.path.exists(os.path.join(logdir,'pos_logs','unit_temp0'+('%03d' % (nposs-1))+'_log_00000001.csv'))
        if os.sys.platform == 'win32' or os.sys.platform == 'win64':
            delcom = 'del'
        else:
            delcom = 'rm'
        if files_exist:
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

    ## Define Plate Number
    platenum = 3
    ## Load positioner locations (see docdb 0530
    pos_locs = os.path.join(allsetdir,'positioner_locations_0530v12.csv')
    positioners = Table.read(pos_locs,format='ascii.csv',header_start=2,data_start=3)
    #positioners = locs[((locs['device_type']=='POS')|(locs['device_type']=='FIF')|(locs['type']=='GIF'))]

    ## Cut data to appropriate number of positioners
    postype = np.asarray(positioners['device_type'])#[:nposs])
    last_posid = positioners['device_location_id'][postype == 'POS'][:nposs][-1]
    last_ind = np.where(positioners['device_location_id'] == last_posid)[0][0]
    cutlist_positioners = positioners[:(last_ind+1)]
    del postype,last_posid,last_ind

    ## Name the positioners (needed for config files)
    temproot = 'temp{}'.format(platenum)
    idnams = np.asarray(['{}{:03d}'.format(temproot,int(nam)) for nam in cutlist_positioners['device_location_id']])
    cutpostype = cutlist_positioners['device_type']
    pos_idnams = idnams[cutpostype=='POS']
    fid_idnams = idnams[((cutpostype=='FIF')|(cutpostype=='GIF'))]

    ## Create the petal with given positioners and fiducials
    curpetal = petal.Petal(petal_id=str(platenum),posids=pos_idnams.tolist(),fidids=fid_idnams.tolist(),simulator_on=True,verbose=True)
       
    ## Loop over positioners, load x,y position and save to config file
    pit = 0
    for row in positioners:
        if pit == nposs:
            break
        idnam, typ, xloc, yloc, zloc, qloc, rloc, sloc = row
        if typ == 'POS':
            model = curpetal.posmodels[pit]
            #transform = model.trans
            #x_off,y_off = transform.QS_to_obsXY([float(qloc),float(sloc)])
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

    ## Find tp combinations that don't initially collide for start and end locations
    tpstarts = create_random_state_opt(curpetal.collider,curpetal.posmodels,typ= 'posTP')
    tpfins = create_random_state_opt(curpetal.collider,curpetal.posmodels,typ= 'obsTP')

    ## Double check everything is the same length
    if len(tpstarts) != len(pos_idnams):
        print("ID names should be same length as generated tpstarts")
        pdb.set_trace()

    ## Store initial locations and create request for final locations
    request_dict = {}
    for itter,idn in enumerate(pos_idnams):
        state = curpetal.posmodels[itter].state
        state.store('POS_T',tpstarts[itter][0])
        state.store('POS_P',tpstarts[itter][1])
        state.write()
        request_dict[idn] = {'command':'obsTP','target':tpfins[itter]}

    ## Print for our information
    print(pos_idnams,fid_idnams)

    ## Clear shcedule just as a precaution
    curpetal._clear_schedule()
    ## Request targets
    curpetal.request_targets(request_dict)

    ## Start Timer
    stime = time.time()
    ## Schedule moves with anticollision
    curpetal.schedule_moves(anticollision=True)
    ## Print out the total time the last step took
    print("Anticollision took: %0.2f seconds" %(time.time()-stime))


def create_random_state_opt(poscols,posmodels,typ= 'obsTP'):
    '''
    Function that selects theta,phi pairs for each positioner that do not overlap with neighbors
    :param poscols: poscollider class instance with positioners loaded
    :param posmodels: posmodels corresponding to all the positioners
    :param typ: whether you want obsTP coordinate system or posTP

    :return:  tp array where each index corresponds to a tp value in 'typ' coordinate system for
                the positioner defined by the posmodel at the same index
    '''
    ## Choose the number of attempts to try
    nattempts = 2000
    tp_obs = []
    tp_pos = []

    ## Loop over posmodels. Iterative since we need to add positioners one at a time
    ## to ensure they won't collider
    for i,posmod in enumerate(posmodels):
        ## Get targetable ranges and convert to obsTP coordinate system
        pos_mins = [posmod.targetable_range_T[0],posmod.targetable_range_P[0]]
        pos_maxs = [posmod.targetable_range_T[1],posmod.targetable_range_P[1]]
        theta_min,phi_min = posmod.trans.posTP_to_obsTP(pos_mins)
        theta_max,phi_max = posmod.trans.posTP_to_obsTP(pos_maxs)

        ## Generate nattempts worth of random positions to try
        randobsthetas = np.random.randint(low=theta_min,high=theta_max,size=nattempts)
        randobsphis = np.random.randint(low=phi_min,high=phi_max,size=nattempts)

        ## Set success flag to true to start (initialized here for domain purposes)
        solution_found = True
        ## Loop over possible locations
        for randobstheta,randobsphi in zip(randobsthetas,randobsphis):
            solution_found = True
            ## Check if current position is safe with respect to fixed targets
            result_fixed = poscols.spatial_collision_with_fixed(i, [randobstheta,randobsphi])
            ## If collision occurs, try next location in new iteration of loop
            if result_fixed != pc.case.I:
                solution_found = False
                continue
            ## Get id's of positioners that would have been assigned earlier
            cur_ids = np.asarray(poscols.pos_neighbor_idxs[i])
            cur_collideable = cur_ids[cur_ids < i]
            ## Loop over already assigned positioners to test for collisions
            for j in cur_collideable:
                result = poscols.spatial_collision_between_positioners(i, j, [randobstheta,randobsphi],tp_obs[j])
                ## If collision occurs, try next location in new iteration of loop
                if result != pc.case.I:
                    solution_found = False
                    break
            ## If the flag hasn't been changed, then no collisions exist,
            ## we've found our solution, and we can break this loop.
            if solution_found:
                break
            else:
                continue

        ## If no solution is found after nattempts, retry with a much safer criterion where the positioner is tucked in
        if not solution_found:
            ## Create random theta/phi pairs with phi all the way tucked in
            randobsthetas = np.random.randint(low=theta_min, high=theta_max, size=nattempts)
            randobsphis = np.random.randint(low=phi_max, high=phi_max, size=nattempts)
            ## Do the same loop as above and hope for the best on finding a solution
            solution_found = True
            for randobstheta, randobsphi in zip(randobsthetas, randobsphis):
                solution_found = True
                result_fixed = poscols.spatial_collision_with_fixed(i, [randobstheta, randobsphi])
                if result_fixed != pc.case.I:
                    solution_found = False
                    continue
                cur_ids = np.asarray(poscols.pos_neighbor_idxs[i])
                cur_collideable = cur_ids[cur_ids < i]
                for j in cur_collideable:
                    result = poscols.spatial_collision_between_positioners(i, j, [randobstheta, randobsphi], tp_obs[j])
                    if result != pc.case.I:
                        solution_found = False
                        break
                if solution_found:
                    break
                else:
                    continue
        ## If either of the above loops has found a solution, append it to the results and continue to the next positioners
        ## Else raise an error because we can't proceed
        if solution_found:
            tp_obs.append([randobstheta,randobsphi])
            if typ == 'posTP':
                tp_pos.append(posmod.trans.obsTP_to_posTP([randobstheta,randobsphi]))
        else:
            raise("Couldn't find a viable theta phi for index {}".format(i))

    ## We have looped over all positioners. Now return the tp pairs in the request coordinate system
    if typ == 'posTP':
        return tp_pos
    else:
        return tp_obs
        

if __name__ == '__main__':
    ## Profile the code to see where things are running slow, etc
    #import cProfile
    #cProfile.run('run_random_example(curnposs)')

    ## For itteration in nloops, run the code for the given number of positioners
    for loopitter in range(nloops):
        run_random_example(nposs=curnposs,deltemps=delete_prev_tempfiles)
        
