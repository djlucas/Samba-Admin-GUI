#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/printer_properties.py
#
# Description:
# This file contains the dialog for viewing and editing printer properties.
#
# -----------------------------------------------------------------------------

import logging
import os
import copy
import ldap
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QHBoxLayout, QDialogButtonBox, QLabel, QCheckBox, QMessageBox, QTabWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from i18n_manager import I18nManager
from samba_backend import get_all_printer_attributes_with_schema_info, update_object_attributes
from shared_properties_tabs import ObjectTab, SecurityTab, ManagedByTab, EmailTab
from attribute_editor import AttributeEditorTab

class PrinterPropertiesDialog(QDialog):
    """Dialog for viewing and editing printer properties."""
    def __init__(self, samba_conn, printer_dn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.printer_dn = printer_dn
        self.is_advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.printer_props = {}
        self.schema_info = {}
        self.editable_printer_props = {}

        self.setWindowTitle(self.i18n.get_string("printer_properties.window_title"))
        self.setMinimumSize(450, 400)
        self.resize(450, 500)

        self._create_widgets()
        self._create_layout()
        self._load_printer_data()
        self._connect_signals()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()

        self._create_general_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)

    def _create_general_tab(self):
        self.general_tab = QWidget()
        self.printer_name_header = QLabel()
        self.location_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.color_check = QCheckBox(self.i18n.get_string("printer_properties.label.color"))
        self.staple_check = QCheckBox(self.i18n.get_string("printer_properties.label.staple"))
        self.double_sided_check = QCheckBox(self.i18n.get_string("printer_properties.label.double_sided"))
        self.speed_edit = QLineEdit()
        self.resolution_edit = QLineEdit()

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        self._layout_general_tab()

    def _connect_signals(self):
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)

    def _layout_general_tab(self):
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("printer_properties.tab.general"))
        layout = QVBoxLayout(self.general_tab)
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'printer.png')
        pixmap = QPixmap(icon_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(40, 40)
        self.printer_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(icon_label)
        header_layout.addWidget(self.printer_name_header)
        header_layout.addStretch()
        
        form_layout.addRow(header_layout)
        form_layout.addRow(self.i18n.get_string("printer_properties.label.location"), self.location_edit)
        form_layout.addRow(self.i18n.get_string("printer_properties.label.model"), self.model_edit)
        form_layout.addRow(self.i18n.get_string("printer_properties.label.description"), self.description_edit)
        
        checkbox_layout = QVBoxLayout()
        checkbox_layout.addWidget(self.color_check)
        checkbox_layout.addWidget(self.staple_check)
        checkbox_layout.addWidget(self.double_sided_check)
        form_layout.addRow(checkbox_layout)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(self.speed_edit)
        speed_layout.addWidget(QLabel("ppm"))
        form_layout.addRow(self.i18n.get_string("printer_properties.label.speed"), speed_layout)

        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(self.resolution_edit)
        resolution_layout.addWidget(QLabel("dpi"))
        form_layout.addRow(self.i18n.get_string("printer_properties.label.resolution"), resolution_layout)

        layout.addLayout(form_layout)
        layout.addStretch()

    def _load_printer_data(self):
        self.printer_props, self.schema_info = get_all_printer_attributes_with_schema_info(self.samba_conn, self.printer_dn)
        if not self.printer_props:
            self.logger.error(f"Could not load properties for printer: {self.printer_dn}")
            return

        self.editable_printer_props = copy.deepcopy(self.printer_props)

        cn = self.printer_props.get('cn', [''])[0]
        self.printer_name_header.setText(cn)

        self.location_edit.setText(self.printer_props.get('location', [''])[0])
        self.model_edit.setText(self.printer_props.get('driverName', [''])[0])
        self.description_edit.setText(self.printer_props.get('description', [''])[0])
        self.color_check.setChecked(self.printer_props.get('printColor', ['FALSE'])[0].upper() == 'TRUE')
        self.staple_check.setChecked(self.printer_props.get('printStaplingSupported', ['FALSE'])[0].upper() == 'TRUE')
        self.double_sided_check.setChecked(self.printer_props.get('printDuplexSupported', ['FALSE'])[0].upper() == 'TRUE')
        self.speed_edit.setText(self.printer_props.get('printRate', [''])[0])
        self.resolution_edit.setText(self.printer_props.get('printMaxResolutionSupported', [''])[0])

        # Add Managed By tab
        self.tab_widget.addTab(ManagedByTab(self.samba_conn, self.printer_props), self.i18n.get_string("computer_properties.tab.managed_by"))

        if self.is_advanced_view:
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.printer_dn, self.printer_props), "Object")
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.printer_dn), "Security")
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.printer_dn, self.printer_props), self.i18n.get_string("user_properties.tab.email"))
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.printer_dn), "Attribute Editor")

    def apply_changes(self):
        """Apply the changes made in the dialog to Active Directory."""
        self.logger.info(f"Applying changes for printer: {self.printer_dn}")
        
        # Update local properties from UI
        self._update_local_properties_from_ui()
        
        # Build LDAP modifications
        modifications = []
        READ_ONLY_ATTRIBUTES = {
            'objectGUID', 'objectSid', 'whenCreated', 'whenChanged',
            'uSNCreated', 'uSNChanged', 'systemFlags', 'instanceType', 
            'objectClass', 'objectCategory', 'distinguishedName'
        }
        
        # Required attributes for printer objects (printQueue class)
        REQUIRED_ATTRIBUTES = {
            'cn', 'objectClass', 'objectCategory',
            'uNCName', 'printerName', 'serverName', 'shortServerName', 'versionNumber'
        }
        
        # Validate required attributes first
        validation_errors = []
        for attr_name, new_values in getattr(self, 'printer_props', {}).items():
            # Check for attempts to modify read-only attributes
            if attr_name in READ_ONLY_ATTRIBUTES:
                validation_errors.append(f"'{attr_name}' is a system attribute and cannot be modified")
                continue
                
            # Check required attributes are not empty
            if attr_name in REQUIRED_ATTRIBUTES:
                if not new_values or (len(new_values) == 1 and not new_values[0].strip()):
                    validation_errors.append(f"'{attr_name}' is required and cannot be empty")
        
        if validation_errors:
            error_msg = "The following errors must be corrected before saving:\n\n" + "\n".join(validation_errors)
            QMessageBox.warning(
                self, 
                self.i18n.get_string("dialog.common.error.title"),
                error_msg
            )
            return
        
        # Build modifications for valid changes
        for attr_name, new_values in getattr(self, 'printer_props', {}).items():
            if attr_name in READ_ONLY_ATTRIBUTES:
                continue
                
            try:
                if not new_values or (len(new_values) == 1 and not new_values[0].strip()):
                    modifications.append((ldap.MOD_DELETE, attr_name, None))
                else:
                    encoded_values = [v.encode('utf-8') for v in new_values if v.strip()]
                    if encoded_values:
                        modifications.append((ldap.MOD_REPLACE, attr_name, encoded_values))
                    else:
                        modifications.append((ldap.MOD_DELETE, attr_name, None))
            except Exception as e:
                self.logger.error(f"Error preparing modification for {attr_name}: {e}")
        
        # Apply modifications
        if modifications:
            success, message = update_object_attributes(self.samba_conn, self.printer_dn, modifications)
            
            if success:
                QMessageBox.information(
                    self, 
                    self.i18n.get_string("dialog.common.success.title"),
                    self.i18n.get_text("printer_properties.apply.success", str(len(modifications)))
                )
                self.logger.info(f"Successfully applied {len(modifications)} changes to printer {self.printer_dn}")
            else:
                QMessageBox.critical(
                    self, 
                    self.i18n.get_string("dialog.common.error.title"),
                    self.i18n.get_string("printer_properties.apply.error") + "\n\n" + message
                )
                self.logger.error(f"Failed to apply changes to printer {self.printer_dn}: {message}")
        else:
            QMessageBox.information(
                self, 
                self.i18n.get_string("dialog.common.info.title"),
                self.i18n.get_string("printer_properties.apply.no_changes")
            )
    
    def _update_local_properties_from_ui(self):
        """Update local printer properties from UI fields."""
        self.printer_props['location'] = [self.location_edit.text()]
        self.printer_props['driverName'] = [self.model_edit.text()]  
        self.printer_props['description'] = [self.description_edit.text()]
        self.printer_props['printColor'] = ['TRUE' if self.color_check.isChecked() else 'FALSE']
        self.printer_props['printStaplingSupported'] = ['TRUE' if self.staple_check.isChecked() else 'FALSE']
        self.printer_props['printDuplexSupported'] = ['TRUE' if self.double_sided_check.isChecked() else 'FALSE']
        self.printer_props['printRate'] = [self.speed_edit.text()]
        self.printer_props['printMaxResolutionSupported'] = [self.resolution_edit.text()]
    
    def accept(self):
        """Override accept to apply changes before closing."""
        # Apply changes first
        self.apply_changes()
        
        # Close the dialog
        super().accept()