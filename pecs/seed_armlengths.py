from pecs import PECS
import posconstants as pc


class SeedArmlengths(PECS):
    def __init__(self, petal_id=None, posids=None, interactive=False):
        super().__init__()
        self.printfunc('\nSeeding armlengths...\n')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_id, posids)
        self.seed_armlengths()
        self.printfunc('Please check DB to ensure new values are committed.')

    def seed_armlengths(self):
        for posid in self.posids:
            self.ptl.set_posfid_val(posid, 'LENGTH_R1',
                                    pc.nominals['LENGTH_R1']['value'])
            self.ptl.set_posfid_val(posid, 'LENGTH_R2',
                                    pc.nominals['LENGTH_R2']['value'])
        self.ptl.commit(mode='calib')


if __name__ == '__main__':
    SeedArmlengths(interactive=True)
