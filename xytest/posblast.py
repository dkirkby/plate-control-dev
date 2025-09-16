import sys
import os
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../../../positioner_logs/data_processing_scripts/'))
import petalcomm
import googlesheets
import posdance

canbus = 'can0'

if __name__ == '__main__':

    _sel = posdance._read_key()
    loop = True
    ptlID = input("Input Petal ID:")
    pcomm = petalcomm.PetalComm(ptlID)
    while loop:
        print("[a]uto CAN ID programming")
        print("[m]anual CAN ID programming")
        print("[h]ardware setup update")
        print("[s]ingle manual CAN ID programming")
        print("[e]xit")
        print("Select: ")

        choice = _sel.__call__()
        choice = choice.lower()

        if choice == 'e':
            sys.exit()

        if choice == 'a':
            boardIDs = googlesheets.connect_to_sheet('SiliconIDs')
            eshop = googlesheets.connect_to_sheet('FIPOS Board Production Log')
            infodict = pcomm.get_posfid_info(canbus)

            for info in infodict.values():
                readable_sid = info[3]
                sid = readable_sid.split(':')
                sid = ''.join(sid)
                if googlesheets.check_for_value(boardIDs, "\"" + sid + "\""):
                    boardID = googlesheets.read(boardIDs, "\"" + sid + "\"", "Board ID")
                    eshoprow = googlesheets.read_col(eshop, 1, False).index(str(boardID)) + 1
                    desiredCAN = googlesheets.read(eshop, eshoprow, "Serial #", False)
                    pcomm.set_canid(canbus, readable_sid, desiredCAN)
                    print("Programmed CAN ID " + str(desiredCAN))
                else:
                    print("Could not find " + sid + " in silicon ID log")

        if choice == 'm':
            poslist = []
            print('Input all positioner IDs that you wish to go into the summary, and type \'done\' when finished')

            posinput = ''
            while posinput != 'done':
                posinput = input('Positioner ID: ')
                if len(posinput) < 6 and not posinput == 'done':
                    newinput = 'M'
                    for x in range(5 - len(posinput)):
                        newinput += '0'
                    posinput = newinput + posinput
                    poslist.append(posinput)
                elif not posinput == 'done':
                    poslist.append(posinput)

            sidlist = []

            infodict = pcomm.get_posfid_info(canbus)
            for info in infodict.values():
                sid = info[3]
                sidlist.append(sid)

            for posid in poslist:

                input("Please plug in positioner " + posid + " and press Enter.")

                for x in range(len(posid)):
                    if not (posid[x] == 'M' or posid[x] == '0'):
                        posid = str(posid[x::])
                        break

                newsids = []
                infodict = pcomm.get_posfid_info(canbus)

                for info in infodict.values():
                    sid = info[3]
                    newsids.append(sid)

                for oldsid in sidlist:
                    newsids.pop(newsids.index(oldsid))

                if len(newsids) == 1:
                    sidlist.append(newsids[0])
                    pcomm.set_canid(canbus, newsids[0], posid)
                else:
                    print('Error - expected one new silicon ID but detected either none or more than this:' + str(newsids))
                    break

        if choice == 'h':

            infodict = pcomm.get_posfid_info(canbus)
            poslist = sorted(list(infodict.keys()))

            print(poslist)

        if choice == 'c':

            print('Would you like to log the following posids and silicon ids to a particular traveler? [y/n]')
            choice2 = _sel.__call__()
            choice2 = choice.lower()

            if choice2 == 'y':
                travelerurl = input('Please provide the traveler url:')
                traveler = googlesheets.connect_by_url(travelerurl, credentials = os.path.abspath('../../../positioner_logs/data_processing_scripts/google_access_account.json')
                used_spaces = googlesheets.read_row(traveler, 'POS_ID').col)
                next_empty_col = 7     #hard coded for now
                while used_spaces[next_empty_col-1] != '':
                    next_empty_col += 1

            posinput = input('Positioner ID: ')
            while posinput != 'done':
                firstchar = posinput[0]

                while firstchar == '0' or firstchar == 'M'
                    posinput = posinput[1:]
                    firstchar = posinput[0]

                input("Plug this positioner into the board and press Enter")
                infodict = pcomm.get_posid_info(canbus)
                if len(infodict) == 1:
                    sid = infodict[0][3]
                    pcomm.set_canid(canbus, sid, posinput)
                    googlesheets.write(traveler, 'CAN_ID', next_empty_col, posinput, ID_col_with_data = False)
                    if len(posinput) < 6:
                        newinput = 'M'
                        for x in range(5 - len(posinput)):
                            newinput += '0'
                        posinput = newinput + posinput
                    googlesheets.write(traveler, 'POS_ID', next_empty_col, posinput, ID_col_with_data = False)
                    googlesheets.write(traveler, 'SI_ID',  next_empty_col, sid, ID_col_with_data = False)

                else:
                    print("The wrong number of positioners is currently plugged in")
                posinput = input("Programmed CAN ID " + posinput + " .\nUnplug the positioner and input the next ID (type 'done' when finished):")




























