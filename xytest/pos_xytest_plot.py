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
        plt.plot(annulus_outer_x,annulus_outer_y,'b-',linewidth=0.5,label='patrol envelope')
        plt.plot(annulus_inner_x,annulus_inner_y,'b-',linewidth=0.5)
        plt.plot(min_line_x,min_line_y,'g-',linewidth=0.5,label='theta min')
        plt.plot(max_line_x,max_line_y,'g--',linewidth=0.8,label='theta max')
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

if __name__=="__main__":
    plot(
        '/home/robot/focalplane/positioner_logs/xytest_plots/fakepos1_2017-04-17_T181551_xyplot',
        'fakepos1',
        {'err2D': [[0.3999196800550003, 0.002541372031378015, 0.007235232309931151, 0.0005879756496901464, 0.003843611715492, 0.005934187628477584, 0.0019037156325524608, 0.007241152285549415],
                   [0.3939112826158115, 0.003304667032676669, 0.008478358992935309, 0.0005592693367937689, 0.004792478992267433, 0.005087659018078488, 0.002393265255193776, 0.016873168889517096]],
         'targ_obsXY': [[-2.8046972403685433, -2.8158370848022183],
                        [-2.8046972403685433, -0.015837084802218397],
                        [-2.8046972403685433, 2.7841629151977805],
                        [-0.004697240368543244, -2.8158370848022183],
                        [-0.004697240368543244, 2.7841629151977805],
                        [2.7953027596314555, -2.8158370848022183],
                        [2.7953027596314555, -0.015837084802218397],
                        [2.7953027596314555, 2.7841629151977805]],
         'errXY': [[[0.2967283681855295, -0.2681194249010068],
                    [0.0025024943087772478, 0.0004428250629852637],
                    [0.006509982003884307, -0.00315732812481917],
                    [0.0005485938703527291, 0.00021156589999327124],
                    [-0.0038215305301127255, -0.0004114066441900377],
                    [-0.003343284459400575, -0.004902757574417382],
                    [-0.0016824783179063552, 0.0008907299924217314],
                    [-0.001326588674503082, 0.007118598802517084]],
                   [[0.28747324892444537, -0.26930508670438735],
                    [-0.0031126995424943793, -0.0011099215084929663],
                    [-0.004694578788477788, 0.00705999300366944],
                    [0.00011267497021611762, 0.0005478015536346525],
                    [0.0047888113042156375, 0.00018745981953793844],
                    [0.0008896336420787243, 0.005009274025955968],
                    [0.0019129170796494677, -0.001438216544232155],
                    [-0.0003511768349375721, -0.016869514018037712]]],
         'meas_obsXY': [[[-2.507968872183014, -3.083956509703225],
                         [-2.802194746059766, -0.015394259739233133],
                         [-2.798187258364659, 2.7810055870729613],
                         [-0.004148646498190515, -2.815625518902225],
                         [-0.00851877089865597, 2.7837515085535904],
                         [2.791959475172055, -2.8207398423766357],
                         [2.793620281313549, -0.014946354809796666],
                         [2.7939761709569524, 2.7912815140002976]],
                        [[-2.517223991444098, -3.0851421715066056],
                         [-2.8078099399110377, -0.016947006310711363],
                         [-2.809391819157021, 2.79122290820145],
                         [-0.004584565398327126, -2.8152892832485836],
                         [9.157093567239418e-05, 2.7843503750173184],
                         [2.796192393273534, -2.8108278107762623],
                         [2.797215676711105, -0.017275301346450552],
                         [2.794951582796518, 2.7672934011797428]]],
         'posTP': [[-177.98072716291577, 117.76526382473853, 86.243690861775562, -152.23489308884174, 27.765112713627445, -93.756314940693571, -62.234741977730607, -3.756163829582448],
                   [97.804324018996553, 124.48506599430519, 97.804324018996539, 124.48506599430519, 124.48506599430519, 97.804324018996539, 124.48506599430519, 97.804324018996539]]},
        [-0.0046972403685432438, -0.015837084802218397],
        [-178.4860025727448, 174.4755390074246],
        3.01141243631,
        3.03058821399,
        '2017-04-17_T181551')