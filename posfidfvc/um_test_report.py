'''
Author: kfanning@umich.edu

Use: A set of functions useful for emailing reports on the test stand.
Currently emails end reports to teststand_watchlist and emails
exception reports to teststand_operatorlist.

Designed specifically for the UM test stand using umdesi.teststand@gmail.com
address for sending emails. Currently only implemented into UM_accuracy_test.py
''' 


import numpy as np
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
teststand_watcherlist = ['kfanning@umich.edu','gtarle@umich.edu','schubnel@umich.edu','cweave@umich.edu','njswimm@umich.edu','igershko@umich.edu', 'bfreud@umich.edu']
#People who want test error reports
teststand_operatorlist = ['kfanning@umich.edu', 'bfreud@umich.edu','njswimm@umich.edu']

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

def status(max0, max1, max2, max3, rms3):
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
    if max3 > 12:
        condition = ' FAIL \n'
        reason += '    Failure reason 5: correction move 3 max error (' + fmt(max3) + 'um) is above 12um.\n'
    if reason == '':
        return ' PASS \n'
    else:
        return condition + reason
        
def pass_fail(max0,max1,max2,max3,rms3):
    if (max0 > 100) or (max1 > 100) or (max2 > 100) or (max3 > 12) or (rms3 > 5):
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
        image_types = ['xyplot_submove0.png','xyplot_submove1.png']
        for pos_id in pos_ids:
            #Attach movedata
            movedata = pc.test_logs_directory + pos_id + '_' + timestamp + '_' + 'movedata.csv'
            mvdt = open(movedata)
            attm = MIMEText(mvdt.read())
            attm.add_header('Content-Disposition', 'attachment', filename=(pos_id + '_' + timestamp + '_' + 'movedata.csv'))
            message.attach(attm)
            #Attach submove images
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

def do_test_report(pos_ids, all_data_by_pos_id, log_timestamp, pos_notes, time, to='full'):
    #Gather Data    
    summary_posids = {}
    for pos_id in pos_ids:
        lst = []
        for i in range(4):
            data = np.array(all_data_by_pos_id[pos_id]['err2D'][i])
            min0 = np.min(data)*um_scale
            max0 = np.max(data)*um_scale
            avg0 = np.mean(data)*um_scale
            rms0 = np.sqrt(np.mean(np.array(data)**2)) * um_scale
            lst.append({'max':max0[-1],'min':min0[-1],'avg':avg0[-1],'rms':rms0[-1]})
        summary_posids[pos_id] = lst
     
    #Write email
    email = 'UM Positioner Test Report\n' + 'Test ID: ' + log_timestamp + '\n'+ 'Execute time: ' + str(time) + ' hours\n\n' + 'Positioner status:\n'
    for pos_id in pos_ids:
        data = summary_posids[pos_id]
        email += '\nPositioner: ' + pos_id + ' - ' + pass_fail(data[0]['max'],data[1]['max'],data[2]['max'],data[3]['max'],data[3]['rms']) + '\n'
        if pos_notes[pos_ids.index(pos_id)] != '':
            email += pos_notes[pos_ids.index(pos_id)] + '\n'
        for i in range(len(move_list)):
            email += move_list[i] + ' (max,min,avg,rms): ' + fmt(data[i]['max']) + ', ' + fmt(data[i]['min']) + ', ' + fmt(data[i]['avg']) + ', ' + fmt(data[i]['rms']) + ' (um)\n'
    email += '\n\n'
    email += 'NOTE: This is an automated message sent by the test stand. Please do not reply to this message.'
    if should_email:    
        email_report(email, log_timestamp, pos_ids,to)
