import os
import sys
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))
import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import xytest
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj
import scipy
import astropy
import csv
import numpy as np
from lmfit import minimize, Parameters
import matplotlib.pyplot as plt


# unique timestamp and fire up the gui
start_filename_timestamp = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()

# start set of new and changed files
new_and_changed_files = set()

# get the station config info
message = 'Pick hardware setup file.'
hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)
new_and_changed_files.add(hwsetup.filename)

# ask user whether to auto-generate a platemaker instrument file
message = 'Should we auto-generate a platemaker instrument file?'
should_make_instrfile = tkinter.messagebox.askyesno(title='Make PM file?',message=message)

# are we in simulation mode?
sim = hwsetup['fvc_type'] == 'simulator'

# update log and settings files from the SVN
if not(sim):
    svn_user, svn_pass, svn_auth_err = xytest.XYTest.ask_user_for_creds(should_simulate=sim)
    svn_update_dirs = [pc.dirs[key] for key in ['pos_logs','pos_settings','xytest_logs','xytest_summaries']]
    should_update_from_svn = tkinter.messagebox.askyesno(title='Update from SVN?',message='Overwrite any existing local positioner log and settings files to match what is currently in the SVN?')
    if should_update_from_svn:
        if svn_auth_err:
            print('Could not validate svn user/password.')
        else:
            for d in svn_update_dirs:
                os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
                os.system('svn revert --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d + '*')

# software initialization and startup
fvc = fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'])    
fvc.rotation = hwsetup['rotation']
fvc.scale = hwsetup['scale']
posids = hwsetup['pos_ids']
fidids = hwsetup['fid_ids']
ptl = petal.Petal(hwsetup['ptl_id'], posids, fidids, simulator_on=sim, user_interactions_enabled=True)
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure([ptl],fvc)
m.make_plots_during_calib = True
print('Automatic generation of calibration plots is turned ' + ('ON' if m.make_plots_during_calib else 'OFF') + '.')
for ptl in m.petals:
    for posmodel in ptl.posmodels:
        new_and_changed_files.add(posmodel.state.unit.filename)
        new_and_changed_files.add(posmodel.state.log_path)
    for fidstate in ptl.fidstates.values():
        new_and_changed_files.add(fidstate.unit.filename)
        new_and_changed_files.add(fidstate.log_path)
m.n_extradots_expected = hwsetup['num_extra_dots']

# check ids with user
text = '\n\nHere are the known positioners and fiducials:\n\n'
text += str(len(posids)) + ' POSITIONERS:'
for posid in posids:
    text += '\n  ' + format(posid+':','11s') + 'busid = ' + format(str(ptl.get(posid,'BUS_ID')),'5s') + '  canid = ' + format(str(ptl.get(posid,'CAN_ID')),'5s')
text += '\n\n' + str(len(fidids)) + ' FIDUCIALS:'
for fidid in fidids:
    text += '\n  ' + format(fidid+':','11s') + 'busid = ' + format(str(ptl.get_fids_val(fidid,'BUS_ID')[0]),'5s') + '  canid = ' + format(str(ptl.get_fids_val(fidid,'CAN_ID')[0]),'5s') + '  ndots = ' + str(ptl.get_fids_val(fidid,'N_DOTS')[0])
text += '\n  num extra dots = ' + str(m.n_extradots_expected) + '\n'
print(text)
if not tkinter.messagebox.askyesno(title='IDs correct?',message='A list of all the positioner and fiducials has been printed to the stdout text console.\n\nPlease check each of these carefully.\n\nAre they all correct?'):
    tkinter.messagebox.showinfo(title='Quitting',message='Ok, will quit now so the IDs can be fixed.')
    gui_root.withdraw()    
    sys.exit(0)

# check if auto-svn commit is desired
if not sim and not svn_auth_err:
    should_commit_to_svn = tkinter.messagebox.askyesno(title='Commit to SVN?',message='Auto-commit files to SVN after script is complete?\n\n(Typically answer "Yes")')
else:
    should_commit_to_svn = False

# determine if we need to identify fiducials and positioners this run
should_identify_fiducials = True
should_identify_positioners = True
extradots_filename = pc.dirs['temp_files'] + os.path.sep + 'extradots.csv'
extradots_existing_data = []
if m.n_extradots_expected > 0 and os.path.isfile(extradots_filename):
    if tkinter.messagebox.askyesno(title='Load extra dots data?',message='An existing extra dots data file was found at ' + extradots_filename + '. Load it and skip re-identification of fiducials?'):
        should_identify_fiducials = False
        with open(extradots_filename,'r',newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                extradots_existing_data.append([row['x_pix'],row['y_pix']])
        if tkinter.messagebox.askyesno(title='Skip id of positioners?',message='Also skip identification of positioner locations?\n\n(Say "YES" only if you are confident of their stored locations from a previous run.)'):
            should_identify_positioners = False
else:
    if tkinter.messagebox.askyesno(title='Skip identification?',message='Skip identification of fiducial and positioner locations?\n\n(Say "YES" only if you are confident of their stored locations from a previous run.)'):
        should_identify_fiducials = False
        should_identify_positioners = False

# close the gui
gui_root.withdraw()

# fire up the fiducials
fid_settings_done = m.set_fiducials('on')
print('Fiducials turned on: ' + str(fid_settings_done))

# make sure control is enabled for all positioners
for ptl in m.petals:
    for posid in ptl.posids:
        ptl.set(posid, 'CTRL_ENABLED', True)

# disable certain features if anticollision is turned off yet it is also a true petal (with close-packed positioenrs)
if hwsetup['plate_type'] == 'petal' and not ptl.anticollision_default:
    should_limit_range = True
else:
    should_limit_range = False

# define function for making platemaker instrument file
def make_instrfile():
    import matplotlib.pyplot as plt
    status = ptl.get(posid=posids) # Read the calibration data
    obsX_arr=[] # Measured position of each FP
    obsY_arr=[]
    length_r1_arr=ptl.get(posid=posids,key='LENGTH_R1')
    length_r2_arr=ptl.get(posid=posids,key='LENGTH_R2')
    for i in range(len(posids)):
        obsX_arr.append(status[i].expected_current_position.get('obsX'))
        obsY_arr.append(status[i].expected_current_position.get('obsY'))       
    obsX_arr=np.array(obsX_arr)
    obsY_arr=np.array(obsY_arr)
    # This is fake test data for now. Just input scale, x and y offset, and rotation angle, generate new positions.
    # Should read the metrology data eventually    
    pars0=np.array([20,1,1,30.])
    test=(rot(obsX_arr-pars0[1],obsY_arr-pars0[2],-pars0[3]))/pars0[0]
    metroX_arr=test[0,:]# Fake data 
    metroY_arr=test[1,:]#+np.random.normal(scale=5,size=len(test[0,:]))

    metro_X_arr=[] # Real data
    metro_Y_arr=[]
    # read the Metrology Data
    metro_list=[]
    csvfile=open(pc.dirs['hwsetups']+os.path.sep+'EMPetal_XY.csv')
    metro=csv.DictReader(csvfile)
    for row in metro:
        metro_list.append(row)
    m_select=('M00096','M00044','M00043','M00069','M00224','M00086','M00074','M00302','M00091','M00088',)
    device_select=('155','171','184',    '201',    '214',   '232',   '247',   '266',   '282',   '302')
    for row in metro_list:
        if row['device_loc'] in device_select:
            metro_X_arr.append(row['X'])
            metro_Y_arr.append(row['Y'])
    print(metro_X_arr)
    print(metro_Y_arr)        
    # metroX_arr= , metroY_arr= 
    pars = Parameters() # Input parameters model and initial guess
    pars.add('scale', value=10.)
    pars.add('offx', value=0.)
    pars.add('offy', value=0.)
    pars.add('angle', value=0.)
    out = minimize(residual, pars, args=(metroX_arr,metroY_arr, obsX_arr,obsY_arr)) # Find the minimum chi2
 #  Plots
    par_out=[out.params['scale'].value,out.params['offx'].value,out.params['offy'].value,out.params['angle'].value]
    pars_out=out.params
    model=pars_out['scale']*(rot(metroX_arr+pars_out['offx'],metroY_arr+pars_out['offy'],pars_out['angle']))
    model_x=np.array(model[0,:]).ravel()
    model_y=np.array(model[1,:]).ravel()
    print(model_x)
    plt.figure(1,figsize=(15,15))
    plt.subplot(221)
    plt.plot(obsX_arr,obsY_arr,'ko',label='fvcmag '+str(out.params['scale'].value)+'\n' +'fvcmag  '+str(out.params['scale'].value)+'\n'+'fvcrot  '+str(out.params['angle'].value % 360)+'\n' \
                                     +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(out.params['offy'].value)+'\n')
    plt.plot(model_x,model_y,'b')
    plt.xlabel('obsX')
    plt.ylabel('obsY')
    plt.legend(loc=2)
    plt.plot()    
    
    plt.subplot(222)
    plt.plot(metro_X_arr,metro_Y_arr,'ko',label='')
    plt.xlabel('metroX')
    plt.ylabel('metroY')
    plt.legend(loc=2)
    plt.plot()    
    
    # Write the output

    filename = os.path.splitext(hwsetup.filename)[0] + '_instr.par'
    f = open(filename,'w')
    output_lines='fvcmag  '+str(out.params['scale'].value)+'\n'+'fvcrot  '+str(out.params['angle'].value % 360)+'\n' \
                +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(out.params['offy'].value)+'\n' \
                +'fvcflip  0\n'+'fvcnrow  6000 \n'+'fvcncol  6000 \n'+'fvcpixmm  0.006' 
    f.write(output_lines)
    return out,metro_list


def rot(x,y,angle): # A rotation matrix to rotate the coordiantes by a certain angle
    theta=np.radians(angle)
    c,s=np.cos(theta),np.sin(theta)
    R=np.matrix([[c,-s],[s,c]])
    rr=np.dot(np.array([x,y]).T,R)
    return rr.T


def residual(pars,x,y,x_data,y_data):
    # Code to calculate the Chi2 that quantify the difference between data and model
    # x, y are the metrology data that specify where each fiber positioner is located on the petal (in mm)
    # x_data and y_data is the X and Y measured by the FVC (in pixel)
    # The pars contains the scale, offx, offy, and angle that transform fiber positioner focal plane coordinate (mm) 
    # to FVC coordinate (in pixel)
    
    xy_model=pars['scale']*(rot(x+pars['offx'],y+pars['offy'],pars['angle']))
    x_model=np.array(xy_model[0,:])
    y_model=np.array(xy_model[1,:])
    res=np.array((x_model-x_data))**2+np.array((y_model-y_data))**2
    return res

    # 1. extract positioner locations that we just measured with FVC
    # 2. read file with nominal locations from metrology data (see DESI-2850 for format)
    # 3. compare FVC measurements with metrology, to calculate:
    #       fvcmag  ... scale in pixels at FVC per mm at positioners
    #       fvcrot  ... rotation in degrees of the field
    #       fvcxoff ... x offset (in pixels) of the field
    #       fvcyoff ... y offset (in pixels) of the field
    #       fvcflip ... either 1 or 0, says whether it image is a mirror (probably 0 in EM petal)
    #    (see DESI-1416 for defining the geometry)
    # 4. write the instrument file to disk (simple text file, named "something.par" including the above params as well as:
    #       fvcnrow  6000
    #       fvcncol  6000 
    #       fvcpixmm 0.006


# calibration routines
m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
if should_identify_fiducials:
    m.identify_fiducials()
    with open(extradots_filename,'w',newline='') as file:
        writer = csv.DictWriter(file,fieldnames=['x_pix','y_pix'])
        writer.writeheader()
        for xy in m.extradots_fvcXY:
            writer.writerow({'x_pix':xy[0],'y_pix':xy[1]})
else:
    m.extradots_fvcXY = extradots_existing_data
if should_identify_positioners:
    m.identify_positioner_locations()
if should_make_instrfile:
    instr_par,metro  = make_instrfile()
if should_limit_range:
    m.measure_range(axis='theta')
    m.measure_range(axis='phi')
plotfiles = m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=start_filename_timestamp)
new_and_changed_files.update(plotfiles)
m.park() # retract all positioners to their parked positions

# commit logs and settings files to the SVN
if should_commit_to_svn:
    n_total = len(new_and_changed_files)
    n = 0
    for file in new_and_changed_files:
        n += 1
        err1 = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file)
        err2 = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from initialize_hwsetup script" ' + file)
        print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1) + ' (add) and ' + str(err2) + ' (commit)')


