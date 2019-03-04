import os, sys
import numpy as np
sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
import posstate
import petal
CONSTANTS_AVAILABLE = False

#point 'positioner_locations_file' to positioner_locations_0530v14.csv
nominals = np.genfromtxt(pc.dirs['positioner_locations_file'], delimiter = ',',
                       names = True, usecols = (0,2,3))

def seed(petals_to_seed):
    """
    Gets each positioner's DEVICE_LOC, looks up nominal device X,Y coordinates,
    rotates by petal rotation (from constants database or petal configuration file),
    translates coordinates by petal's X_OFFSET and Y_OFFSET, and updates positioner 
    configuration files with the transformed OFFSET_X, OFFSET_Y values.
    INPUTS:
    petals_to_seed: list of strings specifying the petal ids to seed or a 
                    single string specifying a single petal id to seed
    """
    if not isinstance(petals_to_seed, list):
        petals_to_seed = [petals_to_seed]
    for petal_to_seed in petals_to_seed:
        ptl_id = str(petal_to_seed).zfill(2)
        if CONSTANTS_AVAILABLE:  
            #will need to access constants database directly when running petal 
            #in stand-alone mode, this metrology is not currently available and
            #cannot be meaningfully used
            pass
        else:
            petal_state = posstate.PosState(ptl_id, logging=True, device_type='ptl')
            ptl_rot =  petal_state.conf['ROTATION']
            ptl_xoff = petal_state.conf['X_OFFSET']
            ptl_yoff = petal_state.conf['Y_OFFSET']
        ptl = petal.Petal(petal_id = ptl_id, posids = [], fidids = [], simulator_on = True)
        for posid in ptl.posids:
            device_loc = ptl.get_posfid_val(posid, 'DEVICE_LOC')
            transformed_x, transformed_y = _transform(nominals[device_loc]['X'],
                                                      nominals[device_loc]['Y'],
                                                      ptl_rot,
                                                      ptl_xoff,
                                                      ptl_yoff)
            ptl.set_posfid_val(posid, 'OFFSET_X', transformed_x)
            ptl.set_posfid_val(posid, 'OFFSET_Y', transformed_y)
            ptl.states[posid].write()

def _transform(x,y,angle,dx,dy): 
    '''
    Rotate coordinate by specified angle in degrees,
    and translate by dx, dy
    '''
    theta=np.radians(angle)
    c,s=np.cos(theta),np.sin(theta)
    R=np.matrix([[c,-s],[s,c]])
    rr = np.dot(np.array([x,y]), R.T)
    return float(rr.T[0] + dx), float(rr.T[1] + dy)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ptls = sys.argv[1]
    else:
        ptls = input('Enter a petal number or list of petal numbers eg. [\'02\',\'03\']: \n')
    seed(ptls)
    print('Positioner configuration files have been seeded')