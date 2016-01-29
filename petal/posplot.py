import numpy as np
import posconstants as pc
from matplotlib import pyplot as plt
from matplotlib import animation

class PosPlot(object):
    """Handles plotting animated visualizations for array of positioners.
    """
    def __init__(self, fignum=0, timestep=0.1):
        self.fignum = fignum
        self.fig = plt.figure(fignum)
        self.ax = plt.axes()
        self.timestep = timestep # frame interval for animations
        self.items = {} # keys shall identify the individual items that get drawn, i.e. 'ferrule 321', 'phi arm 42', 'GFA', etc
                        # values are sub-dictionaries, with the entries:
                        # {'time'  : [], # list of time values at which an update or change is to be applied
                        #  'poly'  : [], # list of arrays of polygon points (each is 2xN), defining the item polygon to draw at that time
                        #  'style' : [], # list of dictionaries, defining the plotting style to draw the polygon at that time
                        #  'collision_time' : np.inf} # time at which collision occurs. if no collision, the time is inf
        self.styles = {'ferrule':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'edgecolor' : 'blue',
                            'facecolor' : '0.3'},

                       'phi arm':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'edgecolor' : 'blue',
                            'facecolor' : '0.3'},

                       'central body':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'edgecolor' : 'blue',
                            'facecolor' : '0.3'},

                       'collision':
                           {'linestyle' : '-',
                            'linewidth' : 2,
                            'edgecolor' : 'red',
                            'facecolor' : '0.6'},

                       'line at 180':
                           {'linestyle' : '-.',
                            'linewidth' : 1,
                            'edgecolor' : '0.5',
                            'facecolor' : 'none'},

                       'Eo':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'edgecolor' : '0.3',
                            'facecolor' : 'none'},

                       'Ei':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'edgecolor' : '0.3',
                            'facecolor' : 'none'},

                       'Ee':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'edgecolor' : '0.1',
                            'facecolor' : 'none'},

                       'PTL':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'edgecolor' : '0.7',
                            'facecolor' : 'white'},

                       'GFA':
                           {'linestyle' : '-',
                            'linewidth' : 1,
                            'edgecolor' : '0.7',
                            'facecolor' : 'white'}
                       }

    def clear(self):
        self = PosPlot(self.fignum, self.timestep)

    def add_or_change_item(self, item_str, item_idx, time, polygon_points, collision_case=pc.case.I):
        """Add a polygonal item at a particular time to the animation data.
        """
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
                for i in range(len(item['time'])):
                    if item['time'][i] > time:
                        idx = i - 1  # this is where the new timestep data will get inserted
                        break
        if collision_case == pc.case.I and time < item['collision_time']:
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

    def anim_init(self):
        """Sets up the animation, using the data that has been already entered via the
        add_or_change_item method.
        """
        self.last_frame = 0
        self.all_times = np.unique([item['time'] for item in self.items])
        patches = []
        for item in self.items:
            patch = self.get_patch(item,0)
            patches.append(self.ax.add_patch(patch))
        return patches

    def anim_frame_update(self):
        """Sequentially update the animation to the next frame.
        """
        frame = self.last_frame + 1
        time = self.all_times[frame]
        for i in range(len(self.items)):
            item = self.items[i]
            if len(item['time']) > 0 and time >= item['time'][0]:
                patches[i] = self.get_patch(item,0)
                item['time'].pop(0)
                item['poly'].pop(0)
                item['style'].pop(0)
        self.last_frame = frame
        return patches

    def animate(self):
        anim = animation.FuncAnimation(figure=self.fig, func=self.anim_frame_update, init_func=self.anim_init,
                                       frames=len(self.all_times), interval=1000*self.timestep, blit=True)
        anim.save('some_filename.mp4', fps=1/self.timestep)
        plt.show(block=False)


    @staticmethod
    def get_patch(item,index):
        patch = plt.Polygon(item['poly'][index].transpose().tolist(),
                            linestyle=item['style'][index]['linestyle'],
                            linewidth=item['style'][index]['linewidth'],
                            edgecolor=item['style'][index]['edgecolor'],
                            facecolor=item['style'][index]['facecolor'])