import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petal
import fvchandler
import posmovemeasure

# initialization
fvc = fvchandler('SBIG')
pos_ids = ['UM00012']
fid_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_ids)
ptl.pos.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)

