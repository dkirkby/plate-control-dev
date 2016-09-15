'''
Author: kfanning@umich.edu

Use: A set of functions useful for emailing reports on the test stand.
Currently emails end reports to teststand_watchlist and emails
exception reports to teststand_operatorlist.

Designed specifically for the UM test stand using umdesi.teststand@gmail.com
address for sending emails. Currently only implemented into UM_accuracy_test.py
''' 


import numpy as np
import os
import sys
sys.path.append('../petal')
import posconstants as pc
import smtplib
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

move_list = ['Blind Move', 'Submove 1', 'Submove 2', 'Submove 3']
stat_list = ['max','min','avg','rms']
indent = '    '
um_scale = 1000
#People who want test results
teststand_watcherlist = ['kfanning@umich.edu','gtarle@umich.edu','schubnel@umich.edu','cweave@umich.edu','njswimm@umich.edu','igershko@umich.edu', 'plawton@umich.edu']
#People who want test error reports
teststand_operatorlist = ['kfanning@umich.edu','plawton@umich.edu','njswimm@umich.edu']

def fmt(number):
    return format(number,'.1f')

def stat_summ(stat, value, mean, stdev, unit = ''):
    num_stdevs = (value-mean)/stdev
    if num_stdevs < 0:
        num_stdevs = abs(num_stdevs)
        preposition = ' standard deviations below the mean of all tests'
    else:
        preposition = ' standard deviations above the mean of all tests'
    return stat + ' = ' + fmt(value) + unit + ', ' + fmt(num_stdevs) + preposition

def status(max0, max1, max2, rms3):
    reason = ''
    if max0 > 100:
        condition = ' FAIL \n'
        reason += '    Failure reason 1: blind move max error (' + fmt(max0) + 'um) is above 100um.\n'
    if rms3 > 5:
        condition = ' FAIL \n'
        reason += '    Failure reason 2: RMS error of final correction (' + fmt(rms3) + 'um) is above 5um.\n'
    if max1 > 100:
        condition = ' FAIL \n'
        reason += '    Failure Reason 3: correction move 1 max error (' + fmt(max1) + 'um) is above 100um.\n'
    if max2 > 100:
        condition = ' FAIL \n'
        reason += '    Failure reason 4: correction move 2 max error (' + fmt(max2) + 'um) is above 100um.\n'
    if reason == '':
        return ' PASS \n'
    else:
        return condition + reason
        
def pass_fail(max0,max1,max2,rms3):
    if (max0 > 100) or (max1 > 100) or (max2 > 100) or (rms3 > 5):
        return 'FAIL'
    else:
        return 'PASS'

def email_report(text, timestamp, pos_ids,to='limited'):
    if to == 'full':
        recipients = teststand_watcherlist
    else:
        recipients = teststand_operatorlist
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login('umdesi.teststand', 'UM00022,UM00017')
        message = MIMEMultipart()
        message['Subject'] = 'Test Complete (' + timestamp + ')'
        message['From'] = 'UM-DESI Test Stand'
        message['To'] = ', '.join(recipients)
        file = pc.test_logs_directory + timestamp + '_report.txt'
        try:
            fp = open(file)
            attachment = MIMEText(fp.read())
            attachment.add_header('Content-Disposition', 'attachment', filename=(timestamp + '_report.txt'))           
            message.attach(attachment)
            attachment = MIMEText(pc.test_logs_directory + timestamp + '_report.txt')
        except:
            print('Failed to attach file:',file)
        image_types = ['xyplot_submove0.png','xyplot_submove1.png']
        for pos_id in pos_ids:
            for image in image_types:
                file = pc.test_logs_directory + pos_id + '_' + timestamp + '_' + image
                try:
                    fp = open(file, 'rb')
                    img = MIMEImage(fp.read())
                    img.add_header('Content-Disposition', 'attachment', filename=(pos_id + '_' + timestamp + '_' + image)) 
                    fp.close()
                    message.attach(img)
                except:
                    print('Failed to attach file:',file)
        content = MIMEText(text)
        message.attach(content)    
        server.sendmail('umdesi.teststand@gmail.com', recipients, message.as_string())
        server.close()
    except:
        print('Failed to email message')

    
def email_error(traceback, timestamp): #TODO add helpful interpretation of tracebacks
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login('umdesi.teststand', 'UM00022,UM00017')
        text = 'Test ' + timestamp + ' ran into an error. \nHere is the traceback:\n\n' + traceback
        message = MIMEText(text)
        message['Subject'] = 'Test Error Report (' + timestamp + ')'
        message['From'] = 'UM-DESI Test Stand'
        message['To'] = ', '.join(teststand_operatorlist)
        server.sendmail('umdesi.teststand@gmail.com', teststand_operatorlist, message.as_string())
        server.close()
    except:
        print('Failed to email message')

