'''Use this application to grade positioners based on their xytest summary results.
'''
import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import csv
import collections
import summarizer
import numpy as np
import copy

# grading parameters
# c.f. DESI-XXXX Fiber Positioner Grades
# the list specs refer to values at the stat_cuts specified in the summarizer
grade_specs = collections.OrderedDict()
grade_spec_headers = ['blind max um','corr max um','corr rms um','failure current','has extended gearbox']
grade_spec_err_keys = grade_spec_headers[0:2]
grading_threshold = summarizer.thresholds_um[0]
min_num_targets = 24 # a test is not considered valid without at least this many targets
min_num_concluding_consecutive_tests = 3 # number of tests for valid results

grade = 'A'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100, 100]
grade_specs[grade]['corr max um']          = [  15,  15]
grade_specs[grade]['corr rms um']          = [   5,   5]
grade_specs[grade]['failure current']      = 80
grade_specs[grade]['has extended gearbox'] = False

grade = 'B'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 150, 200]
grade_specs[grade]['corr max um']          = [  15,  30]
grade_specs[grade]['corr rms um']          = [   5,   5]
grade_specs[grade]['failure current']      = 80
grade_specs[grade]['has extended gearbox'] = False

grade = 'C'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 250, 250]
grade_specs[grade]['corr max um']          = [  20,  40]
grade_specs[grade]['corr rms um']          = [   5,  10]
grade_specs[grade]['failure current']      = 90
grade_specs[grade]['has extended gearbox'] = False

grade = 'D'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 300, 300]
grade_specs[grade]['corr max um']          = [  30,  60]
grade_specs[grade]['corr rms um']          = [  10,  20]
grade_specs[grade]['failure current']      = 100
grade_specs[grade]['has extended gearbox'] = False

grade = 'E'
grade_specs[grade] = grade_specs['C'].copy()
grade_specs[grade]['has extended gearbox'] = True

fail_grade = 'F'
all_grades = list(grade_specs.keys()) + [fail_grade]

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
pos_ids = [os.path.split(file)[1].split(suffix)[0] for file in files]
d = collections.OrderedDict()
for pos_id in pos_ids:
    d[pos_id] = {}
    d[pos_id]['file'] = files[pos_ids.index(pos_id)]
 
# identify motor types
ask_ignore_gearbox = True
ignore_gearbox = False
for pos_id in d.keys():
    d[pos_id]['has extended gearbox'] = 'unknown'
