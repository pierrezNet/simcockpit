"""Préparation de l'environnement Qt, à appeler AVANT de créer QApplication.

Sous GNOME, Qt charge par défaut son thème GTK (libqgtk3), qui lit la clé
« antialiasing » du schéma org.gnome.settings-daemon.plugins.xsettings. Cette clé
n'existe plus dans les GNOME récents : GLib arrête alors le programme (core dumped).
Le thème « xdgdesktopportal » évite ce chemin. Un choix explicite de l'utilisateur
(variable QT_QPA_PLATFORMTHEME déjà définie) est respecté.
"""

import os


def prepare():
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")
