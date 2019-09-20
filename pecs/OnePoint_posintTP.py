from OnePoint import OnePoint

if __name__ == '__main__':
    op = OnePoint()
    print('This will update posintTP using one point calibration.')
    op.run_interactively(mode='posintTP', match_radius=80.0)
