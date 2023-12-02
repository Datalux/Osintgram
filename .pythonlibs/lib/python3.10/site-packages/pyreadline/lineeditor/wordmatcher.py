# -*- coding: utf-8 -*-
#*****************************************************************************
#       Copyright (C) 2006  Jorgen Stenarson. <jorgen.stenarson@bostream.nu>
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#*****************************************************************************
from __future__ import print_function, unicode_literals, absolute_import

import re, operator


def str_find_all(str, ch):
    result = []
    index = 0
    while index >= 0:
        index = str.find(ch, index)
        if index >= 0:
            result.append(index)
            index += 1
    return result
        

word_pattern = re.compile("(x*)")

def markwords(str, iswordfun):
    markers = {True : "x", False : "o"}
    return "".join([markers[iswordfun(ch)] for ch in str])

def split_words(str, iswordfun):
    return [x for x in word_pattern.split(markwords(str,iswordfun)) if x != ""]

def mark_start_segment(str, is_segment):
    def mark_start(s):
        if s[0:1] == "x":
            return "s" + s[1:]
        else:
            return s
    return "".join(map(mark_start, split_words(str, is_segment)))

def mark_end_segment(str, is_segment):
    def mark_start(s):
        if s[0:1] == "x":
            return s[:-1] + "s"
        else:
            return s
    return "".join(map(mark_start, split_words(str, is_segment)))
    
def mark_start_segment_index(str, is_segment):
    return str_find_all(mark_start_segment(str, is_segment), "s")

def mark_end_segment_index(str, is_segment):
    return [x + 1 for x in str_find_all(mark_end_segment(str, is_segment), "s")]


################  Following are used in lineobj  ###########################

def is_word_token(str):
    return not is_non_word_token(str)
    
def is_non_word_token(str):
    if len(str) != 1 or str in " \t\n":
        return True
    else:
        return False

def next_start_segment(str, is_segment):
    str = "".join(str)
    result = []
    for start in mark_start_segment_index(str, is_segment):
        result[len(result):start] = [start for x in range(start - len(result))]
    result[len(result):len(str)] = [len(str) for x in range(len(str) - len(result) + 1)]            
    return result
    
def next_end_segment(str, is_segment):
    str = "".join(str)
    result = []
    for start in mark_end_segment_index(str, is_segment):
        result[len(result):start] = [start for x in range(start - len(result))]
    result[len(result):len(str)] = [len(str) for x in range(len(str) - len(result) + 1)]            
    return result    


def prev_start_segment(str, is_segment):
    str = "".join(str)
    result = []
    prev = 0
    for start in mark_start_segment_index(str, is_segment):
        result[len(result):start+1] = [prev for x in range(start - len(result) + 1)]
        prev=start
    result[len(result):len(str)] = [prev for x in range(len(str) - len(result) + 1)]            
    return result

def prev_end_segment(str, is_segment):
    str = "".join(str)
    result = []
    prev = 0
    for start in mark_end_segment_index(str, is_segment):
        result[len(result):start + 1] = [prev for x in range(start - len(result) + 1)]
        prev=start
    result[len(result):len(str)] = [len(str) for x in range(len(str) - len(result) + 1)]            
    return result    

