"""Tests unitaires du backend Linux, sans modifier les polices de l'utilisateur."""
import subprocess
import sys

import pytest

from core import font_installer
from core.font_installer import Scope, install_font, is_already_registered
from core.models import InstallStatus
from core.font_metadata import read_font_info
from tests.generate_samples import build_font

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="backend Fontconfig Linux")


def test_linux_install_copies_to_xdg_directory_and_refreshes_cache(tmp_path, monkeypatch):
    source = tmp_path / "source.ttf"
    build_font(source, "ZZLinux Vektor", "Regular")
    info = read_font_info(source)
    destination = tmp_path / "xdg-data" / "fonts"
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "fc-list":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(font_installer, "fonts_dir", lambda scope: destination)
    monkeypatch.setattr(font_installer.subprocess, "run", fake_run)

    result = install_font(info, Scope.USER)

    assert result.status is InstallStatus.INSTALLED
    assert (destination / source.name).exists()
    assert ["fc-cache", "-f", str(destination)] in commands


def test_linux_duplicate_detection_uses_fontconfig(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="ZZLinux Vektor Regular\n", stderr="")

    monkeypatch.setattr(font_installer.subprocess, "run", fake_run)

    assert is_already_registered("ZZLinux Vektor Regular (TrueType)", Scope.USER)
