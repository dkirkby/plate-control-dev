'''
Runs an Grid Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
Currently only runs one Petal at a time, awaiting a petalMan proxy.
'''
import os
import posconstants as pc
from pecs import PECS


class GridCalib(PECS):
    '''
    subclass of PECS that adds functions to run an Grid calibration.
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
        self.n_points_P = 5
        self.n_points_T = 7
        updates = self.calibrate(interactive=interactive)
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-grid_calibration')
        self.printfunc(
            updates[['DEVICE_ID', 'LENGTH_R1', 'LENGTH_R2',
                     'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P']])
        updates.to_csv(path+'.csv')
        updates.to_pickle(path+'.pkl')
        self.printfunc(f'Grid calibration data saved to: {path}')
        if interactive:
            if self._parse_yn(input(
                    'Open grid calibration data table? (y/n): ')):
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

        req_list = self.ptl.get_grid_requests(ids=self.posids,
                                              n_points_T=self.n_points_T,
                                              n_points_P=self.n_points_P)
        grid_data = []
        for i, request in enumerate(req_list):
            self.printfunc(f'Measuring grid point {i+1} of {len(req_list)}...')
            merged_data = self.move_measure(request, match_radius=match_radius)
            grid_data.append(merged_data)
            if self.allow_pause and i+1 < len(req_list):
                input('Paused for heat load monitoring, '
                      'press enter to continue: ')
        updates = self.ptl.calibrate_from_grid_data(grid_data,
                                                    auto_update=auto_update)
        updates['auto_update'] = auto_update
        return updates

    def move_measure(self, request, match_radius=80):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Prints missing positioners, returns data merged with request
        '''
        self.ptl.prepare_move(request, anticollision=None)
        self.ptl.execute_move()
        exppos, meapos, matched, unmatched = self.fvc_measure(
                match_radius=match_radius)
        # Want to collect both matched and unmatched
        used_pos = meapos.loc[sorted(list(matched))]  # only matched rows
        request.rename(columns={'X1': 'TARGET_T', 'X2': 'TARGET_P'},
                       inplace=True)
        merged = used_pos.merge(request, how='outer', on='DEVICE_ID')
        return merged

    # def set_calibration(self, posids=None, reset=False, avoid_big_changes=True):
    #     '''
    #     calls set_calibration function in petalApp

    #     allows a filter on posids using the posids kwarg
    #     if reset, the calibration values will reset to their old values
    #     if avoid_big_changes petalApp will avoid setting widly different values
    #     '''
    #     assert self.data is not None, 'Must have data to set!'
    #     assert self.ptl is not None, 'Must set an active petal!'
    #     if posids is not None:
    #         calib_df = self.data.loc[sorted(posids)]
    #     else:
    #         calib_df = self.data
    #     if reset:
    #         tag = '_OLD'
    #     else:
    #         tag = ''
    #     self.ptl.set_calibration(calib_df, tag=tag,
    #                              avoid_big_changes=avoid_big_changes)


if __name__ == '__main__':
    GridCalib(interactive=True)
