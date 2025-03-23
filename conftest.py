#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Root conftest.py for pytest.
This file ensures that the src directory is in the Python path
and mocks common dependencies needed for testing.
"""

import os
import sys
from unittest.mock import MagicMock

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Mock common dependencies required by imports
def pytest_configure(config):
    """
    Set up mocks for external libraries to allow tests to run
    without having all dependencies installed.
    """
    # Mock Instagram API
    instagram_api = MagicMock()
    app_client = MagicMock()
    sys.modules['instagram_private_api'] = instagram_api
    instagram_api.Client = app_client
    instagram_api.ClientCookieExpiredError = Exception
    instagram_api.ClientLoginRequiredError = Exception
    instagram_api.ClientError = Exception
    instagram_api.ClientThrottledError = Exception
    
    # Mock geopy
    mock_geopy = MagicMock()
    mock_geocoders = MagicMock()
    mock_nominatim = MagicMock()
    sys.modules['geopy'] = mock_geopy
    sys.modules['geopy.geocoders'] = mock_geocoders
    mock_geocoders.Nominatim = mock_nominatim

    # Mock PrettyTable
    sys.modules['prettytable'] = MagicMock()
    
    # Mock requests
    sys.modules['requests'] = MagicMock() 