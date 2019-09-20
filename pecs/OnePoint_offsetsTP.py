from OnePoint import OnePoint

if __name__ == '__main__':
    op = OnePoint()
    print('This will update TP offsets using one point calibration.')
    op.run_interactively(mode='offsetsTP', match_radius=80.0)
