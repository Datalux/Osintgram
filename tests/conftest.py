#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_instagram_api():
    """Mock for Instagram Private API"""
    api_mock = MagicMock()
    with patch('instagram_private_api.Client', return_value=api_mock):
        yield api_mock

@pytest.fixture
def mock_config():
    """Mock configuration settings"""
    with patch('src.config.getUsername', return_value='test_user'), \
         patch('src.config.getPassword', return_value='test_pass'):
        yield

@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory for tests"""
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return str(output_dir)

@pytest.fixture
def captured_output(capfd):
    """Fixture to capture and return stdout/stderr output"""
    def _get_output():
        out, err = capfd.readouterr()
        return out.strip(), err.strip()
    
    return _get_output 