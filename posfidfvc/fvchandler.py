import os
import sys
sys.path.append(os.path.abspath('./SBIG/'))
sys.path.append(os.path.abspath('../petal/'))
import numpy as np
import time
import postransforms

class FVCHandler(object):
    """Provides a generic interface to the Fiber View Camera. Can support different
    particular FVC implementations, providing a common set of functions to call
    from positioner control scripts.
    
    The order of operations for transforming from CCD coordinates to output is:
        1. rotation
        2. scale
        3. translation
    """
    def __init__(self, fvc_type='SBIG'):
        self.fvc_type = fvc_type # 'SBIG' or 'SBIG_Yale' or 'FLI' or 'simulator'
        if self.fvc_type == 'SBIG':
            import sbig_grab_cen
            self.sbig = sbig_grab_cen.SBIG_Grab_Cen()
            self.sbig.take_darks = False # typically we have the test stand in a dark enough enclosure, so False here saves time
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':   
            from DOSlib.proxies import FVC
            import json
            self.platemaker_instrument = 'em'
            self.fvcproxy = FVC(self.platemaker_instrument)
            print('proxy FVC created for instrument %s' % self.fvcproxy.get('instrument'))
            # I think here we would want to set the FVC either in FLI mode or SBIG mode?
        elif self.fvc_type == 'simulator':
            self.sim_err_max = 0.1
            print('FVCHandler is in simulator mode with max errors of size ' + str(self.sim_err_max) + '.')
        if 'SBIG' in self.fvc_type:
            self._exposure_time = 0.2
            self.max_counts = 2**16 - 1
        else:
            self._exposure_time = 1.0
        self.exposure_time = self.__exposure_time
        self.trans = postransforms.PosTransforms() # general transformer object -- does not look up specific positioner info, but fine for QS <--> global X,Y conversions
        self.last_sequence_id = ''
        self.rotation = 0        # [deg] rotation angle from image plane to object plane
        self.scale = 1.0         # scale factor from image plane to object plane
        self.translation = [0,0] # translation of origin within the image plane

    @property
    def exposure_time(self):
        """Time in seconds to expose.
        """
        return self.__exposure_time

    @pos.setter
    def exposure_time(self,value):
        self.__exposure_time = value
        if self.fvc_type == 'SBIG':
            self.sbig.exposure_time = value
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':
            self.fvcproxy.set(exptime=value)
    
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
            xy,brightnesses,t,imgfiles = self.sbig.grab(num_objects)
            brightnesses = [b/self.max_counts for b in brightnesses]
        else:
            zeros_dict = {}
            for i in range(num_objects):
                zeros_dict[i] = {'x':0.0, 'y':0.0, 'mag':0.0, 'meas_err':1.0, 'flags':4}
            err = self.fvcproxy.set_targets(zeros_dict)
            sequence_id = self.next_sequence_id
            imgfiles = ['fvc_' + str(sequence_id) + '.FITS']
            centroids = self.fvcproxy.locate(expid=sequence_id, im=imgfiles[0], send_centroids=True)
            if centroids == 'FAILED':
                print('Failed to locate centroids using FVC.')
            else:
                for params in self.centroids.values():
                    xy.append(params['x'],params['y'])
                    brightnesses.append(self.mag2brightness(params['mag']))
        return xy,brightnesses,imgfiles

