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

# grading parameters
# c.f. DESI-XXXX Fiber Positioner Grades
grade_specs = collections.OrderedDict()
grade_spec_headers = ['blind max um','blind max %','corr max um','corr max %','corr rms um','corr rms %','failure current','has extended gearbox']

grade = 'A'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100]
grade_specs[grade]['blind max %']          = [1.00]
grade_specs[grade]['corr max um']          = [  12]
grade_specs[grade]['corr max %']           = [1.00]
grade_specs[grade]['corr rms um']          = [   5]
grade_specs[grade]['corr rms %']           = [1.00]
grade_specs[grade]['failure current']      = 80
grade_specs[grade]['has extended gearbox'] = False

grade = 'B'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100]
grade_specs[grade]['blind max %']          = [1.00]
grade_specs[grade]['corr max um']          = [  12,   30]
grade_specs[grade]['corr max %']           = [0.95, 0.05]
grade_specs[grade]['corr rms um']          = [   5]
grade_specs[grade]['corr rms %']           = [0.95]
grade_specs[grade]['failure current']      = 100
grade_specs[grade]['has extended gearbox'] = False

grade = 'C'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100]
grade_specs[grade]['blind max %']          = [0.95]
grade_specs[grade]['corr max um']          = [  12,   50]
grade_specs[grade]['corr max %']           = [0.95, 0.05]
grade_specs[grade]['corr rms um']          = [   5]
grade_specs[grade]['corr rms %']           = [0.95]
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
process_all_files = tkinter.messagebox.askyesno(title='Batch grade all files?',message='Yes  -->  Process all files in the ' + os.path.relpath(pc.xytest_summaries_directory,pc.all_logs_directory) + ' folder.\n\nNo -->  Process just one file of your choice.')
if not(process_all_files):
    files = [tkinter.filedialog.askopenfilename(initialdir=pc.xytest_summaries_directory, filetypes=filetypes, title='Select summary file to proces.')]
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
            
# read data and grade positioners
for pos_id in d.keys():
    d[pos_id]['grade'] = fail_grade

# write report
timestamp_str = pc.timestamp_str_now()
gui_root = tkinter.Tk()
report_file = tkinter.filedialog.asksaveasfilename(title='Save grade report as...',initialdir=pc.all_logs_directory,initialfile=timestamp_str + '_positioner_grades_report.csv',filetypes=filetypes)
if not(report_file):
    tkinter.messagebox.showwarning(title='No report saved.',message='No grade report was saved to disk.')
gui_root.withdraw()
if report_file:
    with open(report_file,'w',newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['REPORT DATE:'])
        writer.writerow([timestamp_str])
        writer.writerow([''])
        writer.writerow(['SPECIFICATIONS APPLIED IN THIS REPORT:'])
        writer.writerow(['grade'] + grade_spec_headers)
        for key in grade_specs.keys():
            writer.writerow([key] + list(grade_specs[key].values()))
        writer.writerow([fail_grade + ' ... does not meet any of the above grades.'])
        writer.writerow([''])
        writer.writerow(['TOTALS FOR EACH GRADE:'])
        writer.writerow(['grade', 'quantity', 'percent'])
        def percent(value):
            return format(value/len(d)*100,'.1f')+'%'
        for key in all_grades:
            total_this_grade = len([pos_id for pos_id in d.keys() if d[pos_id]['grade'] == key])
            writer.writerow([key,total_this_grade,percent(total_this_grade)])
        writer.writerow(['all',len(d),percent(len(d))])
        writer.writerow([''])
        writer.writerow(['INDIVIDUAL POSITIONER GRADES:'])
        writer.writerow(['pos_id','grade'])
        for pos_id in pos_ids:
            writer.writerow([pos_id,d[pos_id]['grade']])