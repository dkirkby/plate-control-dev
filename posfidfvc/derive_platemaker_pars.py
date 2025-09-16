import os
import sys
#sys.path.remove('/software/products/plate_control-trunk/xytest')
#sys.path.remove('/software/products/plate_control-trunk/posfidfvc')
#sys.path.remove('/software/products/plate_control-trunk/petalbox')
#sys.path.remove('/software/products/plate_control-trunk/petal')

#sys.path.append(os.path.abspath('../petal/'))
#sys.path.append(os.path.abspath('../posfidfvc/'))
#sys.path.append(os.path.abspath('../xytest/'))

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
from lmfit import minimize, Parameters
from astropy.table import Table
from astropy.io import fits
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
#from derive_platemaker_pars import *
from astropy.stats import mad_std, sigma_clipped_stats
from astropy.modeling import models, fitting
from astropy.table import Table, Column
import astropy.visualization as visu
from astropy.visualization.mpl_normalize import ImageNormalize
import photutils as phot

class Derive_Platemaker_Pars(object):
    def __init__(self):
        global gui_root
        gui_root = tkinter.Tk()
        # get the station config info
        message = 'Pick hardware setup file.'
        hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
        self.hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)

        # software initialization and startup
        if self.hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in self.hwsetup:
            self.fvc=fvchandler.FVCHandler(fvc_type=self.hwsetup['fvc_type'],save_sbig_fits=self.hwsetup['save_sbig_fits'],platemaker_instrument=self.hwsetup['pm_instrument'],fvc_role=self.hwsetup['fvc_role'])
        else:
            self.fvc = fvchandler.FVCHandler(fvc_type=self.hwsetup['fvc_type'],save_sbig_fits=True)
            self.fvc.rotation = self.hwsetup['rotation'] # this value is used in setups without fvcproxy / platemaker
            self.fvc.scale = self.hwsetup['scale'] # this value is used in setups without fvcproxy / platemaker
            self.fvc.translation = self.hwsetup['translation']

        #self.ptl = petal.Petal(petal_id = self.hwsetup['ptl_id'],petalcontroller_id=7,posids=[],fidids=[],
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
        self.m = posmovemeasure.PosMoveMeasure([self.ptl],self.fvc)
        self.m.n_extradots_expected = self.hwsetup['num_extra_dots']


        # calibration routines
        rehome=tkinter.messagebox.askyesno(title='Rehome?',message='Rehome?')
        #import pdb;pdb.set_trace()
        if rehome:
            self.m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
        automatic_mode = tkinter.messagebox.askyesno(title='Automatic or Manual Mode?',message='Use Automatic Mode?')
        use_fiducial = tkinter.messagebox.askyesno(title='Use Fiducials?',message='Use Fiducials and measured Metrology data?')
        if automatic_mode:
            w=800
            h=600
            ws=gui_root.winfo_screenwidth()
            hs=gui_root.winfo_screenheight()
            x=(ws/2)-(w/2)
            y=(hs/2)-(h/2)
            gui_root.geometry('%dx%d+%d+%d' % (w,h,x,y))

            self.listbox1 = Listbox(gui_root, width=20, height=20,selectmode='multiple',exportselection=0)
            self.listbox1.grid(row=6, column=0,rowspan=10,pady=4,padx=15)
            Button(gui_root,text='OK',width=10,command=self.ok).grid(row=0,column=4,sticky=W,pady=4)
            yscroll_listbox1 = Scrollbar(command=self.listbox1.yview, orient=tkinter.VERTICAL)
            yscroll_listbox1.grid(row=6, column=0, rowspan=10,sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
            self.listbox1.configure(yscrollcommand=yscroll_listbox1.set)
            self.listbox1.insert(tkinter.END,'ALL')
            for key in sorted(posids):
                self.listbox1.insert(tkinter.END,str(key))
            self.listbox1.bind('<ButtonRelease-1>', self.get_list)

#       Load the information
            Label(gui_root,text="You selected").grid(row=3,column=5)
            self.e_selected=Entry(gui_root)
            self.e_selected.grid(row=3,column=6)

            mainloop()

            self.m.identify_many_enabled_positioners(self.selected_posids)

            self.make_instrfile(self.m.enabled_posids)
            self.push_to_db()
            self.m.identify_disabled_positioners()
        elif not automatic_mode and not use_fiducial:
            num_objects=input('How many dots are there in the image?')
            num_objects=int(num_objects)
            xy,peaks,fwhms,imgfiles=self.fvc.measure(num_objects)
            xy_fvc=self.fvc.obsXY_to_fvcXY(xy)
            x=[xy_fvc[i][0] for i in range(len(xy_fvc))]
            y=[xy_fvc[i][1] for i in range(len(xy_fvc))]
            plt.scatter(x,y)
            plt.show()

            x=[xy[i][0] for i in range(len(xy))]
            y=[xy[i][1] for i in range(len(xy))]
            plt.scatter(x,y)
            plt.show()

            imgfiles=['fvc.20190108160731.fits']
            n_sources=len(xy_fvc)
            id=[i+1 for i in range(n_sources)]

            # Read dots identification result from ptl and store a dictionary
            pix_size=0.006
            if self.fvc.fvc_type == 'FLI':
                flip=1  # x flip right now this is hard coded since we don't change the camera often.
            else:
                flip=0

            if flip==1:
                x_arr=[-xy_fvc[i][0] for i in range(n_sources)]
            else:
                x_arr=[xy_fvc[i][0] for i in range(n_sources)]
            y_arr=[xy_fvc[i][1] for i in range(n_sources)]
            sources=Table([id,x_arr,y_arr],names=('id','xcentroid','ycentroid'),dtype=('i8','f8','f8'))
            hdul = fits.open(imgfiles[0])
            data=hdul[0].data
            plt.ioff()
            sourceSel = SourceSelector(data, sources)
            plt.ion()
            sources_tofit=sourceSel.sources_selected


            if self.ptl.shape == 'petal':
                self.file_metro=pc.positioner_locations_file
            elif self.ptl.shape == 'small_array':
                self.file_metro=pc.small_array_locations_file
            else:
                self.printfunc('Must be a petal or a small_array to proceed. Exit')
                raise SystemExit

            obsX_arr,obsY_arr,obsXY_arr,fvcX_arr,fvcY_arr=[],[],[],[],[]
            metroX_arr,metroY_arr=[],[]

            # read the Metrology data first, then match positioners to DEVICE_LOC
            positioners = Table.read(self.file_metro,format='ascii.csv',header_start=0,data_start=1)
            device_loc_file_arr,metro_X_file_arr,metro_Y_file_arr=[],[],[]
            for row in positioners:
                device_loc_file_arr.append(row['device_loc'])
                metro_X_file_arr.append(row['X'])
                metro_Y_file_arr.append(row['Y'])
            n_sources=len(metro_X_file_arr)
            id=[i+1 for i in range(n_sources)]
            sources_metro=Table([id,metro_X_file_arr,metro_Y_file_arr],names=('id','xcentroid','ycentroid'),dtype=('i8','f8','f8'))
            plt.ioff()
            sourceSel_metro = SourceSelector(data, sources_metro)
            plt.ion()
            sources_tofit_metro=sourceSel_metro.sources_selected
            fvcX_arr=sources_tofit['xcentroid']
            fvcY_arr=sources_tofit['ycentroid']
            for i in range(len(fvcX_arr)):
                obsXY_this=self.fvc.fvcXY_to_obsXY([fvcX_arr[i],fvcY_arr[i]])[0]
                obsX_arr.append(obsXY_this[0])
                obsY_arr.append(obsXY_this[1])
            metroX_arr=sources_tofit_metro['xcentroid']
            metroY_arr=sources_tofit_metro['ycentroid']
            fvcX_arr=fvcX_arr.tolist()
            fvcY_arr=fvcY_arr.tolist()
            metroX_arr=metroX_arr.tolist()
            metroY_arr=metroY_arr.tolist()
            self.fit_and_plot(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr,flip=flip)

        else:

            num_objects=input('How many dots are there in the image?')
            num_objects=int(num_objects)
            xy,peaks,fwhms,imgfiles=self.fvc.measure(num_objects)
            imgfiles=['fvc.20190108160731.fits']
            xy_fvc=self.fvc.obsXY_to_fvcXY(xy)
            if self.fvc.fvc_type == 'FLI':
                flip=1  # x flip right now this is hard coded since we don't change the camera often.
            else:
                flip=0

            use_stored_centroids =False
            if use_stored_centroids:
                flip=1
                fvcdata=Table.read('fvc.20181203141706.pos',format='ascii.csv',header_start=0,data_start=1)
                xy_fvc=[[fvcdata[i]['X'],fvcdata[i]['Y']] for i in range(len(fvcdata))]

            n_sources=len(xy_fvc)
            id=[i+1 for i in range(n_sources)]
            if flip==1:
                x_arr=[-xy_fvc[i][0] for i in range(n_sources)]
            else:
                x_arr=[xy_fvc[i][0] for i in range(n_sources)]
            y_arr=[xy_fvc[i][1] for i in range(n_sources)]
            sources=Table([id,x_arr,y_arr],names=('id','xcentroid','ycentroid'),dtype=('i8','f8','f8'))
            hdul = fits.open(imgfiles[0])
            data = hdul[0].data
            plt.ioff()
            sourceSel = SourceSelector(data, sources)
            plt.ion()
            sources_tofit=sourceSel.sources_selected


            self.file_metro=tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("CSV file","*.csv"),("All Files","*")), title='Select Metrology Data')

            # Read dots identification result from ptl and store a dictionary
            pix_size=0.006
            if self.fvc.fvc_type == 'FLI':
                flip=1  # x flip right now this is hard coded since we don't change the camera often.
            else:
                flip=0
            obsX_arr,obsY_arr,obsXY_arr,fvcX_arr,fvcY_arr=[],[],[],[],[]
            metroX_arr,metroY_arr=[],[]
            obsX_all_arr,obsY_all_arr=[],[]
            # read the Metrology data first
            fiducials= Table.read(self.file_metro,format='ascii.csv',header_start=0,data_start=1)
            device_loc_file_arr,metro_X_file_arr,metro_Y_file_arr=[],[],[]
            for row in fiducials:
                metro_X_file_arr.append(row['X'])
                metro_Y_file_arr.append(row['Y'])
            n_sources=len(metro_X_file_arr)
            id=[i+1 for i in range(n_sources)]
            sources_metro=Table([id,metro_X_file_arr,metro_Y_file_arr],names=('id','xcentroid','ycentroid'),dtype=('i8','f8','f8'))
            plt.ioff()
            sourceSel_metro = SourceSelector(data, sources_metro)
            plt.ion()
            sources_tofit_metro=sourceSel_metro.sources_selected
            fvcX_arr=sources_tofit['xcentroid']
            fvcY_arr=sources_tofit['ycentroid']
            metroX_arr=sources_tofit_metro['xcentroid']
            metroY_arr=sources_tofit_metro['ycentroid']
            fvcX_arr=fvcX_arr.tolist()
            fvcY_arr=fvcY_arr.tolist()
            metroX_arr=metroX_arr.tolist()
            metroY_arr=metroY_arr.tolist()

            use_selected = tkinter.messagebox.askyesno(title='Use Selected Only?',message='Use selected dots only for fitting?')
            if use_selected:
                self.fit_and_plot(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr,flip=flip)
            else:
                output_x,output_y=self.dots_match(x_arr,y_arr,fvcX_arr,fvcY_arr,metro_X_file_arr,metro_Y_file_arr,metroX_arr,metroY_arr)
                self.fit_and_plot(x_arr,y_arr,output_x,output_y,flip=flip)

    def ok(self):
        gui_root.destroy()

    def get_list(self,event):
        # get selected line index
        index = self.listbox1.curselection()
        # get the line's text
        self.selected=[]
        self.selected_posids=[]
        self.selected_can=[]
        for i in range(len(index)):
            self.selected.append(self.listbox1.get(index[i]))
            if 'ALL' in self.selected:
                self.selected_posids=list(self.ptl.posids)
                self.selected_can=[20000]
            else:
                self.selected_posids.append(self.selected[i])
                self.selected_can.append(int(str(self.selected[i][1:6])))
        self.e_selected.delete(0,END)
        self.e_selected.insert(0,str(self.selected_can))

    def make_instrfile(self,posids):
        '''Define function for making platemaker instrument file.
        '''
        if self.ptl.shape == 'petal':
            self.file_metro=pc.positioner_locations_file
        elif self.ptl.shape == 'small_array':
            self.file_metro=pc.small_array_locations_file
        else:
            self.printfunc('Must be a petal or a small_array to proceed. Exit')
            raise SystemExit

        # Read dots identification result from ptl and store a dictionary
        pix_size=0.006
        if self.fvc.fvc_type == 'FLI':
            flip=1  # x flip right now this is hard coded since we don't change the camera often.
        else:
            flip=0
        posids=list(posids)
        n_pos=len(posids)
        pos_fid_dots={}
        obsX_arr,obsY_arr,obsXY_arr,fvcX_arr,fvcY_arr=[],[],[],[],[]
        metroX_arr,metroY_arr=[],[]

        # read the Metrology data first, then match positioners to DEVICE_LOC
        positioners = Table.read(self.file_metro,format='ascii.csv',header_start=0,data_start=1)
        device_loc_file_arr,metro_X_file_arr,metro_Y_file_arr=[],[],[]
        for row in positioners:
            device_loc_file_arr.append(row['device_loc'])
            metro_X_file_arr.append(row['X'])
            metro_Y_file_arr.append(row['Y'])


        for i in range(len(posids)):
            posid=posids[i]
            #thi_petal=self.ptl.petal(posid)
            obsX_arr.append(float(self.ptl.get_posfid_val(posid,'LAST_MEAS_OBS_X')))
            obsY_arr.append(float(self.ptl.get_posfid_val(posid,'LAST_MEAS_OBS_Y')))
            obsXY_arr.append([obsX_arr[i],obsY_arr[i]])
            fvcXY_this=self.fvc.obsXY_to_fvcXY([obsXY_arr[i]])
            if flip ==1:
                fvcX_arr.append(-fvcXY_this[0][0])
            else:
                fvcX_arr.append(fvcXY_this[0][0])
            fvcY_arr.append(fvcXY_this[0][1])
            device_loc_this=self.ptl.get_posfid_val(posid,'DEVICE_LOC')
            index=device_loc_file_arr.index(device_loc_this)
            metroX_arr.append(metro_X_file_arr[index])
            metroY_arr.append(metro_Y_file_arr[index])


        obsX_arr=np.array(obsX_arr)
        obsY_arr=np.array(obsY_arr)

        self.fit_and_plot(fvcX_arr,fvcY_arr,metroX_arr,metroY_arr,flip=flip)

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
            filename = 'instrmaker.par'
            f = open(filename,'w')
            output_lines='fvcmag  '+str(out.params['scale'].value/pix_size)+'\n'+'fvcrot  '+str(rot)+'\n' \
                        +'fvcxoff  '+str(out.params['offx'].value)+'\n'+'fvcyoff  '+str(offy)+'\n' \
                        +'fvcyflip  '+str(flip)+'\n'+'fvcnrow  6000 \n'+'fvcncol  6000 \n'+'fvcpixmm  '+str(pix_size)
            print(output_lines)
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
    gui = Derive_Platemaker_Pars()


