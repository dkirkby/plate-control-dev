import time
import numpy as np
import sys,os
sys.path.append(os.path.abspath('../'))
import petal
"""Script for moving positioner in a fashion characteristic of actual operation.
Intent is to have a repeatable set of actions for measuring the max, idle, and average
power consumption values.
"""
time0=time.time()

# initialization
posids14=[578,907,580,904,603,908,915,14,143,912,913,914,275,596,590,921,665,600,537,219,604,606,159,608,911,
166,103,40,107,876,175,112,625,563,820,53,567,568,916,252] 
posids16=[449,66,1003,68,406,199,568,13,79,144,594,19,149,598,279,991,610,354,998,999,583,555,1006,179,185,769,61,574]
posids15=[385,264,10,12,909,535,280,414,672,240,424,937,941,439,570,223,446,995,67,1014,584,588,335,208,318,
340,597,1013,220,95,352,251,356,613,358,873,874,619]
posids10=[384, 701, 198, 327, 266, 336, 476, 93, 490, 493, 623, 626, 692, 502,376, 505, 506, 508,330]
posids17=[896,897,770,1155,140,269,1171,1172,1173,1175,1176,1177,1178,495,1180,1181,1182,1183,161,675,
556,176,883,438,443,453,582,332,716,206,723,724,607,481,482,485,997,1002,620,494,1007,1008,488,1010,1139,891,510]
posids12=[3970,3563,1029,272,18,2579,1045,919,920,380,3997,927,1315,1064,3369,1068,302,3933,50,3049,310,55,57]#,
#1082,319,322,1349,73,1098,337,83,85,221,96,3937,996,229,230,361,234,363,3437,1518,375,250,1148,3580,3310,1877]
posids22=[4294,1219,1220,2630,1223,1035,2130,2324,2218,1367,2203,3420,1254,870,1192,3241,1962,2216,3442,1012,2615,2041,
1723,2365]
posids23=[1024,256,342,341,1290,365,22,2234,4121,158,58,806,170,43,44,431,177,309,183,314,59,60,64,65,329,207,211,213,
86,215,88,217,218,91,349,224,1506,483,4069,188,109,369,882,1011,631,1528,859]
posids11=[1760,2179,1753,1685,3988,1607,1337,1274,3083,3812]
posids13=[1634,1019,1039,1353,1481,1647,1199,2124,1170,1238,1047,31,2188,1503]
posids=posids14#+posids15+posids16+posids17+posids12 # V2
#posids=posids+posids23+posids22+posids10+posids13+posids11
print('Number of positioners: ',len(posids))
#sys,exit()
#posids=[384, 701, 198, 327, 266, 336, 476, 93]

#, 231, 490, 493, 623, 626, 692, 502,376, 505, 506, 508,330]
''', 18, 19, 22, 40, 43, 44, 50, 53, 55, 57, 58, 59, 60, 61, 64, 65, 66, 67, 68, 69, 73,
79, 83, 85, 86, 88, 91, 93, 95, 96, 99, 103, 107, 109, 112, 140, 143, 144, 149, 158, 159, 161, 166, 170, 175,
176, 177, 179, 183, 185, 188, 198, 199, 206, 207, 208, 211, 213, 215, 217, 218, 219, 220, 221, 223, 224, 229,
230, 231, 234, 240, 245, 250, 251, 252, 256, 264, 266, 269, 272, 275, 279, 280, 302, 309, 310, 314, 318, 319,
321, 322, 327, 329, 330, 332, 335, 336, 337, 340, 341, 342, 349, 352, 354, 356, 358, 361, 363, 365, 369, 370,
375, 376, 380, 384, 385, 406, 414, 424, 431, 438, 439, 443, 446, 449, 453, 476, 481, 482, 483, 485, 488, 490,
493, 494, 495, 502, 505, 506, 508, 510, 530, 531, 533, 535, 536, 537, 555, 556, 563, 567, 568, 570, 574, 578,
580, 582, 583, 584, 586, 588, 590, 594, 596, 597, 598, 600, 603, 604, 606, 607, 608, 610, 613, 617, 619, 620,
623, 625, 626, 631, 665, 672, 675, 692, 701, 716, 723, 724, 763, 764, 769, 770, 806, 820, 870, 873, 874, 876,
877, 879, 880, 881, 882, 883, 884, 886, 891, 895, 896, 897, 904, 907, 908, 909, 911, 912, 913, 914, 915, 916,
919, 920, 921, 922, 927, 937, 941, 991, 995, 996, 997, 998, 999, 1002, 1003, 1004, 1006, 1007, 1008, 1010,
1011, 1012, 1013, 1014, 1015, 1024, 1029, 1035, 1045, 1064, 1068, 1082, 1098, 1139, 1148, 1155, 1171, 1172,
1173, 1175, 1176, 1177, 1178, 1180, 1181, 1182, 1183, 1192, 1219, 1220, 1223, 1254, 1290, 1315, 1349, 1367,
1506, 1518, 1528, 1723, 1877, 1962, 2041, 2130, 2203, 2216, 2218, 2234, 2324, 2365, 2579, 2615, 2630, 3049,
3241, 3310, 3369, 3420, 3437, 3442, 3563, 3580, 3933, 3937, 3970, 3997, 4069, 4121, 4294]
'''
posids=['M'+str(p).zfill(5) for p in posids]

