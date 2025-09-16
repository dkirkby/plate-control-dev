import os
import sys
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
	basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
	sys.path.append(os.path.abspath(basepath+'/petal/'))
else:
	sys.path.append(os.path.abspath('../petal/'))

import posconstants as pc
import numpy as np
import collections
import csv
import datetime
import posstate

auto_init_data_keys = ['test loop data file',
					   'num pts calib T',
					   'num pts calib P',
					   'calib mode',
					   'ranges remeasured',
					   'xytest log file',
					   'code version']

manual_ignore_key = 'bad data ignore this row (enter your initials and justification)'

user_data_keys = ['test operator',
				  'test station',
				  'supply voltage',
				  'temperature (C)',
				  'relative humidity',
				  'operator notes']

init_data_keys = auto_init_data_keys + user_data_keys

meas_suffix = ' (meas)'
used_suffix = ' (used)'

# reporting constants
thresholds_um = [3.0,5.0] # [um] candidate 2D error thresholds to calculate where in real operation on the mountain we would have stopped correcting
stat_cuts = [0.95,1.00] # statistical cutoffs for best moves at which to report


class Summarizer(object):
	'''Provides common functions for summarizing a fiber positioner's performance data.
	When run as an application, summarizer.py provides a utility for making summary files out of
	existing movedata log files.
	'''

	def __init__(self, state, init_data, directory=''):
		'''INPUTS:
			init_data   ... dictionary, should contain values for all the keys given in the list init_data_keys
			state       ... PosState object for the positioner this summarizer will refer to
			directory   ... (optional) override the standard directory for reading / writing summary files

		Make sure to also update_loop_inits() at the beginning of any new xytest loop.
		'''
		self.state = state
		self.row_template = collections.OrderedDict()
		self.row_template['start time']                     = ''
		self.row_template['finish time']                    = ''
		self.row_template['curr cruise']                    = 0
		self.row_template['curr creep']                     = 0
		self.row_template['num targets']                    = 0     # number of targets tested in this loop
		self.err_keys = Summarizer.make_err_keys()
		for key in self.err_keys:
			self.row_template[key] = None
		self.row_template['total move sequences at finish'] = None
		self.row_template['total limit seeks T at finish']  = None
		self.row_template['total limit seeks P at finish']  = None
		self.row_template['pos log files']                  = [self.state.log_basename]
		for suffix in [used_suffix,meas_suffix]:
			for calib_key in pc.nominals.keys():
				self.row_template[calib_key + suffix] = None
		for key in init_data_keys:
			if 'file' in key:
				init_data[key] = os.path.basename(init_data[key])
			self.row_template[key] = init_data[key]
		self.row_template[manual_ignore_key] = ''
		self.basename = self.state._val['POS_ID'] + '_summary.csv'
		if not(directory):
			directory = pc.dirs['xytest_summaries']
		if not directory[-1] == os.path.sep:
			directory += os.path.sep
		self.filename = directory + self.basename

		# checking whether need to start a new file because none exist yet
		if not(os.path.isfile(self.filename)):
			with open(self.filename, 'w', newline='') as csvfile:
				csv.writer(csvfile).writerow(list(self.row_template.keys())) # write header row

		# deal with case where fieldnames have changed since the last time the file was used
		with open(self.filename, 'r', newline='') as csvfile:
			reader = csv.DictReader(csvfile)
			old_fieldnames = reader.fieldnames
			rows = []
			for row in reader:
				rows.append(row)
		for key in self.row_template.keys():
			if key not in old_fieldnames:
				for row in rows:
					if key == manual_ignore_key:
						row[key] = ''
					else:
						row[key] = 'unknown'
		with open(self.filename, 'w', newline='') as csvfile:
			writer = csv.DictWriter(csvfile,fieldnames=list(self.row_template.keys()))
			writer.writeheader()
			for row in rows:
				writer.writerow(row)

	def update_loop_inits(self, loop_data_file, n_pts_calib_T, n_pts_calib_P, calib_mode, ranges_were_remeasured):
		'''At the start of a new loop within an xytest, always run this method
		to update values in the row logging function.

		It will initialize some values for the loop, as well as tell the code that
		the next call to write_row() should append a new row, rather than overwriting
		the most recent one.

		The inputs to this method are those particular data which we cannot
		otherwise infer from positioner state, or the internal clock, etc.
		'''
		self.row_template['test loop data file'] = os.path.basename(loop_data_file)
		self.row_template['num pts calib T']     = n_pts_calib_T
		self.row_template['num pts calib P']     = n_pts_calib_P
		self.row_template['calib mode']          = calib_mode
		self.row_template['start time']          = pc.timestamp_str_now()
		self.row_template['curr cruise']         = self.state._val['CURR_CRUISE']
		self.row_template['curr creep']          = self.state._val['CURR_CREEP']
		self.row_template['ranges remeasured']   = ranges_were_remeasured
		self.next_row_is_new = True

	def update_loop_calibs(self, suffix='', params=list(pc.nominals.keys())):
		'''Update the row template with the current calibration values, gathered up
		from the positioner state file.

		suffix argument is used for example to distinguish between values that were
		only measured vs those that were actually used in the test.

		params argument is used to to restrict which parameters are getting upated.
		'''
		for calib_key in params:
			self.row_template[calib_key + suffix] = self.state._val[calib_key]

	def write_row(self, err_data_mm, autogather=True):
		'''Makes a row of values and writes them to the csv file.

		See threshold_and_summarize() method for comments on err_data.

		The autogather flag says whether to automatically gather certain data values from the
		most current positioner state data.
		'''
		row = self.row_template.copy()
		for threshold in thresholds_um:
			err_summary = Summarizer.threshold_and_summarize(err_data_mm,threshold)
			for key in err_summary.keys():
				if key in self.err_keys:
					row[key] = format(err_summary[key], '.1f')
		row['num targets'] = len(err_summary['all blind errs (um)'])
		if autogather:
			if self.state.log_basename not in self.row_template['pos log files']:
				self.row_template['pos log files'].append(self.state.log_basename)
			row['finish time'] = pc.timestamp_str_now()
			row['total move sequences at finish'] = self.state._val['TOTAL_MOVE_SEQUENCES']
			row['total limit seeks T at finish'] = self.state._val['TOTAL_LIMIT_SEEKS_T']
			row['total limit seeks P at finish'] = self.state._val['TOTAL_LIMIT_SEEKS_P']
		with open(self.filename,'r', newline='') as csvfile:
			rows = list(csv.reader(csvfile))
		row_vals = list(row.values())
		if self.next_row_is_new:
			rows.append(row_vals)
			self.next_row_is_new = False
		else:
			rows[-1] = list(row_vals)
		with open(self.filename, 'w', newline='') as csvfile:
			csv.writer(csvfile).writerows(rows)

	@staticmethod
	def threshold_and_summarize(err_data_mm, threshold_um):
		'''Summarizes the error data for a single positioner, applying thresholds
		to determine which correction submoves are the ones at which in practice
		(on the mountain) we would stop correcting.

		INPUTS:
			err_data      ... list of lists, where the first index is the submove number,
							  and then selecting that gives you the list of all error data
							  for that submove. The units must be mm.

			threshold_um  ... the first submove encountered which has an error value less than
							  or equal to threshold is considered the point at which a robot would
							  (in practice on the mountain) be held there and do no more corrections.
							  The units must be um.

		OUTPUTS:
			err_summary   ... dictionary, with keys:
								  'blind max (um)' + statcut_suffix(stat_cut)
								  'corr max (um)'  + err_suffix(stat_cut,threshold_um)
								  'corr rms (um)'  + err_suffix(stat_cut,threshold_um)
								  'mean num corr'  + err_suffix(stat_cut,threshold_um)
								  'max num corr'   + err_suffix(stat_cut,threshold_um)
								  'all blind errs (um)' ... numpy array of all the blind move error values
								  'all corr errs (um)'  ... numpy array of all the corrected move error values (threshold is applied)
								  'all corr nums'       ... numpy array of which how many correction moves it took for each target to reach the threshold (or end of submove data)
		'''
		err_data = []
		for submove_data in err_data_mm:
			err_data.append([x * pc.um_per_mm for x in submove_data])
		err_summary = {}
		n = len(err_data[0])
		err_summary['all corr errs (um)'] = [np.inf]*n
		err_summary['all corr nums'] = [0]*n
		has_hit_threshold = [False]*n
		for submove in range(len(err_data)):
			for i in range(n):
				this_err = err_data[submove][i]
				if not(has_hit_threshold[i]):
					err_summary['all corr nums'][i] = submove
					err_summary['all corr errs (um)'][i] = this_err
					if this_err <= threshold_um:
						has_hit_threshold[i] = True
		err_summary['all blind errs (um)'] = np.sort(err_data[0])
		corr_sort_idxs = np.argsort(err_summary['all corr errs (um)'])
		err_summary['all corr errs (um)'] = np.array(err_summary['all corr errs (um)'])[corr_sort_idxs]
		err_summary['all corr nums'] = np.array(err_summary['all corr nums'])[corr_sort_idxs]
		for cut in stat_cuts:
			if cut >= 1:
				idxs = list(range(n))
			else:
				idxs = list(range(int(np.ceil(cut*n))))
			suffix1 = Summarizer.statcut_suffix(cut)
			err_summary['blind max (um)' + suffix1] = max(err_summary['all blind errs (um)'][idxs])
			suffix2 = Summarizer.err_suffix(cut,threshold_um)
			err_summary['corr max (um)' + suffix2] = max(err_summary['all corr errs (um)'][idxs])
			err_summary['corr rms (um)' + suffix2] = np.sqrt(np.sum(np.power(err_summary['all corr errs (um)'][idxs],2))/n)
			err_summary['mean num corr' + suffix2] = np.mean(err_summary['all corr nums'][idxs])
			err_summary['max num corr'  + suffix2] = max(err_summary['all corr nums'][idxs])
		return err_summary

	@staticmethod
	def err_suffix(stat_cut, threshold):
		'''For consistent internal generation of certain keys.'''
		return Summarizer.statcut_suffix(stat_cut) + ' with ' + str(threshold) + ' um threshold'

	@staticmethod
	def statcut_suffix(stat_cut):
		'''For consistent internal generation of certain keys.'''
		if stat_cut == 1:
			return ' all targets'
		else:
			return ' best ' + format(stat_cut*100,'g') + '%'

	@staticmethod
	def make_err_keys():
		'''Return list of valid keys for the error data.'''
		err_keys = []
		for cut in stat_cuts:
			suffix1 = Summarizer.statcut_suffix(cut)
			err_keys.append('blind max (um)' + suffix1)    # max error on the blind move 0
			for threshold in thresholds_um:
				suffix2 = Summarizer.err_suffix(cut,threshold)
				err_keys.append('corr max (um)' + suffix2) # max error after correction moves (threshold is applied)
				err_keys.append('corr rms (um)' + suffix2) # rms error after correction moves (threshold is applied)
				err_keys.append('mean num corr' + suffix2) # avg number of correction moves it took to reach either threshold or end of submove data
				err_keys.append('max num corr'  + suffix2) # max number of correction moves it took to reach either threshold or end of submove data
		return err_keys

