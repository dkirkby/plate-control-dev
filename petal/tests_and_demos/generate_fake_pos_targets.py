import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
import petal
import cProfile
import pstats
from astropy.table import Table
import numpy as np
import pdb
import posconstants as pc
import postransforms
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import *

"""Timing test script, all done in simulation mode, with no database commits.
"""

# some sample lists of positioners and fiducials to use
posids_50 = ['M00001','M00002','M00003','M00004','M00005','M00006','M00008','M00009','M00010','M00011','M00012','M00013','M00014','M00015','M00016','M00017','M00018','M00019','M00020','M00021','M00022','M00023','M00024','M00026','M00027','M00028','M00029','M00032','M00033','M00034','M00035','M00036','M00037','M00038','M00039','M00043','M00044','M00047','M00048','M00049','M00050','M00051','M00053','M00055','M00056','M00057','M00058','M00059','M00060','M00061']
posids_100 = ['M00001', 'M00002', 'M00003', 'M00004', 'M00005', 'M00006', 'M00008', 'M00009', 'M00010', 'M00011', 'M00012', 'M00013', 'M00014', 'M00015', 'M00016', 'M00017', 'M00018', 'M00019', 'M00020', 'M00021', 'M00022', 'M00023', 'M00024', 'M00026', 'M00027', 'M00028', 'M00029', 'M00032', 'M00033', 'M00034', 'M00035', 'M00036', 'M00037', 'M00038', 'M00039', 'M00043', 'M00044', 'M00047', 'M00048', 'M00049', 'M00050', 'M00051', 'M00053', 'M00055', 'M00056', 'M00057', 'M00058', 'M00059', 'M00060', 'M00061', 'M00062', 'M00063', 'M00064', 'M00065', 'M00066', 'M00067', 'M00068', 'M00069', 'M00071', 'M00072', 'M00073', 'M00074', 'M00075', 'M00077', 'M00078', 'M00082', 'M00083', 'M00084', 'M00085', 'M00086', 'M00087', 'M00088', 'M00091', 'M00093', 'M00094', 'M00095', 'M00096', 'M00098', 'M00099', 'M00100', 'M00103', 'M00104', 'M00105', 'M00106', 'M00107', 'M00108', 'M00109', 'M00111', 'M00112', 'M00114', 'M00116', 'M00118', 'M00119', 'M00120', 'M00123', 'M00124', 'M00126', 'M00127', 'M00131', 'M00132']
posids_250 = ['M00001', 'M00002', 'M00003', 'M00004', 'M00005', 'M00006', 'M00008', 'M00009', 'M00010', 'M00011', 'M00012', 'M00013', 'M00014', 'M00015', 'M00016', 'M00017', 'M00018', 'M00019', 'M00020', 'M00021', 'M00022', 'M00023', 'M00024', 'M00026', 'M00027', 'M00028', 'M00029', 'M00032', 'M00033', 'M00034', 'M00035', 'M00036', 'M00037', 'M00038', 'M00039', 'M00043', 'M00044', 'M00047', 'M00048', 'M00049', 'M00050', 'M00051', 'M00053', 'M00055', 'M00056', 'M00057', 'M00058', 'M00059', 'M00060', 'M00061', 'M00062', 'M00063', 'M00064', 'M00065', 'M00066', 'M00067', 'M00068', 'M00069', 'M00071', 'M00072', 'M00073', 'M00074', 'M00075', 'M00077', 'M00078', 'M00082', 'M00083', 'M00084', 'M00085', 'M00086', 'M00087', 'M00088', 'M00091', 'M00093', 'M00094', 'M00095', 'M00096', 'M00098', 'M00099', 'M00100', 'M00103', 'M00104', 'M00105', 'M00106', 'M00107', 'M00108', 'M00109', 'M00111', 'M00112', 'M00114', 'M00116', 'M00118', 'M00119', 'M00120', 'M00123', 'M00124', 'M00126', 'M00127', 'M00131', 'M00132', 'M00137', 'M00138', 'M00140', 'M00142', 'M00143', 'M00144', 'M00147', 'M00149', 'M00151', 'M00152', 'M00153', 'M00157', 'M00158', 'M00159', 'M00160', 'M00161', 'M00162', 'M00164', 'M00165', 'M00166', 'M00169', 'M00170', 'M00171', 'M00172', 'M00174', 'M00175', 'M00176', 'M00177', 'M00178', 'M00179', 'M00180', 'M00181', 'M00182', 'M00183', 'M00184', 'M00185', 'M00186', 'M00187', 'M00188', 'M00189', 'M00190', 'M00191', 'M00192', 'M00194', 'M00195', 'M00196', 'M00197', 'M00198', 'M00199', 'M00201', 'M00202', 'M00203', 'M00204', 'M00205', 'M00206', 'M00207', 'M00208', 'M00209', 'M00210', 'M00211', 'M00213', 'M00214', 'M00215', 'M00216', 'M00217', 'M00218', 'M00219', 'M00220', 'M00221', 'M00223', 'M00224', 'M00226', 'M00228', 'M00229', 'M00230', 'M00231', 'M00232', 'M00233', 'M00234', 'M00235', 'M00236', 'M00238', 'M00239', 'M00240', 'M00241', 'M00242', 'M00243', 'M00244', 'M00245', 'M00246', 'M00247', 'M00248', 'M00250', 'M00251', 'M00252', 'M00253', 'M00254', 'M00255', 'M00256', 'M00258', 'M00262', 'M00264', 'M00265', 'M00266', 'M00267', 'M00268', 'M00269', 'M00270', 'M00272', 'M00273', 'M00274', 'M00275', 'M00276', 'M00277', 'M00278', 'M00279', 'M00280', 'M00286', 'M00292', 'M00302', 'M00303', 'M00304', 'M00305', 'M00307', 'M00308', 'M00309', 'M00310', 'M00311', 'M00312', 'M00313', 'M00314', 'M00315', 'M00317', 'M00318', 'M00319', 'M00320', 'M00321', 'M00322', 'M00323', 'M00324', 'M00326', 'M00327', 'M00328', 'M00329', 'M00330', 'M00331', 'M00332', 'M00333', 'M00334', 'M00335']
posids_500 = ['M00001','M00002','M00003','M00004','M00005','M00006','M00008','M00009','M00010','M00011','M00012','M00013','M00014','M00015','M00016','M00017','M00018','M00019','M00020','M00021','M00022','M00023','M00024','M00026','M00027','M00028','M00029','M00032','M00033','M00034','M00035','M00036','M00037','M00038','M00039','M00043','M00044','M00047','M00048','M00049','M00050','M00051','M00053','M00055','M00056','M00057','M00058','M00059','M00060','M00061','M00062','M00063','M00064','M00065','M00066','M00067','M00068','M00069','M00071','M00072','M00073','M00074','M00075','M00077','M00078','M00082','M00083','M00084','M00085','M00086','M00087','M00088','M00091','M00093','M00094','M00095','M00096','M00098','M00099','M00100','M00103','M00104','M00105','M00106','M00107','M00108','M00109','M00111','M00112','M00114','M00116','M00118','M00119','M00120','M00123','M00124','M00126','M00127','M00131','M00132','M00137','M00138','M00140','M00142','M00143','M00144','M00147','M00149','M00151','M00152','M00153','M00157','M00158','M00159','M00160','M00161','M00162','M00164','M00165','M00166','M00169','M00170','M00171','M00172','M00174','M00175','M00176','M00177','M00178','M00179','M00180','M00181','M00182','M00183','M00184','M00185','M00186','M00187','M00188','M00189','M00190','M00191','M00192','M00194','M00195','M00196','M00197','M00198','M00199','M00201','M00202','M00203','M00204','M00205','M00206','M00207','M00208','M00209','M00210','M00211','M00213','M00214','M00215','M00216','M00217','M00218','M00219','M00220','M00221','M00223','M00224','M00226','M00228','M00229','M00230','M00231','M00232','M00233','M00234','M00235','M00236','M00238','M00239','M00240','M00241','M00242','M00243','M00244','M00245','M00246','M00247','M00248','M00250','M00251','M00252','M00253','M00254','M00255','M00256','M00258','M00262','M00264','M00265','M00266','M00267','M00268','M00269','M00270','M00272','M00273','M00274','M00275','M00276','M00277','M00278','M00279','M00280','M00286','M00292','M00302','M00303','M00304','M00305','M00307','M00308','M00309','M00310','M00311','M00312','M00313','M00314','M00315','M00317','M00318','M00319','M00320','M00321','M00322','M00323','M00324','M00326','M00327','M00328','M00329','M00330','M00331','M00332','M00333','M00334','M00335','M00336','M00337','M00339','M00340','M00341','M00342','M00344','M00345','M00347','M00348','M00349','M00350','M00351','M00352','M00353','M00354','M00356','M00357','M00358','M00359','M00360','M00361','M00362','M00363','M00364','M00365','M00366','M00367','M00368','M00369','M00370','M00371','M00372','M00373','M00375','M00376','M00379','M00380','M00383','M00384','M00385','M00386','M00389','M00390','M00391','M00392','M00405','M00406','M00407','M00409','M00410','M00411','M00412','M00413','M00414','M00415','M00416','M00417','M00418','M00419','M00420','M00421','M00422','M00424','M00425','M00427','M00428','M00429','M00431','M00432','M00433','M00434','M00435','M00436','M00437','M00438','M00439','M00440','M00441','M00442','M00443','M00444','M00445','M00446','M00447','M00448','M00449','M00450','M00451','M00452','M00453','M00461','M00465','M00466','M00467','M00468','M00470','M00474','M00476','M00477','M00478','M00480','M00481','M00482','M00483','M00485','M00486','M00488','M00489','M00490','M00493','M00494','M00495','M00497','M00498','M00501','M00502','M00505','M00506','M00508','M00509','M00510','M00511','M00512','M00524','M00526','M00528','M00529','M00532','M00537','M00539','M00540','M00542','M00567','M00568','M00579','M00580','M00587','M00590','M00592','M00595','M00596','M00597','M00598','M00600','M00601','M00604','M00605','M00606','M00608','M00610','M00611','M00614','M00615','M00616','M00621','M00623','M00625','M00626','M00648','M00665','M00667','M00668','M00669','M00670','M00671','M00672','M00674','M00675','M00680','M00682','M00683','M00684','M00686','M00687','M00688','M00689','M00690','M00691','M00692','M00694','M00695','M00696','M00697','M00699','M00701','M00713','M00714','M00716','M00718','M00719','M00722','M00723','M00724','M00726','M00727','M00728','M00757','M00758','M00759','M00760','M00761','M00762','M00763','M00764','M00765','M00768','M00769','M00770','M00771','M00772','M00773','M00775','M00776','M00820','M00821','M00836','M00838','M00844','M00847','M00869','M00870','M00872','M00873','M00874','M00875','M00876','M00877','M00879','M00880','M00881','M00882','M00883','M00884','M00885','M00886','M00887','M00888','M00889','M00890','M00891','M00892','M00893','M00894','M00895','M00896','M00897','M00898','M00899','M00900']
fidids_12 = ['P077','F001','F010','F011','F017','F021','F022','F025','F029','F074','P022','P057']
# selection of ids
posids = posids_500
fidids = fidids_12
petal_id = 666
output_file='repositioning_sim_pars.csv'
output_file_fid='repositioning_sim_fid_pars.csv'
match_target=True
n_pos=len(posids)
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


