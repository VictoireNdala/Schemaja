"""Installation de polices sous Windows et Linux.

Windows utilise le registre. Sous Linux, les polices sont copiées dans les
emplacements XDG puis Fontconfig est rafraîchi avec ``fc-cache``.
"""
import ctypes
import os
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path

if sys.platform == "win32":
    import winreg

from .font_metadata import FontInfo
from .models import InstallResult, InstallStatus

HWND_BROADCAST = 0xFFFF
WM_FONTCHANGE = 0x001D
SMTO_ABORTIFHUNG = 0x0002

REGISTRY_PATH = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"


class Scope(Enum):
    USER = "user"
    SYSTEM = "system"


def is_admin() -> bool:
    if sys.platform != "win32":
        return hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def fonts_dir(scope: Scope) -> Path:
    if sys.platform != "win32":
        if scope is Scope.SYSTEM:
            return Path("/usr/local/share/fonts")
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return data_home / "fonts"
    if scope is Scope.SYSTEM:
        return Path(os.environ["WINDIR"]) / "Fonts"
    return Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"


def _registry_root(scope: Scope):
    return winreg.HKEY_LOCAL_MACHINE if scope is Scope.SYSTEM else winreg.HKEY_CURRENT_USER


def _linux_font_name(registry_name: str) -> str:
    """Supprime le suffixe Windows utilisé par l'API historique publique."""
    for suffix in (" (TrueType)", " (OpenType)"):
        if registry_name.endswith(suffix):
            return registry_name.removesuffix(suffix)
    return registry_name


def _linux_is_registered(registry_name: str) -> bool:
    """Interroge Fontconfig sans dépendance Python supplémentaire."""
    try:
        result = subprocess.run(
            ["fc-list", "--format=%{fullname}\\n"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return _linux_font_name(registry_name) in result.stdout.splitlines()


def is_already_registered(registry_name: str, scope: Scope) -> bool:
    if sys.platform != "win32":
        return _linux_is_registered(registry_name)
    try:
        with winreg.OpenKey(_registry_root(scope), REGISTRY_PATH) as key:
            winreg.QueryValueEx(key, registry_name)
            return True
    except FileNotFoundError:
        return False


def _unique_destination(target_dir: Path, filename: str) -> Path:
    """Évite d'écraser un fichier différent qui porterait le même nom."""
    dest = target_dir / filename
    if not dest.exists():
        return dest
    stem, ext = Path(filename).stem, Path(filename).suffix
    n = 1
    while dest.exists():
        dest = target_dir / f"{stem}_{n}{ext}"
        n += 1
    return dest


def _refresh_linux_font_cache(target_dir: Path) -> None:
    """Rend la police immédiatement visible aux applications Fontconfig."""
    try:
        subprocess.run(["fc-cache", "-f", str(target_dir)], check=False, capture_output=True)
    except FileNotFoundError:
        # La copie reste utilisable dès que Fontconfig sera disponible/rafraîchi.
        pass


def install_font(info: FontInfo, scope: Scope = Scope.USER, force: bool = False) -> InstallResult:
    already_registered = is_already_registered(info.registry_name, scope)
    if not force and already_registered:
        return InstallResult(
            info.path, InstallStatus.SKIPPED_DUPLICATE, f"{info.full_name} est déjà installée"
        )

    try:
        target_dir = fonts_dir(scope)
        target_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32" and force and already_registered:
            # Réutilise le fichier déjà enregistré au lieu d'en créer un nouveau.
            with winreg.OpenKey(_registry_root(scope), REGISTRY_PATH) as key:
                existing_filename, _ = winreg.QueryValueEx(key, info.registry_name)
            dest = target_dir / existing_filename
        else:
            dest = _unique_destination(target_dir, info.path.name)

        shutil.copy2(info.path, dest)

        if sys.platform == "win32":
            # Dans le dossier Fonts, le nom seul suffit comme valeur de registre.
            with winreg.OpenKey(_registry_root(scope), REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, info.registry_name, 0, winreg.REG_SZ, dest.name)
            ctypes.windll.gdi32.AddFontResourceW(str(dest))
        else:
            _refresh_linux_font_cache(target_dir)

        return InstallResult(info.path, InstallStatus.INSTALLED, f"{info.full_name} installée")

    except PermissionError:
        return InstallResult(
            info.path,
            InstallStatus.FAILED,
            "Droits insuffisants — relance en administrateur pour une installation système",
        )
    except OSError as e:
        return InstallResult(info.path, InstallStatus.FAILED, f"Erreur système : {e}")


def notify_system() -> None:
    """Prévient les applications ouvertes qu'il y a de nouvelles polices."""
    if sys.platform == "win32":
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_FONTCHANGE, 0, 0, SMTO_ABORTIFHUNG, 1000, None
        )
    else:
        _refresh_linux_font_cache(fonts_dir(Scope.USER))
