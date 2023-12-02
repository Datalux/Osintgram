# -*- coding: UTF-8 -*-
# Example snippet to use in a PYTHONSTARTUP file
from __future__ import print_function, unicode_literals, absolute_import
try:
    import pyreadline.rlmain
    #pyreadline.rlmain.config_path=r"c:\xxx\pyreadlineconfig.ini"
    import readline, atexit
    import pyreadline.unicode_helper
    #
    #
    #Normally the codepage for pyreadline is set to be sys.stdout.encoding
    #if you need to change this uncomment the following line
    #pyreadline.unicode_helper.pyreadline_codepage="utf8"
except ImportError:
    print("Module readline not available.")
else:
    #import tab completion functionality
    import rlcompleter

    #Override completer from rlcompleter to disable automatic ( on callable
    completer_obj = rlcompleter.Completer()
    def nop(val, word):
        return word
    completer_obj._callable_postfix = nop
    readline.set_completer(completer_obj.complete)

    #activate tab completion
    readline.parse_and_bind("tab: complete")
    readline.read_history_file()
    atexit.register(readline.write_history_file)
    del readline, rlcompleter, atexit
