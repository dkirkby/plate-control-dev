from OnePoint import OnePoint

if __name__ == '__main__':
    print('This will update TP offsets using one point calibration.')
    op = OnePoint()
    op.run_interactively(mode='posTP', match_radius=80)
