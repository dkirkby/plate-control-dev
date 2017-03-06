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

# grading parameters
# c.f. DESI-XXXX Fiber Positioner Grades
# the list specs refer to values at the stat_cuts specified in the summarizer
grade_specs = collections.OrderedDict()
grade_spec_headers = ['blind max um','corr max um','corr rms um','failure current','has extended gearbox']
grade_spec_err_keys = grade_spec_headers[0:2]
grading_threshold = summarizer.thresholds_um[0]

grade = 'A'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100, 100]
grade_specs[grade]['corr max um']          = [  12,  12]
grade_specs[grade]['corr rms um']          = [   5,   5]
grade_specs[grade]['failure current']      = 80
grade_specs[grade]['has extended gearbox'] = False

grade = 'B'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100, 100]
grade_specs[grade]['corr max um']          = [  12,  30]
grade_specs[grade]['corr rms um']          = [   5,  10]
grade_specs[grade]['failure current']      = 90
grade_specs[grade]['has extended gearbox'] = False

grade = 'C'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100, 200]
grade_specs[grade]['corr max um']          = [  20,  50]
grade_specs[grade]['corr rms um']          = [  10,  20]
grade_specs[grade]['failure current']      = 100
grade_specs[grade]['has extended gearbox'] = False

grade = 'D'
grade_specs[grade] = grade_specs['B'].copy()
grade_specs[grade]['has extended gearbox'] = True

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
for pos_id in d.keys():
    d[pos_id]['has extended gearbox'] = True # conservatively assume yes until proven otherwise
motor_types_file = pc.all_logs_directory + os.path.sep + 'as-built_motor_types.csv'
bool_yes_equivalents = ['y','yes','true','1'] + ['']  # conservatively assume blank means 'yes'
with open(motor_types_file,'r',newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        theta_extended = row['has theta extended gearbox'].lower() in bool_yes_equivalents
        phi_extended   = row['has phi extended gearbox'].lower()   in bool_yes_equivalents
        if row['pos_id'] in d.keys():
            d[row['pos_id']]['has extended gearbox'] = theta_extended or phi_extended
            
# read in the summary data
err_keys = summarizer.Summarizer.make_err_keys()
err_keys = [s for s in err_keys if 'num' not in s]
for pos_id in d.keys():
    with open(d[pos_id]['file'],'r',newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        valid_keys = []
        for key in err_keys + ['curr cruise','curr creep']:
            if key in reader.fieldnames:
                valid_keys.append(key)
                d[pos_id][key] = []
        for row in reader:
            for key in valid_keys:
                val = row[key]
                if val.replace('.','').isnumeric():
                    val = float(val)
                    if val % 1 == 0:
                        val = int(val)
                else:
                    val = None
                d[pos_id][key].append(val)
        
# grade positioners
for pos_id in d.keys():
    d[pos_id]['grade'] = fail_grade
    for grade in grade_specs.keys():
        this_grade_valid = True
        selection1 = np.array(d[pos_id]['curr cruise']) >= grade_specs[grade]['failure current']
        selection2 = np.array(d[pos_id]['curr creep']) >= grade_specs[grade]['failure current']
        selection = selection1 * selection2
        for i in range(len(summarizer.stat_cuts)):
            cut = summarizer.stat_cuts[i]
            suffix1 = summarizer.Summarizer.statcut_suffix(cut)
            suffix2 = summarizer.Summarizer.err_suffix(cut,grading_threshold)
            blind_max = np.array(d[pos_id]['blind max (um)' + suffix1])[selection]
            corr_max = np.array(d[pos_id]['corr max (um)' + suffix2])[selection]
            corr_rms = np.array(d[pos_id]['corr rms (um)' + suffix2])[selection]
            if max(blind_max) > grade_specs[grade]['blind max um'][i]:
                this_grade_valid = False
            if max(corr_max) > grade_specs[grade]['corr max um'][i]:
                this_grade_valid = False
            if max(corr_rms) > grade_specs[grade]['corr rms um'][i]:
                this_grade_valid = False
        if d[pos_id]['has extended gearbox'] and not(grade_specs[grade]['has extended gearbox']):
            this_grade_valid = False
        if not(d[pos_id]['has extended gearbox']) and grade_specs[grade]['has extended gearbox']:
            this_grade_valid = False
        if this_grade_valid:
            d[pos_id]['grade'] = grade
            break

# write report
timestamp_str = pc.timestamp_str_now()
filename_timestamp_str = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()
report_file = tkinter.filedialog.asksaveasfilename(title='Save grade report as...',initialdir=pc.all_logs_directory,initialfile=filename_timestamp_str + '_positioner_grades_report.csv',filetypes=filetypes)
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
        writer.writerow(['correction moves threshold at ' + format(grading_threshold,'.1f') + ' um'])
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
        writer.writerow(['','pos_id','grade'])
        for pos_id in pos_ids:
            writer.writerow(['', pos_id, d[pos_id]['grade']])