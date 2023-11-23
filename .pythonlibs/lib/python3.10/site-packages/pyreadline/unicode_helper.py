# -*- coding: utf-8 -*-
#*****************************************************************************
#       Copyright (C) 2007  Jorgen Stenarson. <jorgen.stenarson@bostream.nu>
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#*****************************************************************************
import sys

from .py3k_compat import unicode, bytes

try:
    pyreadline_codepage = sys.stdout.encoding
except AttributeError:        
    # This error occurs when pdb imports readline and doctest has replaced 
    # stdout with stdout collector. We will assume ascii codepage
    pyreadline_codepage = "ascii"

if pyreadline_codepage is None:  
    pyreadline_codepage = "ascii"

if sys.version_info < (2, 6):
    bytes = str

PY3 = (sys.version_info >= (3, 0))

def ensure_unicode(text):
    """helper to ensure that text passed to WriteConsoleW is unicode"""
    if isinstance(text, bytes):
        try:
            return text.decode(pyreadline_codepage, "replace")
        except (LookupError, TypeError):
            return text.decode("ascii", "replace")
    return text


def ensure_str(text):
    """Convert unicode to str using pyreadline_codepage"""
    if isinstance(text, unicode):
        try:
            return text.encode(pyreadline_codepage, "replace")
        except (LookupError, TypeError):
            return text.encode("ascii", "replace")
    return text

def biter(text):
    if PY3 and isinstance(text, bytes):
        return (s.to_bytes(1, 'big') for s in text)
    else:
        return iter(text)
