#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/container_properties.py
#
# Description:
# This file contains the dialog for viewing and editing container properties.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox
)

from i18n_manager import I18nManager
from samba_backend import get_group_properties

class ContainerPropertiesDialog(QDialog):
    """Dialog for viewing and editing container properties."""
    def __init__(self, samba_conn, container_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.container_dn = container_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("group_properties.window_title"))
        self.setMinimumSize(500, 400)

        self._create_widgets()
        self._create_layout()
        self._load_container_data()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()
        self.general_tab = QWidget()

        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("group_properties.tab.general"))

        # General Tab Widgets
        self.container_name_edit = QLineEdit()
        self.container_name_edit.setReadOnly(True)
        self.description_edit = QLineEdit()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        # General Tab Layout
        general_layout = QFormLayout(self.general_tab)
        general_layout.addRow(self.i18n.get_string("group_properties.label.group_name"), self.container_name_edit)
        general_layout.addRow(self.i18n.get_string("group_properties.label.description"), self.description_edit)

    def _load_container_data(self):
        # For now, we can reuse get_group_properties as it fetches common attributes
        container_props = get_group_properties(self.samba_conn, self.container_dn)
        if not container_props:
            self.logger.error(f"Could not load properties for container: {self.container_dn}")
            return

        # General Tab
        self.container_name_edit.setText(container_props.get('cn', [''])[0])
        self.description_edit.setText(container_props.get('description', [''])[0])

    def apply_changes(self):
        # This is a placeholder for now
        self.logger.info("Apply changes clicked, but not yet implemented.")
        pass
