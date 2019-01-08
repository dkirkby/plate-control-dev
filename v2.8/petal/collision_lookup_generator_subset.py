def make_code_pp(dr, obsT1, posP1, obsT2, posP2):

    if obsT1 < 0: obsT1 = 360 + obsT1
    if obsT2 < 0: obsT2 = 360 + obsT2
    
    rrr = str(int(dr)).zfill(3)     # ~1 us
    ttt1 = str(int(obsT1)).zfill(3) # ...
    ppp = str(int(posP1)).zfill(3)
    ttt2 = str(int(obsT2)).zfill(3) # ...
    nnn = str(int(posP2)).zfill(3)
    
    # join() is faster than using '+' 
    code = '-'.join([rrr, ttt1, ppp, ttt2, nnn])
    return code

def make_code_pf(loc_id, dx, dy, obsT, posP):
   
    hhh = str(int(loc_id)).zfill(3)
    xxx = str(dx).zfill(3)
    yyy = str(dy).zfill(3)
    ttt = str(obsT).zfill(3)
    ppp = str(posP).zfill(3)
    
    code = hhh + '-' + xxx + '-' + yyy + '-' + ttt + '-' + ppp
    return code


def nearest(x, spacing, min_allowed, max_allowed):
    lower = (x // spacing) * spacing
    if x - lower > spacing / 2:
        val = lower + spacing
    else:
        val = lower
    val = max(val,min_allowed)
    val = min(val,max_allowed)
    return val
