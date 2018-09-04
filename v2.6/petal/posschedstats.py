import os
import csv
import posconstants as pc

class PosSchedStats(object):
    """Collects statistics from runs of the PosSchedule.
    """
    def __init__(self):
        self.schedule_ids = []
        self.collisions = {}
        self.strings = {'method':[]}
        self.numbers = {'n pos':[], 'n move tables':[], 'max table move time':[],'num path adjustment iters':[], 'request_target calc time':[], 'expert_add_table calc time':[], 'schedule_moves calc time':[]}
        self.num_moving = {}
    
    @property
    def latest(self):
        return self.schedule_ids[-1]
    
    def register_new_schedule(self, schedule_id, num_pos):
        """Register a new schedule object to track statistics of.
        
           schedule_id ... unique string
           num_pos     ... number of positioners
        """
        self.schedule_ids.append(schedule_id)
        self.collisions[self.latest] = {'found':set(), 'resolved':{}}
        self.num_moving[self.latest] = {0:0}
        for key in self.strings:
            self.strings[key].append('-')
        for key in self.numbers:
            self.numbers[key].append(0)
        self.numbers['n pos'][-1] = num_pos
        self.real_data_yet_in_latest_row = False

    def set_num_move_tables(self, n):
        """Record number of move tables in the current schedule."""
        self.numbers['n move tables'][-1] = n
        self.real_data_yet_in_latest_row = True
        
    def add_collisions_found(self, posids):
        """Add collisions that have been found in the current schedule.
            posids ... set of colliding posids
        """
        these_collisions = self.collisions[self.latest]
        these_collisions['found'] = these_collisions['found'].union(posids)
        self.real_data_yet_in_latest_row = True
        
    def add_collisions_resolved(self, method, posids):
        """Add collisions that have been resolved in the current schedule.
            method ... string, collision resolution method
            posids ... set of posids resolved by method
        """
        this_dict = self.collisions[self.latest]['resolved']
        if method not in this_dict:
            this_dict[method] = set()
        this_dict[method] = this_dict[method].union(posids)
        self.real_data_yet_in_latest_row = True
        
    def add_requesting_time(self, time):
        """Add in time spent processing target requests in the current schedule."""
        self.numbers['request_target calc time'][-1] += time
        self.real_data_yet_in_latest_row = True

    def add_expert_table_time(self, time):
        """Add in time spent putting expert tables into the current schedule."""
        self.numbers['expert_add_table calc time'][-1] += time
        self.real_data_yet_in_latest_row = True

    def add_scheduling_time(self, time):
        """Add in time spent processing move schedules in the current schedule."""
        self.numbers['schedule_moves calc time'][-1] += time
        self.real_data_yet_in_latest_row = True
        
    def set_scheduling_method(self, method):
        """Set scheduling method (a string) for the current schedule."""
        self.strings['method'][-1] = method
        self.real_data_yet_in_latest_row = True
        
    def set_max_table_time(self, time):
        """Set the maximum move table time in the current schedule."""
        self.numbers['max table move time'][-1] = time
        self.real_data_yet_in_latest_row = True
    
    def add_num_moving_data(self, num_moving):
        """Add data recording how many positioners are moving at a time.
            num_moving ... dict with keys = time, values = num pos moving at that time.
        """
        self.num_moving[self.latest] = num_moving
        self.real_data_yet_in_latest_row = True
        
    def add_to_num_adjustment_iters(self, iterations):
        """Add data recording number of iterations of path adjustment were made."""
        self.numbers['num path adjustment iters'][-1] += iterations
    
    def summarize_collision_resolutions(self):
        """Returns a summary dictionary of the collisions and resolutions data."""
        summary = {}
        summary['found total collisions'] = [len(self.collisions[sched]['found']) for sched in self.schedule_ids]
        summary['collisions with PTL'] = [len({c for c in self.collisions[sched]['found'] if 'PTL' in c}) for sched in self.schedule_ids]
        summary['collisions with GFA'] = [len({c for c in self.collisions[sched]['found'] if 'GFA' in c}) for sched in self.schedule_ids]
        summary['resolved total collisions'] = []
        summary['found set'] = []
        summary['resolved set'] = []
        for sched in self.schedule_ids:
            coll = self.collisions[sched]
            summary['resolved total collisions'].append(0)
            for method in pc.all_adjustment_methods:
                if method not in summary:
                    summary[method] = []
                if method in coll['resolved']:
                    summary[method].append(len(coll['resolved'][method]))
                else:
                    summary[method].append(0)
                summary['resolved total collisions'][-1] += summary[method][-1]
            summary['found set'].append(coll['found'])
            summary['resolved set'].append(coll['resolved'])
        return summary
    
    def summarize_num_moving(self):
        """Returns a summary dictionary of the data on number of positioners moving at a time."""
        summary = {}
        summary['max moving simultaneously'] = [max(self.num_moving[sched].values()) for sched in self.schedule_ids]
        summary['avg moving simultaneously'] = [sum(self.num_moving[sched].values())/len(self.num_moving[sched].values()) for sched in self.schedule_ids]
        return summary
    
    def summarize_all(self):
        """Returns a summary dictionary of all data."""
        data = {'schedule id':self.schedule_ids}
        data.update(self.strings)
        data.update(self.numbers)
        data.update(self.summarize_num_moving())
        data.update(self.summarize_collision_resolutions())
        return data
    
    def save(self):
        """Saves stats results to disk."""
        filename = pc.filename_timestamp_str_now() + '_schedule_stats.csv'
        path = os.path.join(pc.dirs['temp_files'],filename)
        data = self.summarize_all()
        nrows = len(next(iter(data.values())))
        if not self.real_data_yet_in_latest_row:
            nrows -= 1
        with open(path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile,fieldnames=data.keys())
            writer.writeheader()
            for i in range(nrows):
                row = {key:val[i] for key,val in data.items()}
                writer.writerow(row)
        
                    
        
    # function to plot total power density over time of move before / after annealing