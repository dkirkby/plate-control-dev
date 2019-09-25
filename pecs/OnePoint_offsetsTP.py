from OnePoint import OnePoint

if __name__ == '__main__':
    print('This will update TP offsets using one point calibration.')
    optp = OnePoint()
    optp.run_interactively(mode='offsetsTP', tp_target='default', match_radius=80)
