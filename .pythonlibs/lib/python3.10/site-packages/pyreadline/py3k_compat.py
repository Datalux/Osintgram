from __future__ import print_function, unicode_literals, absolute_import
import sys

if sys.version_info[0] >= 3:
    import collections
    PY3 = True
    def callable(x):
        return isinstance(x, collections.Callable)
    
    def execfile(fname, glob, loc=None):
        loc = loc if (loc is not None) else glob
        with open(fname) as fil:
            txt = fil.read()
        exec(compile(txt, fname, 'exec'), glob, loc)

    unicode = str
    bytes = bytes
    from io import StringIO
else:
    PY3 = False
    callable = callable
    execfile = execfile
    bytes = str
    unicode = unicode
    
    from StringIO import StringIO
