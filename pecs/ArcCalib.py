'''
Runs an Arc Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
Currently only runs one Petal at a time, awaiting a petalMan proxy.
'''
import os
import posconstants as pc
from pecs import PECS


class ArcCalib(PECS):
    '''
    subclass of PECS that adds functions to run an Arc calibration.
    In the future: add methods to display, judge and analyze calibration.
    '''
    def __init__(self, fvc=None, ptls=None,
                 petal_id=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptls=ptls)
        self.printfunc(f'Running arc calibration')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_id, posids)
        self.n_points_P = 6
        self.n_points_T = 6
        updates = self.calibrate(interactive=interactive)
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-arc_calibration')
        self.printfunc(
            updates[['DEVICE_ID', 'LENGTH_R1', 'LENGTH_R2',
                     'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P']])
        updates.to_csv(path+'.csv')
        updates.to_pickle(path+'.pkl')
        self.printfunc(f'Arc calibration data saved to: {path}')
        if interactive:
            if self._parse_yn(input(
                    'Open arc calibration data table? (y/n): ')):
                os.system(f"xdg-open {path+'.csv'}")

    def calibrate(self, auto_update=True, match_radius=80,
                  interactive=False):
        if interactive:
            # Ask for auto_update
            auto_update = self._parse_yn(input(
                        'Automatically update calibration? (y/n): '))
            # Ask for match_radius
            match_radius = float(input(
                    'Please provide a spotmatch radius: '))
            return self.calibrate(auto_update=auto_update,
                                  match_radius=match_radius)

        req_list_T, req_list_P = self.ptl.get_arc_requests(
            ids=self.posids,
            n_points_T=self.n_points_T, n_points_P=self.n_points_P)
        T_data = []
        for i, req in enumerate(req_list_T):
            self.printfunc(f'Measuring theta arc point {i+1} of '
                           f'{len(req_list_T)}')
            T_data.append(self.move_measure(req, match_radius=match_radius))
            if self.allow_pause and i+1 < len(req_list_T):
                input('Paused for heat load monitoring, '
                      'press enter to continue: ')
        P_data = []
        for i, req in enumerate(req_list_P):
            self.printfunc(f'Measuring phi arc point {i+1} of '
                           f'{len(req_list_P)}')
            P_data.append(self.move_measure(req, match_radius=match_radius))
            if self.allow_pause and i+1 < len(req_list_T):
                input('Paused for heat load monitoring, '
                      'press enter to continue: ')
        updates = self.ptl.calibrate_from_arc_data(T_data, P_data,
                                                   auto_update=auto_update)
        updates['auto_update'] = auto_update
        return updates

    def move_measure(self, request, match_radius=30):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Prints missing positioners, returns data merged with request
        by default also include
        '''
        self.ptl.prepare_move(request, anticollision=None)
        self.ptl.execute_move()
        exppos, meapos, matched, unmatched = self.fvc_measure(
            matched_only=True, match_radius=match_radius)
        # Want to collect both matched and unmatched
        # meapos contains not only matched ones but all posids in expected pos
        matched_df = meapos.loc[matched].reset_index()
        request.rename(columns={'X1': 'TARGET_T', 'X2': 'TARGET_P'},
                       inplace=True)
        merged = matched_df.merge(request, how='outer', on='DEVICE_ID')
        return merged


if __name__ == '__main__':
    ArcCalib(interactive=True)
