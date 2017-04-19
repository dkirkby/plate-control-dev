'''Use this application to grade positioners based on their xytest summary results.
'''
import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
import csv
import collections
import summarizer
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt

# grading parameters
# c.f. DESI-XXXX Fiber Positioner Grades
# the list specs refer to values at the stat_cuts specified in the summarizer
grade_specs = collections.OrderedDict()
grade_spec_headers = ['blind max um','corr max um','corr rms um','has extended gearbox']
grade_spec_err_keys = grade_spec_headers[0:2]
grading_threshold = summarizer.thresholds_um[0]
min_num_targets = 24 # a test is not considered valid without at least this many targets
min_num_concluding_consecutive_tests = 3 # number of tests for valid results

grade = 'A'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100, 100]
grade_specs[grade]['corr max um']          = [  15,  15]
grade_specs[grade]['corr rms um']          = [   5,   5]
grade_specs[grade]['has extended gearbox'] = False

grade = 'B'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 150, 200]
grade_specs[grade]['corr max um']          = [  15,  30]
grade_specs[grade]['corr rms um']          = [   5,   5]
grade_specs[grade]['has extended gearbox'] = False

grade = 'C'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 250, 250]
grade_specs[grade]['corr max um']          = [  20,  40]
grade_specs[grade]['corr rms um']          = [   5,  10]
grade_specs[grade]['has extended gearbox'] = False

grade = 'D'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 350, 350]
grade_specs[grade]['corr max um']          = [  30,  60]
grade_specs[grade]['corr rms um']          = [  10,  20]
grade_specs[grade]['has extended gearbox'] = False

grade = 'E'
grade_specs[grade] = grade_specs['C'].copy()
grade_specs[grade]['has extended gearbox'] = True

fail_grade = 'F'
insuff_data_grade = 'insuff data'
all_grades = list(grade_specs.keys()) + [fail_grade] # intentionally not including ignored in this

# functions for getting the best or worst grade out of a list or set
def best(grade):
    return min(grade)
def worst(grade):
    return max(grade)
def as_good_as(grade1,grade2):
    return grade1 <= grade2

# get the files list
filetypes = (('Comma-separated Values','*.csv'),('All Files','*'))
gui_root = tkinter.Tk()
process_all_files = tkinter.messagebox.askyesno(title='Batch grade all files?',message='Yes  -->  Process all files in the ' + os.path.relpath(pc.xytest_summaries_directory,pc.all_logs_directory) + ' folder.\n\nNo -->  Process just some file(s) of your choice.')
if not(process_all_files):
    files = list(tkinter.filedialog.askopenfilenames(initialdir=pc.xytest_summaries_directory, filetypes=filetypes, title='Select summary file(s) to process.'))
else:
    files = os.listdir(pc.xytest_summaries_directory)
    files = [pc.xytest_summaries_directory + file for file in files]
gui_root.withdraw()

# parse and validate the file names
files.sort() # just makes lists easier to read forever after
initial_files = files
suffix = '_summary.csv'
files = [file for file in files if '_summary.csv' in file]
ignored_files = [file for file in initial_files if file not in files]
if ignored_files:
    gui_root = tkinter.Tk()
    plural = 's' if len(ignored_files) > 1 else ''
    message = str(len(ignored_files)) + ' file' + plural + ' skipped:' + ''.join(['\n' + os.path.basename(file) for file in ignored_files])
    tkinter.messagebox.showinfo(title='Skipped non-standard files.',message=message)
    gui_root.withdraw()
posids = [os.path.split(file)[1].split(suffix)[0] for file in files]
d = collections.OrderedDict()
for posid in posids:
    d[posid] = {}
    d[posid]['file'] = files[posids.index(posid)]
 
# identify motor types
ask_ignore_gearbox = True
ignore_gearbox = False
for posid in d.keys():
    d[posid]['has extended gearbox'] = 'unknown'
