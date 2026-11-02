# Schémaja

Installe en masse des fichiers `.ttf`/`.otf` sur Windows et Linux, en une seule commande,
sans passer par la boîte de dialogue native une police à la fois. Accepte
aussi les dossiers ou fichiers `.zip` de polices : ils sont extraits puis
scannés automatiquement.

## But du projet

Schémaja est un **installateur de polices en masse**. Il facilite
l'installation de nombreux fichiers de police à la fois : sélectionnez un
dossier, des fichiers `.ttf`/`.otf` ou une archive `.zip`, puis Schémaja les
repère, évite les doublons et les rend disponibles dans vos applications
(LibreOffice, GIMP, Inkscape, etc.).

Schémaja ne télécharge pas et ne crée pas de polices. Vous devez d'abord
récupérer les fichiers de police que vous souhaitez utiliser, puis les lui
fournir pour installation.

## Installation

```
pip install -r requirements.txt
```

Sous Linux, Fontconfig doit être présent (il fournit les commandes `fc-list`
et `fc-cache`, généralement déjà installées avec l'environnement graphique).

## Utilisation

### Graphical interface

```
python gui.py
```

Pick a folder or files, adjust the options if needed, then click "Scan"
and "Install".

### Command line

```
python main.py "/chemin/vers/MesPolices"
```

Installe pour l'utilisateur courant, sans droits admin requis. Sous Linux,
les fichiers sont copiés dans `~/.local/share/fonts` (ou
`$XDG_DATA_HOME/fonts`) puis le cache Fontconfig est rafraîchi. Les polices
déjà installées sont automatiquement ignorées.

Options : `--system` (tous les utilisateurs, nécessite un terminal
administrateur ; sous Linux, destination `/usr/local/share/fonts`),
`--no-recursive` (ignore les sous-dossiers), `--force`
(réinstalle même si déjà présente). Les mêmes options existent en cases à
cocher dans l'interface graphique.

### Exécutable Windows

Les livrables `dist/Schémaja.exe` et `dist/Schémaja_Setup.exe` sont réservés
à Windows. `dist/Schémaja.exe` est une version portable, se lance directement sans
installer Python. `dist/Schémaja_Setup.exe` : version installable — copie
l'app dans `%LOCALAPPDATA%\Programs\Schémaja`, ajoute un raccourci au menu
Démarrer, et s'enregistre dans "Applications et fonctionnalités" pour une
désinstallation standard.

## Project status

Le noyau (`core/`) prend en charge le registre Windows et Fontconfig sous
Linux. Le CLI (`main.py`) et l'interface graphique PySide6
(`gui.py`) sont tous deux construits par-dessus, sans dupliquer la logique
d'installation.