class SourceSelector():
        """
        Tool created to click a source on a image, and return
        the source found in "sources"
        (astropy Table returned by phot.daofind())
        """

        def __init__(self, im, sources ):
                self.sources = sources
                self.sources_selected=Table([[],[],[]],names=('id','xcentroid','ycentroid'),dtype=('i8','f8','f8'))
                self.im = im
                self.fig = plt.figure(figsize=(22,10))
                self.ax = self.fig.add_subplot(111) #,aspect='equal')
                self.fig.tight_layout()
                self.state = '' # état du selecteur (selecting, adding or deleting)

                # données utiles pour daofind (si ajout de sources ?|  la main)
                pix_sz = 0.015  # pixel size in mm
                self.bkg_sigma = mad_std(im)
                self.FWHM_estim = lambda z: abs(z) / 2.0 / 1.7 / pix_sz + 3.333


                #other way of computing norme for vizualisation
                H,bin_edges=np.histogram(im,bins=20000)
                x=(bin_edges[:-1]+bin_edges[1:])/2.0
                Fitter=fitting.LevMarLSQFitter()
                model = models.Gaussian1D(amplitude=H.max(),mean=np.mean(im),stddev=self.bkg_sigma)
                fit = Fitter(model, x, H)
                mm = fit.mean.value
                self.bkg_sigma = np.abs(fit.stddev.value)
                # high vmax better with R and Z that have bad amps (with high values)
                norm = ImageNormalize(vmin=mm-4*self.bkg_sigma, vmax=mm+40*self.bkg_sigma, stretch=visu.SqrtStretch())

                self.ax.imshow(im, aspect='equal', norm=norm)
                self.crosses, = self.ax.plot(self.sources['xcentroid'],self.sources['ycentroid'],'x',color='green', mew=2,ms=8)
                self.crosses_selected, = self.ax.plot(self.sources_selected['xcentroid'],self.sources_selected['ycentroid'],'x',color='blue', mew=2,ms=8)

                self.sh=im.shape
                self.ax.set_xlim(0,self.sh[1])
                self.ax.set_ylim(0,self.sh[0])

                self.ax.format_coord = self.format_coord # reassign format coord function to my function (just added the "status" display)
                self.cid = self.fig.canvas.mpl_connect('button_press_event', self.onclick)
                self.cidkey1 = self.fig.canvas.mpl_connect('key_press_event', self.onkeypress)
                self.cidkey2 = self.fig.canvas.mpl_connect('key_release_event', self.onkeyrelease)

                self.columns = []
                self.rows = []

                print("Welcome to the Source Selector tool")
                print("------------------------------------")
                print("Press and hold 'Shift' and click left or right to add or suppress sources")
                print("Press and hold 'Ctrl' and click left or right to build a grid")
                print("Press 'Enter' to validate")
                print("Press 'q' to quit")
                plt.show()
                plt.close()

        def onclick(self, event):
                if self.fig.canvas.toolbar._active is not None:
                        return

                distances = np.asarray(np.sqrt((self.sources['xcentroid']-event.xdata)**2+(self.sources['ycentroid']-event.ydata)**2))
                ind, = np.where(distances <= 20.0)
                if len(ind) > 1:
                        # s'il y a plusieurs sources, on garde celle au plus près du clique
                        ind = ind[np.where(distances[ind] == distances[ind].min())]


                distances_selected = np.asarray(np.sqrt((self.sources_selected['xcentroid']-event.xdata)**2+(self.sources_selected['ycentroid']-event.ydata)**2))
                ind_selected, = np.where(distances_selected <= 20.0)
                if len(ind_selected) > 1:
                        # s'il y a plusieurs sources, on garde celle au plus près du clique
                        ind_selected = ind_selected[np.where(distances_selected[ind_selected] == distances_selected[ind_selected].min())]

                if all([ind.shape[0] == 0,any([self.state!='add or suppress',event.button!=1])]):
                # s'il n'y pas de source ?|  moins de 20 pix du clique et qu'on n'est pas
                # ?|  vouloir ajouter une sources, alors, on ne fait rien
                        return
                if len(ind) >= 1:
                        ind = int(ind[0])       # ind est un numpy array. On prend la valeur scalaire, et on la convertit en entier


                if len(ind_selected) >= 1:
                        ind_selected = int(ind_selected[0])       # ind est un numpy array. On prend la valeur scalaire, et on la convertit en entier

                if self.state=='':
                        print(self.sources[ind], "\n")

                if all([event.button == 3, self.state == 'add or suppress']):   # DELETING SOURCE
                        print('deleting source {}'.format(self.sources['id'][ind]))
                        self.sources.remove_row(ind)
                        self.crosses.set_data(self.sources['xcentroid'],self.sources['ycentroid'])
                        plt.pause(0.01)
                if all([event.button == 1, self.state == 'add or suppress']): # ADDING SOURCE
                        hw = 7
                        x0 = event.xdata - hw
                        x1 = event.xdata + hw
                        y0 = event.ydata - hw
                        y1 = event.ydata + hw
                        daofind = phot.DAOStarFinder(3.*self.bkg_sigma,self.FWHM_estim(0),sharplo=0.02, sharphi=0.95, roundlo=-0.9, roundhi=0.9)
                        newsource = daofind(self.im[int(y0):int(y1),int(x0):int(x1)])
                        if len(newsource) != 0:
                                j = newsource['peak'].argmax()
                                newsource = newsource[j]
                                newsource['xcentroid'] = newsource['xcentroid'] + x0
                                newsource['ycentroid'] = newsource['ycentroid'] + y0
                                print('adding source \n{}'.format(newsource))
                                if len(self.sources) != 0:
                                        self.sources.add_row(newsource)
                                else:
                                        self.sources = Table(newsource) # if self.sources was empty (no source found automatically), create it.
                                self.crosses.set_data(self.sources['xcentroid'],self.sources['ycentroid'])
                                plt.pause(0.01)
                if all([event.button == 1, self.state == 'select']): # select SOURCE
                        newsource = self.sources[ind]
                        print('Selected source \n{}'.format(newsource))
                        if len(self.sources_selected) != 0:
                            self.sources_selected.add_row(newsource)
                        else:
                            self.sources_selected = Table(newsource) # if self.sources was empty (no source found automatically), create it.
                        self.crosses_selected.set_data(self.sources_selected['xcentroid'],self.sources_selected['ycentroid'])
                        plt.pause(0.01)
                if all([event.button == 3, self.state == 'select']):   # DELETING SOURCE
                        print('deleting source {}'.format(self.sources_selected['id'][ind_selected]))
                        self.sources_selected.remove_row(ind_selected)
                        self.crosses_selected.set_data(self.sources_selected['xcentroid'],self.sources_selected['ycentroid'])
                        plt.pause(0.01)
                return

        def onkeypress(self, event):
                if (event.key.lower() == 'q'):
                        print("Quitting the Source Selector...")
                        self.fig.canvas.mpl_disconnect(self.cid)
                        self.fig.canvas.mpl_disconnect(self.cidkey1)
                        self.fig.canvas.mpl_disconnect(self.cidkey2)
                        indexes=np.linspace(1,len(self.sources),len(self.sources))
                        self.sources['id']=indexes
                        plt.close(self.fig)

                if (event.key.lower() == 'shift'):
                        self.state = 'add or suppress'
                if (event.key.lower() == 'control'):
                        self.state = 'select'

                if (event.key.lower() == 'enter'):
                        if any([len(self.columns)==0, len(self.rows)==0]):
                                return

                        (Xs,Ys) = self.intersects(self.rows, self.columns)

                        finalsources = self.sources[0:0] # an astropy Table of the same format, with no row.
                        for i,x0 in enumerate(Xs):
                                y0 = Ys[i]
                                distances = np.asarray(np.sqrt((self.sources['xcentroid']-x0)**2+(self.sources['ycentroid']-y0)**2))
                                ind, = np.where(distances <= 20.0)

                                if len(ind) > 1:
                                        # s'il y a plusieurs sources, on garde celle au plus près du clique
                                        ind = ind[np.where(distances[ind] == distances[ind].min())]

                                if ind.shape[0] != 0:
                                        ind = int(ind[0])
                                        finalsources.add_row(self.sources[ind])

                        self.ax.plot(finalsources['xcentroid'],finalsources['ycentroid'],'+',color='yellow', mew=2,ms=8)
                        plt.pause(0.01)

                        self.sources = finalsources # overwrite the "sources" Table with the few sources kept.

        def onkeyrelease(self, event):
                        self.state = ''

        def format_coord(self, x, y):
                """Return a format string formatting the *x*, *y* coord"""
                if x is None:
                        xs = '???'
                else:
                        xs = self.ax.format_xdata(x)
                if y is None:
                        ys = '???'
                else:
                        ys = self.ax.format_ydata(y)
                if all([self.fig.canvas.toolbar._active is None, self.state != '']):
                        return '%s SOURCES...   x=%s y=%s' % (self.state.upper(), xs, ys)
                else:
                        return 'x=%s y=%s' % (xs, ys)



