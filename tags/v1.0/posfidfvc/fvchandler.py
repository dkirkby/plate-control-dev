import os
import sys
sys.path.append(os.path.abspath('./SBIG/'))
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
    def __init__(self, fvc_type='SBIG', platemaker_instrument='em', printfunc=print):
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)
        self.fvc_type = fvc_type # 'SBIG' or 'SBIG_Yale' or 'FLI' or 'simulator'
        if self.fvc_type == 'SBIG':
            import sbig_grab_cen
            self.sbig = sbig_grab_cen.SBIG_Grab_Cen()
            self.sbig.take_darks = False # typically we have the test stand in a dark enough enclosure, so False here saves time
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':   
            self.platemaker_instrument = platemaker_instrument # this setter also initializes self.fvcproxy
            # I think here we would want to set the FVC either in FLI mode or SBIG mode?
        elif self.fvc_type == 'simulator':
            self.sim_err_max = 0.1
            self.printfunc('FVCHandler is in simulator mode with max errors of size ' + str(self.sim_err_max) + '.')
        if 'SBIG' in self.fvc_type:
            self.exposure_time = 0.2
            self.max_counts = 2**16 - 1
        else:
            self.exposure_time = 1.0
        self.trans = postransforms.PosTransforms() # general transformer object -- does not look up specific positioner info, but fine for QS <--> global X,Y conversions
        self.last_sequence_id = ''
        self.rotation = 0        # [deg] rotation angle from image plane to object plane
        self.scale = 1.0         # scale factor from image plane to object plane
        self.translation = [0,0] # translation of origin within the image plane

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
    
    @property
    def next_sequence_id(self):
        self.last_sequence_id = pc.timestamp_str_now()
        return self.last_sequence_id
        
    def measure_fvc_pixels(self, num_objects):
        """Gets a measurement from the fiber view camera of the centroid positions
        of all the dots of light landing on the CCD.
        
        INPUTS:  num_objects  ... integer, number of dots FVC should look for
        
        OUTPUT:  xy           ... list of measured dot positions in FVC pixel coordinates, of the form [[x1,y1],[x2,y2],...]
                 brightnesses ... list of the brightness values for each dot, in the same order
                 imgfiles     ... list of image filenames that were produced
        """
        xy = []
        brightnesses = []
        imgfiles = []
        if self.fvc_type == 'SBIG':
            xy,peaks,t,imgfiles = self.sbig.grab(num_objects)
            brightnesses = [x/self.max_counts for x in peaks]
        else:
            zeros_dict = {}
            for i in range(num_objects):
                zeros_dict[i] = {'x':0.0, 'y':0.0, 'mag':0.0, 'meas_err':1.0, 'flags':4}
            self.fvcproxy.set_targets(zeros_dict)
            sequence_id = self.next_sequence_id
            centroids = self.fvcproxy.send_fvc_command('locate',expid=sequence_id, send_centroids=True)
            if centroids == 'FAILED':
                self.printfunc('Failed to locate centroids using FVC.')
            else:
                for params in self.centroids.values():
                    xy.append(params['x'],params['y'])
                    brightnesses.append(self.mag_to_brightness(params['mag']))
        return xy,brightnesses,imgfiles

    def measure_and_identify(self,expected_pos_xy,expected_ref_xy):
        """Calls for an FVC measurement, and returns a list of measured centroids.
        The centroids are in order according to their closeness to the list of
        expected xy values.

        If the expected xy are unknown, then use the measure method instead.

        INPUT:  expected_pos_xy ... list of expected positioner fiber locations
                expected_ref_xy ... list of expected fiducial positions

        OUTPUT: measured_pos_xy ... list of measured positioner fiber locations
                measured_ref_xy ... list of measured fiducial positions

        Lists of xy coordinates are of the form [[x1,y1],[x2,y2],...]
        
        All coordinates are in obsXY space (mm at the focal plane).
        """
        imgfiles = []        
        if self.fvc_type == 'simulator':
            sim_errors = np.random.uniform(-self.sim_err_max,self.sim_err_max,np.shape(expected_pos_xy))
            measured_pos_xy = (expected_pos_xy + sim_errors).tolist()
            measured_ref_xy = expected_ref_xy
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':
            fiber_ctr_flag = 4
            fiduc_ctr_flag = 8
            index_pos = -1  # future implementation: use positioner/fiducial index mapping module
            index_ref = -1
            indices_pos = []
            indices_ref = []
            expected_xy = []
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
                    expected_xy.append({'id':index, 'q':qs[0], 's':qs[1], 'flags':flag})
            measured_xy = self.fvcproxy.measure(expected_xy)
            measured_pos_xy = [None]*len(indices_pos)
            measured_ref_xy = [None]*len(indices_ref)
            for xydict in measured_xy:
                qs = [xydict['q'],xydict['s']]
                xy = self.trans.QS_to_obsXY(qs)
                if xydict['flags'] == fiber_ctr_flag:
                    index = indices_pos.index(xydict['id'])
                    measured_pos_xy[index] = xy
                else:
                    index = indices_ref.index(xydict['id'])
                    measured_ref_xy[index] = xy
            return measured_pos_xy, measured_ref_xy
        else:
            expected_xy = expected_pos_xy + expected_ref_xy
            num_objects = len(expected_xy)
            unsorted_xy,brightnesses,imgfiles = self.measure(num_objects)
            measured_xy = self.sort_by_closeness(unsorted_xy, expected_xy)
            measured_pos_xy = measured_xy[:len(expected_pos_xy)]
            measured_ref_xy = measured_xy[len(expected_pos_xy):]
            measured_pos_xy = self.correct_using_ref(measured_pos_xy, measured_ref_xy, expected_ref_xy)
        return measured_pos_xy, measured_ref_xy, imgfiles

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
            dist[expected_min_idx,:] = np.inf # disable used up "expected" row
            dist[:,unknown_min_idx] = np.inf # disable used up "unknown" column
        return xy

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
        fvcXY,brightnesses,imgfiles = self.measure_fvc_pixels(num_objects)
        obsXY = self.fvcXY_to_obsXY_noplatemaker(fvcXY)
        return obsXY,brightnesses,imgfiles

    def mag_to_brightness(self,value):
        """Convert magnitude values coming from Rabinowitz code to a normalized
        brightness value in the range 0.0 to 1.0. Would prefer if Rabinowitz can
        modify his code later on to just give us the counts from the camera.
        """
        newval = 10**(value/-2.5)
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
    n_objects = 19
    n_repeats = 1
    xy = []
    brightnesses = []
    print('start taking ' + str(n_repeats) + ' images')
    start_time = time.time()
    for i in range(n_repeats):
        these_xy,these_brightnesses,imgfiles = f.measure(n_objects)
        xy.append(these_xy)
        brightnesses.append(these_brightnesses)
        print('measured xy positions:')
        print(xy[i])
        print('measured brightnesses:')
        print(brightnesses[i])
        print('')
    total_time = time.time() - start_time
    print('total time = ' + str(total_time) + ' (' + str(total_time/n_repeats) + ' per image)')
