'''2017-02-23, Silber
These are scripts analyzing what happened in several cases where the phi axis seems to
get jammed up unnaturally. Thank you Kevin Fanning for identifying this effect and
gathering the key data to illustrate it.
'''

import posmodel
import numpy as np

p = posmodel.PosModel()

print('')
print('CASE OF M00451')
p.state.store('OFFSET_X',45.46179497)
p.state.store('OFFSET_Y',16.3852483)
p.state.store('POS_T',162.6957839)
p.state.store('POS_P',94.82387726)
p.state.store('LENGTH_R1',3.042088442)
p.state.store('LENGTH_R2',3.218954992)
p.state.store('PHYSICAL_RANGE_T',394.7359236)
p.state.store('PHYSICAL_RANGE_P',190)
p.state.store('OFFSET_T',166.3062861)
p.state.store('OFFSET_P',48.5717133)
xy_meas0 = [46.82573863,17.78436007]
xy_exp0 = [p.expected_current_position['obsX'],p.expected_current_position['obsY']]
xy_err0 = [xy_meas0[i]-xy_exp0[i] for i in range(len(xy_exp0))]
errsum0 = sum(xy_err0[i]**2 for i in range(len(xy_err0)))**0.5
p.state.store('POS_T',163.1739089)
p.state.store('POS_P',92.94576171)
xy_meas1 = [46.8573408,17.81353162]
xy_exp1 = [p.expected_current_position['obsX'],p.expected_current_position['obsY']]
xy_err1 = [xy_meas1[i]-xy_exp1[i] for i in range(len(xy_exp1))]
errsum1 = sum(xy_err1[i]**2 for i in range(len(xy_err1)))**0.5
measured_posTP_full = p.trans.obsXY_to_posTP(xy_meas1)[0]
measured_posTP_targetable = p.trans.obsXY_to_posTP(xy_meas1,range_limits='targetable')[0]
print('expect posT near: ' + str(p.expected_current_position['posT']))
print('measured_posT (using full range transform): ' + str(measured_posTP_full[0]))
print('measured_posT (using targetable range transform): ' + str(measured_posTP_targetable[0]))
print('full range T: ' + str(p.full_range_posintT))
print('targetable range T: ' + str(p.targetable_range_posintT))
print('SUMMARY: This transform when updating posT and posP values was operating in the "full" range (hardstop to hardstop) rather than the "targetable" range (which leaves margin for backlash moves. In this case, when calculating the apparent theta angle based on the camera''s xy measurement, a theta angle 360 degrees away was chosen (mathematically correct, but in the "full" range). Then the posT got reset to this far off angle on the other side of the hardstop. So now the positioner was effectively pinning itself against the hardstop.')


print('')
print('CASE OF M00383')
p.state.store('OFFSET_X',37.68168412)
p.state.store('OFFSET_Y',32.25478013)
p.state.store('POS_T',163.3687445)
p.state.store('POS_P',116.9721255)
p.state.store('LENGTH_R1',3.032830929)
p.state.store('LENGTH_R2',3.129230529)
p.state.store('PHYSICAL_RANGE_T',396.6787087)
p.state.store('PHYSICAL_RANGE_P',186.5237842)
p.state.store('OFFSET_T',20.35307464)
p.state.store('OFFSET_P',-0.443724171)
xy_meas = [36.17100015,29.39093237]
xy_exp = [p.expected_current_position['obsX'],p.expected_current_position['obsY']]
xy_err = [xy_meas[i]-xy_exp[i] for i in range(len(xy_exp))]
errsum = sum(xy_err[i]**2 for i in range(len(xy_err)))**0.5
measured_posTP_full = p.trans.obsXY_to_posTP(xy_meas)[0]
measured_posTP_targetable = p.trans.obsXY_to_posTP(xy_meas,range_limits='targetable')[0]
print('expect posT near: ' + str(p.expected_current_position['posT']))
print('measured_posT (using full range transform): ' + str(measured_posTP_full[0]))
print('measured_posT (using targetable range transform): ' + str(measured_posTP_targetable[0]))
print('full range T: ' + str(p.full_range_posintT))
print('targetable range T: ' + str(p.targetable_range_posintT))
print('SUMMARY: Same thing happened as before, with positioner pinning itself against hardstop due to thinking it could be in the full range.')


