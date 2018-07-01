import numpy as np
from lmfit import minimize, Parameters

class InstrMaker(object):
    """Creates a valid platemaker instrument file using data measured by fvc
    (in pixels) for fiducial and positioner locations. These data are compared
    to the known physical size and layout of the petal or test stand.
    
    The nominal locations in the petal are taken from DESI-0530. These are *not*
    metrology data -- they are the nominal center positions of each device at
    the aspheric focal surface.
    """
    def __init__(self,plate_type,ptl,m):
        if plate_type == 'petal':
            # import the positioner locations file
        elif plate_type == 'small_array':
            # import the small array block locations file
            
    
    def make_instrfile():
        '''Define function for making platemaker instrument file.
        '''
        m.request_home()

        # Read dots identification result from ptl and store a dictionary
        posids=ptl.posids
        fidids=ptl.fidids
        n_pos=len(posids)
        n_fid=len(fidids)
        pos_fid_dots={}
        obsX_arr,obsY_arr=[],[]
        metro_X_arr,metro_Y_arr=[],[]

        # read the Metrology data firest, then match positioners to DEVICE_LOC 
        pos_locs = '../positioner_locations_0530v14.csv'#os.path.join(allsetdir,'positioner_locations_0530v12.csv')
        positioners = Table.read(pos_locs,format='ascii.csv',header_start=0,data_start=1)
        for row in positioners:
            idnam, typ, xloc, yloc, zloc, qloc, rloc, sloc = row
            device_loc_file.append(idnam)
            metro_X_file.append(xloc)
            metro_Y_file.append(yloc)

        PFS_file='PFS_ID_Map.csv'
        PFS=Table.read(PFS_file,format='ascii.csv',header_start=0,data_start=1)
        for row in PFS:
            posids_PFS.append(row['DEVICE_ID'])
            device_loc_PFS.append(row['DEVICE_LOC'])
        
        for i in range(n_pos):
            posid=posids[i]
            obsX_arr.append(float(ptl.get_posfid_val(posid,'LAST_MEAS_OBS_X'))
            obsY_arr.append(float(ptl.get_posfid_val(posid,'LAST_MEAS_OBS_Y'))        
            index=posids_PFS.index(posid.strip('M'))
            device_loc_this=device_loc_PFS[index]
            index2=divice_loc_arr.index(device_loc_this)
            metro_X_arr.append(metro_X_file[index2])
            metro_Y_arr.append(metro_Y_file[index2])


        import matplotlib.pyplot as plt
        obsX_arr=np.array(obsX_arr)
        obsY_arr=np.array(obsY_arr)
    

        # metroX_arr= , metroY_arr= 
        pars = Parameters() # Input parameters model and initial guess
        pars.add('scale', value=10.)
        pars.add('offx', value=0.)
        pars.add('offy', value=0.)
        pars.add('angle', value=0.)
        out = minimize(residual, pars, args=(metroX_arr,metroY_arr, obsX_arr,obsY_arr)) # Find the minimum chi2
     #  Plot
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
