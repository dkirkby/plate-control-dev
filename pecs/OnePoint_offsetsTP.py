from OnePoint_posTP import OnePoint

if __name__ == '__main__':
    op = OnePoint()
    print('Notice: this will update offsetsTP!')
    op.run_interactively(mode='offsetsTP',match_radius=80.0)