motor_types_file = pc.all_logs_directory + os.path.sep + 'as-built_motor_types.csv'
bool_yes_equivalents = ['y','yes','true','1'] + ['']  # conservatively assume blank means 'yes'
with open(motor_types_file,'r',newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        theta_extended = row['has theta extended gearbox'].lower() in bool_yes_equivalents
        phi_extended   = row['has phi extended gearbox'].lower()   in bool_yes_equivalents
        if row['posid'] in d.keys():
            d[row['posid']]['has extended gearbox'] = theta_extended or phi_extended
for posid in d.keys():
    if ask_ignore_gearbox and d[posid]['has extended gearbox'] == 'unknown':
        gui_root = tkinter.Tk()
        ignore_gearbox = tkinter.messagebox.askyesno(title='Ignore gearbox extensions?',message='Whether the motors have gearbox extensions is not known for all the positioners being graded.\n\nIgnore the gearbox extension criteria?')
        ask_ignore_gearbox = False
        gui_root.withdraw()
if ignore_gearbox:
    for grade in grade_specs.keys():
        grade_specs[grade]['has extended gearbox'] = 'ignored'
            
# read in the summary data
ask_ignore_min_tests = True
ignore_min_tests = False
ask_ignore_manual_bad_data_rows = True
ignore_manual_bad_data_rows = False
err_keys = summarizer.Summarizer.make_err_keys()
err_keys = [s for s in err_keys if 'num' not in s]
pos_to_delete = set()
for posid in d.keys():
    d[posid]['num manually ignored rows'] = 0
    with open(d[posid]['file'],'r',newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        valid_keys = []
        for key in err_keys + ['curr cruise','curr creep','finish time','total move sequences at finish']:
            if key in reader.fieldnames:
                valid_keys.append(key)
                d[posid][key] = []
        n_rows = 0
        for row in reader:
            ignore_this_row_manual = False
            if summarizer.manual_ignore_key in row.keys():
                if row[summarizer.manual_ignore_key]:
                    if ask_ignore_manual_bad_data_rows:
                        gui_root = tkinter.Tk()
                        ignore_manual_bad_data_rows = tkinter.messagebox.askyesno(title='Ignore manually id\'d rows?',message='Some rows in the summary data files have been marked as bad data that should be ignored. Do you want to do this?\n\nYes --> ignore the data marked bad\nNo --> process all the data')
                        ask_ignore_manual_bad_data_rows = False
                        gui_root.withdraw()
                    ignore_this_row_manual = row[summarizer.manual_ignore_key] and ignore_manual_bad_data_rows
            ignore_this_row_sparse = int(row['num targets']) < min_num_targets
            if not(ignore_this_row_manual or ignore_this_row_sparse):
                for key in valid_keys:
                    val = row[key]
                    if val.replace('.','').isnumeric():
                        val = float(val)
                        if val % 1 == 0:
                            val = int(val)
                    elif key == 'finish time':
                        val = str(val) # could consider doing date parsing here, but doesn't seem necessary so far
                    else:
                        val = None
                    d[posid][key].append(val)
                n_rows += 1
            if ignore_this_row_manual and not(ignore_this_row_sparse):
                d[posid]['num manually ignored rows'] += 1
        d[posid]['num rows'] = n_rows
        if n_rows == 0:
            pos_to_delete.add(posid)
        if n_rows < min_num_concluding_consecutive_tests:
            if ask_ignore_min_tests:
                gui_root = tkinter.Tk()
                ignore_min_tests = tkinter.messagebox.askyesno(title='Ignore min # tests?',message='Some positioners have fewer than the minimum number of tests we typically want.\n\nIgnore the minimum # of tests criterion?')
                ask_ignore_min_tests = False
                gui_root.withdraw()
            if ignore_min_tests:
                min_num_concluding_consecutive_tests = 1
    if (None in d[posid]['curr cruise'] or None in d[posid]['curr creep']):
        d[posid]['curr cruise'] = 100 # assume max current, lacking data
        d[posid]['curr creep'] = 100 # assume max current, lacking data
for posid in pos_to_delete:
    del d[posid]
    del posids[posids.index(posid)]
        
# gather up all grades passed for each test loop for each positioner
for posid in d.keys():
    d[posid]['row grade'] = []
    for row in range(d[posid]['num rows']):
        passing_grades = set(all_grades)
        for grade in grade_specs.keys():
            failed_this_grade = False
            for c in range(len(summarizer.stat_cuts)):
                cut = summarizer.stat_cuts[c]
                suffix1 = summarizer.Summarizer.statcut_suffix(cut)
                suffix2 = summarizer.Summarizer.err_suffix(cut,grading_threshold)
                blind_max = d[posid]['blind max (um)' + suffix1][row]
                corr_max = d[posid]['corr max (um)' + suffix2][row]
                corr_rms = d[posid]['corr rms (um)' + suffix2][row]
                if blind_max > grade_specs[grade]['blind max um'][c]:
                    failed_this_grade = True
                if corr_max > grade_specs[grade]['corr max um'][c]:
                    failed_this_grade = True
                if corr_rms > grade_specs[grade]['corr rms um'][c]:
                    failed_this_grade = True
            if not(ignore_gearbox):
                if d[posid]['has extended gearbox'] and not(grade_specs[grade]['has extended gearbox']):
                    failed_this_grade = True
                if not(d[posid]['has extended gearbox']) and grade_specs[grade]['has extended gearbox']:
                    failed_this_grade = True
            if failed_this_grade:
                passing_grades.remove(grade)
        this_grade = best(passing_grades)
        d[posid]['row grade'].append(this_grade)

# determine the final grade for each positioner
for posid in d.keys():
    these_grades = []
    final_row_idx = d[posid]['num rows'] - 1
    for row in range(final_row_idx, final_row_idx - min_num_concluding_consecutive_tests, -1):
        these_grades.append(d[posid]['row grade'][row])
    if len(these_grades) > 0:
        d[posid]['final grade'] = worst(these_grades)
    else:
        d[posid]['final grade'] = insuff_data_grade
        
# count how many test rows prove this grade
for posid in d.keys():
    d[posid]['consecutive tests proving grade'] = []
    d[posid]['all tests proving grade'] = []
    streak_broken = False
    final_row_idx = d[posid]['num rows'] - 1
    for row in range(final_row_idx, -1, -1):
        if as_good_as(d[posid]['row grade'][row], d[posid]['final grade']):
            d[posid]['all tests proving grade'].append(row)

# find the minimum current at which this grade was proven
for posid in d.keys():
    creeps_proven = [d[posid]['curr creep'][row] for row in d[posid]['all tests proving grade']]
    cruise_proven = [d[posid]['curr cruise'][row] for row in d[posid]['all tests proving grade']]
    d[posid]['lowest curr creep proven'] = min(creeps_proven)
    d[posid]['lowest curr cruise proven'] = min(cruise_proven)

# write report
timestamp_str = pc.timestamp_str_now()
filename_timestamp_str = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()
report_file = tkinter.filedialog.asksaveasfilename(title='Save grade report as...',initialdir=pc.all_logs_directory + os.path.sep + 'xytest_grades',initialfile=filename_timestamp_str + '_positioner_grades_report.csv',filetypes=filetypes)
if not(report_file):
    tkinter.messagebox.showwarning(title='No report saved.',message='No grade report was saved to disk.')
gui_root.withdraw()
proven_keys = ['lowest curr cruise proven','lowest curr creep proven']
if report_file:
    with open(report_file,'w',newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['REPORT DATE:'])
        writer.writerow(['',timestamp_str])
        writer.writerow([''])
        writer.writerow(['SPECIFICATIONS APPLIED IN THIS REPORT:'])
        stat_cuts_text = [summarizer.Summarizer.statcut_suffix(s) for s in summarizer.stat_cuts]
        stat_cuts_text = ''.join([s + ',' for s in stat_cuts_text])
        stat_cuts_text = stat_cuts_text[1:-1] # removal of leading whitespace and trailing comma
        writer.writerow(['statistical cuts made at [' + stat_cuts_text + ']'])
        writer.writerow(['correction move thresholds at ' + format(grading_threshold,'.1f') + ' um'])
        writer.writerow(['min number of targets per test = ' + str(min_num_targets)])
        writer.writerow(['min number of consecutive concluding tests to prove grade = ' + str(min_num_concluding_consecutive_tests)])
        writer.writerow(['','grade'] + grade_spec_headers)
        for key in grade_specs.keys():
            writer.writerow(['',key] + list(grade_specs[key].values()))
        writer.writerow(['',fail_grade + ' ... does not meet any of the above grades.'])
        writer.writerow([''])
        writer.writerow(['TOTALS FOR EACH GRADE:'])
        writer.writerow(['','grade', 'quantity', 'percent'])
        num_insuff = len([posid for posid in d.keys() if d[posid]['final grade'] == insuff_data_grade])
        num_suff = len(d) - num_insuff
        def percent(value):
            return format(value/(num_suff)*100,'.2f')+'%'
        for key in all_grades:
            total_this_grade = len([posid for posid in d.keys() if d[posid]['final grade'] == key])
            writer.writerow(['',key,total_this_grade,percent(total_this_grade)])
        writer.writerow(['','all',num_suff,percent(num_suff)])
        if num_insuff > 0:
            writer.writerow(['',insuff_data_grade,num_insuff])
        writer.writerow([''])
        writer.writerow(['INDIVIDUAL POSITIONER GRADES:'])
        writer.writerow(['','posid','grade'] + proven_keys + ['num manually-ignored bad data rows'])
        posids_sorted_by_grade = []
        for grade in all_grades + [insuff_data_grade]:
            for posid in d.keys():
                if d[posid]['final grade'] == grade:
                    posids_sorted_by_grade.append(posid)
        for posid in posids_sorted_by_grade:
            writer.writerow(['', posid, d[posid]['final grade']] + [d[posid][key] for key in proven_keys] + [d[posid]['num manually ignored rows']])
        writer.writerow([''])
        writer.writerow(['INDIVIDUAL TEST LOOP GRADES:'])
        writer.writerow(['','posid','finish time','total move sequences','grade'])
        for posid in posids_sorted_by_grade:
            for row  in range(d[posid]['num rows']):
                writer.writerow(['', posid] + [d[posid][key][row] for key in ['finish time','total move sequences at finish','row grade']])

# gather some data for plotting
alldata = {}
for key in ['num moves','row grade','posid','is last data point','date tested']:
    alldata[key] = []
for posid in d.keys():
    for row in range(d[posid]['num rows']):
        num_moves = d[posid]['total move sequences at finish'][row]
        alldata['num moves'].append(num_moves)
        alldata['row grade'].append(d[posid]['row grade'][row])
        alldata['posid'].append(posid)
        alldata['is last data point'].append(row + 1 == d[posid]['num rows'])
        datetime = dt.datetime.strptime(d[posid]['finish time'][row],pc.timestamp_format)
        alldata['date tested'].append(datetime)
def sort_alldata_by(sort_key):
    sorted_idxs = np.argsort(alldata[sort_key])
    for key in alldata.keys():
        alldata[key] = np.array(alldata[key])[sorted_idxs].tolist()   

# write plots
gui_root = tkinter.Tk()
keep_asking = True
plot_types = {0: 'None',
              1: 'grade vs date tested (cumulative)',
              2: 'grade vs num moves'}
plot_select_text = ''.join(['Enter what type of plots to save.\n\n'] + [str(key) + ': ' + plot_types[key] + '\n' for key in plot_types.keys()])
while keep_asking:
    response = tkinter.simpledialog.askinteger(title='Select plot type', prompt=plot_select_text, minvalue=min(plot_types.keys()), maxvalue=max(plot_types.keys()))
    if response == 0 or response == None:
        keep_asking = False
    else:
        plt.ioff()
        fig = plt.figure(figsize=(10, 7))
        num_pos_in_each_grade = collections.OrderedDict([(grade,[0]) for grade in all_grades])
        if response == 1:
            sort_alldata_by('date tested')
            for i in range(len(alldata['date tested'])):
                for grade in all_grades:
                    num_pos_in_each_grade[grade].append(num_pos_in_each_grade[grade][-1])
                if alldata['is last data point'][i]:
                    grade = d[alldata['posid'][i]]['final grade']
                    num_pos_in_each_grade[grade][-1] += 1
            for grade in all_grades:
                color = next(plt.gca()._get_lines.prop_cycler)['color']
                del num_pos_in_each_grade[grade][0] # remove those pesky initial rows filled with 0
                label = 'Grade ' + str(grade) + ' (' + str(num_pos_in_each_grade[grade][-1]) + ')'
                plt.plot_date(alldata['date tested'], num_pos_in_each_grade[grade], fmt='-', color=color, label=label)
                plt.plot_date(alldata['date tested'][-1], num_pos_in_each_grade[grade][-1], fmt='o', color=color)
            plt.gca().autoscale_view()
            plt.xlim(xmax=plt.xlim()[1] + 1.0) # add a little padding to the picture
            plt.xlabel('last date tested')
            plt.ylabel('cumulative positioners')
            plt.grid('on')
        elif response == 2:
            sort_alldata_by('num moves')
            num_moves = [0]
            last_grade = dict([(posid,None) for posid in d.keys()])
            cleanup_posid = None
            for i in range(len(alldata['num moves'])):                    
                this_num_moves = alldata['num moves'][i]
                if this_num_moves > num_moves[-1]:
                    num_moves.append(this_num_moves)
                    for grade in num_pos_in_each_grade.keys():
                        num_pos_in_each_grade[grade].append(num_pos_in_each_grade[grade][-1])   
                this_posid = alldata['posid'][i]
                this_grade = alldata['row grade'][i]
                if last_grade[this_posid] != this_grade:
                    if last_grade[this_posid] != None:
                        num_pos_in_each_grade[last_grade[this_posid]][-1] -= 1
                    num_pos_in_each_grade[this_grade][-1] += 1
                    last_grade[this_posid] = this_grade
                if cleanup_posid:
                    num_pos_in_each_grade[last_grade[cleanup_posid]][-1] -= 1
                    cleanup_posid = None
                if alldata['is last data point'][i]:
                    cleanup_posid = this_posid
            del num_moves[0] # remove those pesky initial rows filled with 0
            for L in num_pos_in_each_grade.values():
                del L[0] # remove those pesky initial rows filled with 0
            for grade in all_grades:
                plt.plot(num_moves,num_pos_in_each_grade[grade],label='Grade ' + str(grade))
            plt.xlabel('lifetime moves')
            plt.ylabel('number of positioners')
            plt.grid('on')
        plotname = os.path.splitext(report_file)[0] + '_plot' + str(response) + '.pdf'
        plt.title(' ' + plot_types[response].upper() + '\n ' + os.path.basename(report_file), loc='left')
        plt.legend(loc='best')
        plt.savefig(plotname)
        plt.close(fig)
        tkinter.messagebox.showinfo(title='Plot saved',message='Plot of ' + plot_types[response] + ' saved to:\n\n' + plotname)
gui_root.withdraw()