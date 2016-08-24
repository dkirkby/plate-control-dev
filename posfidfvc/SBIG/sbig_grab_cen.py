import time
import warnings
import multicens
import numpy as np
import gc
import sbigcam
import os

class SBIG_Grab_Cen(object):
    """Module for grabbing images and calculating centroids using the SBIG camera.
    """
    def __init__(self):  
        self.cam=sbigcam.SBIGCam()
        self.cam.select_camera('ST8300')
        self.close_camera() # in case driver was previously left in "open" state
        self.open_camera()      
        self.__exposure_time = 200 # milliseconds, 90 ms is the minimum
        self.cam.set_exposure_time(self.exposure_time)
        self.min_brightness = 5000
        self.max_brightness = 50000
        self.verbose = False
        self.write_fits = False
        self.take_darks = False # whether to measure a dark image and subtract it out
        self.flip_horizontal = True # whether to reflect image across y axis
        self.flip_vertical = False # whether to reflect image across x axis

    @property
    def exposure_time(self):
        return self.__exposure_time

    @exposure_time.setter
    def exposure_time(self, exposure_time):
        self.__exposure_time = int(exposure_time)
        self.cam.set_exposure_time(self.exposure_time)

    def grab(self, nWin=1):
        """Calls function to grab light and dark images from SBIG camera, then centroids spots.
        
        INPUTS:
            nWin       ... integer, number of centroid windows. For the measure_camera_scale script, nwin should be equal 1
    
        RETURNS
            xywin      ... list of centroid coordinates and fwhms for each spot in window ('list of lists')
            brightness ... value of brightest pixel (dark subtracted)
            time       ... elapsed time in seconds
            
        Sample call:
        	xywin, brightness, time = sbig_grab_cen_instance.grab(1)
         """
        tic = time.time()
        if self.take_darks:
            if self.verbose:
                print("Taking dark image...")
            self.cam.set_dark(True)  
            D = self.cam.start_exposure()
            D = self.flip(D)
            if self.write_fits:
                filename = '_SBIG_dark_image.FITS'
                try:
                    os.remove(filename)
                except:
                    print('couldn''t remove file: ' + filename)
                self.cam.write_fits(D,filename)
                
        else:
            D = None             
        if self.verbose:
            print("Taking light image...")
        self.cam.set_dark(False)

        nexpose=3
        while nexpose > 0:
            L = self.cam.start_exposure()
            L = self.flip(L)

            if self.write_fits:
                filename = '_SBIG_light_image.FITS'
                try:
                    os.remove(filename)
                except:
                    print('couldn''t remove file: ' + filename)
                self.cam.write_fits(L,filename)
            if not(self.take_darks):
                D = np.zeros(np.shape(L), dtype=np.int32)
            LD = np.array(L,dtype = np.int32) - np.array(D,dtype = np.int32)
            if self.write_fits and self.take_darks:
                self.cam.write_fits(LD,'_SBIG_diff_image.FITS')
            
            del L
            del D
            gc.collect()
            
            brightness = np.amax(LD)
            if self.verbose:
                print("Brightness: "+str(brightness))
            if brightness < self.min_brightness:
                warnings.warn('Spot seems dark (brightness = {})'.format(brightness))
                nexpose=nexpose-1
            else:
                if brightness > self.max_brightness:
                    warnings.warn('Spot may be over saturated (brightness = {}'.format(brightness))
                nexpose=0
                


        # call routine to determine multiple gaussian-fitted centroids
        centroiding_tic = time.time()
        xcen, ycen, fwhm = multicens.multiCens(LD, nWin, self.verbose, self.write_fits)
        xy = [[xcen[i],ycen[i]] for i in range(len(xcen))]
        centroiding_toc = time.time()
        if self.verbose:
            print('centroiding time: ' + str(centroiding_toc - centroiding_tic))
        
        toc = time.time()
        if self.verbose:
            print("Time used: "+str(toc-tic)+"\n")
        
        return xy,brightness,tic-toc
        
    def open_camera(self):
        self.cam.open_camera()
        
    def close_camera(self):
        self.cam.close_camera()

    def flip(self, img):
        if self.flip_horizontal:
            img = np.fliplr(img)
        if self.flip_vertical:
            img = np.flipud(img)
        return img
    
