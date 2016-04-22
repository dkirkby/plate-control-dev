import time
import warnings
import multicens
import numpy as np
import gc
import sbigcam

class SBIG_Grab_Cen(object):
    """Module for grabbing images and calculating centroids using the SBIG camera.
    """
    def __init__(self):  
        self.cam=sbigcam.SBIGCam()
        self.cam.select_camera('ST8300')
        self.close_camera() # in case driver was previously left in "open" state
        self.open_camera()      
        self.__exposure_time = 90 # milliseconds, 90 ms is the minimum
        self.min_brightness = 5000
        self.max_brightness = 50000
        self.verbose = False
        self.write_fits = True
        self.take_darks = False # whether to measure a dark image and subtract it out

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
            if self.write_fits:
                self.cam.write_fits(D,'_SBIG_dark_image.FITS')
        else:
            D = None             
        if self.verbose:
            print("Taking light image...")
        self.cam.set_dark(False)
        L = self.cam.start_exposure() 
        if self.write_fits:
            self.cam.write_fits(L,'_SBIG_light_image.FITS')
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
        if brightness > self.max_brightness:
            warnings.warn('Spot may be over saturated (brightness = {}'.format(brightness))
        
        # call routine to determine multiple gaussian-fitted centroids
        xcen, ycen, fwhm = multicens.multiCens(LD, nWin, self.verbose, self.write_fits) 
        xy = [[xcen[i],ycen[i]] for i in range(len(xcen))]
        
        toc = time.time()
        if self.verbose:
            print("Time used: "+str(toc-tic)+"\n")
        return xy,brightness,tic-toc
        
    def open_camera(self):
        self.cam.open_camera()
        
    def close_camera(self):
        self.cam.close_camera()
    