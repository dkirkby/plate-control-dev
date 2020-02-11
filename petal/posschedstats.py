import os
import io
import numpy as np
import pandas as pd
import csv
import posconstants as pc


# separated out here because so long
final_checks_str = 'num collisions found by final check (should be zero, or None if no check done)'
found_not_registered_str = 'found but not directly resolved (useful for debugging, not necessarily empty -- some collisions may be indirectly resolved)'

class PosSchedStats(object):
    """Collects statistics from runs of the PosSchedule.
    """
    def __init__(self):
        self._init_data_structures()
        self.clear_cache_after_save_by_append = True
        self.filename_suffix = ''
        self.blank_str = '-'
    
    @property
    def latest(self):
        return self.schedule_ids[-1]
    
    def _init_data_structures(self):
        self.schedule_ids = []
        self.collisions = {}
        self.unresolved = {}
        self.unresolved_tables = {}
        self.unresolved_sweeps = {}
        self.final_checked_collision_pairs = {}
        self.strings = {'method':[]}
        self.numbers = {'n pos':[],
                        'n requests':[],
                        'n requests accepted':[],
                        'n move tables':[],
                        'n tables achieving requested-and-accepted targets':[],
                        final_checks_str:[],
                        'max table move time':[],
                        'num path adjustment iters':[],
                        'request_target calc time':[],
                        'schedule_moves calc time':[],
                        'request + schedule calc time':[],
                        'expert_add_table calc time':[],
                        }
        self.latest_saved_row = None
    
    def register_new_schedule(self, schedule_id, num_pos):
        """Register a new schedule object to track statistics of.
        
           schedule_id ... unique string
           num_pos     ... number of positioners
        """
        self.schedule_ids.append(schedule_id)
        self.collisions[self.latest] = {'found':set(), 'resolved':{}}
        self.unresolved[self.latest] = {}
        self.unresolved_tables[self.latest] = {}
        self.unresolved_sweeps[self.latest] = {}
        self.final_checked_collision_pairs[self.latest] = {}
        for key in self.strings:
            self.strings[key].append(self.blank_str)
        for key in self.numbers:
            val = None if key == final_checks_str else 0
            self.numbers[key].append(val)
        self.numbers['n pos'][-1] = num_pos
        self.real_data_yet_in_latest_row = False

    def set_num_move_tables(self, n):
        """Record number of move tables in the current schedule."""
        self.numbers['n move tables'][-1] = n
        self.real_data_yet_in_latest_row = True
        
    def add_collisions_found(self, collision_pair_ids):
        """Add collisions that have been found in the current schedule.
            collision_pair_ids ... set of colliding posids
        """
        these_collisions = self.collisions[self.latest]
        these_collisions['found'] = these_collisions['found'].union(collision_pair_ids)
        self.real_data_yet_in_latest_row = True
        
    def add_collisions_resolved(self, method, collision_pair_ids):
        """Add collisions that have been resolved in the current schedule.
            method ... string, collision resolution method
            collision_pair_ids ... set of collision_pair_ids resolved by method
        """
        this_dict = self.collisions[self.latest]['resolved']
        if method not in this_dict:
            this_dict[method] = set()
        this_dict[method] = this_dict[method].union(collision_pair_ids)
        self.real_data_yet_in_latest_row = True
        
    def add_request(self):
        """Increment requests count."""
        self.numbers['n requests'][-1] += 1
        self.real_data_yet_in_latest_row = True
        
    def add_request_accepted(self):
        """Increment requests accepted count."""
        self.numbers['n requests accepted'][-1] += 1
        self.real_data_yet_in_latest_row = True
    
    def add_table_matching_request(self):
        """Increment number of tables matching their original requests."""
        self.numbers['n tables achieving requested-and-accepted targets'][-1] += 1
        self.real_data_yet_in_latest_row = True
            
    def add_requesting_time(self, time):
        """Add in time spent processing target requests in the current schedule."""
        self.numbers['request_target calc time'][-1] += time
        self.numbers['request + schedule calc time'][-1] += time
        self.real_data_yet_in_latest_row = True

    def add_scheduling_time(self, time):
        """Add in time spent processing move schedules in the current schedule."""
        self.numbers['schedule_moves calc time'][-1] += time
        self.numbers['request + schedule calc time'][-1] += time
        self.real_data_yet_in_latest_row = True

    def add_expert_table_time(self, time):
        """Add in time spent putting expert tables into the current schedule."""
        self.numbers['expert_add_table calc time'][-1] += time
        self.real_data_yet_in_latest_row = True

    def set_scheduling_method(self, method):
        """Set scheduling method (a string) for the current schedule."""
        self.strings['method'][-1] = method
        self.real_data_yet_in_latest_row = True
        
    def set_max_table_time(self, time):
        """Set the maximum move table time in the current schedule."""
        self.numbers['max table move time'][-1] = time
        self.real_data_yet_in_latest_row = True

    def add_to_num_adjustment_iters(self, iterations):
        """Add data recording number of iterations of path adjustment were made."""
        self.numbers['num path adjustment iters'][-1] += iterations
        
    def add_final_collision_check(self, collision_pairs):
        """Add data recording if there were still any bots colliding after a
        final check."""
        if self.numbers[final_checks_str][-1] == None:
            self.numbers[final_checks_str][-1] = 0
        self.numbers[final_checks_str][-1] += len(collision_pairs)
        self.final_checked_collision_pairs[self.latest] = collision_pairs
    
    def add_unresolved_colliding_at_stage(self, stage_name, colliding_set, colliding_tables, colliding_sweeps):
        """Add data recording ids of any bots colliding in a given stage. This
        is distinct from "final" check data."""
        if stage_name not in self.unresolved[self.latest]:
            self.unresolved[self.latest][stage_name] = set()
            self.unresolved_tables[self.latest][stage_name] = {}
            self.unresolved_sweeps[self.latest][stage_name] = {}
        self.unresolved[self.latest][stage_name].update(colliding_set)
        self.unresolved_tables[self.latest][stage_name].update(colliding_tables)
        self.unresolved_sweeps[self.latest][stage_name].update(colliding_sweeps)
    
    def summarize_collision_resolutions(self):
        """Returns a summary dictionary of the collisions and resolutions data."""
        summary = {}
        summary['found total collisions (before anticollision)'] = [len(self.collisions[sched]['found']) for sched in self.schedule_ids]
        summary['collisions with PTL'] = [len({c for c in self.collisions[sched]['found'] if 'PTL' in c}) for sched in self.schedule_ids]
        summary['collisions with GFA'] = [len({c for c in self.collisions[sched]['found'] if 'GFA' in c}) for sched in self.schedule_ids]
        summary['resolved total collisions'] = []
        summary['found set'] = []
        summary['resolved set'] = []
        summary[found_not_registered_str] = []
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
            summary[found_not_registered_str].append(self.found_but_not_resolved(coll['found'],coll['resolved']))
        return summary
    
    def summarize_unresolved_colliding(self):
        """Returns a summary dictionary of the unresolved colliding items."""
        summary = {'unresolved colliding':[], 'unresolved colliding tables':[], 'unresolved colliding sweeps':[], 'final check collision pairs found':[]}
        for sched in self.schedule_ids:
            summary['unresolved colliding'].append(self.unresolved[sched])
            summary['unresolved colliding tables'].append(self.unresolved_tables[sched])
            summary['unresolved colliding sweeps'].append(self.unresolved_sweeps[sched])
            summary['final check collision pairs found'].append(self.final_checked_collision_pairs[sched])
        return summary
        
    def summarize_all(self):
        """Returns a summary dictionary of all data."""
        data = {'schedule id':self.schedule_ids}
        data.update(self.strings)
        data.update(self.numbers)
        data.update(self.summarize_collision_resolutions())
        data.update(self.summarize_unresolved_colliding())
        nrows = len(next(iter(data.values())))
        if not self.real_data_yet_in_latest_row:
            nrows -= 1
            for key in data:
                if len(data[key]) > nrows:
                    del data[key][-1]
        safe_divide = lambda a,b: a / b if b else np.inf # avoid divide-by-zero errors
        data['calc: fraction of target requests accepted'] = [safe_divide(data['n requests accepted'][i], data['n requests'][i]) for i in range(nrows)]
        data['calc: fraction of targets achieved (of those accepted)'] = [safe_divide(data['n tables achieving requested-and-accepted targets'][i], data['n requests accepted'][i]) for i in range(nrows)]
        return data, nrows

    def generate_table(self, append_footers=False):
        """Returns a pandas dataframe representing a complete report table of
        the current stats.
        
        If the argument append_footers=True, then a number of extra rows will
        be added to the bottom of the returned table. These extra rows will
        give max, min, mean, rms, and median for each data column, collated by
        anticollision  method (e.g. 'adjust' vs 'freeze'). That's no new
        information --- just a convenience when for example evaluating sims of
        hundreds of targets in a row.
        """
        data, nrows = self.summarize_all()
        if append_footers:
            blank_row = {'method':''}
            rms = lambda X: (sum([x**2 for x in X])/len(X))**0.5
            unique_methods = sorted(set(data['method']) - {self.blank_str})
            categories = ['overall'] + unique_methods
            calcs = {'max':max, 'min':min, 'rms':rms, 'avg':np.mean, 'med':np.median}
            stats = {}
            for category in categories:
                stats[category] = {}
                for calc in calcs:
                    stats[category][calc] = {'method':calc} # puts the name of this calc in the method column of csv file
                stats[category]['max']['schedule id'] = category # puts the category of this group of calcs in the schedule id column of csv file, in same row as maxes
            for key in data:
                if len(data[key]) > 0:
                    type_test_val = data[key][0]
                    if isinstance(type_test_val,int) or isinstance(type_test_val,float):
                        this_data = {'overall': [data[key][i] for i in range(nrows)]}
                        for category in unique_methods:
                            this_data[category] = [this_data['overall'][i] for i in range(nrows) if data['method'][i] == category]
                        for category in categories:
                            for calc,stat_function in calcs.items():
                                if this_data[category]:
                                    stats[category][calc][key] = stat_function(this_data[category])
        file = io.StringIO(newline='\n')
        writer = csv.DictWriter(file, fieldnames=data.keys())
        writer.writeheader()
        for i in range(nrows):
            row = {key: val[i] for key, val in data.items()}
            writer.writerow(row)
        if append_footers:
            for category in categories:
                writer.writerow(blank_row)
                for calc in calcs:
                    writer.writerow(stats[category][calc])
        file.seek(0)  # go back to the beginning after finishing write
        return pd.read_csv(file)  # returns a pandas dataframe

    def save(self, path=None, mode='w'):
        """Saves stats results to disk.
        """
        if path is None:
            suffix = str(self.filename_suffix)
            suffix = '_' + suffix if suffix else ''
            filename = f'{pc.filename_timestamp_str()}_schedstats{suffix}.csv'
            path = os.path.join(pc.dirs['temp_files'], filename)
        include_headers = True if mode == 'w' or not os.path.exists(path) else False
        include_footers = False if mode == 'a' else True
        pd = self.generate_table(append_footers=include_footers)
        if mode == 'a':
            start_row = 0 if self.latest_saved_row == None else self.latest_saved_row + 1
            n_rows_to_save = len(pd) - start_row
            self.latest_saved_row = len(pd) - 1 # placed intentionally before the tail operation
            pd = pd.tail(n_rows_to_save)
        pd.to_csv(path, mode=mode, header=include_headers, index=False)
        if mode == 'a' and self.clear_cache_after_save_by_append:
            self._init_data_structures()

    @staticmethod
    def found_but_not_resolved(found, resolved):
        """Searches through the dictionary of resolved collision pairs, and
        eliminates these from the set of found collision pairs.
        
        Inputs:
            found ... set of strings
            resolved ... dict with keys = strings, values = sets of strings
            
        Output:
            set of strings
        """
        output = found.copy()
        for f_pair in found:
            for method in resolved:
                for r_pair in resolved[method]:
                    if f_pair == r_pair and f_pair in output: # second check since pair may repeat in multiple resolved[method] sets, for example if collision was fixed first in a retract stage, and then again in an extend stage
                        output.remove(f_pair)
        return output