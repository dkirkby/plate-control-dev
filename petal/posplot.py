import numpy as np
from matplotlib import pyplot as plt
from matplotlib import animation
from poscollider import case

class PosPlot(object):
    """Handles plotting animated visualizations for array of positioners.
    """
    def __init__(self, fignum=0):
        self.fignum = fignum
        self.fig = plt.figure(fignum)
        self.ax = plt.axes()
        self.items = {} # keys shall identify the individual items that get drawn, i.e. 'ferrule 321', 'phi arm 42', 'GFA', etc
                        # values are sub-dictionaries, with the entries:
                        # {'time'  : [], # list of time values at which an update or change is to be applied
                        #  'poly'  : [], # list of arrays of polygon points (each is 2xN), defining the item polygon to draw at that time
                        #  'style' : [], # list of dictionaries, defining the plotting style to draw the polygon at that time
                        #  'collision_time' : np.inf} # time at which collision occurs. if no collision, the time is inf
        self.styles = {'ferrule':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'blue',
                            'fillcolor' : '0.3'},

                       'phi arm':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'blue',
                            'fillcolor' : '0.3'},

                       'central body':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : 'blue',
                            'fillcolor' : '0.3'},

                       'collision':
                           {'linestyle' : '-',
                            'linewidth' : 2,
                            'linecolor' : 'red',
                            'fillcolor' : '0.6'},

                       'line at 180':
                           {'linestyle' : '-.',
                            'linewidth' : 1,
                            'linecolor' : '0.5',
                            'fillcolor' : 'none'},

                       'Eo':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'linecolor' : '0.3',
                            'fillcolor' : 'none'},

                       'Ei':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'linecolor' : '0.3',
                            'fillcolor' : 'none'},

                       'Ee':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'linecolor' : '0.1',
                            'fillcolor' : 'none'},

                       'PTL':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : '0.7',
                            'fillcolor' : 'white'},

                       'GFA':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'linecolor' : '0.7',
                            'fillcolor' : 'white'}
                       }

    def clear(self):
        self = PosPlot(self.fignum)

    def add_or_change_item(self, item_str, item_idx, time, polygon_points, collision_case=case.I):
        key = str(item_str) + ' ' + str(item_idx)
        if key not in self.items.keys():
            item = {'time':[], 'poly':[], 'style':[], 'collision_time':np.inf}
        else:
            item = self.items[key]
        if time in item['time']:
            idx = item['time'].index(time)
            replace_existing_timestep = True
        else:
            replace_existing_timestep = False
            if len(item['time']) == 0 or time >= max(item['time']):
                idx = len(item['time'])
            elif time < min(item['time']):
                idx = 0
            else:
                idx = [i for i in range(len(item['time'])) if item['time'][i] > time][0] - 1
        if collision_case == case.I and time < item['collision_time']:
            style = self.styles[item_str]
        else:
            style = self.styles['collision']
            item['collision_time'] = min(time, item['collision_time'])
        if replace_existing_timestep:
            item['poly'][idx] = polygon_points
            item['style'][idx] = style
        else:
            item['time'].insert(idx, time)
            item['poly'].insert(idx, polygon_points)
            item['style'].insert(idx, style)
        self.items[key] = item

    def update(self):
        # go to next timestep
        # set plot data to axes
        pass

    def plot(self):
        self.update()
        plt.show(block=False)
