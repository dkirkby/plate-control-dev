################
## Parameters ##
################
# iidea - use argv imports
## How many positioners would you like to use?
curnposs = 50
## How many times should this run iteratively with new positions?
nloops = 1
## Whether to delete the old temporary files with the same names that will be generated upon execution of this script
delete_prev_tempfiles = False
## Define a seed
sim_seed = 1036#103950  # None for 'true' random

make_animations = False


##############################
####  Imports and setup   ####
##############################

## Need os so that we can define all the environment variables appropriately prior to loading focalplane-specific code
import os
import sys
import numpy as np
import time
from astropy.table import Table
import pdb

os.environ["collision_settings"] = '/software/products/fp_settings-trunk/collision_settings'
print(os.environ["collision_settings"])
## Define the locations in the environment so other modules can find them
## Define pythonically all the locations for the desi files
if 'HOME' in os.environ:
    basepath = os.environ['HOME']
else:
    basepath = os.path.abspath('../')
    os.environ['HOME'] = basepath
if 'POSITIONER_LOGS_PATH' in os.environ:
    logdir = os.environ['POSITIONER_LOGS_PATH']
else:
    logdir = os.path.abspath(os.path.join(basepath, 'positioner_logs'))
    os.environ['POSITIONER_LOGS_PATH'] = logdir
if 'PETAL_PATH' in os.environ:
    pass
else:
    basepath = os.path.abspath('../')
    os.environ['PETAL_PATH'] = basepath
if 'FP_SETTINGS_PATH' in os.environ:
    allsetdir = os.environ['FP_SETTINGS_PATH']
else:
    allsetdir = os.path.abspath(os.path.join(basepath, 'fp_settings'))
    os.environ['FP_SETTINGS_PATH'] = allsetdir

## Define other useful directories and make them if they don't exist
outputsdir = os.path.abspath(os.path.join(basepath,'outputs'))
figdir = os.path.abspath(os.path.join(basepath,'figures'))
tempdir = os.path.join(os.environ['HOME'],'fp_temp_files','')
if not os.path.exists(logdir):
    os.makedirs(logdir)
    for dirname in ['move','test','pos']:
        fullpath = os.path.join(logdir,'{}_logs'.format(dirname))
        os.makedirs(fullpath)
for dirname in [allsetdir,tempdir,outputsdir,figdir]:
    if not os.path.exists(dirname):
        os.makedirs(dirname)
sys.path.append(os.path.abspath('../'))
## Make the last imports, desi specific code
import petal
import posconstants as pc


###########################
####  Main Code Body   ####
###########################

