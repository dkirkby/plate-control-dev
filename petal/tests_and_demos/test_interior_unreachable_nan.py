'''2017-02-23, Silber
We have been getting nan returned when trying to conver posXY to posTP, in cases
where the radius of the argued XY point is less than the minimum targetable radius
of the patrol envelope.
'''

import postransforms
trans = postransforms.PosTransforms()
r = [3.0,3.1]
x = [0, 0.05, 0.1, 0.15, 0.2, 6.0, 6.1, 6.2]
y = [0 for i in x]
xy = [x,y]
ranges = [[-185,185],[-5,185]]
tp,unreachable = trans.xy2tp(xy, r, ranges)
t = tp[0]
p = tp[1]

import posmodel
p = posmodel.PosModel()

print('')
print('CASE M00142, after fixing the arccos numeric precision error in xy2tp')
p.state.store('LENGTH_R1',3.0444912734348404)
p.state.store('LENGTH_R2',3.0592099185275723)
p.state.store('OFFSET_T',33.6990237206073)
p.state.store('OFFSET_P',-4.40183469230584)
p.state.store('OFFSET_X',85.76099236364983)
p.state.store('OFFSET_Y',35.80931562807018)
p.state.store('PHYSICAL_RANGE_T',396.77360363210005)
p.state.store('PHYSICAL_RANGE_P',190.0)
print('targetable range theta: ' + str(p.targetable_range_T))
print('targetable range phi: ' + str(p.targetable_range_P))
print('|length r1 - length r2| --> ' + str((p.state._val['LENGTH_R1'] - p.state._val['LENGTH_R2'])))
print('p.trans.posXY_to_posTP([0, .01469]) --> ' + str(p.trans.posXY_to_posTP([0, .01469])))
print('p.trans.posXY_to_posTP([0, .01472]) --> ' + str(p.trans.posXY_to_posTP([0, .01472])))


print('')
print('CASE M00528, after fixing the arccos numeric precision error in xy2tp')
p.state.store('LENGTH_R1',2.8717353438946156)
p.state.store('LENGTH_R2',3.0843491074195599)
p.state.store('OFFSET_T',-65.309004215659343)
p.state.store('OFFSET_P',-6.5767604546238516)
p.state.store('OFFSET_X',53.797074126319295)
p.state.store('OFFSET_Y',80.715848473197767)
p.state.store('PHYSICAL_RANGE_T',395.16777127611419)
p.state.store('PHYSICAL_RANGE_P',188.81443605360451)
print('targetable range theta: ' + str(p.targetable_range_T))
print('targetable range phi: ' + str(p.targetable_range_P))
print('|length r1 - length r2| --> ' + str((p.state._val['LENGTH_R1'] - p.state._val['LENGTH_R2'])))
print('p.trans.posXY_to_posTP([0, .2126]) --> ' + str(p.trans.posXY_to_posTP([0, .2126])))
print('p.trans.posXY_to_posTP([0, .2127]) --> ' + str(p.trans.posXY_to_posTP([0, .2127])))