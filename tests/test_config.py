import os

import pytest

from src import config


def test_config_file_exists():
    """Test that config directory exists"""
    assert os.path.isdir("config"), "Config directory should exist"


def test_get_username():
    """Test that username is defined and loaded correctly"""
    username = config.getUsername()
    assert username is not None, "Username should be loaded from config"
    assert isinstance(username, str), "Username should be a string"


def test_get_password():
    """Test that password is defined and loaded correctly"""
    password = config.getPassword()
    assert password is not None, "Password should be loaded from config"
    assert isinstance(password, str), "Password should be a string"