fidids = []
petal_id = 30
ttt=str(time.time()-time0); print('main 0 '+ttt)
ptl = petal.Petal(petal_id, posids, fidids, simulator_on=True, local_commit_on=False)
ptl.anticollision_default = True # turn off anticollision algorithm for all scheduled moves
ttt=str(time.time()-time0)
print('main 1 '+ttt)
# test settings
should_home = True
n_targets = 10
n_corrections = 2
fvc_pause = 1 # seconds to emulate waiting for an FVC image to be taken and processed
ttt=str(time.time()-time0)
print('main 2 '+ttt)
# generate target points set
grid_max_radius = 2.4 # mm
grid_min_radius = 0.4 # mm
r = np.random.uniform(-grid_max_radius,grid_max_radius,n_targets)
t = np.random.uniform(-180,180,n_targets)
x = r*np.cos(np.deg2rad(t))
y = r*np.sin(np.deg2rad(t))
targets = [[x[i],y[i]] for i in range(len(x))]
ttt=str(time.time()-time0)
print('main 3 '+ttt)
print('Targets:',targets)

# generate simulated error values for correction moves
corrections = []
for move in range(len(targets)):
    corrections.append([])
    for submove in range(n_corrections):
        if submove == 0:
            max_corr = 0.100
        else:
            max_corr = 0.025
        dxdy = np.random.uniform(-max_corr,max_corr,2)
        corrections[move].append(dxdy.tolist())
ttt=str(time.time()-time0)
print('main 4 ')        
# define in-between targets location (simulates anticollision extra moves)
between_TP = [0,90]

# homing of positioner, if necessary
if should_home:
    print('Homing...')
    print('>> calling request_homing')
    ptl.request_homing(posids)
    print('>> calling schedule_send_and_execute')
    ptl.schedule_send_and_execute_moves()
    print('Homing complete.')
#sys.exit()
input('Press enter to begin move sequence...')
for move in range(len(targets)):
    target = targets[move]
    print('Simulated target ' + str(move + 1) + ' of ' + str(len(targets)) + ': moving to (x,y) = (' + str(target[0]) + ',' + str(target[1]) + ')')
    
    log_note = 'anticollision sim in-between move'
    requests = {}
    for posid in posids: 
        requests[posid] = {'command':'posTP', 'target':between_TP, 'log_note':log_note}
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves()    
    
    log_note = 'powertest target ' + str(move + 1)
    requests = {}
    for posid in posids: 
        requests[posid] = {'command':'posXY', 'target':target, 'log_note':log_note}
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves()
    time.sleep(fvc_pause)

    correction = corrections[move]
    for corr in range(len(correction)):
        dxdy = correction[corr]
        print('  ... simulated correction move ' + str(corr + 1) + ' of ' + str(range(len(correction))) + ': moving by (dx,dy) = (' + str(dxdy[0]) + ',' + str(dxdy[1]) + ')')
        log_note = 'powertest target ' + str(move + 1) + ' corr ' + str(corr + 1)
        requests = {}
        for posid in posids: 
            requests[posid] = {'command':'dXdY', 'target':dxdy, 'log_note':log_note}
        ptl.request_targets(requests)
        ptl.schedule_send_and_execute_moves()
        time.sleep(fvc_pause)
        
