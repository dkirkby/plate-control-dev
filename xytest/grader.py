'''Use this application to grade positioners based on their xytest summary results.
'''
import os
import sys
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
	basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
	sys.path.append(os.path.abspath(basepath+'/petal/'))
else:
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
# c.f. DESI-2735 Fiber Positioner Grades
# the list specs refer to values at the stat_cuts specified in the summarizer
grade_specs = collections.OrderedDict()
grade_spec_headers = ['blind max um','corr max um','corr rms um','has extended gearbox']
grade_spec_err_keys = grade_spec_headers[0:2]
grading_threshold = summarizer.thresholds_um[0]
min_num_targets = 24 # a test is not considered valid without at least this many targets
num_moves_infant_mortality = 5000 # a start grade is not proven until after this many cycles on positioner
important_lifetimes = list(set([num_moves_infant_mortality, 0, 5000, 10000, 25000, 50000, 75000, 107000, 125000, 150000, 215000, np.inf]))
important_lifetimes.sort()

grade = 'A'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 100, 100]
grade_specs[grade]['corr max um']          = [  15,  15]
grade_specs[grade]['corr rms um']          = [   5,   5]
grade_specs[grade]['has extended gearbox'] = False

grade = 'B'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 250, 250]
grade_specs[grade]['corr max um']          = [  15,  25]
grade_specs[grade]['corr rms um']          = [   5,  10]
grade_specs[grade]['has extended gearbox'] = False

grade = 'C'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 250, 250]
grade_specs[grade]['corr max um']          = [  25,  50]
grade_specs[grade]['corr rms um']          = [  10,  20]
grade_specs[grade]['has extended gearbox'] = False

grade = 'D'
grade_specs[grade] = collections.OrderedDict().fromkeys(grade_spec_headers)
grade_specs[grade]['blind max um']         = [ 500, 500]
grade_specs[grade]['corr max um']          = [  25,  50]
grade_specs[grade]['corr rms um']          = [  10,  20]
grade_specs[grade]['has extended gearbox'] = False

regular_grades = list(grade_specs.keys())

for grade in ['A','B','C','D']:
	e_grade = 'E' + grade
	grade_specs[e_grade] = grade_specs[grade].copy()
	grade_specs[e_grade]['has extended gearbox'] = True

ext_grades = [key for key in grade_specs.keys() if key not in regular_grades]

fail_grade = 'F'
fail_grade_ext = 'EF'
insuff_data_grade = 'insuff data'
all_grades_regular = regular_grades + [fail_grade]
all_grades_ext = ext_grades + [fail_grade_ext]
all_grades = all_grades_regular + all_grades_ext # intentionally not including ignored in this

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
process_all_files = tkinter.messagebox.askyesno(title='Batch grade all files?',message='Yes  -->  Process all files in the ' + os.path.relpath(pc.dirs['xytest_summaries'], pc.POSITIONER_LOGS_PATH) + ' folder.\n\nNo -->  Process just some file(s) of your choice.')
if not(process_all_files):
	files = list(tkinter.filedialog.askopenfilenames(initialdir=pc.dirs['xytest_summaries'], filetypes=filetypes, title='Select summary file(s) to process.'))
else:
	files = os.listdir(pc.dirs['xytest_summaries'])
	files = [pc.dirs['xytest_summaries'] + file for file in files]
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
motor_types_file = os.path.join(pc.POSITIONER_LOGS_PATH, 'as-built_motor_types.csv')
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
else:
	for posid in d.keys():
		if d[posid]['has extended gearbox'] == 'unknown':
			d[posid]['has extended gearbox'] = False # assume non-extension in unknown cases (conservative representation of yields, since extended is generally worse-performing)

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
	if (None in d[posid]['curr cruise'] or None in d[posid]['curr creep']):
		d[posid]['curr cruise'] = 100 # assume max current, lacking data
		d[posid]['curr creep'] = 100 # assume max current, lacking data
for posid in pos_to_delete:
	del d[posid]
	del posids[posids.index(posid)]

# establish the type of fail grade (non-extension vs extension)
for posid in d.keys():
	if d[posid]['has extended gearbox']:
		d[posid]['fail grade label'] = fail_grade_ext
	else:
		d[posid]['fail grade label'] = fail_grade