print('')
print('CASE OF M00286')
p.state.store('OFFSET_X',75.81364258)
p.state.store('OFFSET_Y',16.72705972)
p.state.store('POS_T',-178.2212597)
p.state.store('POS_P',90.64736057)
p.state.store('LENGTH_R1',3.016980392)
p.state.store('LENGTH_R2',3.066085918)
p.state.store('PHYSICAL_RANGE_T',395.5186039)
p.state.store('PHYSICAL_RANGE_P',184.5664236)
p.state.store('OFFSET_T',-107.8929736)
p.state.store('OFFSET_P',1.242193496)
xy_meas = [73.59751206,20.32934743]
xy_exp = [p.expected_current_position['obsX'],p.expected_current_position['obsY']]
xy_err = [xy_meas[i]-xy_exp[i] for i in range(len(xy_exp))]
errsum = sum(xy_err[i]**2 for i in range(len(xy_err)))**0.5
measured_posTP_full = p.trans.obsXY_to_posTP(xy_meas)[0]
measured_posTP_targetable = p.trans.obsXY_to_posTP(xy_meas,range_limits='targetable')[0]
print('expect posT near: ' + str(p.expected_current_position['posT']))
print('measured_posT (using full range transform): ' + str(measured_posTP_full[0]))
print('measured_posT (using targetable range transform): ' + str(measured_posTP_targetable[0]))
print('full range T: ' + str(p.full_range_posintT))
print('targetable range T: ' + str(p.targetable_range_posintT))
print('SUMMARY: This is not just due to full vs targetable range. Here we again have the 360 deg away mis-identification, but it happened regardless of the range provided to the transform function. Here we need an additional fix: check and use whichever is closest to expected theta: meas_posT +0, or +360, or -360.')
T_meas = measured_posTP_targetable[0]
T_options = np.array([T_meas,T_meas+360,T_meas-360])
T_expected = p.expected_current_position['posT']
T_diff = np.abs(T_options - T_expected)
T_best = T_options[np.argmin(T_diff)]
print('This would result in measured posT = ' + str(T_best))


print('')
print('CASE OF M00334')
p.state.store('OFFSET_X',75.49844874)
p.state.store('OFFSET_Y',48.74102166)
p.state.store('POS_T',-166.4920161)
p.state.store('POS_P',87.73812282)
p.state.store('LENGTH_R1',3.023220709)
p.state.store('LENGTH_R2',3.159322408)
p.state.store('PHYSICAL_RANGE_T',392.0768472)
p.state.store('PHYSICAL_RANGE_P',184.6443874)
p.state.store('OFFSET_T',-94.62441191)
p.state.store('OFFSET_P',-5.044591386)
xy_meas = [71.88434905,51.51496898]
xy_exp = [p.expected_current_position['obsX'],p.expected_current_position['obsY']]
xy_err = [xy_meas[i]-xy_exp[i] for i in range(len(xy_exp))]
errsum = sum(xy_err[i]**2 for i in range(len(xy_err)))**0.5
measured_posTP_full = p.trans.obsXY_to_posTP(xy_meas)[0]
measured_posTP_targetable = p.trans.obsXY_to_posTP(xy_meas,range_limits='targetable')[0]
print('expect posT near: ' + str(p.expected_current_position['posT']))
print('measured_posT (using full range transform): ' + str(measured_posTP_full[0]))
print('measured_posT (using targetable range transform): ' + str(measured_posTP_targetable[0]))
print('full range T: ' + str(p.full_range_posintT))
print('targetable range T: ' + str(p.targetable_range_posintT))
print('SUMMARY: Similar case as the first two, where restricting to targetable range was sufficient.')
T_meas = measured_posTP_targetable[0]
T_options = np.array([T_meas,T_meas+360,T_meas-360])
T_expected = p.expected_current_position['posT']
T_diff = np.abs(T_options - T_expected)
T_best = T_options[np.argmin(T_diff)]
print('Anyway, doing also the min difference from expected theta is no problem here: ' + str(T_best))

print('')
print('CONCLUSION:\nThe problem is when we convert xy measurement to tp (to reset the theta and phi internally-tracked shaft angles) then sometimes we get an angle wrap error of magnitude 360 deg. The solution is to check the three possible thetas (+360, -360, or +0) for which one is closest to where we currently expect the theta axis is.')