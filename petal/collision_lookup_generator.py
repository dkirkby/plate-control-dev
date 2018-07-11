"""This module generates a set of hashable codes for collision lookup.

POS-POS CASE
To check for collision between any two positioners:
    1. Form the code based on:
        ... center-to-center distance between positioners
        ... relative theta angle between positioners
        ... phi w.r.t. theta for each positioner    
    2. See if the code is in the collisions lookup set.

    CODE FORMAT: 'PP-rrr-ttt-ppp-nnn', all digits are integers.
        PP  ... this prefix indicates positioner-positioner code
        rrr ... [um]  rrr = ctr_to_ctr_dist - 10.1 mm
        ttt ... [deg] ttt = obsT1 - obsT2 (wrapped into range 000 to 360)
        ppp ... [deg] ppp = posP1
        nnn ... [deg] nnn = posP2 (neighbor)
        [WHAT ABOUT VARIATION OF R1 ON EACH POSITIONER?]
    
POS-FIXED CASE
To check for collision between a positioner and fixed:
    1. Form the code based on:
        ... device_location_id (i.e., hole number in petal)
        ... dx,dy center variation from nominal
        ... obsT, obsP
    2. See if the code is in the collisions lookup set.
    
    CODE FORMAT: 'PF-hhh-xxx-yyy-ttt-ppp', all digits are integers.
        PF  ... this prefix indicates positioner-fixed code
        hhh ... integer device location (hole) id number
        xxx ... [um]  xxx = actual_flatX - nominal_flatX + 0.5 mm
        yyy ... [um]  yyy = actual_flatY - nominal_flatY + 0.5 mm
        ttt ... [deg] ttt = obsT
        ppp ... [deg] ppp = posP
        [WHAT ABOUT VARIATION OF R1?]
"""

# PSEUDO-CODE
# Divest much of polygon-handling code from poscollider.py into this module.
# Initialize, bringing in the usual poscollider stuff like polygon definitions etc.
#
# POS-POS calculations:
# for r in the range [0, 50, 100 ... 950] um
#   for t in the range [0, 1, 2 ... 360] deg
#       for p in the range [60, 61, 62 ... 210] deg
#           for n in the range [60, 61, 62 ... 210] deg
#               if spatial collision
#                   form code
#                   add to set
#
# Start much **much** coarser than this and see how long it takes to generate / how big is the set.
# Issue: I really want 0.5 deg ~ 53 um resolution @ fully-extended phi. But that may be unreasonable.
# 
# POS-FIXED calculations:
# Import petal layout data (device_location_id vs. obsX,obsY).
# Generate a set of simulation positioners filling all locations.
# for h in the range of device location ids
#   for x in the range [0, 50, 100 ... 950] um
#       for y in the range [0, 50, 100 ... 950] um
#           etc...


# Fastest method I found so far for finding nearest quantized value:
# (Typically <= 1 us on my laptop.)
def nearest(x, spacing, min_allowed, max_allowed):
    lower = (x // spacing) * spacing
    if x - lower > spacing / 2:
        val = lower + spacing
    else:
        val = lower
    val = max(val,min_allowed)
    val = min(val,max_allowed)
    return val