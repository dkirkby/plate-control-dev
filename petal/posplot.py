import poscollider

class PosPlot(object):
    """Handles plotting animated visualizations for array of positioners.
    """
    def __init__(self, collider=None, fignum=0):
        if not(collider):
            self.collider = PosCollider()
        else:
            self.collider = collider
        self.fig = plt.figure(fignum)
        self.ax = plt.axes()
        self.ferrules    = [None]*npos
        self.phi_arms    = [None]*npos
        self.ctr_bodies  = [None]*npos
        self.collisions  = [None]*npos
        self.fixed_items = []
        self.properties = [{'prop_name' : 'ferrule',
                            'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'blue',
                            'fillcolor' : '0.3'},

                           {'prop_name' : 'phi arm',
                            'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'blue',
                            'fillcolor' : '0.3'},

                           {'prop_name' : 'central body',
                            'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'blue',
                            'fillcolor' : '0.3'},

                           {'prop_name' : 'collision',
                            'linestyle' : '-',
                            'linewidth' : 2,
                            'linecolor' : 'red',
                            'fillcolor' : '0.6'},

                           {'prop_name' : 'line at 180',
                            'linestyle' : '-.',
                            'linewidth' : 1,
                            'linecolor' : '0.5',
                            'fillcolor' : 'none'},

                           {'prop_name' : 'Eo',
                            'linestyle' : '--',
                            'linewidth' : 1,
                            'linecolor' : '0.3',
                            'fillcolor' : 'none'},

                           {'prop_name' : 'Ei',
                            'linestyle' : '--',
                            'linewidth' : 1,
                            'linecolor' : '0.3',
                            'fillcolor' : 'none'},

                           {'prop_name' : 'petal',
                            'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : '0.7',
                            'fillcolor' : 'white'},

                           {'prop_name' : 'GFA',
                            'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : '0.7',
                            'fillcolor' : 'white'},

                           {'prop_name' : '',
                            'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'black',
                            'fillcolor' : 'white'}]

    def set_phi(self, item_idx, time_idx, is_collision):
        pass

    def set_theta(self, item_idx, time_idx, is_collision):
        pass

    def set_fixed(self, item_idx, polygon, prop_name, is_collision):
        pass

    def update(self):
        # go to next timestep
        # set plot data to axes
        pass

    def plot(self):
        self.update()
        plt.show(block=False)
