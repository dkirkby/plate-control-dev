import os
from pecs import PECS
import posconstants as pc
from rehome_verify import RehomeVerify


class Rehome(PECS):

    def __init__(self, fvc=None, ptls=None, axis='both',
                 pcid=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptls=ptls)
        input('WARNING: Driving positioners to their hardstops. '
              'Be sure you know what you are doing!\n'
              f'Rehoming for axis: {axis}. (Press enter to continue): ')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(pcid, posids)
        self.axis = axis
        df = self.rehome()
        path = os.path.join(pc.dirs['all_logs'], 'calib_logs',
                            f'{pc.filename_timestamp_str()}-rehome.csv')
        df.to_csv(path)
        self.printfunc(f'Rehome (interally-tracked) data saved to: {path}')
        if input('Verify rehome positions with FVC? (y/n): ') in ['y', 'yes']:
            RehomeVerify(pcid=self.pcid, posids=self.posids)

    def rehome(self, posids=None, anticollision='freeze', attempt=1):
        # three atetmpts built in, two with ac freeze, one with ac None
        if posids is None:
            posids = self.posids
        self.printfunc(f'Attempt {attempt}, rehoming {len(posids)} '
                       f'positioners with anticollision: {anticollision}\n\n'
                       f'{posids}\n')
        self.pause(press_enter=True)
        ret = self.ptl.rehome_pos(posids, axis=self.axis,
                                  anticollision=anticollision)
        assert ret is not None, (
            'Rehome failed, None received as return from rehome_pos, '
            'check PetalApp console for error log.')
        ret = (ret.rename(columns={'X1': 'posintT', 'X2': 'posintP'})
               .sort_values(by='DEVICE_ID').reset_index())
        ret['STATUS'] = self.ptl.decipher_posflags(ret['FLAG'])
        mask = ret['FLAG'] != 4
        retry_list = list(ret.loc[mask, 'DEVICE_ID'])
        if len(retry_list) == 0:
            self.printfunc(f'Rehoming (3 tries) complete for all positioners.')
        else:  # non-empty list, need another attempt
            self.printfunc(f'{len(retry_list)} unsucessful: {retry_list}\n\n'
                           f'{ret[mask].to_string()}\n\n'
                           f'Retrying...')
            if attempt <= 2:
                if attempt == 1:  # set anticollision mode for 2nd attempt
                    ac = 'freeze'  # 2nd attempt ac mode
                elif attempt == 2:  # set anticollision mode for 3rd attempt
                    ac = None  # 3rd attempt ac mode
                attempt += 1
                self.rehome(retry_list, anticollision=ac, attempt=attempt)
            else:  # already at 3rd attempt. fail
                self.printfunc(f'3rd attempt did not complete successfully '
                               f'for positioners: {posids}')
        ret = self.ptl.get_positions(posids=self.posids, return_coord='obsXY')
        return ret.rename(columns={'X1': 'expected_obsX',
                                   'X2': 'expected_obsY'})


if __name__ == '__main__':
    Rehome(axis='both', interactive=True)  # theta_only, phi_only, or both
