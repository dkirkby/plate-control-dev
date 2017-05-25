import os
import sys
sys.path.append(os.path.abspath('../posfidfvc/SBIG/'))
sys.path.append(os.path.abspath('../petal/'))
import numpy as np
import time
import postransforms
import posconstants as pc

class FVCHandler(object):
    """Provides a generic interface to the Fiber View Camera. Can support different
    particular FVC implementations, providing a common set of functions to call
    from positioner control scripts.
    
    The order of operations for transforming from CCD coordinates to output is:
        1. rotation
        2. scale
        3. translation
    """
    def __init__(self, fvc_type='SBIG', platemaker_instrument='em', printfunc=print, save_sbig_fits=True):
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)
        self.fvc_type = fvc_type # 'SBIG' or 'SBIG_Yale' or 'FLI' or 'simulator'
        if self.fvc_type == 'SBIG':
            import sbig_grab_cen
            self.sbig = sbig_grab_cen.SBIG_Grab_Cen(save_dir=pc.dirs['temp_files'])
            self.sbig.take_darks = False # typically we have the test stand in a dark enough enclosure, so False here saves time
            self.sbig.write_fits = save_sbig_fits
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':   
            self.platemaker_instrument = platemaker_instrument # this setter also initializes self.fvcproxy
        elif self.fvc_type == 'simulator':
            self.sim_err_max = 0.01 # 2D err max for simulator
            self.printfunc('FVCHandler is in simulator mode with max 2D errors of size ' + str(self.sim_err_max) + '.')
        if 'SBIG' in self.fvc_type:
            self.exposure_time = 0.20
            self.max_counts = 2**16 - 1 # SBIC camera ADU max
        else:
            self.exposure_time = 1.0
            self.max_counts = 2**16 - 1 # FLI camera ADU max
        self.trans = postransforms.PosTransforms() # general transformer object -- does not look up specific positioner info, but fine for QS <--> global X,Y conversions
        self.rotation = 0        # [deg] rotation angle from image plane to object plane
        self._scale = 1.0        # scale factor from image plane to object plane
        self.translation = [0,0] # translation of origin within the image plane
        self.fitbox_mm = 0.7     # size of gaussian fitbox at the object plane (note minimum fiducial dot distance is 1.0 mm apart)

    @property
    def scale(self):
        '''Return the fiber view camera scale. (scale * image plane --> object plane)
        '''
        return self._scale

    @scale.setter
    def scale(self,scale):
        '''Set the fiber view camera scale. (scale * image plane --> object plane)
        '''
        self._scale = scale
        if 'SBIG' in self.fvc_type:
            self.sbig.size_fitbox = int(np.ceil(self.fitbox_mm/2 / scale))

    @property
    def platemaker_instrument(self):
        """Return name of the platemaker instrument.
        """
        return self.__platemaker_instrument

    @platemaker_instrument.setter
    def platemaker_instrument(self,name):
        """Set the platemaker instrument.
        """
        from DOSlib.proxies import FVC
        self.__platemaker_instrument = name
        self.fvcproxy = FVC(self.platemaker_instrument)
        self.printfunc('proxy FVC created for instrument %s' % self.fvcproxy.get('instrument'))

    @property
    def exposure_time(self):
        """Time in seconds to expose.
        """
        return self.__exposure_time

    @exposure_time.setter
    def exposure_time(self,value):
        self.__exposure_time = value
        if self.fvc_type == 'SBIG':
            self.sbig.exposure_time = value*1000 # sbig_grab_cen thinks in milliseconds
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':
            self.fvcproxy.send_fvc_command('set',exptime=value)
        
    def measure_fvc_pixels(self, num_objects):
        """Gets a measurement from the fiber view camera of the centroid positions
        of all the dots of light landing on the CCD.
        
        INPUTS:  num_objects  ... integer, number of dots FVC should look for
        
        OUTPUT:  xy           ... list of measured dot positions in FVC pixel coordinates, of the form [[x1,y1],[x2,y2],...]
                 peaks        ... list of the peak brightness values for each dot, in the same order
                 fwhms        ... list of the fwhm for each dot, in the same order
                 imgfiles     ... list of image filenames that were produced
        """
        xy = []
        peaks = []
        fwhms = []
        imgfiles = []
        if self.fvc_type == 'SBIG':
            xy,peaks,fwhms,elapsed_time,imgfiles = self.sbig.grab(num_objects)
            peaks = [x/self.max_counts for x in peaks]
        elif self.fvc_type == 'simulator':
            pass # do nothing here -- random returns would break the identify fiducials and identify positioners methods
        else:
            zeros_dict = {i:{'x':0.0, 'y':0.0, 'mag':0.0, 'meas_err':1.0, 'flags':4} for i in range(num_objects)}
            self.fvcproxy.set_targets(zeros_dict)
            centroids = self.fvcproxy.locate('locate', send_centroids=True)
            if centroids == 'FAILED':
                self.printfunc('Failed to locate centroids using FVC.')
            else:
                for params in self.centroids.values():
                    xy.append([params['x'],params['y']])
                    peaks.append(self.normalize_mag(params['mag']))
                    fwhms.append(params['fwhm'])
        return xy,peaks,fwhms,imgfiles

    def measure_and_identify(self,expected_pos_xy,expected_ref_xy):
        """Calls for an FVC measurement, and returns a list of measured centroids.
        The centroids are in order according to their closeness to the list of
        expected xy values.

        If the expected xy are unknown, then use the measure method instead.

        INPUT:  expected_pos_xy ... list of expected positioner fiber locations
                expected_ref_xy ... list of expected fiducial positions

        OUTPUT: measured_pos_xy ... list of measured positioner fiber locations
                measured_ref_xy ... list of measured fiducial dot positions
                peaks_pos       ... list of peak brightnesses of positioners (same order)
                peaks_ref       ... list of peak brightnesses of fiducials dots (same order)
                fwhms_pos       ... list of fwhms of positioners (same order)
                fwhms_ref       ... list of fwhms of fiducial dots (same order)

        Lists of xy coordinates are of the form [[x1,y1],[x2,y2],...]
        
        All coordinates are in obsXY space (mm at the focal plane).
        """
        imgfiles = []        
        if self.fvc_type == 'simulator':
            sim_error_magnitudes = np.random.uniform(-self.sim_err_max,self.sim_err_max,len(expected_pos_xy))
            sim_error_angles = np.random.uniform(-np.pi,np.pi,len(expected_pos_xy))
            sim_errors = sim_error_magnitudes * np.array([np.cos(sim_error_angles),np.sin(sim_error_angles)])
            measured_pos_xy = (expected_pos_xy + np.transpose(sim_errors)).tolist()
            measured_ref_xy = expected_ref_xy
            peaks_pos = np.random.uniform(0.4,0.6,len(measured_pos_xy)).tolist()
            peaks_ref = np.random.uniform(0.4,0.6,len(measured_ref_xy)).tolist()
            fwhms_pos = np.random.uniform(0.4,0.6,len(measured_pos_xy)).tolist()
            fwhms_ref = np.random.uniform(0.4,0.6,len(measured_ref_xy)).tolist()
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':
            fiber_ctr_flag = 4
            fiduc_ctr_flag = 8
            index_pos = -1  # future implementation: use positioner/fiducial index mapping module
            index_ref = -1
            indices_pos = []
            indices_ref = []
            expected_qs = []
            for xylist in [expected_pos_xy,expected_ref_xy]:
                if xylist == expected_pos_xy:
                    flag = fiber_ctr_flag
                    index_pos += 1
                    indices_pos.append[index_pos]
                    index = index_pos
                else:
                    flag = fiduc_ctr_flag
                    index_ref += 1
                    indices_ref.append[index_ref]
                    index = index_ref
                for xy in xylist:
                    qs = self.trans.obsXY_to_QS(xy)
                    expected_qs.append({'id':index, 'q':qs[0], 's':qs[1], 'flags':flag})
            measured_qs = self.fvcproxy.measure(expected_qs)
            measured_pos_xy = [None]*len(indices_pos)
            measured_ref_xy = [None]*len(indices_ref)
            peaks_pos = [None]*len(indices_pos)
            peaks_ref = [None]*len(indices_ref)
            fwhms_pos = [None]*len(indices_pos)
            fwhms_ref = [None]*len(indices_ref)
            for qs_dict in measured_qs:
                qs = [qs_dict['q'], qs_dict['s']]
                xy = self.trans.QS_to_obsXY(qs)
                if qs_dict['flags'] == fiber_ctr_flag:
                    index = indices_pos.index(qs_dict['id'])
                    measured_pos_xy[index] = xy
                    peaks_pos[index] = self.normalize_mag(qs_dict['mag'])
                    fwhms_pos[index] = qs_dict['fwhm']
                else:
                    # As of 2017-05-25, FLI/platemaker sadly still do not support returning ref dot positions or any other data.
                    # index = indices_ref.index(qs_dict['id'])
                    # measured_ref_xy[index] = xy
                    # peaks_ref[index] = self.normalize_mag(qs_dict['mag'])
                    # fwhms_ref[index] = qs_dict['fwhm']
                    pass
            return measured_pos_xy, measured_ref_xy, peaks_pos, peaks_ref, fwhms_pos, fwhms_ref, imgfiles
        else:
            expected_xy = expected_pos_xy + expected_ref_xy
            num_objects = len(expected_xy)
            unsorted_xy,unsorted_peaks,unsorted_fwhms,imgfiles = self.measure(num_objects)
            measured_xy,sorted_idxs = self.sort_by_closeness(unsorted_xy, expected_xy)
            measured_pos_xy = measured_xy[:len(expected_pos_xy)]
            measured_ref_xy = measured_xy[len(expected_pos_xy):]
            peaks = np.array(unsorted_peaks)[sorted_idxs].tolist()
            fwhms = np.array(unsorted_fwhms)[sorted_idxs].tolist()
            split = len(expected_pos_xy)
            peaks_pos = peaks[:split]
            peaks_ref = peaks[split:]
            fwhms_pos = fwhms[:split]
            fwhms_ref = fwhms[split:]
            measured_pos_xy = self.correct_using_ref(measured_pos_xy, measured_ref_xy, expected_ref_xy)
        return measured_pos_xy, measured_ref_xy, peaks_pos, peaks_ref, fwhms_pos, fwhms_ref, imgfiles

    def correct_using_ref(self, measured_pos_xy, measured_ref_xy, expected_ref_xy):
        """Evaluates the correction that transforms measured_ref_xy into expected_ref_xy,
        and then applies this to the measured_xy values.
        """
        if len(measured_ref_xy) > 0:
            xy_diff = np.array(measured_ref_xy) - np.array(expected_ref_xy)
            xy_shift = np.median(xy_diff,axis=0)
            measured_pos_xy -= xy_shift
            measured_pos_xy = measured_pos_xy.tolist()
            # if two or more ref dots that are widely enough spaced, consider applying rotation and scale corrections here
        return measured_pos_xy

    def sort_by_closeness(self, unknown_xy, expected_xy):
        """Sorts the list unknown_xy so that each point is at the same index
        as its closest-distance match in the list expected_xy.
        """
        if len(unknown_xy) != len(expected_xy):
            self.printfunc('warning: unknown_xy length = ' + str(len(unknown_xy)) + ' but expected_xy length = ' + str(len(expected_xy)))
        xy = [None]*len(expected_xy)
        sorted_idxs = [None]*len(expected_xy)
        dist = []
        for e in expected_xy:
            delta = np.array(unknown_xy) - np.array(e)
            dist.append(np.sqrt(np.sum(delta**2,axis=1)).tolist())
        dist = np.array(dist)
        for i in range(len(unknown_xy)):
            min_idx_1D = np.argmin(dist)
            unknown_min_idx = np.mod(min_idx_1D,len(unknown_xy))
            expected_min_idx = np.int(np.floor(min_idx_1D/len(expected_xy)))
            xy[expected_min_idx] = unknown_xy[unknown_min_idx]
            sorted_idxs[expected_min_idx] = unknown_min_idx
            dist[expected_min_idx,:] = np.inf # disable used up "expected" row
            dist[:,unknown_min_idx] = np.inf # disable used up "unknown" column
        return xy, sorted_idxs

    def measure(self, num_objects=1):
        """Calls for an FVC image capture, applies simple transformations to get the
        centroids into the units and orientation of the object plane, and returns
        the centroids.
        
        This method short-circuits platemaker, operating directly on dots from the fiber
        view camera in a more simplistic manner. The general idea is that this is not a
        replacement for the accuracy performance of platemaker. Rather it is used for
        bootstrapping our knowledge of a new setup to a good-enough point where we can
        start to use platemaker.
            num_objects     ... number of dots to look for in the captured image
        """
        fvcXY,peaks,fwhms,imgfiles = self.measure_fvc_pixels(num_objects)
        obsXY = self.fvcXY_to_obsXY_noplatemaker(fvcXY)
        return obsXY,peaks,fwhms,imgfiles

    def normalize_mag(self,value):
        """Convert magnitude values coming from Rabinowitz code to a normalized
        brightness value in the range 0.0 to 1.0.
        25.0 - 2.5*log10(peak signal in ADU)
        """
        newval = 10**((25.0 - value)/2.5)
        newval = newval / self.max_counts
        newval = min(newval,1.0)
        newval = max(newval,0.0)
        return newval

    def fvcXY_to_obsXY_noplatemaker(self,xy):
        """Convert a list of xy values in fvc pixel space to obsXY coordinates,
        using a simple rotation, scale, translate sequence rather than platemaker.
          INPUT:  [[x1,y1],[x2,y2],...]  fvcXY (pixels on the CCD)
          OUTPUT: [[x1,y1],[x2,y2],...]  obsXY (mm at the focal plane)
        """
        if xy != []:
            xy = pc.listify2d(xy)
            xy_np = np.array(xy).transpose()
            rot = FVCHandler.rotmat2D_deg(self.rotation)
            xy_np = np.dot(rot, xy_np)
            xy_np *= self.scale
            translation_x = self.translation[0] * np.ones(np.shape(xy_np)[1])
            translation_y = self.translation[1] * np.ones(np.shape(xy_np)[1])
            xy_np += [translation_x,translation_y]
            xy = xy_np.transpose().tolist()       
        return xy
    
    def obsXY_to_fvcXY_noplatemaker(self,xy):
        """Convert a list of xy values in obsXY coordinates to fvc pixel space,
        using a simple rotation, scale, translate sequence rather than platemaker.
          INPUT:  [[x1,y1],[x2,y2],...]  obsXY (mm at the focal plane)
          OUTPUT: [[x1,y1],[x2,y2],...]  fvcXY (pixels on the CCD)
        """
        if xy != []:
            xy = pc.listify2d(xy)
            xy_np = np.array(xy).transpose()
            translation_x = self.translation[0] * np.ones(np.shape(xy_np)[1])
            translation_y = self.translation[1] * np.ones(np.shape(xy_np)[1])
            xy_np -= [translation_x,translation_y]
            xy_np /= self.scale
            rot = FVCHandler.rotmat2D_deg(-self.rotation)
            xy_np = np.dot(rot, xy_np)
            xy = xy_np.transpose().tolist() 
        return xy
    
    @staticmethod
    def rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        radians = np.deg2rad(angle)
        return np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])

if __name__ == '__main__':
    f = FVCHandler(fvc_type='SBIG')
    n_objects = 5
    n_repeats = 1
    xy = []
    peaks = []
    fwhms = []
    print('start taking ' + str(n_repeats) + ' images')
    start_time = time.time()
    for i in range(n_repeats):
        these_xy,these_peaks,these_fwhms,imgfiles = f.measure(n_objects)
        xy.append(these_xy)
        peaks.append(these_peaks)
        fwhms.append(these_fwhms)
        print('ndots: ' + str(len(xy[i])))
        print('measured xy positions:')
        print(xy[i])
        print('measured peak brightnesses:')
        print(peaks[i])
        print('dimmest (scale 0 to 1): ' + str(min(peaks[i])))
        print('brightest (scale 0 to 1): ' + str(max(peaks[i])))
        print('')
        print('measured full width half maxes:')
        print(fwhms[i])
        print('dimmest (scale 0 to 1): ' + str(min(fwhms[i])))
        print('brightest (scale 0 to 1): ' + str(max(fwhms[i])))
        print('')
    total_time = time.time() - start_time
    print('total time = ' + str(total_time) + ' (' + str(total_time/n_repeats) + ' per image)')
