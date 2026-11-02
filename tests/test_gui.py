"""Test de fumée de l'UI PySide6 : scan + installation réels (mêmes
précautions ZZTest que test_installer.py), piloté sans interface visible
(QT_QPA_PLATFORM=offscreen) pour tourner aussi en CI/headless.

Attend la fin du worker via QEventLoop (pas une boucle `while ... processEvents()`
à la main) : cette dernière a provoqué un crash natif (STATUS_STACK_BUFFER_OVERRUN)
en enchaînant plusieurs fenêtres/threads dans le même process de test."""
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

if sys.platform == "win32":
    import winreg

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWidgets import QApplication

from core.font_installer import REGISTRY_PATH, Scope, fonts_dir
from tests.generate_samples import SAMPLES_DIR, generate_all
from ui.main_window import MainWindow

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="dépend de winreg/ctypes.windll")


def _wait_for_worker(window, timeout_ms: int = 5000) -> None:
    """Attend la fin de InstallWorker via un vrai QEventLoop, pas un
    polling manuel — sinon les signaux cross-thread de Qt peuvent être
    délivrés dans un état incohérent."""
    if window.worker is None:
        return
    loop = QEventLoop()
    window.worker.finished_all.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    win = MainWindow()
    yield win
    _wait_for_worker(win)
    win.close()
    win.deleteLater()
    qapp.processEvents()


@pytest.fixture
def samples():
    generate_all()
    yield
    shutil.rmtree(SAMPLES_DIR, ignore_errors=True)


@pytest.fixture
def cleanup_installed():
    yield
    root = winreg.HKEY_CURRENT_USER
    with winreg.OpenKey(root, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
        i = 0
        to_delete = []
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            if "ZZTest" in name:
                to_delete.append((name, value))
            i += 1
        for name, value in to_delete:
            import ctypes
            dest = fonts_dir(Scope.USER) / value
            ctypes.windll.gdi32.RemoveFontResourceW(str(dest))
            dest.unlink(missing_ok=True)
            winreg.DeleteValue(key, name)


def test_scan_populates_table(window, samples):
    window.sources = [SAMPLES_DIR]

    window._scan()

    assert len(window.found_paths) == 5
    assert window.table.rowCount() == 5
    assert window.btn_install.isEnabled()


def test_install_updates_table_and_summary(window, samples, cleanup_installed):
    window.sources = [SAMPLES_DIR]
    window._scan()

    window._install()
    _wait_for_worker(window)

    assert "Installées : 3" in window.summary_label.text()
    assert "Déjà là : 1" in window.summary_label.text()
    assert "Échouées : 1" in window.summary_label.text()

    statuses = {window.table.item(r, 0).text(): window.table.item(r, 2).text()
                for r in range(window.table.rowCount())}
    assert "installée" in statuses["TestSerif-Regular.ttf"]
    assert "invalide" in statuses["pas_une_police.ttf"].lower()


def test_drop_event_sets_sources_from_local_urls(window, samples):
    class FakeMimeData:
        def __init__(self, urls):
            self._urls = urls

        def hasUrls(self):
            return True

        def urls(self):
            return self._urls

    class FakeDropEvent:
        def __init__(self, mime_data):
            self._mime_data = mime_data

        def mimeData(self):
            return self._mime_data

    dropped = [SAMPLES_DIR / "TestSans-Regular.ttf", SAMPLES_DIR / "sous_dossier"]
    urls = [QUrl.fromLocalFile(str(p)) for p in dropped]

    window.dropEvent(FakeDropEvent(FakeMimeData(urls)))

    assert window.sources == dropped
    assert window.btn_scan.isEnabled()


def test_drop_event_ignores_nonexistent_paths(window, samples):
    class FakeMimeData:
        def hasUrls(self):
            return True

        def urls(self):
            return [QUrl.fromLocalFile(str(SAMPLES_DIR / "n_existe_pas.ttf"))]

    class FakeDropEvent:
        def mimeData(self):
            return FakeMimeData()

    window.dropEvent(FakeDropEvent())

    assert window.sources == []
    assert not window.btn_scan.isEnabled()


def test_system_scope_without_admin_warns_instead_of_crashing(window, samples, monkeypatch):
    import ui.main_window as main_window_module
    monkeypatch.setattr(main_window_module, "is_admin", lambda: False)
    warned = {}
    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning",
        lambda *a, **k: warned.setdefault("shown", True),
    )

    window.sources = [SAMPLES_DIR]
    window._scan()
    window.chk_system.setChecked(True)

    window._install()

    assert warned.get("shown") is True
    assert window.worker is None
