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
grade_specs['A'] = {'blind max um' : [ 100],
                    'blind max %'  : [1.00],
                    'corr max um'  : [  12],
                    'corr max %'   : [1.00],
                    'corr rms um'  : [   5],
                    'corr rms %'   : [1.00],
                    'failure current'      : 80,
                    'has extended gearbox' : False}
grade_specs['B'] = {'blind max um' : [ 100],
                    'blind max %'  : [1.00],
                    'corr max um'  : [  12,   30],
                    'corr max %'   : [0.95, 0.05],
                    'corr rms um'  : [   5],
                    'corr rms %'   : [0.95],
                    'failure current'      : 100,
                    'has extended gearbox' : False}
grade_specs['C'] =  {'blind max um' : [ 100],
                     'blind max %'  : [0.95],
                     'corr max um'  : [  12,   50],
                     'corr max %'   : [0.95, 0.05],
                     'corr rms um'  : [   5],
                     'corr rms %'   : [0.95],
                     'failure current'      : 100,
                     'has extended gearbox' : False}
grade_specs['D'] = grade_specs['B']
grade_specs['D']['has extended gearbox'] = True
grade_specs['E'] = grade_specs['C']
grade_specs['E']['has extended gearbox'] = True
fail_grade = 'F'

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

# write report
gui_root = tkinter.Tk()
report_file = tkinter.filedialog.asksaveasfilename(title='Save grade report as...',initialdir=pc.all_logs_directory,initialfile=pc.timestamp_str_now() + '_positioner_grades_report.csv',filetypes=filetypes)
if not(report_file):
    tkinter.messagebox.showwarning(title='No report saved.',message='No grade report was saved to disk.')
gui_root.withdraw()
if report_file:
    with open(report_file,'w',newline='') as csvfile:
        writer = csv.DictWriter(csvfile,fieldnames=['test1','test2'])
        writer.writeheader()
        writer.writerow({'test1':1,'test2':2})
        writer.writerow({'test1':10,'test2':100})