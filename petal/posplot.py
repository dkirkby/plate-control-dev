import poscollider
import numpy as np

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
        self.poly = [] # list of arrays of polygon points, i.e. each element contains a 2xN polygon coordinates array
        self.time = [] # list of time values, one element per poly, identifies when the poly is applied, duplicate times allowed
        self.prop = [] # list of dictionaries, one element per poly, identifies properties of the poly
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



    def add_polygon_update(self, item_str, time, polygon_points, collision_case):
        if len(self.time) == 0 or time >= max(self.time):
            idx = len(self.time)
        elif time < min(self.time):
            idx = 0
        else:
            idx = [i for i in range(len(self.time)) if self.time[i] > time][0] - 1
        self.time.insert(idx, time)
        self.poly.insert(idx, polygon_points)
        if collision_case == case.I:
            prop = self.get_prop(item_str)
        else:
            prop = self.get_prop('collision')
        self.prop.insert(idx, prop)

    def get_prop(self, name):
        return [DICT for DICT in self.properties if DICT['name'] == name][0]

    def update(self):
        # go to next timestep
        # set plot data to axes
        pass

    def plot(self):
        self.update()
        plt.show(block=False)
