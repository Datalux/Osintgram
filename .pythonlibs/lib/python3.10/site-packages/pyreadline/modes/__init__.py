from __future__ import print_function, unicode_literals, absolute_import
__all__=["emacs", "notemacs", "vi"]
from . import emacs, notemacs, vi
editingmodes = [emacs.EmacsMode, notemacs.NotEmacsMode, vi.ViMode]

#add check to ensure all modes have unique mode names