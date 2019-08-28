'''
Runs an Arc Calibration using fvc and petal proxies. Requires running DOS instance. See pecs.py
'''
import os
from pecs import PECS
import posconstants as pc
import pandas

class Arc(PECS):
    
    def __init__(self,petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self,ptlids=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]

    def arc_calibration(self,selection=None,enabled_only=True,n_points_P=6, n_points_T=6,auto_update=True, match_radius=80):
        if selection is None:
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        requests_list_T, requests_list_P = self.ptls[self.ptlid].get_arc_requests(ids=posid_list)
        T_data = []
        old_radius = self.fvc.get('match_radius')
        self.fvc.set(match_radius=match_radius) #Change radius usually to larger values to accound for poor calibration at this point
        i = 1
        for request in requests_list_T:
            print('Measuring theta arc point '+str(i)+' of '+str(len(requests_list_T)))
            i += 1 
            merged_data = self.move_measure(request)
            T_data.append(merged_data)
        P_data = []
        i = 1
        for request in requests_list_P:
            print('Measuring phi arc point '+str(i)+' of '+str(len(requests_list_P)))
            i += 1
            merged_data = self.move_measure(request)
            P_data.append(merged_data)
        self.fvc.set(match_radius=old_radius)
        data = self.ptls[self.ptlid].calibrate_from_arc_data(T_data,P_data,auto_update=auto_update)
        data['auto_update'] = auto_update
        data['enabled_only'] = enabled_only
        return data

    def move_measure(self, request):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Prints missing positioners, returns data merged with request
        '''
        self.ptls[self.ptlid].prepare_move(request, anticollision=None)
        expected_positions = self.ptls[self.ptlid].execute_move()
        measured_positions = self.fvc.measure(expected_positions)
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

    def run_interactively(self,selection=None,enabled_only=None,n_points_P=None, n_points_T=None,auto_update=None, match_radius=None):
        print('Running interactive arc calibration.')
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
            n_points_P = self._get_integer('Enter the number of points to measure on the phi arc: ')
        # Ask for n_points_T
        if n_points_T is None:
            n_points_T = self._get_integer('Enter the number of points to measure on the theta arc: ')
        # Ask for auto_update
        if auto_update is None:
            user_text = input('Automatically update positioner calibration? (y/n) ')
            enabled_only = self._parse_yn(user_text)
        # Ask for match_radius
        if match_radius is None:
            match_radius = self._get_integer('Enter the match_radius for spotmatch: ')
        # Run calibration
        data = self.arc_calibration(selection=selection,enabled_only=enabled_only,n_points_P=n_points_P,n_points_T=n_points_T,auto_update=auto_update,match_radius=match_radius)
        data.to_csv(os.path.join(
                pc.dirs['all_logs'], 'calib_logs',
                f'{pc.filename_timestamp_str_now()}-arc_calibration.csv'))
        print(data[['DEVICE_ID','LENGTH_R1','LENGTH_R2','OFFSET_X','OFFSET_Y','OFFSET_T','OFFSET_P']])


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
    arc = Arc()
    arc.run_interactively(enabled_only=True,n_points_P=6,n_points_T=6,match_radius=80.0)