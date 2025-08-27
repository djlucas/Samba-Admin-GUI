#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/contact_properties.py
#
# Description:
# Properties dialog for contact objects.
#
# -----------------------------------------------------------------------------

import logging
import os
import copy
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QDialogButtonBox, QLabel
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from i18n_manager import I18nManager
from samba_backend import get_all_contact_attributes_with_schema_info
from rotating_tab_widget import RotatingTabWidget
from tab_styles import STYLE_DEFAULT
from shared_properties_tabs import (
    ObjectTab, SecurityTab, MemberOfTab, AddressTab,
    TelephonesTab, OrganizationTab, EmailTab
)
from attribute_editor import AttributeEditorTab


class ContactPropertiesDialog(QDialog):
    """Dialog for viewing and editing contact properties."""

    def __init__(self, samba_conn, contact_dn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.contact_dn = contact_dn
        self.advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.contact_props = {}
        self.schema_info = {}
        self.editable_contact_props = {}
        self.display_name = ""

        self.setMinimumSize(400, 500)
        self.resize(450, 600)

        self._create_widgets()
        self._create_layout()
        self._load_contact_data()
        self._connect_signals()

    def _create_widgets(self):
        """Create all widgets for the dialog"""
        self.tab_widget = RotatingTabWidget(logger=self.logger)
        self.tab_widget.setTabStyle(STYLE_DEFAULT)

        self._create_general_tab()
        self.tab_widget.addTab(AddressTab(self.contact_props), self.i18n.get_string("user_properties.tab.address"))
        self.tab_widget.addTab(TelephonesTab(self.contact_props), self.i18n.get_string("user_properties.tab.telephones"))
        self.tab_widget.addTab(OrganizationTab(self.contact_props), self.i18n.get_string("user_properties.tab.organization"))
        self.tab_widget.addTab(MemberOfTab(self.samba_conn, self.contact_dn, self.contact_props), self.i18n.get_string("user_properties.tab.member_of"))

        if self.advanced_view:
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.contact_dn, self.contact_props), "Object")
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.contact_dn), "Security")
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.contact_dn), "Attribute Editor")
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.contact_dn, self.contact_props), self.i18n.get_string("user_properties.tab.email"))

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )

    def _create_general_tab(self):
        """Create the General tab"""
        self.general_tab = QWidget()
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("user_properties.tab.general"))

        layout = QVBoxLayout(self.general_tab)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'contact.png')
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_label.setPixmap(scaled_pixmap)
        except Exception as e:
            self.logger.error(f"Failed to load contact icon: {e}")

        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(40, 40)

        self.display_name_header = QLabel("")
        self.display_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")

        header_layout.addWidget(icon_label)
        header_layout.addWidget(self.display_name_header)
        header_layout.addStretch()

        separator = QLabel()
        separator.setFrameStyle(QLabel.HLine | QLabel.Sunken)
        separator.setLineWidth(1)

        layout.addLayout(header_layout)
        layout.addWidget(separator)

        form_layout = QFormLayout()
        name_layout = QHBoxLayout()
        self.first_name_edit = QLineEdit()
        self.initials_edit = QLineEdit()
        self.initials_edit.setMaxLength(6)
        self.initials_edit.setMaximumWidth(80)

        name_layout.addWidget(self.first_name_edit)
        name_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.initials")))
        name_layout.addWidget(self.initials_edit)

        self.last_name_edit = QLineEdit()
        self.display_name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.office_edit = QLineEdit()
        self.email_edit = QLineEdit()

        form_layout.addRow(self.i18n.get_string("user_properties.label.first_name"), name_layout)
        form_layout.addRow(self.i18n.get_string("user_properties.label.last_name"), self.last_name_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.display_name"), self.display_name_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.description"), self.description_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.office"), self.office_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.email"), self.email_edit)

        layout.addLayout(form_layout)
        layout.addStretch()

    def _create_layout(self):
        """Create the main dialog layout"""
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

    def _load_contact_data(self):
        """Load contact data from Active Directory."""
        self.contact_props, self.schema_info = get_all_contact_attributes_with_schema_info(self.samba_conn, self.contact_dn)
        if not self.contact_props:
            self.logger.error(f"Could not load properties for contact: {self.contact_dn}")
            return

        self.editable_contact_props = copy.deepcopy(self.contact_props)
        self._populate_all_tabs()

    def _populate_all_tabs(self):
        """Populate all tabs with data from self.contact_props."""
        self.first_name_edit.setText(self.contact_props.get('givenName', [''])[0])
        self.initials_edit.setText(self.contact_props.get('initials', [''])[0])
        self.last_name_edit.setText(self.contact_props.get('sn', [''])[0])
        self.display_name_edit.setText(self.contact_props.get('displayName', [''])[0])
        self.description_edit.setText(self.contact_props.get('description', [''])[0])
        self.office_edit.setText(self.contact_props.get('physicalDeliveryOfficeName', [''])[0])
        self.email_edit.setText(self.contact_props.get('mail', [''])[0])

        self.display_name = self.contact_props.get('displayName', [''])[0] or self.contact_props.get('cn', ['Contact'])[0]
        self.setWindowTitle(f"{self.display_name} Properties")
        self.display_name_header.setText(self.display_name)

    def _connect_signals(self):
        """Connect signals to slots."""
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)

    def apply_changes(self):
        """Apply the changes made in the dialog to the local contact object."""
        self.logger.info("Applying changes for contact object (read-only mode)")
        
        # Update local properties from UI (contact doesn't have real-time updates yet)
        self._update_local_properties_from_ui()
        
        # Show read-only dialog but keep dialog open
        QMessageBox.information(
            self, 
            "Read-Only Mode", 
            "This application is currently in read-only mode. Changes cannot be saved to Active Directory."
        )
    
    def _update_local_properties_from_ui(self):
        """Update local contact properties from UI fields."""
        # Update contact props from UI - contact properties would need individual field mapping
        # For now, just sync what we have
        self.contact_props.update(self.editable_contact_props)

    def accept(self):
        """Override accept to show read-only dialog before closing."""
        # Update local properties from UI
        self._update_local_properties_from_ui()
        
        # Show read-only dialog
        QMessageBox.information(
            self, 
            "Read-Only Mode", 
            "This application is currently in read-only mode. Changes cannot be saved to Active Directory."
        )
        
        # Close the dialog
        super().accept()

    def reject(self):
        super().reject()

