"""Schémaja — installeur de polices en masse pour Windows et Linux (CLI).

Usage :
    python main.py "/chemin/vers/mes_polices"
    python main.py "C:\\chemin\\vers\\une_police.ttf" --system
"""
import argparse
import sys
from pathlib import Path

from core.font_installer import Scope, install_font, is_admin, notify_system
from core.font_metadata import InvalidFontError, read_font_info
from core.models import InstallStatus
from core.scanner import cleanup_extracted_dirs, scan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Schémaja — installe en masse des polices .ttf/.otf")
    parser.add_argument("source", help="Fichier ou dossier contenant les polices")
    parser.add_argument(
        "--system", action="store_true",
        help="Installer pour tous les utilisateurs (nécessite un terminal administrateur)",
    )
    parser.add_argument("--no-recursive", action="store_true", help="Ne pas parcourir les sous-dossiers")
    parser.add_argument("--force", action="store_true", help="Réinstaller même si déjà présente")
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    if sys.platform not in ("win32", "linux"):
        print("Cet outil est pris en charge sous Windows et Linux uniquement.")
        sys.exit(1)

    args = parse_args()
    scope = Scope.SYSTEM if args.system else Scope.USER

    if scope is Scope.SYSTEM and not is_admin():
        print("L'installation pour tous les utilisateurs nécessite les droits administrateur.")
        print("Relance ce terminal en tant qu'administrateur, ou enlève --system.")
        sys.exit(1)

    source = Path(args.source)
    if not source.exists():
        print(f"Introuvable : {source}")
        sys.exit(1)

    extracted_dirs: list[Path] = []
    try:
        paths = list(scan(source, recursive=not args.no_recursive, extracted_dirs=extracted_dirs))
        if not paths:
            print("Aucune police .ttf/.otf trouvée (y compris dans les .zip).")
            return

        print(f"{len(paths)} police(s) trouvée(s) :")
        for p in paths:
            print(f"  - {p.name}")

        reponse = input("\nInstaller ces polices ? (o/n) : ").strip().lower()
        if reponse not in ("o", "oui", "y", "yes"):
            print("Annulé.")
            return

        installed = skipped = failed = 0
        print()
        for i, path in enumerate(paths, 1):
            try:
                info = read_font_info(path)
            except InvalidFontError as e:
                print(f"[{i}/{len(paths)}] Ignorée, fichier invalide : {e}")
                failed += 1
                continue

            result = install_font(info, scope=scope, force=args.force)
            print(f"[{i}/{len(paths)}] {result.message}")

            if result.status is InstallStatus.INSTALLED:
                installed += 1
            elif result.status is InstallStatus.SKIPPED_DUPLICATE:
                skipped += 1
            else:
                failed += 1

        notify_system()

        print(f"\nInstallées : {installed} | Déjà là : {skipped} | Échouées : {failed}")
    finally:
        cleanup_extracted_dirs(extracted_dirs)


if __name__ == "__main__":
    main()
