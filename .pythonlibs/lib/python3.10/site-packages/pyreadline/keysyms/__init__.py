from __future__ import print_function, unicode_literals, absolute_import

import sys

success = False
in_ironpython = "IronPython" in sys.version
from . import winconstants

if in_ironpython:
    try:
        from .ironpython_keysyms import *
        success = True
    except ImportError as x:
        raise
else:
    try:
        from .keysyms import *
        success = True
    except ImportError as x:
        pass
    
if not success:
    raise ImportError("Could not import keysym for local pythonversion", x)