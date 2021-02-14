# set up a log file
import logging
import simple_logger
import traceback
import os
import posconstants as pc
from pecs import PECS

update_error_report_thresh = 1.0 #warn user that an update of more than value mm was found


log_dir = pc.dirs['sequence_logs']
log_timestamp = pc.filename_timestamp_str()
log_name = 'FP_setup_' + log_timestamp + '.log'
log_path = os.path.join(log_dir, log_name)
logger, logger_fh, logger_sh = simple_logger.start_logger(log_path)
logger_fh.setLevel(logging.DEBUG)
logger_sh.setLevel(logging.INFO)
simple_logger.input2(f'Alert: you are about to run the focalplane setup script to recover positioners or prepare the focalplane. This takes up to half an hour to execute. Hit enter to continue. ')

cs = PECS(interactive=False, test_name=f'FP_setup', logger=logger, inputfunc=simple_logger.input2)

logger.info(f'FP_SETUP: starting as exposure id {cs.exp.id}')

#from 1p_calib import onepoint # doesn't work
import importlib
onept = importlib.import_module('1p_calib')
onepoint = onept.onepoint
from disambiguate_theta import disambig_class

def get_pos_set(which='enabled'):
    pos_set = set()
    if which == 'enabled':
        pos_dict = cs.ptlm.all_enabled_posids()
    elif which == 'disabled':
        pos_dict = cs.ptlm.all_disabled_posids()
    for poslist in pos_dict.values():
        pos_set |= set(poslist)
    return pos_set

initial_disabled = get_pos_set('disabled')
initial_enabled = get_pos_set('enabled')

e = None #no exception

logger.info('FP_SETUP: enabling positioners...')
cs.ptlm.enable_positioners(ids='all', comment='FP setup script initial enable')

logger.info('FP_SETUP: turning on back illumination...')
cs.turn_on_illuminator()

logger.info('FP_SETUP: turning on fiducials...')
cs.turn_on_fids()