def check_collision(ptl,tp_arr):
    posids=list(ptl.posids)
    offsetX_arr=[ptl.get_posfid_val(posids[i],'OFFSET_X') for i in range(len(posids))]
    offsetY_arr=[ptl.get_posfid_val(posids[i],'OFFSET_Y') for i in range(len(posids))]
    print('*******************************************************')
    print('*****  Check if the targets have any collision ********')
    print('*******************************************************')
    pos_checked=[]
    for i in range(len(posids)):
        posid=posids[i]
        pos_checked.append(posid)
        print('******** posid **********',posid)
        tp=tp_arr[i]
        offsetX_this=ptl.get_posfid_val(posids[i],'OFFSET_X')
        offsetY_this=ptl.get_posfid_val(posids[i],'OFFSET_Y')
        postrans=postransforms.PosTransforms(this_posmodel=ptl.posmodels[posid])
        # Check for collision #
        # find neighbours first
        pos_dist=np.sqrt((np.array(offsetX_arr)-offsetX_this)**2+(np.array(offsetY_arr)-offsetY_this)**2)
        index1=np.where(pos_dist <= 11)
        index2=np.where(pos_dist > 0.2)
        index=set(index1[0].tolist()) & set(index2[0].tolist())
        index_neighbour=list(index)
        if index_neighbour:
            for k in range(len(index_neighbour)):
                index_this_neighbour=index_neighbour[k]
                tp_neighbour=tp_arr[index_this_neighbour]
                print('Check if ',posid, ' collides with ',posids[index_this_neighbour])
                #print('tp',tp,'tp_neighbour',tp_neighbour)
                if posids[index_this_neighbour] in pos_checked:
                    pass
                else:
                    case=ptl.collider.spatial_collision_between_positioners(posid, posids[index_this_neighbour],tp, tp_neighbour)
                    if case != pc.case.I:
                        print('~~~~~~~~~~~ Oh, no, a collision! ~~~~~~~~~~~')
                    case=ptl.collider.spatial_collision_with_fixed(posid,tp)
                    if case != pc.case.I:
                        print('~~~~~~~~~~~ Oh, no, a collision with wall! ~~~~~~~~~~~')

