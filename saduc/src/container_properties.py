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
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QFrame, QMessageBox
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from i18n_manager import I18nManager
from samba_backend import get_container_properties, get_user_properties

class ContainerPropertiesDialog(QDialog):
    """Dialog for viewing and editing container/OU properties."""
    def __init__(self, samba_conn, container_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.container_dn = container_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("container_properties.window_title"))
        self.setMinimumSize(500, 400)

        self._create_widgets()
        self._create_layout()
        self._load_container_data()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()
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

        # --- Managed By Tab Widgets (created on demand) ---
        self.managed_by_tab = None
        self.manager_name_edit = QLineEdit()
        self.manager_name_edit.setReadOnly(True)
        self.change_manager_btn = QPushButton(self.i18n.get_string("user_properties.button.change"))
        self.clear_manager_btn = QPushButton(self.i18n.get_string("computer_properties.managed_by.button_clear"))
        self.manager_view_btn = QPushButton(self.i18n.get_string("action_pane.menu.properties"))

        # PIM fields for manager
        self.manager_office_label = QLabel()
        self.manager_street_label = QLabel()
        self.manager_city_state_label = QLabel()
        self.manager_country_label = QLabel()
        self.manager_telephone_label = QLabel()
        self.manager_fax_label = QLabel()

        # --- COM+ Tab Widgets (created on demand) ---
        self.com_plus_tab = None
        self.partition_combo = QComboBox()

        # --- Dialog Buttons ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

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
        self.general_form_layout.setVerticalSpacing(10) # Add spacing between fields
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.description"), self.description_edit)

        self.general_layout.addLayout(header_layout)
        self.general_layout.addWidget(separator)
        self.general_layout.addLayout(self.general_form_layout)
        self.general_layout.addStretch()

    def _add_ou_general_fields(self):
        """Add fields specific to OUs to the General tab."""
        self.street_edit.setFixedHeight(80) # ~4 lines
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.street"), self.street_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.city"), self.city_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.state"), self.state_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.zip"), self.zip_edit)
        self.general_form_layout.addRow(self.i18n.get_string("user_properties.label.country"), self.country_combo)

    def _create_managed_by_tab(self):
        """Create and add the Managed By tab."""
        self.managed_by_tab = QWidget()
        layout = QVBoxLayout(self.managed_by_tab)

        manager_group = QGroupBox()
        group_layout = QVBoxLayout(manager_group)

        # Name field
        name_form_layout = QFormLayout()
        name_form_layout.addRow(self.i18n.get_string("user_properties.label.name"), self.manager_name_edit)
        group_layout.addLayout(name_form_layout)

        # Buttons below the name field
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.change_manager_btn)
        button_layout.addWidget(self.manager_view_btn)
        button_layout.addWidget(self.clear_manager_btn)
        group_layout.addLayout(button_layout)

        # Spacer
        group_layout.addSpacing(15)

        # PIM fields
        pim_form_layout = QFormLayout()
        pim_form_layout.setVerticalSpacing(10)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.office"), self.manager_office_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.street"), self.manager_street_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.city_state"), self.manager_city_state_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.country"), self.manager_country_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        pim_form_layout.addRow(separator)

        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.telephone"), self.manager_telephone_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.fax"), self.manager_fax_label)

        group_layout.addLayout(pim_form_layout)

        layout.addWidget(manager_group)
        layout.addStretch()
        self.tab_widget.addTab(self.managed_by_tab, self.i18n.get_string("container_properties.tab.managed_by"))

        # Connect signals for button logic
        self.manager_name_edit.textChanged.connect(self._update_managed_by_buttons)
        self.change_manager_btn.clicked.connect(self._change_manager)

    def _create_com_plus_tab(self):
        """Create and add the COM+ tab."""
        self.com_plus_tab = QWidget()
        layout = QVBoxLayout(self.com_plus_tab)
        header = QLabel(self.i18n.get_string("user_properties.title.com_partition_set"))
        group = QGroupBox(self.i18n.get_string("user_properties.group.com_partition_set"))
        group_layout = QVBoxLayout(group)
        group_layout.addWidget(self.partition_combo)

        layout.addWidget(header)
        layout.addWidget(group)
        layout.addStretch()
        self.tab_widget.addTab(self.com_plus_tab, self.i18n.get_string("container_properties.tab.com_plus"))

    def _load_container_data(self):
        props = get_container_properties(self.samba_conn, self.container_dn)
        if not props:
            self.logger.error(f"Could not load properties for container: {self.container_dn}")
            return

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
            self._create_managed_by_tab()
            self._create_com_plus_tab()

            # Populate OU-specific fields
            self.street_edit.setText(props.get('street', [''])[0])
            self.city_edit.setText(props.get('l', [''])[0])
            self.state_edit.setText(props.get('st', [''])[0])
            self.zip_edit.setText(props.get('postalCode', [''])[0])
            self.country_combo.setCurrentText(props.get('co', [''])[0])

            # Populate Managed By tab
            manager_dn = props.get('managedBy', [None])[0]
            if manager_dn:
                manager_props = get_user_properties(self.samba_conn, manager_dn)
                if manager_props:
                    self.manager_name_edit.setText(manager_props.get('displayName', [''])[0])
                    self.manager_office_label.setText(manager_props.get('physicalDeliveryOfficeName', [''])[0])
                    self.manager_street_label.setText(manager_props.get('streetAddress', [''])[0])
                    city = manager_props.get('l', [''])[0]
                    state = manager_props.get('st', [''])[0]
                    self.manager_city_state_label.setText(f"{city}, {state}")
                    self.manager_country_label.setText(manager_props.get('co', [''])[0])
                    self.manager_telephone_label.setText(manager_props.get('telephoneNumber', [''])[0])
                    self.manager_fax_label.setText(manager_props.get('facsimileTelephoneNumber', [''])[0])

            # COM+ tab is a placeholder for now
            self.partition_combo.addItem("N/A")

            self._update_managed_by_buttons()

    def _update_managed_by_buttons(self):
        has_manager = bool(self.manager_name_edit.text())
        self.manager_view_btn.setEnabled(has_manager)
        self.clear_manager_btn.setEnabled(has_manager)

    def _change_manager(self):
        QMessageBox.information(self, "Not Implemented", "A user search dialog is not yet implemented.")

    def apply_changes(self):
        self.logger.info("Apply changes clicked, but not yet implemented.")
        pass