# COMMENTS ON FUTURE WORK BELOW...
# --------------------------------
# VERIFICATIONS AND CALIBRATIONS SEQUENCE:
# (TO IMPLEMENT IN FULLY AUTOMATED FASHION (IN THIS ORDER)
#   [note, not doing focus here -- too difficult to automate with our astronomy cameras' lack of control over lenses]
#   - look up the canids for all the positioners, and validate that the number of unique canids matches the number of positioners
#   - calibrate each fiducial
#       - get relative brightness at a standard setting
#   - calibrate fiber illumination
#       - get relative brightness at a standard setting
#   - select new optimal combination of settings for:
#       - fiducial brightness
#       - fiber brightness
#           - if manual setting, tell user:
#               - how much to change power level
#               - or if there is too much variation, which spots look dim (make a plot where the point labels are the relative brightness)
#       - camera exposure time (may prefer to leave this fixed, for test timing issues)
#   (rehome)
#   - verify each positioner moves
#   - verify number of extra ref dots
#   - verify positioner motor directions are correct:
#       - theta, by moving a few degrees with phi arm a little extended
#           - use this to set first rough fvc scale
#       - phi, by moving 180 degress with phi arm retracted, and dot shouldn't move much
#   (quick calibration)
#   - using plate_type, which defines the possible device locations:
#       - which devices are in which holes
#       - calculate fvc rotation, offset, and scale
#       - calculate precise xy offsets for each positioner, and for fiducial dots, and record these to their calib files
#       - make a platemaker instrument file if needed
#   - phi bearing bond integrity
#       - we can detect if phi bearing bond is broken by ramming ferrule holder hard against stop and looking for lateral prying motion
#       - this will be a great one to generally automate, and perhaps incor
#       1. ram hard stop with no back-off and measure
#       2. back off a few degrees and re-measure
#       3. do a few more points on the phi arc
#       4. calculate: if there is any significant radial component w.r.t. phi arc center when you rammed hard stop, then there was prying / broken bond
