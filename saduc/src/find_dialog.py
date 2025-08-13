#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/find_dialog.py
#
# Description:
# This file contains the dialog for finding objects in Active Directory.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QLineEdit, QPushButton, QComboBox, QLabel, QFrame, QTabWidget,
    QTableWidget, QHeaderView
)
import ldap.dn

from i18n_manager import I18nManager
from samba_backend import BASE_DN

class FindObjectsDialog(QDialog):
    """Dialog for finding Active Directory objects."""
    def __init__(self, samba_conn, search_base_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.search_base_dn = search_base_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setMinimumSize(750, 500)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._initial_setup()

    def _create_widgets(self):
        # Top line widgets
        self.find_label = QLabel("Find:")
        self.find_combo = QComboBox()
        self.in_label = QLabel("In:")
        self.in_combo = QComboBox()
        self.in_combo.setMinimumWidth(200)
        self.browse_btn = QPushButton("Browse...")

        # Tabs
        self.tab_widget = QTabWidget()
        self.find_details_tab = QWidget() # This will be renamed dynamically
        self.advanced_tab = QWidget()

        # Widgets for the main find tab
        self.name_label = QLabel("Name:")
        self.name_edit = QLineEdit()
        self.description_label = QLabel("Description:")
        self.description_edit = QLineEdit()

        # Buttons on the right
        self.find_now_btn = QPushButton("Find Now")
        self.stop_btn = QPushButton("Stop")
        self.clear_all_btn = QPushButton("Clear All")
        self.search_icon_label = QLabel() # Placeholder for search icon

        # Results table
        self.results_table = QTableWidget()

    def _create_layout(self):
        main_layout = QHBoxLayout(self)

        # --- Left Panel (Inputs and Results) ---
        left_panel_layout = QVBoxLayout()

        # Top line layout
        top_line_layout = QHBoxLayout()
        top_line_layout.addWidget(self.find_label)
        top_line_layout.addWidget(self.find_combo)
        top_line_layout.addWidget(self.in_label)
        top_line_layout.addWidget(self.in_combo, 1)
        top_line_layout.addWidget(self.browse_btn)
        left_panel_layout.addLayout(top_line_layout)

        # --- Tab Widget ---
        find_details_layout = QFormLayout(self.find_details_tab)
        find_details_layout.addRow(self.name_label, self.name_edit)
        find_details_layout.addRow(self.description_label, self.description_edit)

        advanced_layout = QVBoxLayout(self.advanced_tab)
        advanced_layout.addWidget(QLabel("Custom LDAP query not yet implemented."))
        
        self.tab_widget.addTab(self.find_details_tab, "") # Title set dynamically
        self.tab_widget.addTab(self.advanced_tab, "Advanced")
        left_panel_layout.addWidget(self.tab_widget)

        # Results table
        left_panel_layout.addWidget(self.results_table)
        self._setup_results_table()

        # --- Right Panel (Buttons) ---
        right_panel_layout = QVBoxLayout()
        right_panel_layout.addWidget(self.find_now_btn)
        right_panel_layout.addWidget(self.stop_btn)
        right_panel_layout.addWidget(self.clear_all_btn)
        right_panel_layout.addStretch()
        right_panel_layout.addWidget(self.search_icon_label)
        right_panel_layout.addStretch()

        main_layout.addLayout(left_panel_layout, 4)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        main_layout.addLayout(right_panel_layout, 1)

    def _connect_signals(self):
        self.find_combo.currentIndexChanged.connect(self._on_find_type_changed)

    def _initial_setup(self):
        self.find_combo.addItems([
            "Users, Contacts, and Groups",
            "Computers",
            "Shared Folders",
            "Organizational Units",
            "Custom Search",
            "Common Queries"
        ])

        display_path = self._format_dn_for_display(self.search_base_dn)
        self.in_combo.addItem(display_path, self.search_base_dn)

        self._on_find_type_changed(0)

    def _on_find_type_changed(self, index):
        find_type = self.find_combo.currentText()
        self.setWindowTitle(f"Find {find_type}")
        self.tab_widget.setTabText(0, find_type)

    def _format_dn_for_display(self, dn_string):
        if not dn_string:
            return ""
        
        domain_parts = [p.split('=')[1] for p in BASE_DN.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)

        if dn_string.lower() == BASE_DN.lower():
            return domain

        try:
            dn_struct = ldap.dn.str2dn(dn_string)
            base_dn_struct = ldap.dn.str2dn(BASE_DN)

            relative_dn_struct = [rdn for rdn in dn_struct if rdn not in base_dn_struct]
            
            path_parts = []
            for rdn_part in reversed(relative_dn_struct):
                path_parts.append(rdn_part[0][1])

            if not path_parts:
                return domain
            
            return f"{domain}/{'/'.join(path_parts)}"
        except Exception:
            return dn_string

    def _setup_results_table(self):
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Name", "Type", "Description"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results_table.verticalHeader().hide()