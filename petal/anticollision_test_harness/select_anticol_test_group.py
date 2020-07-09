'''This tool selects a small set of positioners for use in anticollision
testing on hardware. At the time of this writing (2020-07-09) it is
considered something of a one-time use tool. For quickness of writing it,
I allowed a somewhat annoying dependency --- it has to be run on a system
with the DOS operational, and ICS properly configured. And you must join
a running intance of the desired petal. And you must type in the petal
role number you want to query below. And you must enter any other selection
parameters hardcoded below, as well. You get the picture --- I didn't try
to make it a joy to work with. -Joe
'''

from DOSlib.proxies import Petal
ptl = Petal(3)

allowed_buses = {'can10', 'can11'}
print('allowed_buses:', allowed_buses)

disallowed_calib = {'LENGTH_R1': 3.0, 'LENGTH_R2': 3.0}
print('disallowed_calib:', disallowed_calib)

min_enabled_neighbors = 4
print('min_enabled_neighbors:', min_enabled_neighbors)

posids = ptl.app_get('posids')
enabled = ptl.all_enabled_posids()
disabled = ptl.all_disabled_posids()
neighbors = ptl.app_get('collider.pos_neighbors')
fixed_neighbors = ptl.app_get('collider.fixed_neighbor_cases')

selection = set()
removal = set()
for posid in posids:
    busid = ptl.get_posfid_val(posid, 'BUS_ID')
    if busid in allowed_buses:
        selection.add(posid)
    if posid not in enabled:
        removal.add(posid)
    enabled_neighbors = {n for n in neighbors[posid] if n in enabled}
    if len(enabled_neighbors) < min_enabled_neighbors:
        removal.add(posid)
    for key, value in disallowed_calib.items():
        if ptl.get_posfid_val(posid, key) == value:
            removal.add(posid)
selection -= removal
print('Ok for use:', selection, 'count:', len(selection))

import numpy as np
x = {}
y = {}
r = {}
for posid in selection:
    x[posid] = ptl.get_posfid_val(posid, 'OFFSET_X')
    y[posid] = ptl.get_posfid_val(posid, 'OFFSET_Y')
    r[posid] = np.hypot(x[posid], y[posid])
avg_r = np.mean(list(r.values()))
closeness = {posid: abs(r[posid] - avg_r) for posid in selection}
sorted_closeness = sorted(closeness.items(), key=lambda x: x[-1])
sorted_selection = [item[0] for item in sorted_closeness]

def print_pos_info(posid):
    r1 = ptl.get_posfid_val(posid, 'LENGTH_R1')
    r2 = ptl.get_posfid_val(posid, 'LENGTH_R2')
    s = f'{posid}: enabled={posid in enabled}, r1={r1}, r2={r2}'
    s += f', n_neighbors={len(neighbors[posid])}, n_fixed_neighbors={len(fixed_neighbors[posid])}'
    print(s)

found = False
for ctr_posid in sorted_selection:
    bad_neighbors = {p for p in neighbors[ctr_posid] if p not in selection}
    group = {ctr_posid}
    group |= neighbors[ctr_posid]
    bad_neighbors_of_neighbors = set()
    for n in neighbors[ctr_posid]:
        these_bad = {p for p in neighbors[n] if p not in selection}
        bad_neighbors_of_neighbors |= these_bad
    if not any(bad_neighbors) and len(group) >= 7 and not any(bad_neighbors_of_neighbors):
        found = True
        break

if not found:
    print('no group found matching the constraints!')
else:
    print('')
    print('center posid:', ctr_posid, 'at r:', r[ctr_posid], 'device_loc:', ptl.get_posfid_val(ctr_posid, 'DEVICE_LOC'))
    print('')
    print('group to test:', group, 'count:', len(group))
    for posid in group:
        print_pos_info(posid)
    print('')
    neighbors_of_group = set()
    for posid in group:
        neighbors_of_group |= neighbors[posid]
    neighbors_of_group -= group
    print('neighbors of group', neighbors_of_group, 'count:', len(neighbors_of_group))
    for posid in neighbors_of_group:
        print_pos_info(posid)
