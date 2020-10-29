'''
1p_calib.py

Contains a function to perform a onepoint calibration on positioners.

If executed standalone, main function will create a PECS instance to
interactively run the onepoint calibration.
'''


def onepoint(pecs, mode='posintTP', move=False, commit=True, tp_tol=0.0, tp_frac=1.0):
    '''
    Function to do a onepoint calibration with given PECS isntance.
    args:
        pecs - instance of PECS
    kwargs:
        mode - string, posTP or offsetTP
        move - bool, whether or not to move positioners to nominal park position.
        commit - bool, whether or not to automatically commit updates.
        tp_tol - float, Minimum error in mm over which to update TP.
        tp_frac - float, Percentatge of error to apply in the TP update.

    returns 
        updates - pandas.DataFrame with columns 'DEVICE_ID','DEVICE_LOC',
                  'PETAL_LOC','ERR_XY','dT','dP' and a pair of TP parameters
    '''
    if pecs.interactive:
        move = pecs._parse_yn(input('Move positioners to default parked position? (y/n): '))
        commit = pecs._parse_yn(input('Commit calibration results (y/n): '))
    pecs.ptlm.set_exposure_info(pecs.exp.id, pecs.iteration)
    pecs.decorate_note(log_note=f'1p_calib_{mode}')
    if move:
        pecs.ptlm.park_positioners(pecs.posids, mode='normal', log_note=f'Moving for 1p_calib_{mode}')
    _, meas, matched, _ = pecs.fvc_measure(test_tp=False, check_unmatched=False)
    calib_pos = meas.loc[sorted(matched & (set(pecs.posids)))]
    updates = pecs.ptlm.test_and_update_TP(calib_pos.reset_index(), mode=mode,
                                           auto_update=commit, tp_updates_tol=tp_tol,
                                           tp_updates_fraction=tp_frac,
                                           log_note=f'1p_calib_{mode}', verbose=True)
    return updates

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-m', '--mode', type=str, default='posTP', help='Which pair or tp angles to adjust, posTP or offsetsTP. ')
    parser.add_argument('-t', '--tp_tol', type=float, default=0.0, help='Minimum error in mm over which to update TP.')
    parser.add_argument('-f', '--tp_frac', type=float, default=1.0, help='Percentatge of error to apply in the TP update. Maximum 1.0.')
    uargs = parser.parse_args()
    assert uargs.mode in ['posTP', 'offsetsTP'], 'mode argument must be either posTP or offsetsTP!'
    assert uargs.tp_frac <= 1.0, 'Updates fraction cannot be greater than 1.0!'
    from pecs import PECS
    print(f'Running one point calibration for {uargs.mode}')
    cs = PECS(interactive=True, test_name=f'1p_calib_{uargs.mode}')
    updates = onepoint(cs, mode=uargs.mode, tp_tol=uargs.tp_tol, tp_frac=uargs.tp_frac)
    if uargs.mode == 'posTP':
        key1, key2 = 'POS_T', 'POS_P'
    else:
        key1, key2 = 'OFFSET_T', 'OFFSET_P'
    updates = updates['DEVICE_ID', 'DEVICE_LOC', 'PETAL_LOC', 'ERR_XY', key1, key2, f'OLD_{key1}', f'OLD_{key2}']
    updates.sort_values('ERR_XY', inplace=True, ascending=False)
    print(updates)
    cs.fvc_collect()
