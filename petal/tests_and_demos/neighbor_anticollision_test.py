#Two neighbor positioner anticollision test 
#Kevin Fanning 08/08/2018

import time
import sys
sys.path.append('../')
import petal

posids = {'left': 'M00137', 'right': 'M00138'} #Change this
posid_list = [posids['left'],posids['right']
petalid = 48 #change this
fifids = None

ptl = petal.Petal(petalid, posid_list, fifids)
ptl.anticollision_default = 'adjust'

case_1 = {'command':'obsTP','type': 'Type II', 'left': [0,0], 'right', [190,0]}
case_2 = {'command':'obsTP','type': 'Interference', 'left': [0,0], 'right', [180,0]}

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
    for i in range(3):
        ptl.request_rehoming(posids)
        time.sleep(sleep_time)
        request = assemble_requests(case1)
        print(request['log_note'])
        time.sleep(sleep_time)
        ptl.request_rehoming(posids)
        time.sleep(sleep_time)
        request = assemble_requests(case2)
        print(request['log_note'])
        time.sleep(sleep_time)
        