if __name__=="__main__":
	import tkinter
	import tkinter.messagebox
	import tkinter.filedialog

	# get the files list
	filetypes = (('Comma-separated Values','*movedata.csv'),('All Files','*'))
	gui_root = tkinter.Tk()
	process_all_files = tkinter.messagebox.askyesno(title='Batch summarize directory?',message='Yes  -->  Process all files in the folder of your choice.\n\nNo -->  Process just one or multiple file(s) of your choice.')
	start_dir = pc.POSITIONER_LOGS_PATH + os.path.sep + '..'
	if not(process_all_files):
		files = list(tkinter.filedialog.askopenfilenames(initialdir=start_dir, filetypes=filetypes, title='Select movedata file(s) to process.'))
	else:
		directory = tkinter.filedialog.askdirectory(initialdir=start_dir,title='Select directory.')
		files = os.listdir(directory)
		files = [directory + os.path.sep + file for file in files]
	gui_root.withdraw()
	files = [file for file in files if 'movedata.csv' in file]
	files.sort()

	# gather the data by file
	ask_ignore_files_with_logsuffix = True
	ignore_files_with_logsuffix = False
	d = collections.OrderedDict() # store the data here
	for file in files:
		with open(file,'r',newline='') as csvfile:
			reader = csv.DictReader(csvfile)
			err_xy_fields = [field for field in reader.fieldnames if 'err_xy' in field]
			if err_xy_fields:
				namesplit = os.path.basename(file).split('_')
				posid = namesplit[0]
				logsuffix = ''.join(namesplit[3:-1])
				if logsuffix and ask_ignore_files_with_logsuffix:
					gui_root = tkinter.Tk()
					ignore_files_with_logsuffix = tkinter.messagebox.askyesno(title='Ignore if log suffix?',message='Ignore any data files that have a log suffix?\n(Historically these are often odd test cases like playing with parameters or running in thermal chamber.)')
					gui_root.withdraw()
					ask_ignore_files_with_logsuffix = False
				d[file] = {}
				d[file]['test loop data file'] = os.path.basename(file)
				err_data = [[] for field in err_xy_fields]
				timestamps = []
				cycles = []
				pos_logs = set()
				n_rows_read = 0
				for row in reader:
					for i in range(len(err_xy_fields)):
						err_data[i].append(float(row[err_xy_fields[i]]))
					if 'timestamp' in reader.fieldnames:
						timestamp = row['timestamp']
						if '_' in timestamp: # convert from occasional usage of filename format inside some of the data logs
							timestamp = datetime.datetime.strptime(timestamp,pc.filename_timestamp_format)
							timestamp = datetime.datetime.strftime(timestamp,pc.timestamp_format)
						timestamps.append(timestamp)
					if 'cycle' in reader.fieldnames:
						cycles.append(row['cycle'])
					if 'move_log' in reader.fieldnames:
						pos_logs.add(row['move_log'])
					n_rows_read += 1
				if logsuffix and ignore_files_with_logsuffix:
					ignore_due_to_logsuffix = True
				else:
					ignore_due_to_logsuffix = False
				if n_rows_read > 0 and not(ignore_due_to_logsuffix):
					if timestamps:
						d[file]['start time'] = timestamps[0]
						d[file]['finish time'] = timestamps[-1]
					else:
						filename_timestamp = namesplit[1] + '_' + namesplit[2]
						timestamp = datetime.datetime.strptime(filename_timestamp,pc.filename_timestamp_format)
						timestamp = datetime.datetime.strftime(timestamp,pc.timestamp_format)
						d[file]['start time'] = timestamp
					if cycles:
						d[file]['total move sequences at finish'] = cycles[-1]
					if logsuffix and not(ignore_files_with_logsuffix):
						d[file]['operator notes'] = [logsuffix]
					if pos_logs:
						d[file]['pos log files'] = list(pos_logs)
					d[file]['err_data'] = err_data
					d[file]['pos_id'] = posid
				else:
					del d[file]

	# find out where the user wants to save outputs
	gui_root = tkinter.Tk()
	if d:
		save_directory = tkinter.filedialog.askdirectory(initialdir=start_dir,title='Folder to save outputs?')
		existing_files = os.listdir(save_directory)
		ask_overwrite = True
		should_overwrite = False
		all_posids = [d[file]['pos_id'] for file in d.keys()]
		for file in existing_files:
			for posid in all_posids:
				if posid in file:
					if ask_overwrite:
						should_overwrite = tkinter.messagebox.askyesnocancel('Overwrite summaries?',message='Some summary files already exist in that directory. Should we overwrite them?\n\nYes --> overwrite completely\nNo --> attempt to merge data\nCancel --> Do nothing')
						ask_overwrite = False
					if should_overwrite:
						full_path = save_directory + os.path.sep + file
						os.remove(full_path)
					break
		if should_overwrite == None:
			d = {}
	if not(d):
		tkinter.messagebox.showwarning(title='No files summarized.',message='No movedata files were summarized.')
	gui_root.withdraw()

	# run the summarizer on all the file data
	for file in d.keys():
		state = posstate.PosState(d[file]['pos_id'])
		init_data = d[file].copy()
		for key in init_data_keys:
			if key not in init_data.keys():
				init_data[key] = 'unknown'
			if key == manual_ignore_key:
				init_data[key] = ''
		summ = Summarizer(state,init_data,save_directory)
		with open(summ.filename,'r',newline='') as csvfile:
			reader = csv.DictReader(csvfile)
			already_summarized = set()
			for row in reader:
				already_summarized.add(row['test loop data file'])
		file_basename = os.path.basename(file)
		if file_basename not in already_summarized:
			summ.next_row_is_new = True
			default_summary_row = {} # will search below if there is an existing default summary file from which to pluck any additional data
			if summ.basename in os.listdir(pc.dirs['xytest_summaries']):
				default_summary_file = pc.dirs['xytest_summaries'] + summ.basename
				with open(default_summary_file,'r',newline='') as csvfile:
					reader = csv.DictReader(csvfile)
					if 'test loop data file' in reader.fieldnames:
						for row in reader:
							if row['test loop data file'] == file_basename:
								default_summary_row = row
								break
			for key in summ.row_template.keys():
				if key not in d[file].keys():
					if key in default_summary_row.keys():
						summ.row_template[key] = default_summary_row[key]
					else:
						summ.row_template[key] = 'unknown'
				else:
					summ.row_template[key] = d[file][key]
			summ.write_row(d[file]['err_data'],autogather=False)
