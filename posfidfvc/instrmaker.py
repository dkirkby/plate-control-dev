import numpy as np
from lmfit import minimize, Parameters
import os
import pdb
from astropy.table import Table
class InstrMaker(object):
    """Creates a valid platemaker instrument file using data measured by fvc
    (in pixels) for fiducial and positioner locations. These data are compared
    to the known physical size and layout of the petal or test stand.
    
    The nominal locations in the petal are taken from DESI-0530. These are *not*
    metrology data -- they are the nominal center positions of each device at
    the aspheric focal surface.
    """
    def __init__(self,ptl,m,fvc,hwsetup):
        if ptl.shape == 'petal':
            self.file_metro=os.getenv('FP_SETTINGS_PATH')+'/hwsetups/Petal_Metrology.csv'
            # import the positioner locations file
        elif ptl.shape == 'small_array':
            self.file_metro=os.getenv('FP_SETTINGS_PATH')+'/hwsetups/SWIntegration_XY.csv'
            # import the small array block locations file
        else:
            self.file_metro=os.getenv('FP_SETTINGS_PATH')+'/hwsetups/SWIntegration_XY.csv'

        self.PFS_file=os.getenv('FP_SETTINGS_PATH')+'/hwsetups/PFS_ID_Map.csv' 
        self.m=m 
        self.ptl=ptl
        self.hwsetup=hwsetup
        self.fvc=fvc

    def make_instrfile(self):
        '''Define function for making platemaker instrument file.
        '''
        #data,imgfile=self.m.measure()
        # Read dots identification result from ptl and store a dictionary
        pix_size=0.006
        if self.fvc.fvc_type == 'FLI':
            flip=1  # x flip right now this is hard coded since we don't change the camera often. 
        else:
            flip=0 
        posids=list(self.ptl.posids)
        fidids=list(self.ptl.fidids)
        n_pos=len(posids)
        n_fid=len(fidids)
        pos_fid_dots={}
        obsX_arr,obsY_arr,obsXY_arr,fvcX_arr,fvcY_arr=[],[],[],[],[]
        metroX_arr,metroY_arr=[],[]

        # read the Metrology data firest, then match positioners to DEVICE_LOC 
        positioners = Table.read(self.file_metro,format='ascii.csv',header_start=0,data_start=1)
        device_loc_file_arr,metro_X_file_arr,metro_Y_file_arr=[],[],[]
        for row in positioners:
            device_loc_file_arr.append(row['device_loc'])
            metro_X_file_arr.append(row['X'])
            metro_Y_file_arr.append(row['Y'])

        PFS=Table.read(self.PFS_file,format='ascii.csv',header_start=0,data_start=1)
        posids_PFS,device_loc_PFS=[],[]
        for row in PFS:
            posids_PFS.append(row['DEVICE_ID'])
            device_loc_PFS.append(row['DEVICE_LOC'])
        
        enabled_posids=self.m.enabled_posids

        for i in range(len(enabled_posids)):
            posid=enabled_posids[i]
            obsX_arr.append(float(self.ptl.get_posfid_val(posid,'LAST_MEAS_OBS_X')))
            obsY_arr.append(float(self.ptl.get_posfid_val(posid,'LAST_MEAS_OBS_Y')))
            obsXY_arr.append([obsX_arr[i],obsY_arr[i]])
            fvcXY_this=self.fvc.obsXY_to_fvcXY([obsXY_arr[i]])
            if flip ==1:
                fvcX_arr.append(-fvcXY_this[0][0])
            else:
                fvcX_arr.append(fvcXY_this[0][0])
            fvcY_arr.append(fvcXY_this[0][1])
            index=posids_PFS.index(posid.strip('M'))
            device_loc_this=device_loc_PFS[index]
            index2=device_loc_file_arr.index(device_loc_this)
            metroX_arr.append(metro_X_file_arr[index2])
            metroY_arr.append(metro_Y_file_arr[index2])
        
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        
        obsX_arr=np.array(obsX_arr)
        obsY_arr=np.array(obsY_arr)
    
 
        # metroX_arr= , metroY_arr= 
        pars = Parameters() # Input parameters model and initial guess
        pars.add('scale', value=10.)
        pars.add('offx', value=0.)
        pars.add('offy', value=0.)
        pars.add('angle', value=0.)
        print('fvcX:',fvcX_arr,'\n metroX:',metroX_arr,'\n fvcY:',fvcY_arr,'\n metroY:',metroY_arr,'\n')
        if self.fvc.fvc_type == 'FLI':
            out = minimize(self._residual, pars, args=(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr)) # Find the minimum chi2
        else:
            out = minimize(self._residual_sbig, pars, args=(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr)) # Find the minimum chi2^M


        if flip==1:
            offy=-out.params['offy'].value
            rot=out.params['angle'].value % 360 - 180.
        else:
            offy=out.params['offy'].value
            rot=out.params['angle'].value
     #  Plot
        pars_out=out.params
        if self.fvc.fvc_type=='FLI':
            model=pars_out['scale']*(self._rot(fvcX_arr+pars_out['offx'],fvcY_arr+pars_out['offy'],pars_out['angle']))
            model_x=np.array(model[0,:]).ravel()
            model_y=np.array(model[1,:]).ravel()
            label='fvcmag  '+str(out.params['scale'].value/pix_size)+'\n'+'fvcrot  '+str(rot)+'\n' +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n'
        else:
            rot_xy=self._rot(fvcX_arr,fvcY_arr,pars['angle'])
            model=pars_out['scale']*rot_xy
            model_x=np.array(model[0,:])+pars_out['offx']
            model_y=np.array(model[1,:])+pars_out['offy']
            model_x=model_x.ravel()
            model_y=model_y.ravel()
            label='fvcmag  '+str(out.params['scale'].value)+'\n'+'fvcrot  '+str(rot)+'\n' +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n'

        pp = PdfPages('instrmaker_fit_check.pdf')
        plt.figure(1,figsize=(15,15))
        plt.subplot(111)
        plt.plot(metroX_arr,metroY_arr,'ko',label=label)
        plt.plot(model_x,model_y,'b+')
        plt.xlabel('metroX')
        plt.ylabel('metroY')
        plt.legend(loc=2)
        plt.plot()    
        pp.savefig()
        plt.close()
        pp.close()
 
        # Write the output
        if self.fvc.fvc_type == 'FLI': 
            filename = 'instrmaker.par'
            f = open(filename,'w')
            output_lines='fvcmag  '+str(out.params['scale'].value/pix_size)+'\n'+'fvcrot  '+str(rot)+'\n' \
                        +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n' \
                        +'fvcflip  '+str(flip)+'\n'+'fvcnrow  6000 \n'+'fvcncol  6000 \n'+'fvcpixmm  '+str(pix_size) 
            f.write(output_lines)
            f.close()
            print('PM instrument file saved to instrmaker.par')
        else:
            print('Instrument Pars:',out.params['angle'].value ,out.params['scale'].value,[out.params['offx'].value,out.params['offy'].value])
            print('The original Instrument Pars are:',self.fvc.rotation,self.fvc.scale,self.fvc.translation)
            a=input('Do you want to update the Pars?')
            if a =='Y' or a=='y' or a=='Yes' or a=='YES' or a=='yes':
                self.fvc.rotation=out.params['angle'].value 
                self.fvc.translation=[out.params['offx'].value,out.params['offy'].value]
                self.fvc.scale=out.params['scale'].value


        return out
    
    
    def _rot(self,x,y,angle): # A rotation matrix to rotate the coordiantes by a certain angle
        theta=np.radians(angle)
        c,s=np.cos(theta),np.sin(theta)
        R=np.matrix([[c,-s],[s,c]])
        rr=np.dot(np.array([x,y]).T,R)
        return rr.T
    
    
    def _residual(self,pars,x,y,x_data,y_data):
        # Code to calculate the Chi2 that quantify the difference between data and model
        # x, y are the metrology data that specify where each fiber positioner is located on the petal (in mm)
        # x_data and y_data is the X and Y measured by the FVC (in pixel)
        # The pars contains the scale, offx, offy, and angle that transform fiber positioner focal plane coordinate (mm) 
        # to FVC coordinate (in pixel)
        
        xy_model=pars['scale']*(self._rot(x+pars['offx'],y+pars['offy'],pars['angle']))
        x_model=np.array(xy_model[0,:])
        y_model=np.array(xy_model[1,:])
        res=np.array((x_model-x_data))**2+np.array((y_model-y_data))**2
        return res
    
    def _residual_sbig(self,pars,x,y,x_data,y_data):
        rot_xy=self._rot(x,y,pars['angle'])
        xy_model=pars['scale']*rot_xy
        x_model=np.array(xy_model[0,:])+pars['offx']
        y_model=np.array(xy_model[1,:])+pars['offy']
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
    def push_to_db(self):
        pass
