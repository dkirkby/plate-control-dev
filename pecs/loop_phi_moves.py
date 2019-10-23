from OnePoint import OnePointCalib
from pecs import PECS

ctrl = PECS()
ctrl.interactive_ptl_setup()
fvc = ctrl.fvc
ptls = ctrl.ptls
posids = ctrl.posids
petal_id = ctrl.ptlid

go = True
iterations = 0
while go:
    if iterations%2 == 0:
        tp_target = (0, 125)
    else:
        tp_target = (0, 175)
    user_text = input(f'Please enter "go" to move (num iterations {iterations}): ')
    if 'g' in user_text.lower():
        go = True
        OnePointCalib(fvc=fvc,ptls=ptls,petal_id=petal_id,posids=posids,interactive=False,auto_update=False)
    else:
        go=False
    iterations += 1