ptl = petal.Petal(petal_id, posids, fidids, simulator_on=True, db_commit_on=False, local_commit_on=True,verbose=False, anticollision='adjust')

pos_locs = '../positioner_locations_0530v14.csv'#os.path.join(allsetdir,'positioner_locations_0530v12.csv')
positioners = Table.read(pos_locs,format='ascii.csv',header_start=0,data_start=1)

##########################################
# Make fake positioner array in a petal 
##########################################

seed = 1036
## if seed is defined, create the random state
if seed is not None:
    rand = np.random.RandomState(seed)
else:
    rand = np.random.RandomState()

## Randomize arm lengths based on empirical data
r1s,r2s = get_arm_lengths(n_pos,rand)
## Randomized tp offsets
toffs,poffs = get_tpoffsets(n_pos,rand)
i=0
j=0
offsetX_arr=[]
offsetY_arr=[]
offsetT_arr=[]
offsetP_arr=[]
for row in positioners:
    idnam, typ, xloc, yloc, zloc, qloc, rloc, sloc = row
    if i == n_pos:
        break
    if typ == 'POS':
        offsetX_arr.append(xloc)
        offsetY_arr.append(yloc)
        offsetT_arr.append(toffs[i])
        offsetP_arr.append(poffs[i])
        model = ptl.posmodels[i]
        state = model.state
        ptl.posmodels[i].state.store('OFFSET_X',xloc)
        ptl.posmodels[i].state.store('OFFSET_Y',yloc)
        ## store randomized tp offsets
        ptl.posmodels[i].state.store('OFFSET_T',toffs[i])
        ptl.posmodels[i].state.store('OFFSET_P',poffs[i])
        ## Stored randomized arm lengths
        ptl.posmodels[i].state.store('LENGTH_R1',r1s[i])
        ptl.posmodels[i].state.store('LENGTH_R2',r2s[i])
        ptl.posmodels[i].state.store('CTRL_ENABLED',True)
        ptl.posmodels[i].state.store('POS_P',170)
        ptl.posmodels[i].state.store('POS_T',0)
        #state.write()
        i += 1
    elif typ == 'FIF' or typ == 'GIF':
        fidid = fidids[j]
        state = ptl.fidstates[fidid]
        state.store('Q',float(qloc))
        state.store('S',float(sloc))
        #state.write()
        j +=1
    else:
        print("Type {} didn't match fiducial or positioner!".format(typ))

 