# gather up all grades passed for each test loop for each positioner
for posid in d.keys():
	d[posid]['row grade'] = []
	for row in range(d[posid]['num rows']):
		passing_grades = set(regular_grades + [fail_grade]) # specifically use the non-extension criteria here, and will add on a prefix later if extension
		for grade in regular_grades:
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
			if failed_this_grade:
				passing_grades.remove(grade)
		this_grade = best(passing_grades)
		if not(ignore_gearbox) and d[posid]['has extended gearbox']:
			this_grade = 'E' + this_grade
		d[posid]['row grade'].append(this_grade)

# determine the starting and finishing grades for each positioner
start_grade_min_current = 100
final_grade_min_current = start_grade_min_current
for posid in d.keys():
	d[posid]['start grade'] = None
	d[posid]['start grade date'] = None
	d[posid]['final grade'] = None
	d[posid]['final grade date'] = None
	for grade_label in ['start grade','final grade']:
		d[posid][grade_label] = None
		d[posid][grade_label + ' date'] = None
		if grade_label == 'start grade':
			iter_range = range(d[posid]['num rows'])
			min_current = start_grade_min_current
		else:
			iter_range = range(d[posid]['num rows']-1,-1,-1)
			min_current = final_grade_min_current
		for row in iter_range:
			if d[posid]['curr creep'][row] >= min_current and d[posid]['curr cruise'][row] >= min_current:
				d[posid][grade_label] = d[posid]['row grade'][row]
				d[posid][grade_label + ' date'] = dt.datetime.strptime(d[posid]['finish time'][row],pc.timestamp_format)
			if d[posid]['total move sequences at finish'][row] >= num_moves_infant_mortality and d[posid][grade_label] != None:
				break
		if d[posid][grade_label] == None:
			d[posid][grade_label] = insuff_data_grade

# determine at how many moves the positioner failed (if it did)
for posid in d.keys():
	highest_row_idx = d[posid]['num rows'] - 1
	final_row_idx = highest_row_idx
	d[posid]['num moves at failure'] = np.Inf
	while final_row_idx > 0 and d[posid]['row grade'][final_row_idx] == d[posid]['fail grade label']:
		if d[posid]['curr creep'][final_row_idx] >= final_grade_min_current and d[posid]['curr cruise'][final_row_idx] >= final_grade_min_current:
			d[posid]['num moves at failure'] = d[posid]['total move sequences at finish'][final_row_idx]
		final_row_idx -= 1
	if final_row_idx == 0 and d[posid]['final grade'] == d[posid]['fail grade label']:
		d[posid]['num moves passing'] = 0
	else:
		d[posid]['num moves passing'] = d[posid]['total move sequences at finish'][final_row_idx]
	if d[posid]['num moves at failure'] == np.Inf:
		d[posid]['num moves at failure'] = 'n/a' # for formatting in report

# count how many test rows prove this grade
for posid in d.keys():
	d[posid]['consecutive tests proving grade'] = []
	d[posid]['all tests proving grade'] = []
	streak_broken = False
	final_row_idx = d[posid]['num rows'] - 1
	for row in range(final_row_idx, -1, -1):
		if as_good_as(d[posid]['row grade'][row], d[posid]['start grade']):
			d[posid]['all tests proving grade'].append(row)

# find the minimum current at which this grade was proven
for posid in d.keys():
	creeps_proven = [d[posid]['curr creep'][row] for row in d[posid]['all tests proving grade']]
	cruise_proven = [d[posid]['curr cruise'][row] for row in d[posid]['all tests proving grade']]
	d[posid]['lowest curr creep proven'] = min(creeps_proven)
	d[posid]['lowest curr cruise proven'] = min(cruise_proven)

# gather up lifetime statistics
lifestats = collections.OrderedDict()
for key in ['ranges','num tested regular','num tested ext'] + ['Qty ' + grade for grade in all_grades] + ['% ' + grade for grade in all_grades]:
	lifestats[key] = []
for i in range(len(important_lifetimes)-1):
	low = important_lifetimes[i]
	high = important_lifetimes[i+1]
	lifestats['ranges'].append(str(low) + ' to ' + str(high) + ' moves')
	for has_ext in [False,True]:
		num_all_grades_this_bin = 0
		these_all_grades = all_grades_regular if not(has_ext) else all_grades_ext
		for grade in these_all_grades:
			num_this_grade_this_bin = 0
			for posid in d.keys():
				this_pos_all_grades_this_bin = [d[posid]['row grade'][row] for row in range(d[posid]['num rows']) if d[posid]['total move sequences at finish'][row] >= low and d[posid]['total move sequences at finish'][row] < high]
				if any(this_pos_all_grades_this_bin) and grade == this_pos_all_grades_this_bin[-1]:
					num_this_grade_this_bin += 1
					num_all_grades_this_bin += 1
			lifestats['Qty ' + grade].append(num_this_grade_this_bin)
		for grade in these_all_grades:
			num_this_grade_this_bin = lifestats['Qty ' + grade][-1]
			if num_this_grade_this_bin == 0:
				fraction_with_this_many_moves = 0 # avoids case of divide by zero
			else:
				fraction_with_this_many_moves = num_this_grade_this_bin / num_all_grades_this_bin
			lifestats['% ' + grade].append(fraction_with_this_many_moves)
		key = 'num tested regular' if not(has_ext) else 'num tested ext'
		lifestats[key].append(num_all_grades_this_bin)

