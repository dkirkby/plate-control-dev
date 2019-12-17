'''
Set armlengths R1 and R2 to nominal values. Needs running DOS instance. See pecs.py
'''
from pecs import PECS
import posconstants as pc

interactive = True
seed = PECS(fvc=None, ptls=None, pcid=None, posids=None)
if interactive:
    seed.interactive_ptl_setup()
else:
    seed.ptl_setup(pcid=None, posids=None)
print('\nSeeding armlengths...\n')
for posid in seed.posids:
    seed.ptl.set_posfid_val(posid, 'LENGTH_R1',
                            pc.nominals['LENGTH_R1']['value'])
    seed.ptl.set_posfid_val(posid, 'LENGTH_R2',
                            pc.nominals['LENGTH_R2']['value'])
seed.ptl.commit(mode='calib', log_note='seed_armlengths')
print('Please check DB to ensure new values are committed.')