def do_test_report(pos_ids, all_data_by_pos_id, log_timestamp, pos_notes, time, should_email=False, to='full'):
    test_summaries = pc.test_logs_directory + 'UM_test_summaries.csv'
    report_log = pc.test_logs_directory + os.path.sep + log_timestamp + '_results.txt'
    #Update prior test data from SVN
    try:
        os.system('svn up ' + test_summaries)
    except:
        pass
    #Read Prior test data
    pf = [] #pass or fail
    min0 = []; min1 = []; min2 = []; min3 = []
    max0 = []; max1 = []; max2 = []; max3 = []
    avg0 = []; avg1 = []; avg2 = []; avg3 = []
    rms0 = []; rms1 = []; rms2 = []; rms3 = []
    read_ts = open(test_summaries, 'r')
    next(read_ts)
    for line in read_ts:
        ls = line.split(',')
        pf.append(ls[1])
        min0.append(float(ls[2]))
        max0.append(float(ls[3]))
        avg0.append(float(ls[5]))
        rms0.append(float(ls[5]))
        min1.append(float(ls[6]))
        max1.append(float(ls[7]))
        avg1.append(float(ls[8]))
        rms1.append(float(ls[9]))
        min2.append(float(ls[10]))
        max2.append(float(ls[11]))
        avg2.append(float(ls[12]))
        rms2.append(float(ls[13]))
        min3.append(float(ls[14]))
        max3.append(float(ls[15]))
        avg3.append(float(ls[16]))
        rms3.append(float(ls[17]))
    read_ts.close()
    len_old = len(pf)
    summary_posids = {}
    for pos_id in pos_ids:
        lst = []
        for i in range(4):
            data = np.array(all_data_by_pos_id[pos_id]['err2D'][i])
            if i == 0:
                min0.append(np.min(data)*um_scale)
                max0.append(np.max(data)*um_scale)
                avg0.append(np.mean(data)*um_scale)
                rms0.append(np.sqrt(np.mean(np.array(data)**2)) * um_scale)
                lst.append({'max':max0[-1],'min':min0[-1],'avg':avg0[-1],'rms':rms0[-1]})
            elif i == 1:
                min1.append(np.min(data)*um_scale)
                max1.append(np.max(data)*um_scale)
                avg1.append(np.mean(data)*um_scale)
                rms1.append(np.sqrt(np.mean(np.array(data)**2)) * um_scale)
                lst.append({'max':max1[-1],'min':min1[-1],'avg':avg1[-1],'rms':rms1[-1]})
            elif i == 2:
                min2.append(np.min(data)*um_scale)
                max2.append(np.max(data)*um_scale)
                avg2.append(np.mean(data)*um_scale)
                rms2.append(np.sqrt(np.mean(np.array(data)**2)) * um_scale)
                lst.append({'max':max2[-1],'min':min2[-1],'avg':avg2[-1],'rms':rms2[-1]})
            elif i == 3:
                min3.append(np.min(data)*um_scale)
                max3.append(np.max(data)*um_scale)
                avg3.append(np.mean(data)*um_scale)
                rms3.append(np.sqrt(np.mean(np.array(data)**2)) * um_scale)
                lst.append({'max':max3[-1],'min':min3[-1],'avg':avg3[-1],'rms':rms3[-1]})
        summary_posids[pos_id] = lst
    for i in range(len_old, len(min0)):
        pf.append(pass_fail(max0[i],max1[i],max1[i],rms3[i]))
                
    statistics = [{'min':{'mean':np.mean(min0),'stdev':np.sqrt(np.mean(np.array(min0)**2)-np.mean(min0)**2)},
                   'max':{'mean':np.mean(max0),'stdev':np.sqrt(np.mean(np.array(max0)**2)-np.mean(max0)**2)},
                   'avg':{'mean':np.mean(avg0),'stdev':np.sqrt(np.mean(np.array(avg0)**2)-np.mean(avg0)**2)},
                   'rms':{'mean':np.mean(rms0),'stdev':np.sqrt(np.mean(np.array(rms0)**2)-np.mean(rms0)**2)}},
                  {'min':{'mean':np.mean(min1),'stdev':np.sqrt(np.mean(np.array(min1)**2)-np.mean(min1)**2)},
                   'max':{'mean':np.mean(max1),'stdev':np.sqrt(np.mean(np.array(max1)**2)-np.mean(max1)**2)},
                   'avg':{'mean':np.mean(avg1),'stdev':np.sqrt(np.mean(np.array(avg1)**2)-np.mean(avg1)**2)},
                   'rms':{'mean':np.mean(rms1),'stdev':np.sqrt(np.mean(np.array(rms1)**2)-np.mean(rms1)**2)}},
                  {'min':{'mean':np.mean(min2),'stdev':np.sqrt(np.mean(np.array(min2)**2)-np.mean(min2)**2)},
                   'max':{'mean':np.mean(max2),'stdev':np.sqrt(np.mean(np.array(max2)**2)-np.mean(max2)**2)},
                   'avg':{'mean':np.mean(avg2),'stdev':np.sqrt(np.mean(np.array(avg2)**2)-np.mean(avg2)**2)},
                   'rms':{'mean':np.mean(rms2),'stdev':np.sqrt(np.mean(np.array(rms2)**2)-np.mean(rms2)**2)}},
                  {'min':{'mean':np.mean(min3),'stdev':np.sqrt(np.mean(np.array(min3)**2)-np.mean(min3)**2)},
                   'max':{'mean':np.mean(max3),'stdev':np.sqrt(np.mean(np.array(max3)**2)-np.mean(max3)**2)},
                   'avg':{'mean':np.mean(avg3),'stdev':np.sqrt(np.mean(np.array(avg3)**2)-np.mean(avg3)**2)},
                   'rms':{'mean':np.mean(rms3),'stdev':np.sqrt(np.mean(np.array(rms3)**2)-np.mean(rms3)**2)}}]
    
    failures = 0
    for cond in pf:
        if cond == 'FAIL':
            failures += 1
         
    #Write log
    report_log = pc.test_logs_directory + log_timestamp + '_report.txt'
    text = 'UM Positioner Test Report\n' + 'Test ID: ' + log_timestamp + '\n\n' + 'Positioner status (more detail below):\n'
    email = 'UM Positioner Test Report\n' + 'Test ID: ' + log_timestamp + '\n'+ 'Execute time: ' + time + 'hours\n\n' + 'Positioner status:\n'
    count = 0
    for pos_id in pos_ids:
        data = summary_posids[pos_id]
        text += pos_id + ' - ' + pass_fail(data[0]['max'],data[1]['max'],data[2]['max'],data[3]['rms']) + '\n'
        count += 1
        if count%5 == 0:
            text += '\n             '
    text += '\n\n\n\n'
    for pos_id in pos_ids:
        data = summary_posids[pos_id]
        text += 'Positioner ' + pos_id + ' -' + status(data[0]['max'],data[1]['max'],data[2]['max'],data[3]['rms'])
        email += '\nPositioner: ' + pos_id + ' - ' + pass_fail(data[0]['max'],data[1]['max'],data[2]['max'],data[3]['rms']) + '\n'
        if pos_notes[pos_ids.index(pos_id)] != '':
            email += pos_notes[pos_ids.index(pos_id)] + '\n'
        for i in range(len(move_list)):
            text += indent + move_list[i] + ':\n'
            email += move_list[i] + ' (max,min,avg,rms): ' + fmt(data[i]['max']) + ', ' + fmt(data[i]['min']) + ', ' + fmt(data[i]['avg']) + ', ' + fmt(data[i]['rms']) + ' (um)\n'
            for stat in stat_list:
                text += 2*indent + stat_summ(stat,data[i][stat],statistics[i][stat]['mean'], statistics[i][stat]['stdev'],unit='um') + '\n'
                
        text += '\n'
    text += 'Total Test Statistics:\n'
    text += indent + 'Number of Samples: ' + str(len(pf)) + '\n'
    text += indent + 'Number of Passes: ' + str(len(pf)-failures) + '\n'
    text += indent + 'Number of Failures: ' + str(failures) + '\n'
    text += indent + 'Failure Rate: ' + fmt((failures*100.)/len(pf)) + '%\n'
    for i in range(len(move_list)):
        text += indent + move_list[i] + ' Statistics:\n'
        for stat in stat_list:
            text += 2*indent + stat + ': avg = ' + fmt(statistics[i][stat]['mean']) + 'um, stdev = ' + fmt(statistics[i][stat]['stdev']) + '\n'
    report = open(report_log, 'w')
    report.write(text)
    report.close()

    #Email
    email += '\n\nMore test information can be found in attached images and report text file.\n'
    email += 'NOTE: This is an automated message sent by the test stand. Please do not reply to this message.'
    if should_email:    
        email_report(email, log_timestamp, pos_ids,to)

    #Update test summaries
    update = ''
    for i in range(len_old,len(pf)):
        update += pos_ids[i-len_old] + ',' + pf[i] + ','
        update += str(min0[i]) + ',' + str(max0[i]) + ',' + str(avg0[i]) + ',' + str(rms0[i]) + ','
        update += str(min1[i]) + ',' + str(max1[i]) + ',' + str(avg1[i]) + ',' + str(rms1[i]) + ','
        update += str(min2[i]) + ',' + str(max2[i]) + ',' + str(avg2[i]) + ',' + str(rms2[i]) + ','
        update += str(min3[i]) + ',' + str(max3[i]) + ',' + str(avg3[i]) + ',' + str(rms3[i]) + '\n'
    write_ts = open(test_summaries,'a')
    write_ts.write(update)
    write_ts.close()
    try:
        os.system('svn commit ' + test_summaries + ' -m "UM_test_summaries automated update"')
    except:
        pass
