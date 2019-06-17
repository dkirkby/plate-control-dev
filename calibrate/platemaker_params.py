import os
import sys

import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
from tkinter import *
import configobj
import csv

import numpy as np
import pandas as pd
from lmfit import minimize, Parameters
from astropy.table import Table
from astropy.io import fits
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from astropy.stats import mad_std, sigma_clipped_stats
from astropy.modeling import models, fitting
from astropy.table import Table, Column
import astropy.visualization as visu
from astropy.visualization.mpl_normalize import ImageNormalize
import photutils as phot

class Derive_Platemaker_Pars(object):
    def __init__(self, petal_num):
        self.petal_num = str(int(petal_num))
        self.petal_dir = '/home/msdos/data/petaltests/platemaker/instruments/petal%s/'%self.petal_num


        self.ref_dist_tol = 3.0 # [pixels on FVC CCD] used for identifying fiducial dots
        self.ref_dist_thres = 100.0 

        # get the station config info
        hwsetup_conf = pc.dirs['hwsetups']+'/hwsetup_petal%s.conf' % self.petal_num
        self.hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)

        # software initialization and startup
        if self.hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in self.hwsetup:
            self.fvc=fvchandler.FVCHandler(fvc_type=self.hwsetup['fvc_type'],save_sbig_fits=self.hwsetup['save_sbig_fits'],platemaker_instrument='lbnl3') #=self.hwsetup['pm_instrument'])
        else:
            self.fvc = fvchandler.FVCHandler(fvc_type=self.hwsetup['fvc_type'],save_sbig_fits=True)    
            self.fvc.rotation = self.hwsetup['rotation'] # this value is used in setups without fvcproxy / platemaker
            self.fvc.scale = self.hwsetup['scale'] # this value is used in setups without fvcproxy / platemaker
            self.fvc.translation = self.hwsetup['translation']

        self.ptl = petal.Petal(petal_id = self.hwsetup['ptl_id'],posids=[],fidids=[],
                  simulator_on = False,
                  user_interactions_enabled = True,
                  db_commit_on = False,
                  local_commit_on = True,
                  local_log_on = True,
                  printfunc = print,
                  verbose = True,
                  collider_file = None,
                  sched_stats_on = False,
                  anticollision = None) # valid options for anticollision arg: None, 'freeze', 'adjust'
        posids=self.ptl.posids
        fidids=self.ptl.fidids
        
        self._petals_map = {}
        for posid in self.ptl.posids:
            self._petals_map[posid] = self.ptl
        for fidid in self.ptl.fidids:
            self._petals_map[fidid] = self.ptl
        #self.m = posmovemeasure.PosMoveMeasure([self.ptl],self.fvc)
        #self.m.n_extradots_expected = self.hwsetup['num_extra_dots']


        #Get number of dots
        self.N_dots = {}
        for fidid in self.ptl.fidids:
            self.N_dots[fidid] = self.ptl.get_posfid_val(fidid,'N_DOTS')
        self.total_dots = sum(self.N_dots.values())
        # Initial image
        xy_meas,peaks,fwhms,imgfiles = self.fvc.measure_fvc_pixels(self.total_dots)
        xy_init = xy_meas
        xy_test = xy_meas

        #Get rid of any points that are moving
        self.xy_ref = []
        for this_xy in xy_test:
            test_delta = np.array(this_xy) - np.array(xy_init)
            test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
            if any(test_dist < self.ref_dist_tol) or all(test_dist > self.ref_dist_thres):
                self.xy_ref.append(this_xy)

        #Then turn one off at a time
        self.fids_identified = {}
        for fid in self.ptl.fidids:
            data = self.identify_one_fid(fid)
            if data is not None:
                self.fids_identified[fid] = data 
        import pdb;pdb.set_trace()    
        #Identify pinhole numbers and label data
        XY = {'ID':[], 'fvcX':[], 'fvcY':[]}
        for fidid, data in self.fids_identified.items():
            dev_loc = self.ptl.get_posfid_val(fidid, 'DEVICE_LOC')
            new_data = self.identify_pinholes(data)
            for i, xy in enumerate(new_data):
                name = str(dev_loc) + '-%d' %(i+1)
                XY['ID'].append(name)
                XY['fvcX'].append(xy[0])
                XY['fvcY'].append(xy[1])

        self.XY = pd.DataFrame.from_dict(XY)

        #Then pull the metrology data (maybe from the database?)
        self.file_metro = pc.dirs['hwsetups'] + '/petal%d_fiducials_metrology.csv' % int(self.petal_num)

        # Read dots identification result from ptl and store a dictionary
        pix_size=0.006

        metrology = pd.read_csv(self.file_metro)    
        metrology.columns = ['ID','metroX','metroY','metroZ']

        #merge pandas databases
        self.XY = self.XY.merge(metrology, on='ID',how='left')
         
        #Then send them through the fit and plot function
        fvcX_arr=self.XY['fvcX'].tolist()
        fvcX_arr = [-x for x in fvcX_arr]
        fvcY_arr=self.XY['fvcY'].tolist()
        metroX_arr=self.XY['metroX'].tolist()
        metroY_arr=self.XY['metroY'].tolist()

        #Then save the file 
        self.fit_and_plot(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr,flip=1)


    def identify_pinholes(self, data):
        this_data = np.array(data).T
        X = this_data[0]
        Y = this_data[1]

        xavg = np.mean(X)
        yavg = np.mean(Y)

        rr = []
        for pin in [0,1,2,3]:
            r = np.sqrt((X[pin]-xavg)**2.+(Y[pin]-yavg)**2.)
            rr.append(r)

        r = [(i/max(rr))*1.0969 for i in rr]
        ##Figure out correct labelling
        index_value=[3,0,2,1] # pinhole indices in order of increasing r_value
        index_name = ['FIF-4','FIF-1','FIF-3','FIF-2']
        r_values=[0.2500,0.7499,0.9607,1.0969]  # mm
        r_tolerance = 0.001

        index = []
        r_error =[]

        for i in range(0,len(r)):
            best_index=-1
            best_diff = 1.0e12  # start with infinity
            for j in range(0,len(r)):
                diff=r[i]-r_values[index_value[j]]  # difference
                if np.fabs(diff)<np.fabs(best_diff):
                    best_index=index_value[j]
                    best_diff=diff

            index.append(best_index)
            r_error.append(best_diff)
        new_list = []
        for i in index:
            new_list.append([X[i], Y[i]])
        return new_list

    def identify_one_fid(self, fidid):
        ptl = self.petal(fidid)
        num_expected = self.N_dots[fidid]
        if num_expected > 0:
            print('Temporarily turning off fiducial ' + fidid + ' to determine which dots belonged to it.')
            ptl.set_fiducials(fidid,'off')
            xy_meas,peaks,fwhms,imgfiles = self.fvc.measure_fvc_pixels(self.total_dots - num_expected)

            #Make sure no points are moving
            these_xyref = []
            for this_xy in self.xy_ref:
                test_delta = np.array(this_xy) - np.array(xy_meas)
                test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
                matches = [dist < self.ref_dist_tol for dist in test_dist]
                if not any(matches):
                    these_xyref.append(this_xy)
                    print('Ref dot ' + str(len(these_xyref)-1) + ' identified for fiducial ' + fidid + ' at fvc coordinates ' + str(this_xy))

            num_detected = len(these_xyref)
            if num_detected != num_expected:
                print('warning: expected ' + str(num_expected) + ' dots for fiducial ' + fidid + ', but detected ' + str(num_detected))
                return
            else:
                ptl.set_posfid_val(fidid,'DOTS_FVC_X',[these_xyref[i][0] for i in range(num_detected)])
                ptl.set_posfid_val(fidid,'DOTS_FVC_Y',[these_xyref[i][1] for i in range(num_detected)])
                ptl.set_posfid_val(fidid,'LAST_MEAS_OBS_X',[these_xyref[i][0] for i in range(num_detected)])
                ptl.set_posfid_val(fidid,'LAST_MEAS_OBS_Y',[these_xyref[i][1] for i in range(num_detected)])
                ptl.set_fiducials(fidid,'on')

                return these_xyref


    def petal(self, posid_or_fidid_or_dotid):
        """Returns the petal bject associated with a asingle id key.
        """
        return self._petals_map[posid_or_fidid_or_dotid]

    def fit_and_plot(self,fvcX_arr,fvcY_arr,metroX_arr,metroY_arr,flip=0):

        pars = Parameters() # Input parameters model and initial guess
        pars.add('offx', value=0.)
        pars.add('offy', value=0.)
        pars.add('angle', value=0.0)
        print('Fitting Data: \n fvcX:',fvcX_arr,'\n metroX:',metroX_arr,'\n fvcY:',fvcY_arr,'\n metroY:',metroY_arr,'\n')

        pars.add('scale', value=1.)
        out = minimize(self._residual, pars, args=(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr)) # Find the minimum chi2

        if flip==1:
            offy=-out.params['offy'].value
            rot=(180.-out.params['angle'].value) % 360 # fixed 01/24/19
        else:
            offy=out.params['offy'].value
            rot=out.params['angle'].value
     #  Plot
        pars_out=out.params
        model=pars_out['scale']*(self._rot(fvcX_arr+pars_out['offx'],fvcY_arr+pars_out['offy'],pars_out['angle']))
        model_x=np.array(model[0,:]).ravel()
        model_y=np.array(model[1,:]).ravel()
        if self.fvc.fvc_type=='FLI':
            pix_size=0.006
            label='fvcmag  '+str(out.params['scale'].value/pix_size)+'\n'+'fvcrot  '+str(rot)+'\n' +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n'
        else: 
            label='scale  '+str(out.params['scale'].value)+'\n'+'fvcrot  '+str(rot)+'\n' +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n'

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

            filename = self.petal_dir+'petal%s.par' % self.petal_num
            print("Saving these parameters to this file: ", filename)
            f = open(filename,'w')
            output_lines='fvcmag  '+str(out.params['scale'].value/pix_size)+'\n'+'fvcrot  '+str(rot)+'\n' \
                        +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n' \
                        +'fvcyflip  '+str(flip)+'\n'+'fvcnrow  6000 \n'+'fvcncol  6000 \n'+'fvcpixmm  '+str(pix_size)
            print(output_lines)
            f.write(output_lines)
            f.close()

        else:
            print('Instrument Pars:',out.params['angle'].value ,out.params['scale'].value,[out.params['offx'].value,out.params['offy'].value])
            print('The original Instrument Pars are:',self.fvc.rotation,self.fvc.scale,self.fvc.translation)
            a=input('Do you want to update the Pars?')
            if a =='Y' or a=='y' or a=='Yes' or a=='YES' or a=='yes':
                self.fvc.rotation=out.params['angle'].value
                self.fvc.translation=[out.params['offx'].value,out.params['offy'].value]
                self.fvc.scale=out.params['scale'].value
                self.hwsetup['rotation']=out.params['angle'].value
                self.hwsetup['translation']=[out.params['offx'].value,out.params['offy'].value]
                self.hwsetup['scale']=out.params['scale'].value
                self.hwsetup.write()
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

    def dots_match(self,obs_x,obs_y,obs_ref_x,obs_ref_y,metro_x,metro_y,metro_ref_x,metro_ref_y):
        if len(obs_x) > len(metro_x):
            raise exception('Obs Data Length > Metrology Data Length! Can not work. ')
        n_dots=len(obs_x)
        n_metro_dots=len(metro_x)
        obs_x=np.array(obs_x)
        obs_y=np.array(obs_y)
        obs_ref_x=np.array(obs_ref_x)
        obs_ref_y=np.array(obs_ref_y)
        metro_x=np.array(metro_x)
        metro_y=np.array(metro_y)
        metro_ref_x=np.array(metro_ref_x)
        metro_ref_y=np.array(metro_ref_y)
        output_x=obs_x
        output_y=obs_y
        mask_selected=np.zeros((n_metro_dots,), dtype=int)
        for i in range(n_dots):
            x_this,y_this=obs_x[i],obs_y[i]
            scale_obs=np.sqrt((obs_ref_x[0]-obs_ref_x[1])**2+(obs_ref_y[0]-obs_ref_y[1])**2)
            scale_metro=np.sqrt((metro_ref_x[0]-metro_ref_x[1])**2+(metro_ref_y[0]-metro_ref_y[1])**2)

            dist_vector_obs=np.sqrt((x_this-obs_ref_x)**2+(y_this-obs_ref_y)**2)/scale_obs
            dist_arr=np.zeros(n_metro_dots)
            for j in range(n_metro_dots):
                xx,yy=metro_x[j],metro_y[j]
                dist_vector_metro=np.sqrt((xx-metro_ref_x)**2+(yy-metro_ref_y)**2)/scale_metro
                dist_arr[j]=np.sum((dist_vector_metro-dist_vector_obs)**2)
            print(dist_arr)
            ind_min,=np.where(dist_arr == min(dist_arr))
            output_x[i]=metro_x[ind_min[0]] 
            output_y[i]=metro_y[ind_min[0]]
            mask_selected[ind_min[0]]=1 
        return output_x,output_y
            
if __name__=="__main__":
    petal_num = input("Enter Petal No. being tested (2-11): ")
    DPP = Derive_Platemaker_Pars(petal_num)