def run_random_example(nposs,deltemps=False,seed=None,do_anims=False):
    '''
    Main calling function that generates random locations for positioners in true petal locations
    in a formation that is tightly packed such that anticollision is necessary

    The code creates initial and final tp positioners for the positioners and runs the schduling code to generate
    movetables that get the positioners from beginning to end without collisions (using anticollision where necessary)

    :param nposs: Number of positioners to 'load into the petal'
    :param deltemps: Whether to delete the old temporary positioner configurations files before regenerating them,
        as opposed to overwriting them
    :param seed: Seed given to randomization functions for reproducibility. (Set to none for non-reproducible)
    '''
    ## Define Plate Number
    platenum = 3

    ## if seed is defined, create the random state
    if seed is not None:
        rand = np.random.RandomState(seed)
    else:
        rand = np.random.RandomState()
    ## Load positioner locations (see docdb 0530
    pos_locs = 'positioner_locations_0530v14.csv'#os.path.join(allsetdir,'positioner_locations_0530v12.csv')
    positioners = Table.read(pos_locs,format='ascii.csv',header_start=0,data_start=1)
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

    ## If we want ot cleanup old files before writing new ones, lets tell code how the system deletes the files and
    ## then delete them if they exist
    if deltemps:
        files_exist = os.path.exists(os.path.join(logdir,'pos_logs','unit_{}{:03d}{}'.format(temproot,nposs-1,'_log_00000001.csv')))
        if os.sys.platform == 'win32' or os.sys.platform == 'win64':
            delcom = 'del'
        else:
            delcom = 'rm'
        if files_exist:
            locdict = {'logs':logdir, 'settings':allsetdir}
            for dirtype,rootdir in locdict.items():
                for subdirtype in ['pos','fid']:
                    subdir = '{}_{}'.format(subdirtype,dirtype)
                    fullpath = os.path.join(rootdir, subdir)
                    filenames = '{}{}unit_{}*'.format(fullpath,os.path.sep,temproot)
                    print("Removing {}".format(filenames))
                    try:
                        os.system('{} {}'.format(delcom,filenames))
                    except:
                        pass

    ## Create the petal with given positioners and fiducials
    curpetal = petal.Petal(petal_id=str(platenum),posids=pos_idnams.tolist(),fidids=fid_idnams.tolist(),simulator_on=True,verbose=True)

    ## Loop over positioners, load x,y position and save to config file
    pit = 0

    ## Randomize arm lengths based on empirical data
    r1s,r2s = get_arm_lengths(nposs,rand)
    ## Randomized tp offsets
    toffs,poffs = get_tpoffsets(nposs,rand)
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
            ## store randomized tp offsets
            state.store('OFFSET_T',toffs[pit])
            state.store('OFFSET_P',poffs[pit])
            ## Stored randomized arm lengths
            state.store('LENGTH_R1',r1s[pit])
            state.store('LENGTH_R2',r2s[pit])
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
    tpstarts = create_random_state_opt(curpetal.collider,curpetal.posmodels,typ= 'posTP',randomizer=rand)
    tpfins = create_random_state_opt(curpetal.collider,curpetal.posmodels,typ= 'obsTP',randomizer=rand)

    ## Double check everything is the same length
    if len(tpstarts) != len(pos_idnams):
        print("ID names should be same length as generated tpstarts")
        pdb.set_trace()

    ## Store initial locations and create request for final locations
    request_dict = {}
    for itter,idn in zip(np.arange(len(pos_idnams))[::-1],pos_idnams[::-1]):
        posmodel = curpetal.posmodels[itter]
        state = posmodel.state
        state.store('POS_T',tpstarts[itter][0])
        state.store('POS_P',tpstarts[itter][1])
        state.write()
        posTP = posmodel.trans.obsTP_to_posTP(tpfins[itter])
        obsXY = posmodel.trans.posTP_to_obsXY(posTP)
        request_dict[idn] = {'command':'obsXY','target':obsXY}

    ## Print for our information
    print(pos_idnams,fid_idnams)

    ## Clear shcedule just as a precaution
    curpetal._clear_schedule()
    ## Request targets
    curpetal.request_targets(request_dict)

    ## Several things set to False by default but useful for debugging
    ## This is hackey but keeps us from propogating a bunch of function parameters
    curpetal.schedule.anticol.make_animations = do_anims
    curpetal.schedule.anticol.plotting = True
    curpetal.schedule.anticol.create_debug_outputs = True
    curpetal.schedule.anticol.astar_plotting = True
    curpetal.schedule.anticol.use_pdb = True
    curpetal.anticollision_override = False
    ## Start Timer
    stime = time.time()
    ## Schedule moves with anticollision
    curpetal.schedule_moves(anticollision=True)
    # for tablenum, table in enumerate(curpetal.schedule.move_tables):
    #     posmodel = table.posmodel
    #     print(posmodel == curpetal.posmodels[tablenum])
    #     dp = posmodel.trans.delta_posTP(tpfins[tablenum],tpstarts[tablenum],range_wrap_limits='targetable')
    #     print("Requested dt,dp: ",dp[0],dp[1])
    #     sched = table.for_hardware
    #     #sched = table.for_schedule
    #     stats = sched['stats']
    #     print("Stats dt,dp: ",stats['net_dT'][-1],stats['net_dP'][-1])
    #     if len(table.rows) > 2:
    #         print("Ideal table dtdp: ", table.rows[1].data['dT_ideal'],
    #               table.rows[0].data['dP_ideal'] + table.rows[2].data['dP_ideal'])
    #         print("rre dp,dt,dp,nmoves: ",table.rows[0].data['dP_ideal'],table.rows[1].data['dT_ideal'], table.rows[2].data['dP_ideal'],len(table.rows))
    #     else:
    #         print("direct dt,dp,nmoves: ", table.rows[0].data['dT_ideal'], table.rows[0].data['dP_ideal'],len(table.rows))
    #     print("\n")
    for tablenum, table in enumerate(curpetal.schedule.move_tables):
        posmodel = table.posmodel
        dp = posmodel.trans.delta_posTP(tpfins[tablenum],tpstarts[tablenum],range_wrap_limits='targetable')
        print(posmodel.posid)
        print("Requested dt,dp: ",dp[0],dp[1])
        sched = table.for_hardware

        if len(sched['motor_steps_T']) == 6:
            tstep = sched['motor_steps_T'][2]
            pstep = sched['motor_steps_P'][1]+sched['motor_steps_P'][3]
            print([sched['motor_steps_T'][i] for i in range(len(sched['motor_steps_T']))])
            print([sched['motor_steps_P'][i] for i in range(len(sched['motor_steps_P']))])
            #print([tstep,sched['motor_steps_T'][4],sched['motor_steps_T'][5]])
            #print([pstep, sched['motor_steps_P'][4], sched['motor_steps_P'][5]])
        else:
            print([sched['motor_steps_T'][i] for i in range(len(sched['motor_steps_T']))])
            print([sched['motor_steps_P'][i] for i in range(len(sched['motor_steps_P']))])

    # return the movetables as a list of movetables
    ## Print out the total time the last step took
    print("Anticollision took: %0.2f seconds" %(time.time()-stime))


