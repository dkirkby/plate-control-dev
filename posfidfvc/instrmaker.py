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
    def __init__(self,plate_type):
        if plate_type == 'petal':
            # import the positioner locations file
        elif plate_type == 'small_array':
            # import the small array block locations file
            
    
    def make_instrfile():
        '''Define function for making platemaker instrument file.
        '''
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
