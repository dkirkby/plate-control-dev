'''
Set armlengths R1 and R2 to nominal values. Needs running DOS instance. See pecs.py
'''
from pecs import PECS
import posconstants as pc

seed = PECS(fvc=None, ptlm=None, interactive=True)
print('Seeding armlengths...')
for posid in self.posids:
    role = self.get_owning_ptl_role(posid)
    self.ptlm.set_posfid_val(posid, 'LENGTH_R1',
                             pc.nominals['LENGTH_R1']['value'],
                             participating_petals=role)
    self.ptlm.set_posfid_val(posid, 'LENGTH_R2',
                             pc.nominals['LENGTH_R2']['value'],
                             participating_petals=role)
self.ptlm.commit(mode='calib', log_note='seed_armlengths')
print('Please check DB to ensure new values are committed.')