motor_types_file = pc.all_logs_directory + os.path.sep + 'as-built_motor_types.csv'
bool_yes_equivalents = ['y','yes','true','1'] + ['']  # conservatively assume blank means 'yes'
with open(motor_types_file,'r',newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        theta_extended = row['has theta extended gearbox'].lower() in bool_yes_equivalents
        phi_extended   = row['has phi extended gearbox'].lower()   in bool_yes_equivalents
        if row['pos_id'] in d.keys():
            d[row['pos_id']]['has extended gearbox'] = theta_extended or phi_extended
for pos_id in d.keys():
    if ask_ignore_gearbox and d[pos_id]['has extended gearbox'] == 'unknown':
        gui_root = tkinter.Tk()
        ignore_gearbox = tkinter.messagebox.askyesno(title='Ignore gearbox extensions?',message='Whether the motors have gearbox extensions is not known for all the positioners being graded. Ignore the gearbox extension criteria?')
        ask_ignore_gearbox = False
        gui_root.withdraw()
if ignore_gearbox:
    for grade in grade_specs.keys():
        grade_specs[grade]['has extended gearbox'] = 'ignored'
            
# read in the summary data
ask_ignore_unknown_curr = True
ignore_currents = False
ask_ignore_min_tests = True
ignore_min_tests = False
err_keys = summarizer.Summarizer.make_err_keys()
err_keys = [s for s in err_keys if 'num' not in s]
pos_to_delete = set()
for pos_id in d.keys():
    with open(d[pos_id]['file'],'r',newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        valid_keys = []
        for key in err_keys + ['curr cruise','curr creep']:
            if key in reader.fieldnames:
                valid_keys.append(key)
                d[pos_id][key] = []
        n_rows = 0
        for row in reader:
            if int(row['num targets']) >= min_num_targets:
                for key in valid_keys:
                    val = row[key]
                    if val.replace('.','').isnumeric():
                        val = float(val)
                        if val % 1 == 0:
                            val = int(val)
                    else:
                        val = None
                    d[pos_id][key].append(val)
                n_rows += 1
        d[pos_id]['num rows'] = n_rows
        if n_rows == 0:
            pos_to_delete.add(pos_id)
        if n_rows < min_num_concluding_consecutive_tests:
            if ask_ignore_min_tests:
                gui_root = tkinter.Tk()
                ignore_min_tests = tkinter.messagebox.askyesno(title='Ignore min # tests?',message='Some positioenrs have fewer than the minimum number of tests we typically want. Ignore the minimum # of tests criterion?')
                ask_ignore_min_tests = False
                gui_root.withdraw()
            if ignore_min_tests:
                min_num_concluding_consecutive_tests = 0
    if ask_ignore_unknown_curr and (None in d[pos_id]['curr cruise'] or None in d[pos_id]['curr creep']):
        gui_root = tkinter.Tk()
        ignore_currents = tkinter.messagebox.askyesno(title='Ignore failure currents?',message='Some current values are not known in the data. (Historically current was not recorded in early test runs.) Ignore the failure current criteria?')
        ask_ignore_unknown_curr = False
        gui_root.withdraw()
if ignore_currents:
    for grade in grade_specs.keys():
        grade_specs[grade]['failure current'] = 'ignored'
for pos_id in pos_to_delete:
    del d[pos_id]
    del pos_ids[pos_ids.index(pos_id)]
        
# grade positioners
for pos_id in d.keys():
    d[pos_id]['grade'] = fail_grade
    for grade in grade_specs.keys():
        D = copy.deepcopy(d[pos_id])
        while D['num rows'] > min_num_concluding_consecutive_tests:
            this_grade_valid = True
            if not(ignore_currents):
                selection1 = np.array(D['curr cruise']) >= grade_specs[grade]['failure current']
                selection2 = np.array(D['curr creep']) >= grade_specs[grade]['failure current']
                selection = selection1 * selection2
            else:
                selection = range(D['num rows'])
            for i in range(len(summarizer.stat_cuts)):
                cut = summarizer.stat_cuts[i]
                suffix1 = summarizer.Summarizer.statcut_suffix(cut)
                suffix2 = summarizer.Summarizer.err_suffix(cut,grading_threshold)
                blind_max = np.array(D['blind max (um)' + suffix1])[selection]
                corr_max = np.array(D['corr max (um)' + suffix2])[selection]
                corr_rms = np.array(D['corr rms (um)' + suffix2])[selection]
                if max(blind_max) > grade_specs[grade]['blind max um'][i]:
                    this_grade_valid = False
                if max(corr_max) > grade_specs[grade]['corr max um'][i]:
                    this_grade_valid = False
                if max(corr_rms) > grade_specs[grade]['corr rms um'][i]:
                    this_grade_valid = False
            if not(ignore_gearbox):
                if D['has extended gearbox'] and not(grade_specs[grade]['has extended gearbox']):
                    this_grade_valid = False
                if not(D['has extended gearbox']) and grade_specs[grade]['has extended gearbox']:
                    this_grade_valid = False
            if this_grade_valid:
                d[pos_id]['grade'] = grade
                break
            else:
                for key in D.keys():
                    if isinstance(D[key],list):
                        D[key].pop(0)
                D['num rows'] -= 1
        if this_grade_valid:
            break
    d[pos_id]['num tests proven'] = D['num rows']
    for curr_text in ['curr cruise','curr creep']:
        key = 'lowest ' + curr_text + ' proven'
        if ignore_currents:
            d[pos_id][key] = 'ignored'
        elif d[pos_id]['grade'] == fail_grade:
            d[pos_id][key] = 'n/a'
        else:
            d[pos_id][key] = min(D[curr_text])
proven_keys = [key for key in d[pos_id].keys() if 'proven' in key]
proven_keys.reverse() # I like this sequence better in the report

# write report
timestamp_str = pc.timestamp_str_now()
filename_timestamp_str = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()
report_file = tkinter.filedialog.asksaveasfilename(title='Save grade report as...',initialdir=pc.all_logs_directory + os.path.sep + 'xytest_grades',initialfile=filename_timestamp_str + '_positioner_grades_report.csv',filetypes=filetypes)
if not(report_file):
    tkinter.messagebox.showwarning(title='No report saved.',message='No grade report was saved to disk.')
gui_root.withdraw()
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
        def percent(value):
            return format(value/len(d)*100,'.1f')+'%'
        for key in all_grades:
            total_this_grade = len([pos_id for pos_id in d.keys() if d[pos_id]['grade'] == key])
            writer.writerow(['',key,total_this_grade,percent(total_this_grade)])
        writer.writerow(['','all',len(d),percent(len(d))])
        writer.writerow([''])
        writer.writerow(['INDIVIDUAL POSITIONER GRADES:'])
        writer.writerow(['','pos_id','grade'] + proven_keys)
        pos_ids_sorted_by_grade = []
        for grade in all_grades:
            for pos_id in d.keys():
                if d[pos_id]['grade'] == grade:
                    pos_ids_sorted_by_grade.append(pos_id)
        for pos_id in pos_ids_sorted_by_grade:
            writer.writerow(['', pos_id, d[pos_id]['grade']] + [d[pos_id][key] for key in proven_keys])