# write report
timestamp_str = pc.timestamp_str_now()
filename_timestamp_str = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()
report_file = tkinter.filedialog.asksaveasfilename(title='Save grade report as...',initialdir=pc.POSITIONER_LOGS_PATH + os.path.sep + 'xytest_grades',initialfile=filename_timestamp_str + '_positioner_grades_report.csv',filetypes=filetypes)
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
		writer.writerow(['min moves burn-in infant mortality = ' + str(num_moves_infant_mortality)])
		writer.writerow(['','grade'] + grade_spec_headers)
		for key in grade_specs.keys():
			writer.writerow(['',key] + list(grade_specs[key].values()))
		writer.writerow(['',fail_grade + ' or ' + fail_grade_ext + ' ... does not meet any of the above grades.'])
		writer.writerow([''])
		for stage in ['final','start']:
			header_text = 'TOTALS FOR EACH GRADE:  '
			if stage == 'start':
				header_text += '** INITIAL (at burn-in >= ' + str(num_moves_infant_mortality) + ' moves) **'
			else:
				header_text += '** FINAL (latest values) **'
			writer.writerow([header_text])
			writer.writerow(['','grade', 'quantity', 'percent'])
			for has_ext in [False,True]:
				these_posids = [posid for posid in d.keys() if d[posid]['has extended gearbox'] == has_ext]
				these_all_grades = all_grades_regular if not(has_ext) else all_grades_ext
				num_insuff = len([posid for posid in these_posids if d[posid][stage + ' grade'] == insuff_data_grade])
				num_suff = len(these_posids) - num_insuff
				def percent(value):
					if value == 0 and num_suff == 0:
						frac = 0
					else:
						frac = value/num_suff*100
					return format(frac,'.1f')+'%'
				for key in these_all_grades:
					total_this_grade = len([posid for posid in these_posids if d[posid][stage + ' grade'] == key])
					writer.writerow(['',key,total_this_grade,percent(total_this_grade)])
				all_text = 'all non-extension' if not(has_ext) else 'all extension'
				writer.writerow(['',all_text,num_suff,percent(num_suff)])
				if num_insuff > 0:
					writer.writerow(['',insuff_data_grade,num_insuff])
				writer.writerow([''])
		writer.writerow(['LIFETIME STATISTICS:'])
		writer.writerow(['',''] + [r for r in lifestats['ranges']])
		for has_ext in [False,True]:
			label = 'regular' if not(has_ext) else 'ext'
			writer.writerow(['','num ' + label + ' pos with test results in this range'] + [str(n) for n in lifestats['num tested ' + label]])
			for prefix in ['Qty ','% ']:
				these_all_grades = all_grades_regular if not(has_ext) else all_grades_ext
				for grade in these_all_grades:
					key = prefix + grade
					if any(lifestats[key]):
						if '%' in prefix:
							val_strs = [format(val*100,'.1f')+'%' for val in lifestats[key]]
						else:
							val_strs = [str(val) for val in lifestats[key]]
						writer.writerow(['',key] + val_strs)
			writer.writerow([''])
		writer.writerow(['INDIVIDUAL POSITIONER GRADES:'])
		writer.writerow(['','posid','final grade','initial grade'] + proven_keys + ['num moves passing','num moves at failure','num manually-ignored bad data rows'])
		posids_sorted_by_grade = []
		for grade in all_grades + [insuff_data_grade]:
			for posid in d.keys():
				if d[posid]['final grade'] == grade:
					posids_sorted_by_grade.append(posid)
		for posid in posids_sorted_by_grade:
			writer.writerow(['', posid, d[posid]['final grade'], d[posid]['start grade']] + [d[posid][key] for key in proven_keys + ['num moves passing','num moves at failure','num manually ignored rows']])
		writer.writerow([''])
		writer.writerow(['INDIVIDUAL TEST LOOP GRADES:'])
		writer.writerow(['','posid','finish time','total move sequences','grade'])
		for posid in d.keys():
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
			  1: 'initial grades vs test dates (cumulative)',
			  2: 'present grades vs latest test dates (cumulative)',
			  3: 'grade vs num moves (qty)',
			  4: 'grade vs num moves (%)',
			  5: 'all plots, then quit'}