# timed test sequencedd
ptl.request_homing(posids)
ptl.schedule_send_and_execute_moves()

###########################################
## Check if the initial positions collide ##
###########################################
pos_tp_arr=[]
for i in range(len(posids)):
    posid=ptl.posmodels[i].posid
    pos_tp_arr.append([ptl.posmodels[i].state._val['POS_T'],ptl.posmodels[i].state._val['POS_P']])

print('Check Initial Positions Collisions ')
a=check_collision(ptl,pos_tp_arr)

###########################################
# Read Targets
#data format:
#k=fiber number id= a large random integer      RA      dec     x       y       Q       S       Z5      N
###########################################

def read_targets(ptl,target_file):
    f=open(target_file,"r")
    lines=f.readlines()
    loc_assigned=[]
    pos_assigned=[]
    xy_assigned=[]
    x_assigned=[]# x on focalplane
    y_assigned=[]
    qs_assigned=[]
    print('Reading Targets...')
    for x in lines:
        if x.strip() != '-1' and x.strip() and match_target:
            temp=x.split(' ')
            ## Match targets ##
            distance=np.sqrt(np.subtract(np.array(offsetX_arr),float(temp[4]))**2+(np.array(offsetY_arr)-float(temp[5]))**2)
            distance=distance.tolist()
            index=distance.index(min(distance))#
            if min(distance) <=ptl.posmodels[index].state._val['LENGTH_R1']+ptl.posmodels[index].state._val['LENGTH_R2'] :
                if ptl.posmodels[index].posid not in pos_assigned: 
                    loc_assigned.append(temp[0])
                    xy_assigned.append([float(temp[4]),float(temp[5])])
                    x_assigned.append(float(temp[4]))
                    y_assigned.append(float(temp[5]))
                    qs_assigned.append([float(temp[6]),float(temp[7])]) 
                    pos_assigned.append(ptl.posmodels[index].posid)
    f.close()
    return pos_assigned,xy_assigned,x_assigned,y_assigned,qs_assigned



