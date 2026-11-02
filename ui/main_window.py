"""Fenêtre principale : sélection de source, options, scan, installation.

Ne contient aucune logique métier — tout passe par core/ (scan, lecture de
métadonnées, installation), exactement comme main.py (CLI).
"""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.font_installer import Scope, is_admin
from core.scanner import cleanup_extracted_dirs, scan
from ui.install_worker import InstallWorker

ICON_PATH = Path(__file__).parent.parent / "assets" / "icon.ico"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Schémaja")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(700, 500)
        self.setAcceptDrops(True)

        self.sources: list[Path] = []
        self.found_paths: list[Path] = []
        self.worker: InstallWorker | None = None
        self._extracted_dirs: list[Path] = []

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        source_row = QHBoxLayout()
        self.source_label = QLabel("Aucune source sélectionnée (ou glissez-déposez ici)")
        self.source_label.setWordWrap(True)
        btn_folder = QPushButton("Choisir un dossier…")
        btn_folder.clicked.connect(self._choose_folder)
        btn_files = QPushButton("Choisir des fichiers…")
        btn_files.clicked.connect(self._choose_files)
        source_row.addWidget(self.source_label, 1)
        source_row.addWidget(btn_folder)
        source_row.addWidget(btn_files)
        layout.addLayout(source_row)

        options_row = QHBoxLayout()
        label = "Tous les utilisateurs (admin)" if sys.platform == "win32" else "Système (root)"
        self.chk_system = QCheckBox(label)
        self.chk_no_recursive = QCheckBox("Ne pas parcourir les sous-dossiers")
        self.chk_force = QCheckBox("Forcer la réinstallation")
        options_row.addWidget(self.chk_system)
        options_row.addWidget(self.chk_no_recursive)
        options_row.addWidget(self.chk_force)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        action_row = QHBoxLayout()
        self.btn_scan = QPushButton("Scanner")
        self.btn_scan.clicked.connect(self._scan)
        self.btn_scan.setEnabled(False)
        self.btn_install = QPushButton("Installer")
        self.btn_install.clicked.connect(self._install)
        self.btn_install.setEnabled(False)
        action_row.addWidget(self.btn_scan)
        action_row.addWidget(self.btn_install)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Fichier", "Police", "Statut"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        self.summary_label = QLabel("")
        layout.addWidget(self.summary_label)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier de polices")
        if path:
            self._set_sources([Path(path)])

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des fichiers de police", "", "Polices et archives (*.ttf *.otf *.zip)"
        )
        if paths:
            self._set_sources([Path(p) for p in paths])

    def _set_sources(self, paths: list[Path]) -> None:
        self.sources = paths
        label = str(paths[0]) if len(paths) == 1 else f"{len(paths)} éléments sélectionnés"
        self.source_label.setText(label)
        self._reset_results()
        self.btn_scan.setEnabled(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        paths = [p for p in paths if p.exists()]
        if paths:
            self._set_sources(paths)

    def _reset_results(self) -> None:
        self.found_paths = []
        self.table.setRowCount(0)
        self.summary_label.setText("")
        self.btn_install.setEnabled(False)

    def _scan(self) -> None:
        cleanup_extracted_dirs(self._extracted_dirs)

        recursive = not self.chk_no_recursive.isChecked()
        found: list[Path] = []
        for src in self.sources:
            found.extend(scan(src, recursive=recursive, extracted_dirs=self._extracted_dirs))
        self.found_paths = sorted(set(found))

        self.table.setRowCount(len(self.found_paths))
        for row, path in enumerate(self.found_paths):
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(row, 1, QTableWidgetItem(""))
            self.table.setItem(row, 2, QTableWidgetItem("En attente"))

        self.summary_label.setText(f"{len(self.found_paths)} police(s) trouvée(s).")
        self.btn_install.setEnabled(bool(self.found_paths))

    def _install(self) -> None:
        scope = Scope.SYSTEM if self.chk_system.isChecked() else Scope.USER

        if scope is Scope.SYSTEM and not is_admin():
            QMessageBox.warning(
                self,
                "Droits insuffisants",
                "L'installation système nécessite des droits administrateur.\n"
                "Relance le programme avec les privilèges nécessaires, ou décoche cette option.",
            )
            return

        self.btn_scan.setEnabled(False)
        self.btn_install.setEnabled(False)
        self.summary_label.setText("Installation en cours…")

        self.worker = InstallWorker(self.found_paths, scope, self.chk_force.isChecked())
        self.worker.item_done.connect(self._on_item_done)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _on_item_done(self, row: int, name: str, status: str) -> None:
        self.table.setItem(row, 1, QTableWidgetItem(name))
        self.table.setItem(row, 2, QTableWidgetItem(status))

    def _on_finished(self, installed: int, skipped: int, failed: int) -> None:
        self.summary_label.setText(
            f"Installées : {installed} | Déjà là : {skipped} | Échouées : {failed}"
        )
        self.btn_scan.setEnabled(True)
        self.btn_install.setEnabled(True)
        self.worker = None
        cleanup_extracted_dirs(self._extracted_dirs)
