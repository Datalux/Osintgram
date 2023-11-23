# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import
"""Release data for the pyreadline project.

$Id$"""

#*****************************************************************************
#       Copyright (C) 2006  Jorgen Stenarson. <jorgen.stenarson@kroywen.se>
#
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#*****************************************************************************

# Name of the package for release purposes.  This is the name which labels
# the tarballs and RPMs made by distutils, so it's best to lowercase it.
name = 'pyreadline'

# For versions with substrings (like 0.6.16.svn), use an extra . to separate
# the new substring.  We have to avoid using either dashes or underscores,
# because bdist_rpm does not accept dashes (an RPM) convention, and
# bdist_deb does not accept underscores (a Debian convention).

branch = ''

version = '2.1'

description = "A python implmementation of GNU readline."

long_description = \
"""
The pyreadline package is a python implementation of GNU readline functionality
it is based on the ctypes based UNC readline package by Gary Bishop.
It is not complete. It has been tested for use with windows 2000 and windows xp.

* pyreadline 2.1 <2015-09-16>

  This is a bugfix release to make pyreadline work with python 3.5.

  Contributors to this release:

    - Jörgen Stenarson, maintainer
    - kivhift, improved error message for running on non windows platforms
    - zooba, made helpful suggestions to make it work for python 3.5

  Version 2.1 of pyreadline has been verfied for Python 2.7, and 3.4, 3.5.


Features:
 *  keyboard text selection and copy/paste
 *  Shift-arrowkeys for text selection
 *  Control-c can be used for copy activate with allow_ctrl_c(True) in config file
 *  Double tapping ctrl-c will raise a KeyboardInterrupt, use ctrl_c_tap_time_interval(x)
    where x is your preferred tap time window, default 0.3 s.
 *  paste pastes first line of content on clipboard.
 *  ipython_paste, pastes tab-separated data as list of lists or numpy array if all data is numeric
 *  paste_mulitline_code pastes multi line code, removing any empty lines.


 The latest development version is always available at the IPython github
 repository_.

.. _repository: https://github.com/pyreadline/pyreadline.git
 """

license = 'BSD'

authors = {'Jorgen' : ('Jorgen Stenarson','jorgen.stenarson@kroywen.se'),
           'Gary':    ('Gary Bishop', ''),
           'Jack':    ('Jack Trainor', ''),
           }

url = 'http://ipython.org/pyreadline.html'
download_url = 'https://pypi.python.org/pypi/pyreadline/'
platforms = ['Windows XP/2000/NT',
             'Windows 95/98/ME']

keywords = ['readline',
            'pyreadline']

classifiers = ['Development Status :: 5 - Production/Stable',
               'Environment :: Console',
               'Operating System :: Microsoft :: Windows',
               'License :: OSI Approved :: BSD License',
               'Programming Language :: Python :: 2.7',
               'Programming Language :: Python :: 3.2',
               'Programming Language :: Python :: 3.3',
               'Programming Language :: Python :: 3.4',
               'Programming Language :: Python :: 3.5',
               ]
