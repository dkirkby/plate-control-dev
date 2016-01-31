import numpy as np
import posconstants as pc
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import os
plt.rcParams['animation.ffmpeg_path'] = os.getcwd()

class PosPlot(object):
    """Handles plotting animated visualizations for array of positioners.
    """
    def __init__(self, fignum=0, timestep=0.1):
        self.fignum = fignum
        self.fig = plt.figure(fignum, figsize=(16,12))
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
                            'linewidth' : 2,
                            'edgecolor' : 'blue',
                            'facecolor' : 'none'},

                       'phi arm':
                           {'linestyle' : '-',
                            'linewidth' : 2,
                            'edgecolor' : 'blue',
                            'facecolor' : 'none'},

                       'central body':
                           {'linestyle' : '-',
                            'linewidth' : 2,
                            'edgecolor' : 'blue',
                            'facecolor' : 'none'},

                       'collision':
                           {'linestyle' : '-',
                            'linewidth' : 2,
                            'edgecolor' : 'red',
                            'facecolor' : 'none'},

                       'line at 180':
                           {'linestyle' : '-.',
                            'linewidth' : 2,
                            'edgecolor' : '0.6',
                            'facecolor' : 'none'},

                       'Eo':
                           {'linestyle' : '-',
                            'linewidth' : 0.5,
                            'edgecolor' : '0.9',
                            'facecolor' : 'none'},

                       'Ei':
                           {'linestyle' : '-',
                            'linewidth' : 0.5,
                            'edgecolor' : '0.9',
                            'facecolor' : 'none'},

                       'Ee':
                           {'linestyle' : '-',
                            'linewidth' : 0.5,
                            'edgecolor' : '0.9',
                            'facecolor' : 'none'},

                       'PTL':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'edgecolor' : '0.5',
                            'facecolor' : 'none'},

                       'GFA':
                           {'linestyle' : '--',
                            'linewidth' : 1,
                            'edgecolor' : '0.5',
                            'facecolor' : 'none'}
                       }

    def clear(self):
        self = PosPlot(self.fignum, self.timestep)

    def add_or_change_item(self, item_str, item_idx, time, polygon_points, collision_time=np.inf):
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
        if time < item['collision_time']:
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
        temp = np.array([])
        for item in self.items.values():
            temp = np.append(temp, item['time'])
        self.all_times = np.unique(temp)
        self.patches = []
        xmin = np.inf
        xmax = -np.inf
        ymin = np.inf
        ymax = -np.inf
        i = 0
        for item in self.items.values():
            patch = self.get_patch(item,0)
            self.patches.append(self.ax.add_patch(patch))
            xmin = min(xmin,min(item['poly'][0][0]))
            xmax = max(xmax,max(item['poly'][0][0]))
            ymin = min(ymin,min(item['poly'][0][1]))
            ymax = max(ymax,max(item['poly'][0][1]))
            plt.xlim(xmin=xmin,xmax=xmax)
            plt.ylim(ymin=ymin,ymax=ymax)
            item['last_patch_update'] = -1
            item['patch_idx'] = i
            i += 1
        return self.patches

    def anim_frame_update(self, time):
        """Sequentially update the animation to the next frame.
        """
        for item in self.items.values():
            this_patch_update = item['last_patch_update'] + 1
            if this_patch_update < len(item['time']) and time >= item['time'][item['last_patch_update']]:
                self.set_patch(self.patches[item['patch_idx']], item, this_patch_update)
                item['last_patch_update'] = this_patch_update
        return self.patches

    def animate(self):
        self.anim_init()
        n_frames = int(np.round(max(self.all_times)/self.timestep))
        anim = animation.FuncAnimation(fig=self.fig, func=self.anim_frame_update,
                                       frames=n_frames, interval=1000*self.timestep, blit=True, repeat=False)
        #writer = animation.FFMpegWriter()
        #anim.save('some_filename.mp4', fps=1/self.timestep, writer=writer)
        plt.show()


    @staticmethod
    def get_patch(item,index):
        return plt.Polygon(item['poly'][index].transpose().tolist(),
                           linestyle=item['style'][index]['linestyle'],
                           linewidth=item['style'][index]['linewidth'],
                           edgecolor=item['style'][index]['edgecolor'],
                           facecolor=item['style'][index]['facecolor'])

    @staticmethod
    def set_patch(patch,item,index):
        patch.set_xy(item['poly'][index].transpose().tolist())
        patch.set_linestyle(item['style'][index]['linestyle'])
        patch.set_linewidth(item['style'][index]['linewidth'])
        patch.set_edgecolor(item['style'][index]['edgecolor'])
        patch.set_facecolor(item['style'][index]['facecolor'])

