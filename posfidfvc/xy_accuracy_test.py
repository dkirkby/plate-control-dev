import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petal
import fvchandler
import posmovemeasure

# initialization
fvc = fvchandler('SBIG')
fvc.scale = 0.015  # mm/pixel
fvc.rotation = -90 # deg
pos_ids = ['UM00012']
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.pos.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
m.n_fiducial_dots = 1 # number of centroids the FVC should expect

