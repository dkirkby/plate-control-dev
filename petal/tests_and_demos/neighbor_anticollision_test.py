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
should_anneal = False


case_1 = {'command':'obsTP','type': 'Type II', 'left': [180,20], 'right': [-10,10]}
case_2 = {'command':'obsTP','type': 'No', 'left': [0,45], 'right': [90,45]}
case_3 = {'command':'obsTP','type': 'Type II', 'left': [180,20], 'right': [-20,10]}


def assemble_requests(case):
    log_note = case['type'] + ' collision test'
    requests = {}
    for side in ['left','right']:
        requests[posids[side]] = {'command':case['command'],'target':case[side],'log_note':log_note}
    return requests
    
def move(requests):
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves(should_anneal = should_anneal)
    
if __name__ == '__main__':
    sleep_time = 1
    print('rehoming')
    ptl.request_homing(posid_list)
    ptl.schedule_send_and_execute_moves(should_anneal = False)
    time.sleep(sleep_time)
    for i in range(3):
        request = assemble_requests(case_1)
        print(request[posid_list[0]]['log_note'])
        move(request)
        time.sleep(sleep_time)
        request = assemble_requests(case_2)
        print(request[posid_list[0]]['log_note'])
        move(request)
        time.sleep(sleep_time)
