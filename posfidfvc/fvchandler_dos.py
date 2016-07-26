ipcsimport os
import sys
sys.path.append(os.path.abspath('./SBIG/'))
try:
    import sbig_grab_cen
except Exception:
    pass
import numpy as np
import time
import threading
try:
    # DOS imports
    import Pyro4
    from DOSlib.advertise import Seeker
except Exception:
    pass

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
        self.fvc_type = fvc_type # 'SBIG' or 'FLI'
        self.dos_fvc = {'pyro_uri' : None, 'proxy':None, 'uid':None}
        if self.fvc_type == 'SBIG':
            self.sbig = sbig_grab_cen.SBIG_Grab_Cen()
        elif self.fvc_type == 'FLI':
            # In case an instance is not running, do not count on a name server
            # Fine the FVC through the advertising instead
            self.seeker = Seeker('-dos-', 'DOStest', found_callback=self._dos_seeker_callback)
            self.seeker.seek()
            delay = 4.0
            self.seeker_thread = threading.Thread(target=self._repeat_seeker, 
                                                  kwargs={'delay':delay})
            self.seeker_thread.setDaemon(True)
            self.seeker_thread.start()
            if self.dos_fvc['proxy'] == None:
                print('Looking for FVC app in the background')
            else:
                print('Found FVC')
        elif self.fvc_type == 'simulator':
            self.sim_err_max = 0.1
            print('FVCHandler is in simulator mode with max errors of size ' + str(self.sim_err_max) + '.')
        self.rotation = 0        # [deg] rotation angle from image plane to object plane
        self.scale = 1.0         # scale factor from image plane to object plane
        self.translation = [0,0] # translation of origin within the image plane

        self.fid_dict = {1100: {'x': -71.3107,'y': 145.9311,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1118: {'x': -71.3222,'y': 104.0277,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1102: {'x': -80.5255,'y': 166.9440,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1103: {'x': -80.4125,'y': 83.0324,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1117: {'x': -89.4959,'y': 135.5507,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1106: {'x': -89.4696,'y': 114.5588,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1107: {'x': -107.8175,'y': 166.9728,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1108: {'x': -107.7875,'y': 124.9432,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1116: {'x': -107.8036,'y': 83.0034,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1115: {'x': -125.0158,'y': 180.9813,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1111: {'x': -125.0252,'y': 68.8910,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1112: {'x': -149.9411,'y': 181.0755,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1113: {'x': -160.0506,'y': 69.0207,'mag': 0.000, 'meas_err': 1.000,'flags':8},
                         1114: {'x': -185.0396,'y': 114.9531,'mag': 0.000, 'meas_err': 1.000,'flags':8}}

    # Internal callback and utility functions
    def _repeat_seeker(self, delay = 4.0):
        while True:
            self.seeker.seek()
            time.sleep(delay)
            
    def create_target_dict(self, expected_pos_xy):
        """creates a target dict to send to FLI
        INPUT: expected xy positions of positioners in [[x1,y1],[x2,y2],..]
        """

        target_dict = self.fid_dict
        for i,n in enumerate(expected_pos_xy):
            id = int(3000+i)
            target_dict[id] = {'x':n[0],'y':n[1],'mag':0.000,'meas_err':1.000,'flags':4}

        return target_dict

    def fake_platemaker(self,measured_centroids):
        """ Takes FVC centroids and turns them into XY positions"""

        xy = measured_centroids
        xy_np = np.array(xy).transpose()
        rot = FVCHandler.rotmat2D_deg(self.rotation)
        xy_np = np.dot(rot, xy_np)
        xy_np *= self.scale
        translation_x = self.translation[0] * np.ones(np.shape(xy_np)[1])
        translation_y = self.translation[1] * np.ones(np.shape(xy_np)[1])
        xy_np += [translation_x,translation_y]
        xy = xy_np.transpose().tolist()
        return xy

    def create_new_fid_dict(self,center_dict):
        fid_dict = center_dict
        for n in center_dict:
             if center_dict[n]['flag']==8.0:
                  xy = self.fake_platemaker([[center_dict[n]['x'],center_dict[n]['y']]]
)
                  print(xy)
                  fid_dict[n]['x'] = xy[0][0]
                  self.fid_dict[n]['y'] = xy[0][1]

        return fid_dict

    def measured_xy_from_fvc_centroid(self,center_dict):
        """reformats the centroid dictionary from the fvc to a list of measured [x,y]
        centroids for the positioner software for the FLI
        """

        measured_pos_xy = []
        measured_ref_xy = []
        for n in center_dict:
            if center_dict[n]['flag']==5.0:
                measured_pos_xy.append([center_dict[n]['x'],center_dict[n]['y']])
            elif center_dict[n]['flag']==3.0:
                measured_pos_xy.append([center_dict[n]['x'],center_dict[n]['y']])
                print(center_dict[n],'This was flagged as a 3')
            elif center_dict[n]['flag']==8.0:
                measured_ref_xy.append([center_dict[n]['x'],center_dict[n]['y']])
            else:
                print(center_dict[n]['flag'],type(center_dict[n]['flag']),'Doesnt seem to be a fiber or positioner') 

        measured_pos_xy=self.fake_platemaker(measured_pos_centroid)
        measured_ref_xy=self.fake_platemaker(measured_ref_centroid)
        fid_dict = self.create_new_fid_dict(center_dict)
	#fid_dict=measured_ref_xy

        return measured_pos_xy, measured_ref_xy

    def measure_and_identify(self, expected_pos_xy, expected_ref_xy, send_target_dict = False):
        """Calls for an FVC measurement, and returns a list of measured centroids.
        The centroids are in order according to their closeness to the list of
        expected xy values.

        If the expected xy are unknown, then use the measure method instead.

        INPUT:  expected_pos_xy ... list of expected positioner fiber locations (optional)
                expected_ref_xy ... list of expected fiducial positions (optional)
                send_target_dict    if True create and send target dict to FVC

        OUTPUT: measured_pos_xy ... list of measured positioner fiber locations
                measured_ref_xy ... list of measured fiducial positions

        Lists of xy coordinates are of the form [[x1,y1],[x2,y2],...]
        """
        if self.fvc_type == 'simulator':
            sim_errors = np.random.uniform(-self.sim_err_max,self.sim_err_max,np.shape(expected_pos_xy))
            measured_pos_xy = (expected_pos_xy + sim_errors).tolist()
            measured_ref_xy = expected_ref_xy
        elif self.fvc_type == 'FLI':
            # 1. pass expected_pos_xy (in mm at the focal plate) thru platemaker to get expected_pos_xy (in pixels at the FVC CCD)
            # 2. tell FVC software where we expect the positioner centroids to be so it can identify positioners
            # 3. use DOS commands to ask FVC to take a picture
            # 4. use DOS commands to get the centroids list
            # 5. send centroids (in pixels at FVC) thru platemaker to get measured xy (in mm at focal plate)
            # 6. organize those centroids so you can return them as measured_pos_xy, measured_ref_xy
            self.exptime = 1 #sec
            try:
                fvc = self.dos_fvc['proxy']
                fvc.set(exptime=self.exptime)
            except Exception as e:
                print('messure_and_identify: Exception communicating with the FVC: %s' % str(e))
                self.dos_fvc['uid'] = None
                self.seeker.seek()
                try:
                    fvc = self.dos_fvc['proxy']
                    fvc.set(exptime=self.exptime)
                except Exception as e:
                    rstring = 'measure_and_identify: Exception attempting to reset FVC connection: %s' % str(e)
                    print(rstring)
                    self.dos_fvc['uid'] = None
                    return 'FAILED: ' + rstring
            if send_targer_dict == True:
                t = self.create_target_dict(expected_pos_xy)
                fvc.set_target_dict(t)
                
            try:
                fvc.measure() 
                measured_dict = fvc.get("centers")
                print(measured_dict)
            except Exception as e:
                rstring = 'measure_and_identify: Exception calling fvc.measure or fvc.get(centers): %s' % str(e)
                print(rstring)
                return 'FAILED: ' + rstring 
            measured_pos_xy,measured_ref_xy = self.measured_xy_from_fvc_centroid(measured_dict)	
            return measured_pos_xy, measured_ref_xy
        else:
            expected_xy = expected_pos_xy + expected_ref_xy
            num_objects = len(expected_xy)
            unsorted_xy = self.measure(num_objects)
            measured_xy = self.sort_by_closeness(unsorted_xy, expected_xy)
            measured_pos_xy = measured_xy[:len(expected_pos_xy)]
            measured_ref_xy = measured_xy[len(expected_pos_xy):]
            if len(measured_ref_xy) > 0:
                xy_diff = np.array(measured_ref_xy) - np.array(expected_ref_xy)
                xy_shift = np.median(xy_diff,axis=0)
                measured_pos_xy -= xy_shift
                measured_pos_xy = measured_pos_xy.tolist()
        return measured_pos_xy, measured_ref_xy

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
        if self.fvc_type == 'SBIG':
            xy,brightness,t = self.sbig.grab(num_objects)
        elif self.fvc_type == 'FLI':
            ret = self.dos_fvc['proxy'].measure()
            assert ret != 'FAILED'
            xy_dict = self.dos_fvc['proxy'].get_centers()
            xy = []
            for params in xy_dict.values():
                xy.append([params['x'], params['y']])
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
        return xy

    def _dos_seeker_callback(self, dev):
        """Check found connection from seeker
        """
        for key, value in dev.items():
            if key == 'FVC':
                if self.dos_fvc['uid'] == value['uid']:
                    return # Already have a connection
                proxy = Pyro4.Proxy(value['pyro_uri'])
                self.dos_fvc['proxy'] = proxy
                self.dos_fvc['pyro_uri'] = value['pyro_uri']
                self.dos_fvc['uid'] = value['uid']

    @staticmethod
    def rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        radians = np.deg2rad(angle)
        return np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])

if __name__ == '__main__':
    f = FVCHandler(fvc_type='SBIG')
    n_objects = 4
    n_repeats = 1
    xy = []
    print('start taking ' + str(n_repeats) + ' images')
    start_time = time.time()
    for i in range(n_repeats):
        xy.append(f.measure(n_objects))
        print(xy[i])
    total_time = time.time() - start_time
    print('total time = ' + str(total_time) + ' (' + str(total_time/n_repeats) + ' per image)')
