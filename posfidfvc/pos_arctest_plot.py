import matplotlib.pyplot as plt
import numpy as np

# Functions for plotting results of arc_accuracy_test for a fiber positioner.

def plot(path, pos_id, tests, title):
    """See arc_accuracy_test.py for format of 'tests' data structure.
    """
    std_markers = ['o','+','x','^']
    std_colors = ['b','r','k','m']
    plt.ioff() # interactive plotting off
    fig = plt.figure(figsize=(12,8))
    
    plt.subplot(2,3,1)
    markers = std_markers.copy()
    colors = std_colors.copy()
    for test in tests:
        x_meas = test[pos_id]['meas_obsX']
        y_meas = test[pos_id]['meas_obsY']
        plt.plot(x_meas,y_meas,markers.pop(0),label=test['title'],markeredgecolor=colors.pop(0),markerfacecolor='None',markersize=3)
    plt.xlabel('x (mm)')
    plt.ylabel('y (mm)')
    plt.title(title)
    plt.margins(0.1, 0.1)
    plt.axis('equal')
    plt.legend(loc='upper right',fontsize=6)
    
    plt.subplot(2,3,4)
    markers = std_markers.copy()
    colors = std_colors.copy()
    for test in tests:
        angle = test['targ_angle']
        err_r = test[pos_id]['err_radial']
        err_r = np.multiply(err_r,1000)
        plt.plot(angle,err_r,markers.pop(0),label=test['title'],markeredgecolor=colors.pop(0),markerfacecolor='None',markersize=3)
    plt.xlabel('target (deg)')
    plt.ylabel('radial error (um)')
    plt.legend(loc='upper right',fontsize=6)

    remaining_subplots = [2,3,5,6]
    markers = std_markers.copy()
    colors = std_colors.copy()
    for test in tests:
        plt.subplot(2,3,remaining_subplots.pop(0))
        angle = test['targ_angle']
        err_t = test[pos_id]['err_tangential']
        err_t = np.multiply(err_t,1000)
        plt.plot(angle,err_t,markers.pop(0),markeredgecolor=colors.pop(0),markerfacecolor='None',markersize=3)
        plt.xlabel('target ' + test['axis'] + ' (deg)')
        plt.ylabel('tangential error (um)')
        plt.title(test['title'])
        txt =  'max: ' + format(np.max(err_t),'6.1f') + ' um\n'
        txt += 'rms: ' + format(np.sqrt(np.mean(err_t**2)),'6.1f') + ' um\n'
        txt += 'avg: ' + format(np.mean(err_t),'6.1f') + ' um\n'
        txt += 'min: ' + format(np.min(err_t),'6.1f') + ' um\n'
        txt_x = np.min(plt.xlim()) + np.diff(plt.xlim()) * 0.01
        txt_y = np.max(plt.ylim()) - np.diff(plt.ylim()) * 0.02
        plt.text(txt_x,txt_y,txt,horizontalalignment='left',verticalalignment='top',family='monospace',fontsize=6)    
    
    plt.tight_layout(pad=2.0)
    plt.savefig(path,dpi=150)
    plt.close(fig)
    
#faketests = []
#pos_id = 'somepos'
#for i in range(4):
#    faketest = {}
#    faketest[pos_id] = {}
#    faketest['axis'] = 'phi'
#    faketest['title'] = 'test ' + str(i)
#    x0 = i/10
#    y0 = i/10
#    x_meas = np.add([3.05, 3.1, -3.2, -4.2],x0)
#    y_meas = np.add([3.99, -4.2, 4.2, -2.9],y0)
#    a_targ = np.arctan2(y_meas,x_meas)
#    faketest['targ_angle'] = np.degrees(a_targ).tolist()
#    faketest[pos_id]['meas_obsX'] = x_meas.tolist()
#    faketest[pos_id]['meas_obsY'] = y_meas.tolist()
#    r0 = 5
#    sin = np.sin(a_targ)
#    cos = np.cos(a_targ)
#    tan = np.tan(a_targ)
#    x_targ = r0*cos
#    y_targ = r0*sin
#    err_x = x_meas - x_targ
#    err_y = y_meas - y_targ
#    err_tangential = (err_y - err_x*tan)/(sin*tan + cos)
#    err_radial = (err_x + sin*err_tangential)/cos
#    err_total = np.sqrt(err_radial**2 + err_tangential**2)    
#    faketest[pos_id]['err_total'] = err_total.tolist()
#    faketest[pos_id]['err_radial'] = err_radial.tolist()
#    faketest[pos_id]['err_tangential'] = err_tangential.tolist()
#    faketests.append(faketest)
#plot('out.png',pos_id,faketests,'some title')