try:
    logger.info('FP_SETUP: running 1p calibration...')
    enabled_before_1p = get_pos_set('enabled')
    updates = onepoint(cs, mode='posintTP', move=False, commit=True, tp_tol=0.065,
                       tp_frac=1.0, num_meas=1, use_disabled=True, check_unmatched=True)
    enabled_after_1p = get_pos_set('enabled')
    updates = updates[['DEVICE_ID', 'DEVICE_LOC', 'PETAL_LOC', 'ERR_XY', 'POS_T', 'POS_P', 'OLD_POS_T', 'OLD_POS_P']]
    updates.sort_values('ERR_XY', inplace=True, ascending=False)
    logger.debug('Updates sorted by descending ERR_XY:')
    logger.debug(updates.to_string())
    #logger.info(updates.to_string(max_rows=100))
    if update_error_report_thresh:
        selection = updates.loc[updates['ERR_XY'] > update_error_report_thresh]
        if not(selection.empty()):
            logger.warn(f'FP_SETUP: found {len(selection)} positioners with updates greater than {update_error_report_thresh}!')
            logger.warn(f'FP_SETUP: update deatils: \n{selection}')
    disabled_during_1p = enabled_before_1p - enabled_after_1p
    logger.info(f'FP_SETUP: {len(disabled_during_1p)} disabled during initial 1p calib. Posids {disabled_during_1p}')

    logger.info('FP_SETUP: running disambiguation loops...')
    enabled_before_disambig = get_pos_set('enabled')
    disambig_obj = disambig_class(pecs=cs, logger=logger, num_meas=1, check_unmatched=True, num_tries=4)
    ambig = disambig_obj.disambig()
    logger.info('FP_SETUP: Disambiguation loops complete.')
    if ambig:
        details = cs.ptlm.quick_table(posids=ambig, coords=['posintTP', 'poslocTP'], as_table=False, sort='POSID')
        if pc.is_string(details):
            details_str = details
        else:
            details_str = ''
            for petal_id, table_str in details.items():
                details_str += f'\n{petal_id}\n{table_str}\n'
        logger.warning(f'{len(ambig)} positioners remain *unresolved* and will be disabled. Details:\n{details_str}')
        cs.ptlm.disable_positioners(ids=ambig, comment='FP setup - disabling positioners that remain in ambiguous theta range.')
    else:
        logger.info('FP_SETUP: All selected ambiguous cases were resolved!')
    enabled_after_disambig = get_pos_set('enabled')
    disabled_during_disambig = enabled_before_disambig - enabled_after_disambig
    logger.info(f'FP_SETUP: {len(disabled_during_disambig)} disabled during disambiguation loops. Posids {disabled_during_disambig}')

    logger.info(f'FP_SETUP: running final 1p calibration...')
    enabled_before_1p2 = get_pos_set('enabled')
    updates = onepoint(cs, mode='posintTP', move=False, commit=True, tp_tol=0.065,
                       tp_frac=1.0, num_meas=3, use_disabled=True, check_unmatched=True)
    enabled_after_1p2 = get_pos_set('enabled')
    updates = updates[['DEVICE_ID', 'DEVICE_LOC', 'PETAL_LOC', 'ERR_XY', 'POS_T', 'POS_P', 'OLD_POS_T', 'OLD_POS_P']]
    updates.sort_values('ERR_XY', inplace=True, ascending=False)
    logger.debug('Updates sorted by descending ERR_XY:')
    logger.debug(updates.to_string())
    #logger.info(updates.to_string(max_rows=100))
    if update_error_report_thresh:
        selection = updates.loc[updates['ERR_XY'] > update_error_report_thresh]
        if not(selection.empty()):
            logger.warn(f'FP_SETUP: found {len(selection)} positioners with updates greater than {update_error_report_thresh}!')
            logger.warn(f'FP_SETUP: update deatils: \n{selection}')
    disabled_during_1p2 = enabled_before_1p2 - enabled_after_1p2
    logger.info(f'FP_SETUP: {len(disabled_during_1p2)} disabled during initial 1p calib. Posids {disabled_during_1p2}')
    final_enabled = get_pos_set('enabled')
except Exception as e:
    logger.error('FP_SETUP crashed! See traceback below:')
    logger.critical(traceback.format_exc())
    logger.info('Attempting to preform cleanup before hard crashing. Configure the instance before trying again.')
    try:
        logger.info('FP_SETUP: Re-disabling initially disabled positioners for safety...')
        cs.ptlm.disable_positioners(ids=initial_disabled, comment='FP_SETUP - crashed in execution, resetting disabled devices')
    except:
        logger.critical('FP_SETUP: failed to return to initial state. DO NOT continue without consulting FP expert.')

logger.info('FP_SETUP: turning off back illumination...')
cs.turn_off_illuminator()

logger.info('FP_SETUP: turning off fiducials...')
cs.turn_off_fids()

if e is None:
    logger.info('FP_SETUP: Successfully completed! Please record any following notes in the log book in addition to any other observations:')
    newly_enabled = final_enabled - initial_enabled
    if newly_enabled:
        logger.info(f'FP_SETUP NOTE: recovered {len(newly_enabled)} positioner robots.')
    if ambig:
        logger.info(f'FP_SETUP NOTE: {len(ambig)} positioners remaing in ambiguous theta range and are not used tonight: posids {ambig}')
    non_ambig_disabled = disabled_during_1p | disabled_during_1p2 | (disabled_during_disambig-ambig)
    if non_ambig_disabled:
        logger.info(f'FP_SETUP_NOTE: {len(non_ambig_disabled)} positioners were disabled during the course of this script for other reasons, likely due to match errors.')
        logger.info(f'FP_SETUP_NOTE: other disabled posids: {non_ambig_disabled}')

cs.fvc_collect()
logger.info(f'Log file: {log_path}')
simple_logger.clear_logger()
