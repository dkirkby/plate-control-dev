#Two neighbor positioner anticollision test 
#Kevin Fanning 08/08/2018

import time
import sys
sys.path.append('../')
import petal

posids = {'left': 'M00131', 'right': 'M00137'} #Change this
posid_list = [posids['left'],posids['right']]
petalid = 48 #change this
fifids = []

ptl = petal.Petal(petalid, posid_list, fifids)
ptl.anticollision_default = 'adjust'

case_1 = {'command':'obsTP','type': 'Type II', 'left': [0,0], 'right': [190,0]}
case_2 = {'command':'obsTP','type': 'No', 'left': [0,145], 'right': [180,45]}

def assemble_requests(case):
    log_note = case['type'] + ' collision test'
    requests = {}
    for side in ['left','right']:
        requests[posids[side]] = {'command':case['command'],'target':case[side],'log_note':log_note}
    return requests
    
def move(requests):
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves()
    
if __name__ == '__main__':
    sleep_time = 5
    for i in range(2):
        print('rehoming')
        ptl.request_homing(posid_list)
        time.sleep(sleep_time)
        request = assemble_requests(case_1)
        print(request[posid_list[0]]['log_note'])
        move(request)
        time.sleep(sleep_time)
        print('rehoming')
        ptl.request_homing(posid_list)
        time.sleep(sleep_time)
        request = assemble_requests(case_2)
        print(request[posid_list[0]]['log_note'])
        move(request)
        time.sleep(sleep_time)