def create_random_state_opt(poscols,posmodels,typ= 'obsTP',randomizer=np.random.RandomState()):
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
        print(i,posmod)
        ## Get targetable ranges and convert to obsTP coordinate system
        pos_mins = [posmod.targetable_range_T[0],posmod.targetable_range_P[0]]
        pos_maxs = [posmod.targetable_range_T[1],posmod.targetable_range_P[1]]
        theta_min,phi_min = posmod.trans.posTP_to_obsTP(pos_mins)
        theta_max,phi_max = posmod.trans.posTP_to_obsTP(pos_maxs)

        ## Generate nattempts worth of random positions to try
        randobsthetas = randomizer.randint(low=theta_min,high=theta_max,size=nattempts)
        randobsphis = randomizer.randint(low=144,high=phi_max,size=nattempts) # phi_min

        ## Set success flag to true to start (initialized here for domain purposes)
        solution_found = True
        ## Loop over possible locations
        for randobstheta,randobsphi in zip(randobsthetas,randobsphis):
            solution_found = True
            ## Check if current position is safe with respect to fixed targets
            result_fixed = poscols.spatial_collision_with_fixed(posmod.posid, [randobstheta,randobsphi])
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
        
def get_arm_lengths(nvals,rand):
    ## Empirical data based on first ~2000 positioners
    r1mean = 3.018
    r2mean = 3.053626
    r1std = 0.083
    r2std = 0.055065
    r1s = rand.normal(r1mean, r1std, nvals)
    r2s = rand.normal(r2mean, r2std, nvals)
    return r1s,r2s

# todo-anthony make this more realistic
def get_tpoffsets(nvals,rand):
    ## Completely madeup params
    tlow,thigh = -180,180 # degrees
    pmean,pstd = 0, 3 # degrees
    toffs = rand.uniform(tlow, thigh, nvals)
    poffs = rand.normal(0, 3, nvals)
    return toffs,poffs

if __name__ == '__main__':
    ## Profile the code to see where things are running slow, etc
    #import cProfile
    #cProfile.run('run_random_example(curnposs)')

    ## For itteration in nloops, run the code for the given number of positioners
    for loopitter in range(nloops):
        run_random_example(nposs=curnposs,deltemps=delete_prev_tempfiles,seed=sim_seed,do_anims = make_animations)
        
