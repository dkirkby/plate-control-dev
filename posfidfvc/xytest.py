# module xyaccuracy_test.py
# created December 2016 based on xy_accuracy_test.py
#
# Change log:
# 
# 
# 2017-01-31(MS): moved instantiation of fvc to __init__
# 2017-01-31(MS): FVC type is now an entry in config file


import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import fvchandler
import petal
import posmovemeasure
import posconstants as pc
import datetime
import numpy as np
import time
import pos_xytest_plot
import um_test_report as test_report
import traceback
import logging
import configobj
import shutil


class AccuracyTest(object):

    def __init__(self,configfile='accuracy_test.conf'): 
        self.config = configobj.ConfigObj(configfile,unrepr=True)

        fvc_type = self.config['local']['fvc_type']
        self.fvc = fvchandler.FVCHandler(fvc_type)
        if self.config['local']['platemaker_type'] == 'NONE':
            self.fvc.rotation = self.config['local']['rotation']  # deg
            self.fvc.scale =  self.config['local']['scale'] # mm/pixel
        pos_ids = self.config['positioners']['pos_ids']
        pos_notes = self.config['positioners']['notes'] # notes for report to add about positioner (reported with positioner in same slot as pos_ids list)
        while len(pos_notes) < len(pos_ids):
            pos_notes.append('')
        fid_ids = self.config['fiducials']['fid_ids']
        petal_id = self.config['petals']['petal_id'] # note that single petal is not general. below I treat this as a 
        for ptl_id in [petal_id]: # this elaboration of a for loop is just a placeholder for future implementations, where we would have a list of multiple petals being handled by posmovemeasure 
            petals += petal.Petal(ptl_id, pos_ids, fid_ids)
        self.m = posmovemeasure.PosMoveMeasure(ptl_ids,self.fvc)
        
        self.ptl.anticollision_default = self.config['petal']['anticollision']
        
        self.should_log = False
        self.should_auto_commit_logs = self.config['mode']['should_auto_commit_logs']
        self.should_email = self.config['mode']['should_email']
        self.should_report = self.config['mode']['should_report']
        self.email_list = self.config['email']['email_list'] #full or limited
        self.log_suffix = self.config['mode']['log_suffix']

    def enable_logging(self,logfile=''):        
        now=datetime.datetime.now().strftime("%y%m%d.%H%M%S")
        if not logfile: logfile = 'logs/xyaccuracy_test_'+now+'.log'
        logging.basicConfig(filename=logfile,format='%(asctime)s %(message)s',level=logging.INFO)        # ToDo: read logging level from config file
        self.should_log=True        

    def run_xyaccuracy_test(self, loop_number=0):
        # grab config settings for this test
        self.n_pts_across_grid = self.config['sequence']['n_pts_across_grid'][loop_number]
        self.n_points_calib_T = self.config['sequence']['n_points_calib_T'][loop_number]
        self.n_points_calib_P = self.config['sequence']['n_points_calib_P'][loop_number]
        self.num_corr_max = self.config['sequence']['num_corr_max'][loop_number]

        # start timer on the whole script
        script_start_time = time.time()
        
        # JOE TEMPORARY COMMENT: NOTE THAT WE WILL ENHANCE THIS IN THE NEAR FUTURE ONCE
        # WE HAVE INDIVIDUAL CONFIG FILES FOR FIDUCIALS IMPLEMENTED (SIMILAR TO POSITIONERS)
        # self.m.n_fiducial_dots = ptl.n_fiducial_dots + self.config['calib']['n_other_dots']
        self.m.n_fiducial_dots = self.config['calib']['n_other_dots'] # number of fiducial centroids the FVC should expect

        email_list = self.email_list #self.config['email']['email_list'] #full or limited

        # log file setup
        log_directory = pc.test_logs_directory
        os.makedirs(log_directory, exist_ok=True)
        log_suffix = self.log_suffix #self.config['mode']['log_suffix'] # string gets appended to filenames -- useful for user to identify particular tests
        log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
        log_timestamp = pc.timestamp_str_now()
        def path_prefix(pos_id):
            return log_directory + os.path.sep + pos_id + '_' + log_timestamp + log_suffix
        def move_log_name(pos_id):
            return path_prefix(pos_id) + '_movedata.csv'
        def summary_log_name(pos_id):
            return path_prefix(pos_id) + '_summary.csv'
        def summary_plot_name(pos_id):
            return path_prefix(pos_id) + '_xyplot'    
        def cal_prior_name(pos_id):
            return path_prefix(pos_id) + '_cal_prior.conf'    
        def cal_after_name(pos_id):
            return path_prefix(pos_id) + '_cal_after.conf' 


        # save a copy of the unit_*.conf file prior to calibration    
        for pos_id in pos_ids:
            try:
                #cmd1=pc.pos_settings_directory+'/unit_'+pos_id+'.conf'
                #cmd2=cal_prior_name(pos_id)
                #print(cmd1, cmd2)
                shutil.copy2(pc.pos_settings_directory+'/unit_'+pos_id+'.conf',cal_prior_name(pos_id))
            except IOError as e:
                print ("Error copying unit_"+pos_id+" file:",str(e))

        # test grid configuration (local to any positioner, centered on it)
        # this will get copied and transformed to each particular positioner's location below
        grid_max_radius = self.config['grid']['grid_max_radius'] # mm
        grid_min_radius =  self.config['grid']['grid_min_radius'] # mm
        line = np.linspace(-grid_max_radius,grid_max_radius,self.n_pts_across_grid)
        local_targets = [[x,y] for x in line for y in line]
        for i in range(len(local_targets)-1,-1,-1): # traverse list from end backward
            r = (local_targets[i][0]**2 + local_targets[i][1]**2)**0.5
            if r < grid_min_radius or r > grid_max_radius: local_targets.pop(i)

        try:
           
            self.m.n_points_full_calib_T = self.n_points_calib_T
            self.m.n_points_full_calib_P = self.n_points_calib_P            
            self.m.calibrate(pos_ids='all', mode='full', save_file_dir=log_directory, save_file_timestamp=log_timestamp)
            
            submove_idxs = [i for i in range(self.num_corr_max+1)]
        
            # write headers for move data log files
            move_log_header = 'timestamp,cycle,target_x,target_y'
            submove_fields = ['meas_obsXY','errXY','err2D','posTP']
            for i in submove_idxs: move_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
            for i in submove_idxs: move_log_header += ',err_x'  + str(i) + ',err_y' + str(i)
            for i in submove_idxs: move_log_header += ',err_xy' + str(i)
            for i in submove_idxs: move_log_header += ',pos_t'  + str(i) + ',pos_p' + str(i)
            move_log_header += '\n'
            for pos_id in pos_ids:
                file = open(move_log_name(pos_id),'w')
                file.write(move_log_header)
                file.close()
        
            # transform test grid to each positioner's global position, and create all the move request dictionaries
            all_targets = []
            for local_target in local_targets:
                these_targets = {}
                for pos_id in pos_ids:
                    posmodel = ptl.get(pos_id)
                    these_targets[pos_id] = {'command':'obsXY', 'target':posmodel.trans.posXY_to_obsXY(local_target)}
                all_targets.append(these_targets)
        
            # initialize some data structures for storing test data
            targ_num = 0
            all_data_by_target = []
            all_data_by_pos_id = {}
            for pos_id in pos_ids:
                all_data_by_pos_id[pos_id] = {'targ_obsXY': []}
                for key in submove_fields:
                    all_data_by_pos_id[pos_id][key] = [[] for i in submove_idxs]
            start_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
            start_cycles = ptl.get(pos_ids,'TOTAL_MOVE_SEQUENCES')
           
            # run the test
            for these_targets in all_targets:
                targ_num += 1
                message='\nMEASURING TARGET ' + str(targ_num) + ' OF ' + str(len(all_targets))
                print(message)
                if self.should_log:
                    logging.info(message)

                message='Local target (posX,posY)=(' + format(local_targets[targ_num-1][0],'.3f') + ',' + format(local_targets[targ_num-1][1],'.3f') + ') for each positioner.'
                print(message)
                if self.should_log:
                    logging.info(message)

                this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
                these_meas_data = self.m.move_and_correct(these_targets, num_corr_max=self.num_corr_max)
                
                # store this set of measured data
                all_data_by_target.append(these_meas_data)
                for pos_id in these_targets.keys():
                    all_data_by_pos_id[pos_id]['targ_obsXY'].append(these_meas_data[pos_id]['targ_obsXY'])
                    for sub in submove_idxs:
                        for key in submove_fields:
                            all_data_by_pos_id[pos_id][key][sub].append(these_meas_data[pos_id][key][sub])              
                
                # update summary data log
                for pos_id in pos_ids:
                    summary_log_data =  'pos_id,' + str(pos_id) + '\n'
                    summary_log_data += 'log_suffix,' + str(log_suffix) + '\n'
                    summary_log_data += 'cycles at start,' + str(start_cycles[pos_ids.index(pos_id)]) + '\n'
                    summary_log_data += 'cycles at finish,' + str(ptl.get(pos_id,'TOTAL_MOVE_SEQUENCES')) + '\n'
                    summary_log_data += 'start time,' + start_timestamp + '\n'
                    summary_log_data += 'finish time,' + this_timestamp + '\n'
                    summary_log_data += 'num requested targets,' + str(len(all_targets)) + '\n'
                    summary_log_data += 'num corrections max,' + str(self.num_corr_max) + '\n'
                    summary_log_data += 'submove index -->'
                    for i in submove_idxs: summary_log_data += ',' + str(i)
                    summary_log_data += '\n'
                    for calc in ['max','min','mean','rms']:
                        summary_log_data += calc + '(um)'
                        for i in submove_idxs:
                            this_submove_data = all_data_by_pos_id[pos_id]['err2D'][i]
                            if calc == 'max':    summary_log_data += ',' + str(np.max(this_submove_data) * pc.um_per_mm)
                            elif calc == 'min':  summary_log_data += ',' + str(np.min(this_submove_data) * pc.um_per_mm)
                            elif calc == 'mean': summary_log_data += ',' + str(np.mean(this_submove_data) * pc.um_per_mm)
                            elif calc == 'rms':  summary_log_data += ',' + str(np.sqrt(np.mean(np.array(this_submove_data)**2)) * pc.um_per_mm)
                            else: pass
                            if i == submove_idxs[-1]: summary_log_data += '\n'
                    file = open(summary_log_name(pos_id),'w')
                    file.write(summary_log_data)
                    file.close()
        
                # update move data log
                for pos_id in these_targets.keys():
                    row = this_timestamp
                    row += ',' + str(ptl.get(pos_id,'TOTAL_MOVE_SEQUENCES'))
                    row += ',' + str(these_targets[pos_id]['targ_obsXY'][0])
                    row += ',' + str(these_targets[pos_id]['targ_obsXY'][1])
                    for key in submove_fields:
                        for submove_data in these_targets[pos_id][key]:
                            if isinstance(submove_data,list):
                                for j in range(len(submove_data)):
                                    row += ',' + str(submove_data[j])
                            else:
                                row += ',' + str(submove_data)
                    row += '\n'
                    file = open(move_log_name(pos_id),'a')
                    file.write(row)
                    file.close()
            
            # make summary plots showing the targets and measured positions
            for pos_id in all_data_by_pos_id.keys():
                posmodel = ptl.get(pos_id)
                title = log_timestamp + log_suffix
                center = [ptl.get(pos_id,'OFFSET_X'),ptl.get(pos_id,'OFFSET_Y')]
                theta_min = posmodel.trans.posTP_to_obsTP([min(posmodel.targetable_range_T),0])[0]
                theta_max = posmodel.trans.posTP_to_obsTP([max(posmodel.targetable_range_T),0])[0]
                theta_range = [theta_min,theta_max]
                r1 = ptl.get(pos_id,'LENGTH_R1')
                r2 = ptl.get(pos_id,'LENGTH_R2')
                pos_xytest_plot.plot(summary_plot_name(pos_id),pos_id,all_data_by_pos_id[pos_id],center,theta_range,r1,r2,title)

            script_exec_time = time.time() - script_start_time
            test_time = format(script_exec_time/60/60,'.1f')        
            

            # save a copy of the unit_*.conf file prior to calibration    
            for pos_id in pos_ids:
                try:
                    shutil.copy2(pc.pos_settings_directory+'/unit_'+pos_id+'.conf',cal_after_name(pos_id))
                except:
                    print ("Error copying unit_"+pos_id+" file")


            #Test report and email only on certain tests
            if should_email:
                test_report.do_test_report(pos_ids, all_data_by_pos_id, log_timestamp, pos_notes, test_time, email_list)
             
            #Commit logs through SVN
            if should_auto_commit_logs:
                filetypes = ['xyplot_submove0.png','xyplot_submove1.png','xyplot_submove2.png','xyplot_submove3.png',
                             'calib_full.png','calib_quick.png','summary.csv','movedata.csv']
                for pos_id in pos_ids:
                    for file in filetypes:
                        command = 'svn add ' + pc.test_logs_directory + pos_id + '_' + log_timestamp + '_' + file
                        try:
                            os.system(command)
                        except:
                            print('Failed run command: ' + command)
                try:
                    os.system('svn commit ' + pc.test_logs_directory + ' -m "' + log_timestamp + ' test logs"')
                except:
                    print('Failed to commit files.')
                            

        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            #Email traceback to alert that test failed and why
            if should_email:
                test_report.email_error(traceback.format_exc(),log_timestamp)
            raise
   
        # retract the phi arm as the final step
        target = {}
        for pos_id in pos_ids:
            target[pos_id] = {'command':'posTP', 'target':[185,-3]}
        print('Setting to neutral position')
        self.m.move(target)

            
        script_exec_time = time.time() - script_start_time
        message='Total test time: ' + format(script_exec_time/60/60,'.1f') + 'hrs'
        print(message)
        if self.should_log:
            logging.info(message)

if __name__=="__main__":
    acc_test=AccuracyTest()
    acc_test.enable_logging()
    acc_test.update_config()
    acc_test.run_xyaccuracy_test()