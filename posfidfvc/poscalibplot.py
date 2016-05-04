import matplotlib.pyplot as plt
import numpy as np

# Functions for plotting calibration arcs of the fiber positioner.

def plot_arc(path, pos_id, data):
    """See _calculate_and_set_arms_and_offsets() method in posmovemeasure.py for data format.
    """    
    plt.ioff() # interactive plotting off
    fig = plt.figure(figsize=(14, 8))
    
    for ax in ['T','P']:
        name = 'theta' if ax == 'T' else 'phi'
        other_ax = 'P' if ax == 'T' else 'T'
        other_name = 'phi' if ax == 'T' else 'theta'
        plot_num_base = 0 if ax == 'T' else 3
        target_angles = np.array(data[pos_id]['targ_pos' + ax + '_during_' + ax + '_sweep'])
        measured_angles = np.array(data[pos_id]['meas_pos' + ax + '_during_' + ax + '_sweep'])
        other_axis_angle = data[pos_id]['targ_pos' + other_ax + '_during_' + ax + '_sweep']
        radius = data[pos_id]['radius_' + ax]    
        center = data[pos_id]['xy_ctr_' + ax]
        measured_xy = np.array(data[pos_id]['measured_obsXY_' + ax])

        plt.subplot(2,3,plot_num_base+1)
        arc_start = np.arctan2(measured_xy[0,1]-center[1],measured_xy[0,0]-center[0]) * 180/np.pi
        arc_finish = arc_start + np.sum(np.diff(measured_angles))
        if arc_start > arc_finish:
            arc_finish += 360
        ref_arc_angles = np.arange(arc_start,arc_finish,5)*np.pi/180
        if ref_arc_angles[-1] != arc_finish:
            ref_arc_angles = np.append(ref_arc_angles,arc_finish)
        arc_x = radius * np.cos(ref_arc_angles) + center[0]
        arc_y = radius * np.sin(ref_arc_angles) + center[1]
        axis_zero_angle = arc_start - target_angles[0] # where global observer would nominally see the axis's local zero point in this plot        
        axis_zero_line_x = [center[0], radius * np.cos(axis_zero_angle*np.pi/180) + center[0]]
        axis_zero_line_y = [center[1], radius * np.sin(axis_zero_angle*np.pi/180) + center[1]]
        plt.plot(arc_x,arc_y,'b-')
        plt.plot(measured_xy[:,0], measured_xy[:,1], 'ko')
        plt.plot(measured_xy[0,0], measured_xy[0,1], 'ro')
        plt.plot(center[0],center[1],'k+')
        plt.plot(axis_zero_line_x,axis_zero_line_y,'k--')
        zero_text_angle = np.mod(axis_zero_angle+360, 360)
        zero_text_angle = zero_text_angle-180 if zero_text_angle > 90 and zero_text_angle < 270 else zero_text_angle
        zero_text = name + '=0\n(' + other_name + '=' + format(other_axis_angle,'.1f') + ')'
        plt.text(np.mean(axis_zero_line_x),np.mean(axis_zero_line_y),zero_text,rotation=zero_text_angle,horizontalalignment='center',verticalalignment='top')
        for i in range(len(measured_angles)):
            text_x = center[0] + radius*1.1*np.cos((axis_zero_angle+measured_angles[i])*np.pi/180)
            text_y = center[1] + radius*1.1*np.sin((axis_zero_angle+measured_angles[i])*np.pi/180)
            plt.text(text_x,text_y,str(i),verticalalignment='center',horizontalalignment='center')
        plt.xlabel('x (mm)')
        plt.ylabel('y (mm)')
        plt.title(pos_id + ' ' + name + ' calibration points')
        plt.grid(True)
        plt.margins(0.05, 0.05)
        plt.axis('equal')
       
        plt.subplot(2,3,plot_num_base+2)
        err_angles = measured_angles - target_angles
        plt.plot(target_angles, err_angles, 'ko-')
        plt.plot(target_angles[0], err_angles[0], 'ro')
        for i in range(len(target_angles)):
            plt.text(target_angles[i],err_angles[i],'\n\n'+str(i),verticalalignment='center',horizontalalignment='center')
        plt.xlabel('target ' + name + ' angle (deg)')
        plt.ylabel('measured ' + name + ' - target ' + name + ' (deg)')
        plt.title('measured angle variation')
        plt.grid(True)
        plt.margins(0.1, 0.1)
        
        plt.subplot(2,3,plot_num_base+3)
        measured_radii = np.sqrt(np.sum((measured_xy - center)**2,axis=1)) * 1000 # um
        best_fit_radius = radius * 1000 # um
        err_radii = measured_radii - best_fit_radius
        plt.plot(target_angles, err_radii, 'ko-')
        plt.plot(target_angles[0], err_radii[0], 'ro')
        for i in range(len(target_angles)):
            plt.text(target_angles[i],err_radii[i],'\n\n'+str(i),verticalalignment='center',horizontalalignment='center')
        plt.xlabel('target ' + name + ' angle (deg)')
        plt.ylabel('measured radius - best fit radius (um)')
        plt.title('measured radius variation')
        plt.grid(True)
        plt.margins(0.1, 0.1)
        
    plt.tight_layout(pad=2.0)
    plt.savefig(path,dpi=150)
    plt.close(fig)

# test with sample data
test_data = {'UM00012': {'radius_T': 3.5638118202067899,
                         'xy_ctr_P': np.array([ 50.78005157,  22.62802738]),
                         'targ_posP_during_P_sweep': [107.0, 144.30020231284081, 181.60040462568162],
                         'measured_obsXY_P': np.array([[ 49.42756029,  19.95453731],[ 51.33393847,  19.68354251],[ 53.01255502,  20.62985066]]),
                         'targ_posT_during_T_sweep': [-187.43428791216851, -63.478095970722833, 60.478095970722848, 184.43428791216851],
                         'meas_posT_during_T_sweep': [-188.998564650126, -63.992824477967659, 59.991597812513589, 184.4239692264789],
                         'gear_ratio_T': 1.0040264050300087,
                         'xy_ctr_T': np.array([ 52.96177541,  20.47691133]),
                         'gear_ratio_P': 1.0065729034873383,
                         'radius_P': 2.9961278073568209,
                         'meas_posP_during_P_sweep': np.array([ 107.76087963,  145.24867362,  182.7654912 ]),
                         'measured_obsXY_T': np.array([[ 56.52036933,  20.44999557],[ 50.94245683,  23.41261195],[ 51.65488552,  17.16064952],[ 56.44099264,  21.27206227]])}}
plot_arc('./testplot.png', 'UM00012', test_data)