plot_select_text = ''.join(['Enter what type of plots to save.\n\n'] + [str(key) + ': ' + plot_types[key] + '\n' for key in plot_types.keys()])
extra_title_text = {0: '',
					1: ' (after burn-in testing only)\n',
					2: ' (including lifetime or other extra testing / wear)\n',
					3: '',
					4: '',
					5: ''}
while keep_asking:
	user_response = tkinter.simpledialog.askinteger(title='Select plot type', prompt=plot_select_text, minvalue=min(plot_types.keys()), maxvalue=max(plot_types.keys()))
	if user_response == 5:
		responses = [1,2,3,4]
		plotnames = set()
		keep_asking = False
	else:
		responses = [user_response]
	for response in responses:
		if response == 0 or response == None:
			keep_asking = False
		else:
			plt.ioff()
			fig = plt.figure(figsize=(10, 7))
			num_pos_in_each_grade = collections.OrderedDict([(grade,[0]) for grade in all_grades])
			if response == 1 or response == 2:
				sort_alldata_by('date tested')
				for i in range(len(alldata['date tested'])):
					posid = alldata['posid'][i]
					for grade in all_grades:
						num_pos_in_each_grade[grade].append(num_pos_in_each_grade[grade][-1])
					if response == 1:
						compare_date = d[posid]['start grade date']
						this_grade = d[posid]['start grade']
					else:
						compare_date = d[posid]['final grade date']
						this_grade = d[posid]['final grade']
					if alldata['date tested'][i] == compare_date:
						num_pos_in_each_grade[this_grade][-1] += 1
				for grade in all_grades:
					if any(num_pos_in_each_grade[grade]):
						color = next(plt.gca()._get_lines.prop_cycler)['color']
						del num_pos_in_each_grade[grade][0] # remove those pesky initial rows filled with 0
						label = 'Grade ' + str(grade) + ' (' + str(num_pos_in_each_grade[grade][-1]) + ')'
						plt.plot_date(alldata['date tested'], num_pos_in_each_grade[grade], fmt='-', color=color, label=label)
						plt.plot_date(alldata['date tested'][-1], num_pos_in_each_grade[grade][-1], fmt='o', color=color)
				plt.gca().autoscale_view()
				plt.xlim(xmax=plt.xlim()[1] + 1.0) # add a little padding to the picture
				plt.xlabel('date tested')
				plt.ylabel('cumulative positioners')
				plt.grid('on')
			elif response == 3 or response == 4:
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
				if response == 4:
					divisors = [1e-10]*len(num_moves) # small number avoids divide-by-zero later
					for grade in all_grades:
						divisors = [divisors[i] + num_pos_in_each_grade[grade][i] for i in range(len(num_moves))]
				for grade in all_grades:
					if any(num_pos_in_each_grade[grade]):
						if response == 3:
							y_vals = num_pos_in_each_grade[grade]
							ylabel_prefix = 'number'
						else:
							y_vals = [num_pos_in_each_grade[grade][i]/divisors[i]*100 for i in range(len(divisors))]
							ylabel_prefix = '%'
						plt.plot(num_moves,y_vals,label='Grade ' + str(grade))
				plt.xlabel('lifetime moves')
				plt.ylabel(ylabel_prefix + ' of positioners')
				if response == 4:
					from matplotlib.ticker import FormatStrFormatter
					plt.gca().yaxis.set_major_formatter(FormatStrFormatter('%d%%'))
				plt.grid('on')
			plotname = os.path.splitext(report_file)[0] + '_plot' + str(response) + '.pdf'
			plt.title(' ' + plot_types[response].upper() + '\n ' + extra_title_text[response] + ' ' + os.path.basename(report_file), loc='left')
			plt.legend(loc='best')
			plt.savefig(plotname)
			plt.close(fig)
			if user_response == 5:
				plotnames.add(plotname)
			else:
				tkinter.messagebox.showinfo(title='Plot saved',message='Plot of ' + plot_types[response] + ' saved to:\n\n' + plotname)
	if user_response == 5:
		tkinter.messagebox.showinfo(title='Plot saved',message='Plots saved to:\n' + ''.join(['\n' + s for s in plotnames]))
gui_root.withdraw()
