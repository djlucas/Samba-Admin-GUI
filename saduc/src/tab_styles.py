#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/tab_styles.py
#
# Description:
# This file contains style definitions for the RotatingTabWidget.
#
# -----------------------------------------------------------------------------

from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

STYLE_DEFAULT = {
    "drawer": "_paint_default_tabs",
    "padding": 10,
    "y_offset_factor": 5,
    "colors": {
        "bg_back": QColor(Qt.lightGray),
    }
}

STYLE_ROUNDED = {
    "drawer": "_paint_rounded_tabs",
    "padding": 20,
    "border_radius": 15,
    "y_offset_factor": 10,
    "colors": {
        "bg_back": QColor(Qt.lightGray),
    }
}

STYLE_DARK_ROUNDED = {
    "drawer": "_paint_rounded_tabs",
    "padding": 20,
    "border_radius": 15,
    "y_offset_factor": 10,
    "colors": {
        "bg_selected": QColor("#4a4a4a"),
        "text_selected": QColor(Qt.white),
        "bg_front": QColor("#3c3c3c"),
        "text_front": QColor(Qt.white),
        "bg_back": QColor("#2a2a2a"),
        "text_back": QColor(Qt.lightGray),
    }
}
