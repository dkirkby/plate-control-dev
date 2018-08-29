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
import matplotlib as mpl
from matplotlib.patches import Polygon
from matplotlib.collections import PatchCollection
import configobj
import time

"""Run generate__fake_pos_targets.py to take the random pos pars and collisionless targets list. 
"""
n_pos_limit=500
n_targets=100
fidids_12 = ['P077']#,'F001','F010','F011','F017','F021','F022','F025','F029','F074','P022','P057']
fidids = fidids_12
petal_id = 666
input_pars='repositioning_sim_pars.csv'
output_file='repositioning_sim3.pdf'
output_result='repositioning_sim3.out'
# timing helper wrapper function
n_stats_lines = 15
statsfile = 'stats_petalcode'

filename_collision=os.getenv('FP_SETTINGS_PATH')+'/collision_settings/_collision_settings_DEFAULT.conf'
config=configobj.ConfigObj(filename_collision,unrepr=True)
ptl_temp=[]
b=config['KEEPOUT_PTL']
for i in range(len(b[0])):
    ptl_temp.append([b[0][i],b[1][i]])
ptl_polygon = Polygon(ptl_temp, True)

gfa_temp=[]
b=config['KEEPOUT_GFA']
for i in range(len(b[0])):
    gfa_temp.append([b[0][i],b[1][i]])
gfa_polygon = Polygon(gfa_temp, True)

theta_temp=[]
b=config['KEEPOUT_THETA']
for i in range(len(b[0])):
    theta_temp.append([b[0][i],b[1][i]])
theta_polygon = Polygon(theta_temp, True)

phi_temp=[]
b=config['KEEPOUT_PHI']
for i in range(len(b[0])):
    phi_temp.append([b[0][i],b[1][i]])
phi_polygon = Polygon(phi_temp, True)


def cProfile_wrapper(evaluatable_string):
    print(evaluatable_string)
    cProfile.run(evaluatable_string,statsfile)
    p = pstats.Stats(statsfile)
    p.strip_dirs()
    p.sort_stats('tottime')
    p.print_stats(n_stats_lines)

###############################
### Read the pars #######
##########################
positioners = Table.read(input_pars,format='ascii.csv',header_start=0,data_start=1,data_end=n_pos_limit+1)
posids=[positioners[i]['posid'] for i in range(len(positioners))]
n_pos=len(posids)
print(n_pos,' pos read')
# Generate a simulated petal
# timed test sequence
anticollision = 'adjust'
cProfile_wrapper("ptl = petal.Petal(petal_id, posids, fidids, simulator_on=True, db_commit_on=False, local_commit_on=True,verbose=True,anticollision="+anticollision+")")




##########################################
# Make fake positioner array in a petal 
##########################################
offsetX_arr=[]
offsetY_arr=[]
requests={}
for i in range(len(posids)):
    posid=posids[i]
    model = ptl.posmodels[posid]
    state = model.state
    postrans=model.trans
    ptl.posmodels[posid].state.store('OFFSET_X',positioners[i]['OFFSET_X'])
    ptl.posmodels[posid].state.store('OFFSET_Y',positioners[i]['OFFSET_Y'])
    offsetX_arr.append(float(positioners[i]['OFFSET_X']))
    offsetY_arr.append(float(positioners[i]['OFFSET_Y']))
    ptl.posmodels[posid].state.store('OFFSET_T',positioners[i]['OFFSET_T'])
    ptl.posmodels[posid].state.store('OFFSET_P',positioners[i]['OFFSET_P'])
    ptl.posmodels[posid].state.store('LENGTH_R1',positioners[i]['LENGTH_R1'])
    ptl.posmodels[posid].state.store('LENGTH_R2',positioners[i]['LENGTH_R2'])
    ptl.posmodels[posid].state.store('CTRL_ENABLED',True)
    ptl.posmodels[posid].state.store('POS_P',170)
    ptl.posmodels[posid].state.store('POS_T',0)

# timed test sequence
cProfile_wrapper('ptl.request_homing(posids)')
cProfile_wrapper('ptl.schedule_send_and_execute_moves()')


#######################################
##  Request Targets###
#######################################


#####################################
#### Plot petal metrology (positioner centers) and targets##########
######################################
ps=True
if ps:
    pp = PdfPages(output_file)

#plt.figure(0,figsize=(9.5,9.5))
font = {'family' : 'sans-serif',
        'weight' : 'normal',
        'size'   : 9}
plt.rc('font', **font)
head_width=0.1
head_length=0.15
    

f = open(output_result, 'w')
f.close()

