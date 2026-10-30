"""Valide font_installer.py de bout en bout sur une vraie machine Windows :
écriture registre HKCU réelle + copie réelle dans le dossier Fonts utilisateur.

Utilise des noms de famille préfixés "ZZTestInstaller" pour ne jamais entrer
en collision avec une vraie police, et nettoie systématiquement (registre +
fichier copié + désenregistrement GDI) même si une assertion échoue.
"""
import ctypes
import shutil
import sys
if sys.platform == "win32":
    import winreg

import pytest

from core.font_installer import (
    REGISTRY_PATH,
    Scope,
    fonts_dir,
    install_font,
    is_admin,
    is_already_registered,
    notify_system,
)
from core.font_metadata import read_font_info
from core.models import InstallStatus
from tests.generate_samples import SAMPLES_DIR, generate_all

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="dépend de winreg/ctypes.windll")


def _cleanup(registry_name: str, scope: Scope) -> None:
    """Retire l'entrée registre et le fichier copié, quoi qu'il arrive."""
    root = winreg.HKEY_LOCAL_MACHINE if scope is Scope.SYSTEM else winreg.HKEY_CURRENT_USER
    try:
        with winreg.OpenKey(root, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            try:
                filename, _ = winreg.QueryValueEx(key, registry_name)
            except FileNotFoundError:
                filename = None
            if filename:
                dest = fonts_dir(scope) / filename
                ctypes.windll.gdi32.RemoveFontResourceW(str(dest))
                dest.unlink(missing_ok=True)
            try:
                winreg.DeleteValue(key, registry_name)
            except FileNotFoundError:
                pass
    except (FileNotFoundError, PermissionError):
        # SYSTEM sans droits admin : rien n'a pu être écrit, rien à nettoyer.
        pass


@pytest.fixture(scope="module", autouse=True)
def samples():
    generate_all()
    yield
    shutil.rmtree(SAMPLES_DIR, ignore_errors=True)


@pytest.fixture
def installed_cleanup():
    """Liste de (registry_name, scope) à nettoyer après le test."""
    to_clean = []
    yield to_clean
    for registry_name, scope in to_clean:
        _cleanup(registry_name, scope)


def test_is_admin_returns_bool():
    assert isinstance(is_admin(), bool)


def test_notify_system_does_not_raise():
    notify_system()  # doit juste ne pas planter (broadcast Windows)


def test_install_font_user_scope_writes_registry_and_copies_file(installed_cleanup):
    info = read_font_info(SAMPLES_DIR / "TestSans-Regular.ttf")
    installed_cleanup.append((info.registry_name, Scope.USER))

    result = install_font(info, scope=Scope.USER)

    assert result.status is InstallStatus.INSTALLED
    assert is_already_registered(info.registry_name, Scope.USER)

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as key:
        filename, _ = winreg.QueryValueEx(key, info.registry_name)
    dest = fonts_dir(Scope.USER) / filename
    assert dest.exists()


def test_install_font_skips_duplicate_by_default(installed_cleanup):
    info = read_font_info(SAMPLES_DIR / "TestSans-Regular.ttf")
    installed_cleanup.append((info.registry_name, Scope.USER))

    first = install_font(info, scope=Scope.USER)
    second = install_font(info, scope=Scope.USER)

    assert first.status is InstallStatus.INSTALLED
    assert second.status is InstallStatus.SKIPPED_DUPLICATE


def test_install_font_dedupes_across_different_files_same_family(installed_cleanup):
    """Deux fichiers différents contenant la même police (même registry_name)
    doivent être détectés comme doublon — décision actée dans CLAUDE.md."""
    a = read_font_info(SAMPLES_DIR / "TestSans-Regular.ttf")
    b = read_font_info(SAMPLES_DIR / "TestSans-Duplicate.ttf")
    installed_cleanup.append((a.registry_name, Scope.USER))
    assert a.path != b.path
    assert a.registry_name == b.registry_name

    first = install_font(a, scope=Scope.USER)
    second = install_font(b, scope=Scope.USER)

    assert first.status is InstallStatus.INSTALLED
    assert second.status is InstallStatus.SKIPPED_DUPLICATE


def test_install_font_force_reinstalls(installed_cleanup):
    info = read_font_info(SAMPLES_DIR / "TestSans-Regular.ttf")
    installed_cleanup.append((info.registry_name, Scope.USER))

    install_font(info, scope=Scope.USER)
    result = install_font(info, scope=Scope.USER, force=True)

    assert result.status is InstallStatus.INSTALLED


def test_install_font_force_does_not_leak_orphan_files(installed_cleanup):
    """Régression : un --force répété ne doit pas laisser d'anciennes copies
    (TestSans-Regular_1.ttf, _2.ttf, ...) non référencées par le registre."""
    info = read_font_info(SAMPLES_DIR / "TestSans-Regular.ttf")
    installed_cleanup.append((info.registry_name, Scope.USER))

    for _ in range(3):
        install_font(info, scope=Scope.USER, force=True)

    matches = list(fonts_dir(Scope.USER).glob(f"{info.path.stem}*{info.path.suffix}"))
    assert len(matches) == 1, f"copies orphelines détectées : {matches}"


def test_install_font_system_scope_without_admin_fails_gracefully(installed_cleanup):
    if is_admin():
        pytest.skip("terminal élevé : le scope système réussirait, rien à observer ici")

    info = read_font_info(SAMPLES_DIR / "TestSans-Bold.ttf")
    installed_cleanup.append((info.registry_name, Scope.SYSTEM))

    result = install_font(info, scope=Scope.SYSTEM)

    assert result.status is InstallStatus.FAILED
    assert "administrateur" in result.message.lower()
