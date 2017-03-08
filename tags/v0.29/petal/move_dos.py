import posmodel
import posschedule
import posmovetable
import posstate
import posconstants as pc
import numpy as np
import time
import Pyro4

from DOSlib.application import Application
from DOSlib.discovery import discoverable
from DOSlib.util import dos_parser
from DOSlib.advertise import Seeker


"""Test script for the move function in petal_dos.
"""

# initialization done when starting petal application
petal_id = 0
role = 'PETAL%d' % petal_id
ptl = None

# Find petal application
s = Seeker('-dos-','DOStest')
while ptl == None:
    s.seek()
    if role in s.devices:
        ptl = Pyro4.Proxy(s.devices[role]['pyro_uri'])
        break
    time.sleep(1)

# get configuration info
pos_ids = ptl.get('pos_ids')
print('Using positioners: ', repr(pos_ids))
fid_ids = ptl.get('fid_ids')
print('Using fiducials: ', repr(fid_ids))

ptl.set(anticollision_default = False) # turn off anticollision algorithm for all scheduled moves

print('INITIAL POSITION')
for pos_id in pos_ids:
    print('pos_id: ', ptl.get(posid=pos_id))
    print('expected: ', ptl.expected_current_position_str(pos_id))

# demo script flags
use_standard_syntax = True # enter False to try out the "quick" move syntax
should_flash        = False
should_home         = True
should_direct_dtdp  = False
should_move_xy      = False
should_move_dxdy    = False
should_move_tp      = False
should_move_dtdp    = False
should_test_move    = True

# flash the LEDs
if should_flash:
    canids = pc.listify(ptl.get(key='CAN_ID'),True)[0]
    for canid in canids: # this usage of get method returns a list with that value for all the positioners
        ptl.communicate('set_led', canid,'on')
    time.sleep(1)
    for canid in canids:
        ptl.communicate('set_led', canid,'off')

# run the various move types
if should_home:
    print('MOVE: homing')
    # ptl.set(key='CREEP_TO_LIMITS',value=True) # to force only creeping to hard stops
    ptl.request_homing(pos_ids)
    ptl.schedule_send_and_execute_moves()
else:
    ptl.set(key=['POS_T','POS_P'],value=[-180,180]) # faking having just homed

# Here I define a common wrapper function that illustrates the syntax for generating move
# requests and then executing them on the positioners. There are several distinct syntaxes, all
# shown here, and I put in copious comments to help explain what is going on in each one.
def general_move(command,targets):
    targets = pc.listify2d(targets)
    for target in targets:
        print('MOVE: ' + command + ' (' + str(target[0]) + ',' + str(target[1]) + ')')
        log_note = 'demo ' + command + ' point ' + str(targets.index(target))
        if use_standard_syntax:
            
            # The standard syntax has four basic steps: request targets, schedule them, send them to positioners,
            # and execute the moves. See comments in petal.py for more detail. The requests are formatted as
            # dicts of dicts, where the primary keys are positioner ids, and then each subdictionary describes
            # the move you are requesting for that positioner.
        
            requests = {}
            if command == 'direct_dTdP':
                
                # The 'direct_dTdP' is for 'expert' use.
                # It instructs the theta and phis axes to simply rotate by some argued angular distances, with
                # no regard for anticollision or travel range limits.

                for pos_id in pos_ids:                
                    requests[pos_id] = {'target':target, 'log_note':log_note}
                ptl.request_direct_dtdp(requests)

            else:

                # Here is the request syntax for general usage.
                # Any coordinate system can be requested, range limits are respected, and anticollision can be calculated.

                for pos_id in pos_ids: 
                    requests[pos_id] = {'command':command, 'target':target, 'log_note':log_note}
                    
                ptl.request_targets(requests) # this is the general use function, where 
            
            # For the three steps below, petal.py also provides a wrapper function called 'schedule_send_and_execute_moves'.
            # That function does them all in one line of syntax. But here I show them separately, for illustrative clarity
            # of what is happening in the software. This is important to understand, because there are some potential use
            # cases where we will indeed want to do these three operations separately.
            ptl.schedule_moves()    # all the requests get scheduled, with anticollision calcs, generating a unique table of scheduled shaft rotations on theta and phi axes for every positioner 
            ptl.send_move_tables()  # the tables of scheduled shaft rotations are sent out to all the positioners over the CAN bus
            ptl.execute_moves()     # the synchronized start signal is sent, so all positioners start executing their scheduled rotations in sync
            # ptl.schedule_send_and_execute_moves() # alternative wrapper which just does the three things above in one line
            
        else:

            # This 'quick' syntax is mostly intended for manual operations, or simple operations on test stations.
            # You can send the command to multiple pos_ids simultaneously, but all the positioners receive the same command and target coordinates.
            # (So it generally would make no sense to use these in any global coordinate system, where all the positioners are in different places.)

            if command == 'direct_dTdP':
                ptl.quick_direct_dtdp(pos_ids, target, log_note) # expert, no limits or anticollision
            else:
                ptl.quick_move(pos_ids, command, target, log_note) # general, with limits and anticollision

# now do the requested move sequences
if should_direct_dtdp:
    general_move('direct_dTdP',[[270,0], [0,-60], [-180,30]])

if should_move_xy:
    general_move('posXY',[[-4,-4], [-4,0], [-4,4], [0,-4], [0,0], [0,4], [4,-4], [4,0], [4,4]])

if should_move_dxdy:
    general_move('dXdY',[[2.5,0], [2.5,0], [-10,0], [5,-5], [0,5]])

if should_move_tp:
    general_move('posTP',[[-90,90], [0,90], [90,90], [0,180]])

if should_move_dtdp:
    general_move('dTdP',[[180,0], [-90,-90],[180,60],[-90,30]]) # this is different from 'direct' dTdP. here, the dtdp is treated like any other general move, and anticollision calculations are allowed

if should_test_move:
    request = {}
    offset = 0.0
    for p in pos_ids:
        request[p] = {'command' : 'obsXY', 'target' : [-10.0+offset, 10.0-offset]}
        offset += 1.0

    print('move request: %s' % repr(request))
    try:
        retcode = ptl.move(request)
        print('move returns %s' % str(retcode))
    except Exception as e:
        print('Exception in move: %s' % str(e))

    # relative move
    request = {}
    offset = 0.1
    for p in pos_ids:
        request[p] = {'command' : 'dXdY', 'target' : [0.0+offset, 0.0-offset]}
        offset += 0.05

    print('move request: %s' % repr(request))
    try:
        retcode = ptl.move(request)
        print('move (dXdY) returns %s' % str(retcode))
    except Exception as e:
        print('Exception in move (dXdY(: %s' % str(e))

    
