from pecs import PECS
import posconstants as pc


class SeedArmlengths(PECS):

    def __init__(self, fvc=None, ptlm=None,
                 petal_roles=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptlm=ptlm)
        self.printfunc('\nSeeding armlengths...\n')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_roles, posids)
        self.seed_vals()
        self.printfunc('Please check DB to ensure new values are committed.')

    def seed_vals(self):
        for posid in self.posids:
            ptl = self.get_owning_ptl(posid)
            self.ptlm.set_posfid_val(posid, 'LENGTH_R1',
                                     pc.nominals['LENGTH_R1']['value'],
                                     participating_petals=[ptl])
            self.ptlm.set_posfid_val(posid, 'LENGTH_R2',
                                     pc.nominals['LENGTH_R2']['value'],
                                     participating_petals=[ptl])
        self.ptlm.commit(mode='calib', log_note='seed_armlengths')


if __name__ == '__main__':
    SeedArmlengths(interactive=True)
