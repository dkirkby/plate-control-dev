'''
Runs a Grid Calibration using fvc and petal proxies. Requires running DOS instance. See pecs.py
'''
import os
import posconstants as pc
import pandas

class Grid(object):
    
    def __init__(self,pecs=None, petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print, verbose=False):
        if pecs is None:
            from pecs import PECS
            self.pecs = PECS(self,ptlids=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        else:
            self.pecs = pecs
        self.verbose = verbose
        if self.verbose:
            print('Selecting default petal, override with a call to select_petal.')
        self.select_petal(petal_id=petal_id)

    def grid_calibration(self,selection=None,n_points_P=5, n_points_T=7,enabled_only=True,auto_update=True,match_radius=80.0):
        if selection is None:
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        requests_list = self.ptls[self.ptlid].get_grid_requests(ids=posid_list,n_points_T=n_points_T,n_points_P=n_points_P)
        meas_data = []
        i = 1
        old_radius = self.fvc.get('match_radius')
        self.fvc.set(match_radius=match_radius)
        for request in requests_list:
            print('Measuring grid point '+str(i)+' of '+str(len(requests_list)))
            i += 1 
            merged = self.move_measure(request)
            meas_data.append(merged)
        self.fvc.set(match_radius=old_radius)
        updates = self.ptls[self.ptlid].calibrate_from_grid_data(meas_data,auto_update=auto_update)
        updates['match_radius'] = match_radius
        updates['auto_update'] = auto_update
        updates['enabled_only'] = enabled_only
        return updates

    def move_measure(self, request):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Prints missing positioners, returns data merged with request
        '''
        self.ptl.prepare_move(request, anticollision=None)
        expected_positions = self.ptl.execute_move()
        measured_positions = self.pecs.fvc.measure(expected_positions)
        measured_positions = pandas.DataFrame(measured_positions)
        measured_positions.rename(columns={'q':'MEASURED_Q','s':'MEASURED_S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
        used_positions = measured_positions[measured_positions['DEVICE_ID'].isin(posid_list)]
        request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'},inplace=True)
        merged = used_positions.merge(request, how='outer',on='DEVICE_ID')
        unmatched_merged = merged.loc[merged['FLAGS'].isnull()]
        #if unmatched_merged.empty:
        #    unmatched_merged = merged[merged['FLAGS'] & 1 == 0] #split into unmatched and matched
        #    matched_merged = merged[merged['FLAGS'] & 1 != 0]
        #else:
        matched_merged = merged.loc[merged['FLAGS'].notnull()]
        unmatched = unmatched_merged['DEVICE_ID'].values
        print(f'Missing {len(unmatched)} of the selected positioners:\n{unmatched}')
        return merged

    def run_interactively(self,petal=None,selection=None,enabled_only=None,n_points_P=None, n_points_T=None,auto_update=None, match_radius=None):
        print('Running interactive grid calibration.')
        # Ask for petal_id
        if petal is None:
            ptlid = self._get_integer('Please select a petal_id, availible petal_IDs: %s ' % list(self.pecs.ptls.keys()))
            self.select_petal(petal_id = ptlid)
        # Ask for selection
        if selection is None:
            user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
            if user_text != '':
                user_text = user_text.split()
                selection = []
                for item in user_text:
                    selection.append(item)
            else:
                selection = None
            print('You chose: %s' % selection)
        # Ask for enabled_only
        if enabled_only is None:
            user_text = input('Use enabled positioners only? (y/n) ')
            enabled_only = self._parse_yn(user_text)
        # Ask for n_points_P
        if n_points_P is None:
            n_points_P = self._get_integer('Enter the number of points to sample on phi (total points = phi*theta): ')
        # Ask for n_points_T
        if n_points_T is None:
            n_points_T = self._get_integer('Enter the number of points to sample on theta (total points = phi*theta): ')
        # Ask for auto_update
        if auto_update is None:
            user_text = input('Automatically update positioner calibration? (y/n) ')
            enabled_only = self._parse_yn(user_text)
        # Ask for match_radius
        if match_radius is None:
            match_radius = self._get_integer('Enter the match_radius for spotmatch: ')
        # Run calibration
        data = self.grid_calibration(selection=selection,enabled_only=enabled_only,n_points_P=n_points_P,n_points_T=n_points_T,auto_update=auto_update,match_radius=match_radius)
        data.to_csv(os.path.join(
                pc.dirs['all_logs'], 'calib_logs',
                f'{pc.filename_timestamp_str_now()}-grid_calibration.csv'))
        #Run analysis function here
        print(data[['DEVICE_ID','LENGTH_R1','LENGTH_R2','OFFSET_X','OFFSET_Y','OFFSET_T','OFFSET_P']])
        return data

    #TODO: add some sort of analysis function, takes in data and decides if
    # the calib needs to be looked at for each positioner
    # Maybe return a list to repeat so that can be used in interactive terminal?

    def select_petal(self, petal_id=None, index=None):
        if petal_id is None:
            if index is None:
                print(f'No petal selected, choosing index=0 as default, petal_id {list(self.pecs.ptls.keys())[0]}')
                self.ptl = self.pecs.ptls[list(self.pecs.ptls.keys())[0]]
            else:
                print(f'Choosing petal in index {index}, petal_id {list(self.pecs.ptls.keys())[index]}')
                self.ptl = self.pecs.ptls[list(self.pecs.ptls.keys())[index]]
        else:
            print('Choosing petal_id %s' % petal_id)
            self.ptl = self.ptl = self.pecs.ptls[petal_id]

    def _parse_yn(yn_str):
        if 'y' in yn_str.lower():
            return True
        else:
            return False

    def _get_integer(prompt_string):
        user_text = input(prompt_string)
        if user_text.isdigit():
            return int(user_text)
        else:
            user_text = input('You did not enter an integer, try again. ' + prompt_string)
            if user_text.isdigit():
                return int(user_text)
            else:
                raise ValueError('Input requires an integer.')

if __name__ == '__main__':
    grid = Grid()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
    if user_text != '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    print('You chose: %s' % selection)
    user_text = input('Automatically update calibration? (y/n) ')
    if 'y' in user_text:
        auto_update = True
    else:
        auto_update = False
    updates = grid.grid_calibration(selection=selection, auto_update=auto_update)
    print(updates)
    updates.to_csv(os.path.join(
            pc.dirs['all_logs'], 'calib_logs',
            f'{pc.filename_timestamp_str_now()}-grid_calibration.csv'))
