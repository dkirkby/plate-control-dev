import matplotlib.pyplot as plt
import numpy as np

# Functions for plotting results of xy_accuracy_test for a fiber positioner.

def plot(path_no_ext, posid, data, center, theta_range, r1, r2, title_txt):
    """See xy_accuracy_test.py for format of data dictionary.
    """    
    plt.ioff() # interactive plotting off
    n_submoves = len(data['meas_obsXY'])
    n_targets = len(data['targ_obsXY'])
    targ_x = [data['targ_obsXY'][i][0] for i in range(n_targets)]
    targ_y = [data['targ_obsXY'][i][1] for i in range(n_targets)]
    radius = r1 + r2
    min_line_x = [center[0], radius * np.cos(theta_range[0]*np.pi/180) + center[0]]
    min_line_y = [center[1], radius * np.sin(theta_range[0]*np.pi/180) + center[1]]
    max_line_x = [center[0], radius * np.cos(theta_range[1]*np.pi/180) + center[0]]
    max_line_y = [center[1], radius * np.sin(theta_range[1]*np.pi/180) + center[1]]
    annulus_angles = np.arange(0,360,5)*np.pi/180
    annulus_angles = np.append(annulus_angles,annulus_angles[0])
    annulus_inner_x = center[0] + np.abs(r1-r2) * np.cos(annulus_angles)
    annulus_inner_y = center[1] + np.abs(r1-r2) * np.sin(annulus_angles)
    annulus_outer_x = center[0] + np.abs(r1+r2) * np.cos(annulus_angles)
    annulus_outer_y = center[1] + np.abs(r1+r2) * np.sin(annulus_angles)
    filenames = set()
    for s in range(n_submoves):
        fig = plt.figure(figsize=(10, 8))
        meas_x = [data['meas_obsXY'][s][i][0] for i in range(n_targets)]
        meas_y = [data['meas_obsXY'][s][i][1] for i in range(n_targets)]
        summary_txt  = '\n'
        summary_txt += 'SUBMOVE: ' + str(s) + '\n'
        summary_txt += '--------------------\n'
        summary_txt += 'error max: ' + format(np.max(data['err2D'][s])*1000,'6.1f') + ' um\n'
        summary_txt += '      rms: ' + format(np.sqrt(np.mean(np.array(data['err2D'][s])**2))*1000,'6.1f') + ' um\n'
        summary_txt += '      avg: ' + format(np.mean(data['err2D'][s])*1000,'6.1f') + ' um\n'
        summary_txt += '      min: ' + format(np.min(data['err2D'][s])*1000,'6.1f') + ' um\n'
        plt.plot(targ_x,targ_y,'ro',label='target points',markersize=4,markeredgecolor='r',markerfacecolor='None')        
        plt.plot(meas_x,meas_y,'k+',label='measured data',markersize=6,markeredgewidth='1')
        plt.plot(annulus_outer_x,annulus_outer_y,'b-',linewidth='0.5',label='patrol envelope')    
        plt.plot(annulus_inner_x,annulus_inner_y,'b-',linewidth='0.5')
        plt.plot(min_line_x,min_line_y,'g-',linewidth='0.5',label='theta min')
        plt.plot(max_line_x,max_line_y,'g--',linewidth='0.8',label='theta max')
        txt_x = np.min(plt.xlim()) + np.diff(plt.xlim()) * 0
        txt_y = np.max(plt.ylim()) - np.diff(plt.ylim()) * 0
        plt.text(txt_x,txt_y,summary_txt,horizontalalignment='left',verticalalignment='top',family='monospace',fontsize=10)
        plt.xlabel('x (mm)')
        plt.ylabel('y (mm)')
        plt.title(str(title_txt) + '\n' + str(posid) + ', ' + str(n_targets) + ' targets\n ')
        plt.grid(True)
        plt.margins(0.0, 0.03)
        plt.axis('equal')
        plt.legend(loc='upper right',fontsize=8)
        this_filename = path_no_ext + '_submove' + str(s) + '.png'
        filenames.add(this_filename)
        plt.savefig(this_filename,dpi=150)
        plt.close(fig)
    return filenames

