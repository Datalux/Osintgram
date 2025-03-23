import pytest

from src import printcolors as pc

def test_printcolors_constants():
    """Test that color constants are defined correctly"""
    assert pc.RED is not None, "RED color should be defined"
    assert pc.GREEN is not None, "GREEN color should be defined"
    assert pc.YELLOW is not None, "YELLOW color should be defined"
    assert pc.BLUE is not None, "BLUE color should be defined"
    assert pc.MAGENTA is not None, "MAGENTA color should be defined"
    assert pc.CYAN is not None, "CYAN color should be defined"
    assert pc.WHITE is not None, "WHITE color should be defined"
    # NOCOLOR is not defined in the module
    
def test_printcolors_printout(capfd):
    """Test that printout function outputs correctly"""
    test_string = "Test String"
    pc.printout(test_string, pc.RED)
    out, err = capfd.readouterr()
    assert test_string in out, "Printout should contain the test string" 