#
#    def measured_xy_from_fvc_centroid(self,center_dict):
#        """reformats the centroid dictionary from the fvc to a list of measured [x,y]
#        centroids for the positioner software
#
#        written by PAF for the FLI""" 
#
#        measured_pos_xy = []
#        measured_ref_xy = []
#        for n in center_dict:
#            if center_dict[n]['flag']==5.0:
#                measured_pos_xy.append([center_dict[n]['x'],center_dict[n]['y']])
#            elif center_dict[n]['flag']==3.0:
#                measured_pos_xy.append([center_dict[n]['x'],center_dict[n]['y']])
#                print(center_dict[n],'This was flagged as a 3')
#            elif center_dict[n]['flag']==8.0:
#                measured_ref_xy.append([center_dict[n]['x'],center_dict[n]['y']])
#            else:
#                print(center_dict[n]['flag'],type(center_dict[n]['flag']),'Doesnt seem to be a fiber or positioner') 
#
#
#        return measured_pos_xy, measured_ref_xy

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
        """
        imgfiles = []        
        if self.fvc_type == 'simulator':
            sim_errors = np.random.uniform(-self.sim_err_max,self.sim_err_max,np.shape(expected_pos_xy))
            measured_pos_xy = (expected_pos_xy + sim_errors).tolist()
            measured_ref_xy = expected_ref_xy
        elif self.fvc_type == 'FLI' or self.fvc_type == 'SBIG_Yale':
            
            # will use new api here to talk to platemaker + fvc
            # the format of the expected positions to send them is:
            #   list of dictionaries
            #   each dict has keys: 'id', 'q', 's', 'flags'
            #   id and flags are integers
            #   q,s are floats
            # and as a result from measure() function I get the same structure, but now q,s are the measured positions
            # I do not get fiducials from measure() function
            #
            # measure() --> centers, one per fiber or one per fiducial
            #                 - use this in this function
            #                 - using klaus's DOSlib.proxies api, it handles working with platemaker already
            #
            # locate() --> centroids, one for every light dot (four from fiducials)
            #                 - use this in fvchandler's measure function
            #                 - using DOS calls direct to fvc.py
            #                 - these come back as just pixel centroids
            #                 - to get an unidentified list when you know nothing but # of dots, send a list of 0s of that length
            
            
            # 1. pass expected_pos_xy (in mm at the focal plate) thru platemaker to get expected_pos_xy (in pixels at the FVC CCD)
            # 2. tell FVC software where we expect the positioner centroids to be so it can identify positioners
            # 3. use DOS commands to ask FVC to take a picture
            # 4. use DOS commands to get the centroids list
            # 5. send centroids (in pixels at FVC) thru platemaker to get measured xy (in mm at focal plate)
            # 6. organize those centroids so you can return them as measured_pos_xy, measured_ref_xy
            
#            target_dict = self.create_target_dict(expected_pos_xy)
#            fvc_uri = 'PYRO:FVC@131.243.51.74:40539'
#            fvc = Pyro4.Proxy(fvc_uri)
#            fvc.set(exptime=self.exptime)
#            fvc.set_target_dict(target_dict) 
#            fvc.print_targets()
            #fvc.calibrate_image()
            
            index = 0 # future implementation: use positioner/fiducial index mapping module
            expected_xy = []
            for xylist in [expected_pos_xy,expected_ref_xy]:
                if xylist == expected_pos_xy:
                    flag = 4 # flag 4 means fiber center
                else:
                    flag = 8 # flag 8 means fiducial center
                for xy in xylist:
                    qs = self.trans.obsXY_to_QS(xy)
                    expected_xy.append({'id':index, 'q':qs[0], 's':qs[1], 'flags':flag})
                    index += 1
            measured_xy = DOSLIBPROXYGOESHERE.measure(expected_xy, self.next_sequence_id)
            for xydict in measured_xy:
                # make these match up in order...
            measured_pos_xy,measured_ref_xy = self.measured_xy_from_fvc_centroid(measured_dict)
            return measured_pos_xy, measured_ref_xy
        else:
            expected_xy = expected_pos_xy + expected_ref_xy
            num_objects = len(expected_xy)
            unsorted_xy,brightnesses,imgfiles = self.measure_fvc_pixels(num_objects)
            unsorted_xy,imgfiles = self.measure(num_objects)
            measured_xy = self.sort_by_closeness(unsorted_xy, expected_xy)
            measured_pos_xy = measured_xy[:len(expected_pos_xy)]
            measured_ref_xy = measured_xy[len(expected_pos_xy):]
            if len(measured_ref_xy) > 0:
                xy_diff = np.array(measured_ref_xy) - np.array(expected_ref_xy)
                xy_shift = np.median(xy_diff,axis=0)
                measured_pos_xy -= xy_shift
                measured_pos_xy = measured_pos_xy.tolist()
        return measured_pos_xy, measured_ref_xy, imgfiles

    def sort_by_closeness(self, unknown_xy, expected_xy):
        """Sorts the list unknown_xy so that each point is at the same index
        as its closest-distance match in the list expected_xy.
        """
        if len(unknown_xy) != len(expected_xy):
            print('warning: unknown_xy length = ' + str(len(unknown_xy)) + ' but expected_xy length = ' + str(len(expected_xy)))
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
        """Calls for an FVC image capture, applies transformations to get the
        centroids into the units and orientation of the object plane,  and returns
        the centroids.
            num_objects     ... number of dots to look for in the captured image
        """
        imgfiles = []
        if self.fvc_type == 'SBIG':
            # already_moved
        elif self.fvc_type == 'FLI':
            
        else:
            xy = []
        xy_np = np.array(xy).transpose()
        rot = FVCHandler.rotmat2D_deg(self.rotation)
        xy_np = np.dot(rot, xy_np)
        xy_np *= self.scale
        translation_x = self.translation[0] * np.ones(np.shape(xy_np)[1])
        translation_y = self.translation[1] * np.ones(np.shape(xy_np)[1])
        xy_np += [translation_x,translation_y]
        xy = xy_np.transpose().tolist()
        return xy,imgfiles

    def mag2brightness(self,value):
        """Convert magnitude values coming from Rabinowitz code to a normalized
        brightness value in the range 0.0 to 1.0. Would prefer if Rabinowitz can
        modify his code later on to just give us the counts from the camera.
        """
        newval = 10**(value/-2.5)
        newval = min(newval,1.0)
        newval = max(newval,0.0)
        return newval

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
    print('start taking ' + str(n_repeats) + ' images')
    start_time = time.time()
    for i in range(n_repeats):
        xy.append(f.measure(n_objects))
        print(xy[i])
    total_time = time.time() - start_time
    print('total time = ' + str(total_time) + ' (' + str(total_time/n_repeats) + ' per image)')
