'''
Set armlengths R1 and R2 to nominal values. Needs running DOS instance
'''
from pecs import PECS
import posconstants as pc

seed = PECS(fvc=None, ptlm=None, interactive=False)
print(f'Seeding armlengths for PCIDs: {seed.pcids}')
for posid in seed.posids:
    role = seed.get_owning_ptl_role(posid)
    seed.ptlm.set_posfid_val(posid, 'LENGTH_R1',
                             pc.nominals['LENGTH_R1']['value'],
                             participating_petals=role)
    seed.ptlm.set_posfid_val(posid, 'LENGTH_R2',
                             pc.nominals['LENGTH_R2']['value'],
                             participating_petals=role)
seed.ptlm.commit(mode='calib', log_note='seed_armlengths')
print('Please check DB to ensure new values are committed.')