for l in range(n_targets):
    f = open(output_result, 'a')
    t0=time.time()
    offsetX_arr=[]
    offsetY_arr=[]
    requests={}
    target_x=[]
    target_y=[]
    for i in range(len(posids)):
        posid=posids[i]
        model = ptl.posmodels[posid]
        state = model.state
        postrans=model.trans
        offsetX_arr.append(float(positioners[i]['OFFSET_X']))
        offsetY_arr.append(float(positioners[i]['OFFSET_Y']))
        cmd='posTP_this=postrans.obsTP_to_posTP([float(positioners[i]["target_t'+str(l+1)+'"]),float(positioners[i]["target_p'+str(l+1)+'"])])'
        exec(cmd)
        posXY_this=postrans.posTP_to_posXY(posTP_this)
        requests[posid] = {'command':'posXY', 'target':posXY_this, 'log_note':'Reach target posXY:'+str(posXY_this[0])+','+str(posXY_this[1])}
        cmd='target_x.append(float(positioners[i]["target_x'+str(l+1)+'"]))'
        exec(cmd)
        cmd='target_y.append(float(positioners[i]["target_y'+str(l+1)+'"]))'
        exec(cmd)
    plt.figure(1,figsize=(9.5,9.5))
    plt.rc('font', **font)
    plt.subplot(111)
    axes = plt.gca()
    axes.set_xlim([0,450])
    axes.set_ylim([0,450])

    plt.plot(target_x,target_y,'b+',label='target',markersize=3)
    for i in range(len(offsetX_arr)):
        plt.text(offsetX_arr[i],offsetY_arr[i],posids[i],fontsize=2)
    plt.xlabel('X')
    plt.ylabel('Y')
    plt.legend(loc=1)
    plt.plot(offsetX_arr,offsetY_arr,'r+',label='center',markersize=3)
    cProfile_wrapper('ptl.request_targets(requests)')
    cProfile_wrapper('ptl.schedule_send_and_execute_moves()')

    x_final_arr=[]
    y_final_arr=[]
    patches=[]
    patches.append(ptl_polygon)
    patches.append(gfa_polygon)
    for i in range(len(posids)):
        posid=posids[i]
        pos_t=ptl.posmodels[posid].state.read('POS_T')
        pos_p=ptl.posmodels[posid].state.read('POS_P')
        offset_X=ptl.posmodels[posid].state.read('OFFSET_X')
        offset_Y=ptl.posmodels[posid].state.read('OFFSET_Y')
        r1=ptl.posmodels[posid].state.read('LENGTH_R1')
        r2=ptl.posmodels[posid].state.read('LENGTH_R2')
        postrans=ptl.posmodels[posid].trans
        obs_tp=postrans.posTP_to_obsTP([pos_t,pos_p])
        #xy=postrans.obsTP_to_flatXY(obs_tp)
        xy=postrans.posTP_to_obsXY([pos_t,pos_p])
        x_final_arr.append(xy[0])
        y_final_arr.append(xy[1])

        theta_polygon = Polygon(theta_temp, True)
        t_theta = mpl.transforms.Affine2D().rotate_deg(obs_tp[0]) + mpl.transforms.Affine2D().translate(offset_X,offset_Y)
        theta_polygon.set_transform(t_theta)
        patches.append(theta_polygon)

        phi_polygon = Polygon(phi_temp, True)
        t_phi=mpl.transforms.Affine2D().rotate_deg(obs_tp[0]+obs_tp[1]) +  mpl.transforms.Affine2D().translate(offset_X+r1*np.cos(np.pi*obs_tp[0]/180.),offset_Y+r1*np.sin(np.pi*obs_tp[0]/180.))
        phi_polygon.set_transform(t_phi)
        patches.append(phi_polygon)

    p = PatchCollection(patches, cmap=mpl.cm.jet, alpha=0.4)
    axes.add_collection(p)
    plt.scatter(x_final_arr,y_final_arr,s=10,c='g')



    if ps:
        pp.savefig()


    plt.close()

#############################
    offset_x_arr=[]
    offset_y_arr=[]
    offset_all_arr=[]
    for k in range(len(posids)):
        posid=posids[k]
        pos_t=ptl.posmodels[posid].state.read('POS_T')
        pos_p=ptl.posmodels[posid].state.read('POS_P')
        postrans=ptl.posmodels[posid].trans
        #obs_tp=postrans.posTP_to_obsTP([pos_t,pos_p])
        #xy=postrans.obsTP_to_flatXY(obs_tp)
        xy=postrans.posTP_to_obsXY([pos_t,pos_p])
        offset_x_arr.append(xy[0]-target_x[k])
        offset_y_arr.append(xy[1]-target_y[k])
        offset_all_arr.append(np.sqrt((xy[0]-target_x[k])**2+(xy[1]-target_y[k])**2))
    if offset_x_arr:
        index=np.where(np.array(offset_all_arr)>0.02)
        ind=index[0].tolist()
        if ind:
            n_not_reach=len(ind)
            print(str(n_not_reach)+' positioners not reach targets')
            for i in range(len(ind)):
                print(posids[ind[i]],offset_all_arr[ind[i]])
    t1=time.time()
    out_str=str(t1-t0)+'  ,  '+str(n_not_reach)+ ' \n'
    f.write(out_str)
    f.close()
if ps:
    pp.close()

