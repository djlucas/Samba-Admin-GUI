#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/container_properties.py
#
# Description:
# This file contains the dialog for viewing and editing container and OU 
# properties.
#
# -----------------------------------------------------------------------------

import logging
import os
import copy
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QFrame, QMessageBox
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from i18n_manager import I18nManager
from samba_backend import get_all_container_attributes_with_schema_info
from rotating_tab_widget import RotatingTabWidget
from tab_styles import STYLE_DEFAULT
from shared_properties_tabs import ObjectTab, SecurityTab, ManagedByTab, ComPlusTab
from attribute_editor import AttributeEditorTab

class ContainerPropertiesDialog(QDialog):
    """Dialog for viewing and editing container/OU properties."""
    def __init__(self, samba_conn, container_dn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.container_dn = container_dn
        self.advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.container_props = {}
        self.schema_info = {}
        self.editable_container_props = {}

        self.setWindowTitle(self.i18n.get_string("container_properties.window_title"))
        self.setMinimumSize(450, 400)

        self._create_widgets()
        self._create_layout()
        self._load_container_data()
        self._connect_signals()

    def _create_widgets(self):
        self.tab_widget = RotatingTabWidget(logger=self.logger)
        self.tab_widget.setTabStyle(STYLE_DEFAULT)
        self.general_tab = QWidget()
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("user_properties.tab.general"))

        # --- General Tab Widgets ---
        self.ou_icon_label = QLabel()
        self.ou_name_header = QLabel()
        self.description_edit = QLineEdit()
        self.street_edit = QTextEdit()
        self.city_edit = QLineEdit()
        self.state_edit = QLineEdit()
        self.zip_edit = QLineEdit()
        self.country_combo = QComboBox()
        self.country_combo.setEditable(True)
        countries = ["", "United States", "Canada", "United Kingdom", "Germany", "France", "Australia", "Other"]
        self.country_combo.addItems(countries)

        # --- Dialog Buttons ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        # --- General Tab Layout ---
        self.general_layout = QVBoxLayout(self.general_tab)

        header_layout = QHBoxLayout()
        self.ou_icon_label.setFixedSize(40, 40)
        self.ou_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.ou_icon_label)
        header_layout.addWidget(self.ou_name_header)
        header_layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)

        self.general_form_layout = QFormLayout()
        self.general_form_layout.setVerticalSpacing(10)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.description"), self.description_edit)

        self.general_layout.addLayout(header_layout)
        self.general_layout.addWidget(separator)
        self.general_layout.addLayout(self.general_form_layout)
        self.general_layout.addStretch()

    def _add_ou_general_fields(self):
        """Add fields specific to OUs to the General tab."""
        self.street_edit.setFixedHeight(80)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.street"), self.street_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.city"), self.city_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.state"), self.state_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.zip"), self.zip_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.country"), self.country_combo)

    def _load_container_data(self):
        """Load container data from Active Directory, including schema info."""
        self.container_props, self.schema_info = get_all_container_attributes_with_schema_info(self.samba_conn, self.container_dn)
        if not self.container_props:
            self.logger.error(f"Could not load properties for container: {self.container_dn}")
            return

        self.editable_container_props = copy.deepcopy(self.container_props)
        self._populate_all_tabs()

    def _populate_all_tabs(self):
        """Populate all tabs with data from self.container_props."""
        props = self.container_props
        name = (props.get('ou') or props.get('cn', ['']))[0]
        self.ou_name_header.setText(name)
        self.description_edit.setText(props.get('description', [''])[0])
        self.setWindowTitle(f"{name} {self.i18n.get_string('container_properties.window_title')}")

        is_ou = 'organizationalUnit' in props.get('objectClass', [])

        # Set icon based on type
        icon_name = "folder_ou.png" if is_ou else "folder.png"
        icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', icon_name)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.ou_icon_label.setPixmap(pixmap)
        else:
            self.logger.warning(f"Icon not found at {icon_path}")

        # Check if it's an OU and add specific tabs/fields
        if is_ou:
            self._add_ou_general_fields()
            self.tab_widget.addTab(ManagedByTab(self.samba_conn, props), self.i18n.get_string("container_properties.tab.managed_by"))
            self.tab_widget.addTab(ComPlusTab(), self.i18n.get_string("container_properties.tab.com_plus"))
            
            # Populate OU-specific fields
            self.street_edit.setText(props.get('street', [''])[0])
            self.city_edit.setText(props.get('l', [''])[0])
            self.state_edit.setText(props.get('st', [''])[0])
            self.zip_edit.setText(props.get('postalCode', [''])[0])
            self.country_combo.setCurrentText(props.get('co', [''])[0])

        # Add advanced tabs if enabled
        if self.advanced_view:
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.container_dn, self.container_props), "Object")
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.container_dn), "Security")
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.container_dn), "Attribute Editor")

    def _connect_signals(self):
        """Connect all UI element signals to the attribute change handler."""
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)

        self.widget_to_attribute_map = {
            self.description_edit: 'description',
            self.street_edit: 'street',
            self.city_edit: 'l',
            self.state_edit: 'st',
            self.zip_edit: 'postalCode',
            self.country_combo: 'co',
        }

        for widget, attr_name in self.widget_to_attribute_map.items():
            if isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._on_attribute_change)
            elif isinstance(widget, QTextEdit):
                widget.textChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._on_attribute_change)

    def _on_attribute_change(self):
        """Handle changes to any attribute field."""
        sender = self.sender()
        if sender in self.widget_to_attribute_map:
            attr_name = self.widget_to_attribute_map[sender]
            
            new_value = ''
            if isinstance(sender, (QLineEdit)):
                new_value = sender.text()
            elif isinstance(sender, QTextEdit):
                new_value = sender.toPlainText()
            elif isinstance(sender, QComboBox):
                new_value = sender.currentText()

            if attr_name in self.editable_container_props:
                if self.editable_container_props.get(attr_name, ['']) != [new_value]:
                    self.logger.debug(f"Attribute '{attr_name}' changed from '{self.editable_container_props.get(attr_name, [''])[0]}' to '{new_value}'")
                    self.editable_container_props[attr_name] = [new_value]
            else:
                self.logger.debug(f"Attribute '{attr_name}' set to '{new_value}'")
                self.editable_container_props[attr_name] = [new_value]

    def apply_changes(self):
        """Logs the changes that have been made in the dialog."""
        self.logger.info("Applying changes for container object.")
        changes = {}
        for attr, value in self.editable_container_props.items():
            if self.container_props.get(attr) != value:
                changes[attr] = value
                self.logger.debug(f"Change to be applied: {attr}: {self.container_props.get(attr)} -> {value}")

        if not changes:
            self.logger.info("No changes to apply.")
            return

        self.logger.info("Changes logged. Write-back is not yet implemented.")
        self.container_props = copy.deepcopy(self.editable_container_props)
