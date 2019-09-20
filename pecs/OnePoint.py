import os
import pandas as pd
import posconstants as pc


class OnePoint(object):

    def __init__(self, pecs=None, petal_id=None, platemaker_instrument=None,
                 fvc_role=None, printfunc=print, verbose=False):
        if pecs is None:
            from pecs import PECS
            self.pecs = PECS(self, ptlids=petal_id,
                             platemaker_instrument=platemaker_instrument,
                             fvc_role=fvc_role, printfunc=printfunc)
        else:
            self.pecs = pecs
        self.verbose = verbose
        self.poslocP = 135
        if self.verbose:
            self.printfunc(f'Selecting default petal: PTL {petal_id}')
        self.select_petal(petal_id=petal_id)

    def one_point_calib(self, selection=None, enabled_only=True,
                        mode='posintTP', tp_target='default',
                        auto_update=True, match_radius=80.0):

        # Interpret tp_target and move if target != None
        offsetPs = {}
        if tp_target == 'default':  # use (0, self.obsP to posP) as target
            rows = []
            for posid in posids:
                offsetP = ptl.get_posfid_val(posid, 'OFFSET_P')
                offsetPs[posid] = offsetP
                tp_target = [0.0,self.obsP]
                row = {'DEVICE_ID': posid,
                       'COMMAND': 'posintTP',
                       'X1': 0.0,
                       'X2': self.poslocP - offsetP, #conversion obsP to posP as in posmovemeasure
                       'LOG_NOTE': f'One point calibration {mode}'}
                rows.append(row)
            ptl.prepare_move(pd.DataFrame(rows), anticollision=None)
            expected_pos = ptl.execute_move()
        elif isinstance(tp_target, list):
            row = []
            for posid in posids:
                offsetP = ptl.get_posfid_val(posid, 'OFFSET_P')
                offsetPs[posid] = offsetP
                row = {'DEVICE_ID': posid,
                       'COMMAND': 'posTP',
                       'X1': tp_target[0],
                       'X2': tp_target[1] - offsetP, #conversion poslocP to posingP as in posmovemeasure
                       'LOG_NOTE': f'One point calibration {mode}'}
                rows.append(row)
            ptl.prepare_move(pd.DataFrame(rows), anticollision=None)
            expected_pos = ptl.execute_move()
        else:  # don't move, just use current position
            expected_pos = ptl.get_positions()
        # Prepare FVC and measure targets
        old_radius = self.fvc.get('match_radius')  # hold old radius
        self.fvc.set(match_radius=match_radius)  # set larger radius for calib
        measured_pos = (pd.DataFrame(self.fvc.measure(expected_pos,matched_only=True))
                        .rename(columns={'id': 'DEVICE_ID'}))
        measured_pos.columns = measured_pos.columns.str.upper()
        self.fvc.set(match_radius=old_radius)  # restore old radius
        used_pos = measured_pos[measured_pos['DEVICE_ID'].isin(posids)] #filter only selected positioners
        # Do analysis with test_and_update_TP
        updates = ptl.test_and_update_TP(
            used_pos, tp_updates_tol=0.0, tp_updates_fraction=1.0,
            tp_updates=mode, auto_update=auto_update)
        # Clean up and record additional entries in updates
        updates['auto_update'] = auto_update
        target_t, target_p = [], []
        for posid in posids:
            if posid in matched_used_pos['DEVICE_ID'].values:
                try: #ask for forgiveness later
                    target_t.append(tp_target[0])
                    target_p.append(tp_target[1] - offsetPs[posid])
                except:
                    target_t = tp_target #Positioners weren't moved so
                    target_p = tp_target #tp_target is not 'default' or a list
                    break
            else:  # was not measured by FVC and ommited in the return
                pass  # skip this posid because length is shorted by Nunmatched
        updates['target_t'] = target_t
        updates['target_p'] = target_p
        updates['enabled_only'] = enabled_only
        unmatched = set(posids) - set(updates['DEVICE_ID'])
        print(f'Missing {len(unmatched)} of the selected positioners:\n{unmatched}')
        unmatched_used_pos.drop(['Q','S'],axis=1) #Drop QS so we don't get columns QS in updates with NaNs
        updates.append(unmatched_used_pos,ignore_index=True) #List unmeasured positioners in updates, even with no data
        return updates

    def run_interactively(self, petal=None, mode=None, tp_target=None,
                          selection=None, enabled_only=None,
                          auto_update=None, match_radius=None):


        # Ask for enabled_only

        # Ask for mode
        if mode is None:
            mode = input('Please enter the calibration mode you wish to use (posTP, offsetsTP): ')
            if mode not in ['posTP','offsetsTP','both']:
                mode = input('Invalid entry, please try again (posTP, offsetsTP): ')
       # Ask for auto_update
        if auto_update is None:
            user_text = input('Automatically update positioner calibration? (y/n) ')
            enabled_only = self._parse_yn(user_text)
        # Ask for tp_target
        if tp_target is None:
            user_text = self._parse_yn('Do you want to move positioners? (y/n) ')
            if user_text:
                tp_target = 'default'
            else:
                tp_target = None #this was already true but is more readable
        # Ask for match_radius
        if match_radius is None:
            match_radius = self._get_integer('Enter the match_radius for spotmatch: ')
        updates = op.one_point_calib(selection=selection, mode='posTP',
                                     auto_update=auto_update, tp_target=tp_target)
        updates.to_csv(os.path.join(
            pc.dirs['all_logs'], 'calib_logs',
            f'{pc.filename_timestamp_str_now()}-onepoint_calibration-{mode}.csv'))
        #TODO: call analysis function here
        print(updates[['DEVICE_ID','POS_T','POS_P','dT','dP']])
        return updates

    #TODO: add some sort of analysis function, takes in updates and decides if
    # the calib needs to be looked at for each positioner
    # Maybe return a list to repeat so that can be used in interactive terminal?

        self.select_petal(petal_id = int(ptlid))