from distutils.core import setup
from Cython.Build import cythonize
import os

for module in ['poscollider']:
    for file in os.listdir():
        if os.path.splitext(file)[-1] in ['.so','.pyd'] and module in file:
            os.remove(file)
    setup(name=module, ext_modules=cythonize(module + '.pyx', annotate=True))

# General tips for the Cython-uninitiated...
# ------------------------------------------
# sample call to compile in Spyder console:
#   runfile('setup.py', args='build_ext --inplace')
# and generally, do so within a fresh console

# sample call to compile at general console:
# python setup.py build_ext --inplace

# for Windows compiling, need build tools for visual studio:
# https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2017
# also see: https://wiki.python.org/moin/WindowsCompilers
