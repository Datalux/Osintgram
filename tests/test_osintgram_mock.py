import os
from unittest.mock import MagicMock, patch

import pytest

# Import Osintgram - dependencies are mocked in root conftest.py
from src.Osintgram import Osintgram


@pytest.fixture
def mock_config():
    """Mock config for tests"""
    with patch("src.config.getUsername", return_value="test_user"), patch(
        "src.config.getPassword", return_value="test_pass"
    ):
        yield


@pytest.fixture
def mock_api():
    """Mock Instagram API"""
    with patch("instagram_private_api.Client"):
        yield


@pytest.fixture
def mock_osintgram(mock_config, mock_api, tmp_path):
    """Create a mock Osintgram instance"""
    with patch.object(Osintgram, "login", return_value=None), patch.object(
        Osintgram, "setTarget", return_value=None
    ):

        # Create a mock output directory
        output_dir = str(tmp_path / "output")
        os.makedirs(output_dir, exist_ok=True)

        # Create the instance
        instance = Osintgram("test_target", False, False, True, output_dir, False)

        # Manually set the target property
        instance.target = "test_target"

        return instance


def test_osintgram_initialization(mock_osintgram):
    """Test Osintgram instance initialization"""
    assert mock_osintgram is not None
    assert mock_osintgram.target == "test_target"
    assert mock_osintgram.writeFile is False
    assert mock_osintgram.jsonDump is False
    assert mock_osintgram.cli_mode is True


def test_osintgram_set_write_file(mock_osintgram):
    """Test set_write_file method"""
    mock_osintgram.set_write_file(True)
    assert mock_osintgram.writeFile is True

    mock_osintgram.set_write_file(False)
    assert mock_osintgram.writeFile is False


def test_osintgram_set_json_dump(mock_osintgram):
    """Test set_json_dump method"""
    mock_osintgram.set_json_dump(True)
    assert mock_osintgram.jsonDump is True

    mock_osintgram.set_json_dump(False)
    assert mock_osintgram.jsonDump is False
