import os
import sys
sys.path.append(os.path.abspath('../'))
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

# Find the conf file
posid1='M00476'
posid2='M00330'
#posid1='M00336'
#posid2='M00305'
posid1='M00623'
posid2='M00502'

use_posxy=True

posids=[posid1,posid2]
ptl = petal.Petal('EM', posids=posids,fidids=[],simulator_on=True, sched_stats_on=True, db_commit_on=False, anticollision='adjust')

filename1=os.getenv('FP_SETTINGS_PATH')+'/pos_settings/unit_'+posid1.strip()+'.conf'
pos_conf1 = configobj.ConfigObj(filename1,unrepr=True)

filename2=os.getenv('FP_SETTINGS_PATH')+'/pos_settings/unit_'+posid2.strip()+'.conf'
pos_conf2 = configobj.ConfigObj(filename2,unrepr=True)

r1=3
r2=3

posXY1=[3.8335692467871247,-3.0713578893438562]
posXY2=[2.103229825396454,-4.305786692300427]
posTP1=[pos_conf1['POS_T'],pos_conf1['POS_P']]
posTP2=[pos_conf2['POS_T'],pos_conf2['POS_P']]

posmodel1=ptl.posmodels[posid1]
posmodel2=ptl.posmodels[posid2]
trans1 = ptl.posmodels[posid1].trans
trans2 = ptl.posmodels[posid2].trans
#import pdb;pdb.set_trace()

if use_posxy:
    obs_tp1=trans1.posTP_to_obsTP(trans1.posXY_to_posTP(posXY1)[0])
    obs_tp2=trans2.posTP_to_obsTP(trans2.posXY_to_posTP(posXY2)[0])
else:
    obs_tp1=trans1.posTP_to_obsTP(posTP1)
    obs_tp2=trans2.posTP_to_obsTP(posTP2)


offset_X1=pos_conf1['OFFSET_X']
offset_Y1=pos_conf1['OFFSET_Y']

offset_X2=pos_conf2['OFFSET_X']
offset_Y2=pos_conf2['OFFSET_Y']

offset_X_arr=[offset_X1,offset_X2]
offset_Y_arr=[offset_Y1,offset_Y2]



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

def plot_circle(center,radius,theta_range):
    annulus_angles = np.arange(0,360,5)*np.pi/180
    annulus_angles = np.append(annulus_angles,annulus_angles[0])
    annulus_outer_x = center[0] + np.abs(radius) * np.cos(annulus_angles)
    annulus_outer_y = center[1] + np.abs(radius) * np.sin(annulus_angles)
    plt.plot(annulus_outer_x,annulus_outer_y,'b-',linewidth=0.5,label='patrol envelope')
    min_line_x = [center[0], radius * np.cos(theta_range[0]*np.pi/180) + center[0]]
    min_line_y = [center[1], radius * np.sin(theta_range[0]*np.pi/180) + center[1]]
    max_line_x = [center[0], radius * np.cos(theta_range[1]*np.pi/180) + center[0]]
    max_line_y = [center[1], radius * np.sin(theta_range[1]*np.pi/180) + center[1]]
    plt.plot(min_line_x,min_line_y,'g-',linewidth=0.5,label='theta min')
    plt.plot(max_line_x,max_line_y,'g--',linewidth=0.8,label='theta max')



#####################################
#### Plot petal metrology (positioner centers) and targets##########
######################################
ps=False
if ps:
    pp = PdfPages(output_file)

font = {'family' : 'sans-serif',
        'weight' : 'normal',
        'size'   : 9}
plt.rc('font', **font)
head_width=0.1
head_length=0.15
fontsize=25
    
plt.figure(1,figsize=(9.5,9.5))
plt.rc('font', **font)
plt.subplot(111)
axes = plt.gca()
axes.set_xlim([min(offset_X_arr)-7,max(offset_X_arr)+7])
axes.set_ylim([min(offset_Y_arr)-7,max(offset_Y_arr)+7])

patches=[]
patches.append(ptl_polygon)
patches.append(gfa_polygon)

### POS1 ###
theta_min = trans1.posTP_to_obsTP([min(posmodel1.targetable_range_posintT),0])[0]
theta_max = trans1.posTP_to_obsTP([max(posmodel1.targetable_range_posintT),0])[0]
theta_range = [theta_min,theta_max]
plot_circle([offset_X1,offset_Y1],r1+r2,theta_range)
theta_polygon = Polygon(theta_temp, True)
t_theta = mpl.transforms.Affine2D().rotate_deg(obs_tp1[0]) + mpl.transforms.Affine2D().translate(offset_X1,offset_Y1)
theta_polygon.set_transform(t_theta)
patches.append(theta_polygon)

phi_polygon = Polygon(phi_temp, True)
t_phi=mpl.transforms.Affine2D().rotate_deg(obs_tp1[0]+obs_tp1[1]) +  mpl.transforms.Affine2D().translate(offset_X1+r1*np.cos(np.pi*obs_tp1[0]/180.),offset_Y1+r1*np.sin(np.pi*obs_tp1[0]/180.))
phi_polygon.set_transform(t_phi)
patches.append(phi_polygon)
plt.text(offset_X1,offset_Y1,posid1,fontsize=fontsize)

### POS2 ###
theta_min = trans2.posTP_to_obsTP([min(posmodel2.targetable_range_posintT),0])[0]
theta_max = trans2.posTP_to_obsTP([max(posmodel2.targetable_range_posintT),0])[0]
theta_range = [theta_min,theta_max]
plot_circle([offset_X2,offset_Y2],r1+r2,theta_range)
theta_polygon = Polygon(theta_temp, True)
t_theta = mpl.transforms.Affine2D().rotate_deg(obs_tp2[0]) + mpl.transforms.Affine2D().translate(offset_X2,offset_Y2)
theta_polygon.set_transform(t_theta)
patches.append(theta_polygon)

phi_polygon = Polygon(phi_temp, True)
t_phi=mpl.transforms.Affine2D().rotate_deg(obs_tp2[0]+obs_tp2[1]) +  mpl.transforms.Affine2D().translate(offset_X2+r1*np.cos(np.pi*obs_tp2[0]/180.),offset_Y2+r1*np.sin(np.pi*obs_tp2[0]/180.))
phi_polygon.set_transform(t_phi)
patches.append(phi_polygon)
plt.text(offset_X2,offset_Y2,posid2,fontsize=fontsize)

p = PatchCollection(patches, cmap=mpl.cm.jet, alpha=0.4)
axes.add_collection(p)
plt.show()
plt.close()

if ps:
    pp.close()

