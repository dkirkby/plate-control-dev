import numpy as np
import posconstants as pc
import matplotlib.pyplot as plt
import matplotlib.animation as animation

class PosPlot(object):
    """Handles plotting animated visualizations for array of positioners.

    Saving movie files of animations is implemented. Must have ffmpeg to write the
    movie. For Windows machines, download a static binary of ffmpeg, and copy just
    the executable file 'ffmpeg.exe' into the working directory. As of 2016-01-31,
    binaries of ffmpeg are available at: http://ffmpeg.zeranoe.com/builds
    """
    def __init__(self, fignum=0, timestep=0.1):
        self.live_animate = True # whether to plot the animation live
        self.write_movie_file = True # whether to write out a movie file of animation
        self.fignum = fignum
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
            item = {'time':[], 'poly':[], 'style':[], 'collision_time':collision_time}
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
        if time < collision_time:
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
        self.anim_fig = plt.figure(self.fignum, figsize=(16,12))
        self.anim_ax = plt.axes()
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
            self.patches.append(self.anim_ax.add_patch(patch))
            xmin = min(xmin,min(item['poly'][0][0]))
            xmax = max(xmax,max(item['poly'][0][0]))
            ymin = min(ymin,min(item['poly'][0][1]))
            ymax = max(ymax,max(item['poly'][0][1]))
            item['patch_idx'] = i
            item['last_frame'] = self.all_times.tolist().index(item['time'][-1])
            i += 1
        plt.xlim(xmin=xmin,xmax=xmax)
        plt.ylim(ymin=ymin,ymax=ymax)

    def anim_frame_update(self, frame):
        """Sequentially update the animation to the next frame.
        """
        for item in self.items.values():
            i = item['patch_idx']
            if frame <= item['last_frame']:
                self.set_patch(self.patches[i], item, frame)

    def animate(self):
        self.anim_init()
        plt.ion()
        start_end_still_time = 0.5
        if self.write_movie_file:
            fps = 1/self.timestep
            metadata = dict(title='', artist='',comment='')
            filename = 'something.mp4'
            dpi = 75
            writer = animation.FFMpegWriter(fps=fps, metadata=metadata)
            writer.setup(fig=self.anim_fig, outfile=filename, dpi=dpi)
            for i in range(round(start_end_still_time/self.timestep)):
                writer.grab_frame()
        if self.live_animate:
            plt.pause(start_end_still_time)
        frame_times = np.arange(min(self.all_times), max(self.all_times)+self.timestep/2, self.timestep) # extra half-timestep on max ensures inclusion of max val in range
        for frame in range(len(frame_times)):
            self.anim_frame_update(frame)
            if self.write_movie_file:
                writer.grab_frame()
            if self.live_animate:
                plt.pause(self.timestep)
        if self.write_movie_file:
            for i in range(round(start_end_still_time/self.timestep)):
                writer.grab_frame()
            writer.finish()
        if self.live_animate:
            plt.pause(start_end_still_time)
        plt.close()

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