#######################################
##  Request Targets###
#######################################

def assign_targets(ptl,pos_assigned,qs_assigned,x_assigned,y_assigned):
    posids=list(ptl.posids)
    offsetX_arr=[ptl.get_posfid_val(posids[i],'OFFSET_X') for i in range(len(posids))]
    offsetY_arr=[ptl.get_posfid_val(posids[i],'OFFSET_Y') for i in range(len(posids))]
    requests = {}
    target_x=[]   # On focal plane
    target_y=[]
    target_tp=[]
    pos_collide=[]
    for i in range(len(ptl.posmodels)):
        posid=posids[i]
        index_posid=posids.index(posid)
        print('$$$$$$$$$$$$ posid $$$$$$$$$$$$$$' ,posid)
        offsetX_this=ptl.posmodels[i].state._val['OFFSET_X']
        offsetY_this=ptl.posmodels[i].state._val['OFFSET_Y']
        postrans=postransforms.PosTransforms(this_posmodel=ptl.posmodels[i])
        distance=10.
        # Find neighbours
        pos_dist=np.sqrt((np.array(offsetX_arr)-offsetX_this)**2+(np.array(offsetY_arr)-offsetY_this)**2)
        index1=np.where(pos_dist <= 11)
        index2=np.where(pos_dist > 0.2)
        index=set(index1[0].tolist()) &set(index2[0].tolist())
        index_neighbour=list(index)
        print(len(index_neighbour),' neighbours found') 
        while 1:

            if posid in pos_assigned and posid not in pos_collide:  # Target from list
                distance=0.
                index = pos_assigned.index(posid)
                target=qs_assigned[index]
                tp1,unreachable_this=postrans.QS_to_posTP(target) # posTP
                tp=postrans.posTP_to_obsTP(tp1) #obsTP 
                if index_neighbour:
                    for k in range(len(index_neighbour)):
                        index_this_neighbour=index_neighbour[k]
                        if index_this_neighbour+1<=len(target_x): # target already assigned
                            tp_neighbour=target_tp[index_this_neighbour]
                            print('Check if ',posid, ' collides with ',posids[index_this_neighbour])
                            case=ptl.collider.spatial_collision_between_positioners(posid, posids[index_this_neighbour],tp, tp_neighbour)
                            if case != pc.case.I:
                                pos_collide.append(posid)
                                distance=10.
                            else:
                                case=ptl.collider.spatial_collision_with_fixed(posid,tp)
                                if case != pc.case.I:
                                    print('collide')
                                    pos_collide.append(posid)
                                    distance=10. 
                                else:
                                    pass
                if distance<5:
                    target_tp.append(tp)
                    posXY_this=postrans.posTP_to_posXY(tp1)

                    target_x.append(x_assigned[index])
                    target_y.append(y_assigned[index])
                    requests[posid] = {'command':'posXY', 'target':posXY_this, 'log_note':'Reach target posXY:'+str(posXY_this[0])+','+str(posXY_this[1])}
                    break
            else:  # Generate a random target
                xy=rand.uniform(-6, 6, 2)
                xy=xy.tolist()
                tp1,unreachable=postrans.posXY_to_posTP(xy)
                tp=postrans.posTP_to_obsTP(tp1)
                distance=np.sqrt(xy[0]**2+xy[1]**2)
                print('random xy',xy,'distance',distance)
                if distance<=ptl.get_posfid_val(posids[index_posid],'LENGTH_R1')+ptl.get_posfid_val(posids[index_posid],'LENGTH_R2'):  # Make sure it is reachable
                    # Check for collision #
                    # find neighbours first
                    if index_neighbour:
                        for k in range(len(index_neighbour)):
                            index_this_neighbour=index_neighbour[k]
                            if index_this_neighbour+1<=len(target_x): # target already assigned
                                tp_neighbour=target_tp[index_this_neighbour]
                                print('Check if ',posid, ' collides with ',ptl.posmodels[index_this_neighbour].posid)
                                case=ptl.collider.spatial_collision_between_positioners(posid, posids[index_this_neighbour],tp, tp_neighbour)
                                if case != pc.case.I:
                                    distance=10.
                                    print('Oops, collides with ',ptl.posmodels[index_this_neighbour].posid)
                                else:
                                    case=ptl.collider.spatial_collision_with_fixed(posid,tp)
                                    if case != pc.case.I:
                                        distance=10.
                                        print('Oops, collides with wall')
                                    else:
                                        pass
                if distance<=ptl.get_posfid_val(posids[index_posid],'LENGTH_R1')+ptl.get_posfid_val(posids[index_posid],'LENGTH_R2'):
                    print('final xy',xy,'distance',distance)
                    obsXY_this=postrans.posXY_to_obsXY(xy)
                    target_x.append(obsXY_this[0])
                    target_y.append(obsXY_this[1])
                    target_tp.append(tp)  #obsTP
                    requests[posid] = {'command':'posXY', 'target':xy, 'log_note':'Reach target posXY:'+str(xy[0])+','+str(xy[1])}
                    break
    return requests,target_x,target_y,target_tp 



