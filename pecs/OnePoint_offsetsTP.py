from OnePoint_posTP import OnePoint

if __name__ == '__main__':
    op = OnePoint()
    print('Notice: this will update offsetsTP!')
    user_text = input(
        'Please list BUSIDs or POSIDs (not both) seperated by spaces, '
        'leave it blank to use all on petal: ')
    if user_text == '':
        selection = None
    else:
        selection = [item for item in user_text.split()]
    user_text = input('Do you want to move positioners? (y/n) ')
    if 'y' in user_text:
        tp_target = 'default'
    else:
        tp_target = None
    user_text = input('Automatically update calibration? (y/n) ')
    if 'y' in user_text:
        auto_update = True
    else:
        auto_update = False
    user_text = input()
    updates = op.one_point_calib(selection=selection, mode='offsetsTP',
                                 auto_update=auto_update, tp_target=tp_target)
    print(updates)
    updates.to_csv(os.path.join(
        pc.dirs['all_logs'], 'calib_logs',
        f'{pc.filename_timestamp_str_now()}-onepoint_calibration-offsetsTP.csv'))