target_dir=os.getenv('FP_SETTINGS_DIR')+'/predefined_positioner_locations/petal_targets/BCahns_realistic_targets/'
count=1
count_limit=10
header='posid,OFFSET_X,OFFSET_Y,OFFSET_T,OFFSET_P,LENGTH_R1,LENGTH_R2'
for target_file in os.listdir(target_dir):
    if target_file.endswith(".txt") and target_file.startswith("tile") and count<=count_limit:
        pos_assigned,xy_assigned,x_assigned,y_assigned,qs_assigned=read_targets(ptl,target_dir+'/'+target_file)
        cmd='requests,target_x'+str(count)+',target_y'+str(count)+',target_tp'+str(count)+'=assign_targets(ptl,pos_assigned,qs_assigned,x_assigned,y_assigned)'
        exec(cmd)
        header=header+',target_x'+str(count)+',target_y'+str(count)+',target_t'+str(count)+',target_p'+str(count)
        count+=1


################################################
########## Output ###########
#############################
f = open(output_file, 'w')
f.write(header+' \n')
for i in range(len(posids)):
    posid=posids[i]
    output=posid
    output=output+', '+str(ptl.get_posfid_val(posid,'OFFSET_X'))
    output=output+', '+str(ptl.get_posfid_val(posid,'OFFSET_Y'))
    output=output+', '+str(ptl.get_posfid_val(posid,'OFFSET_T'))
    output=output+', '+str(ptl.get_posfid_val(posid,'OFFSET_P'))
    output=output+', '+str(ptl.get_posfid_val(posid,'LENGTH_R1'))
    output=output+', '+str(ptl.get_posfid_val(posid,'LENGTH_R2'))
    for j in range(count_limit-1):
        cmd='output=output+", "+str(target_x'+str(j+1)+'[i])+","+str(target_y'+str(j+1)+'[i])+","+str(target_tp'+str(j+1)+'[i][0])+","+str(target_tp'+str(j+1)+'[i][1])'
        exec(cmd)
    output=output+'\n'
    f.write(output)

f.close()

f = open(output_file_fid,'w')
f.write('fidid, Q, S \n')
for j in range(len(fidids)):
    fidid=fidids[j]
    output=fidid
    output=output+', '+str(ptl.fidstates[fidid].read('Q'))+', '+str(ptl.fidstates[fidid].read('S'))+ '\n'
    if int(ptl.fidstates[fidid].read('Q')) !=0:
        f.write(output)

f.close()


