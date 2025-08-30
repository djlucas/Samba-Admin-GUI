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
        self.is_advanced_view = advanced_view
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
        if self.is_advanced_view:
            self.object_tab = ObjectTab(self.samba_conn, self.container_dn, self.container_props)
            self.tab_widget.addTab(self.object_tab, "Object")
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
        """Apply the changes made in the dialog to Active Directory."""
        self.logger.info("Applying changes for container to Active Directory")
        
        # Build LDAP modifications
        modifications = []
        READ_ONLY_ATTRIBUTES = {
            'objectGUID', 'objectSid', 'whenCreated', 'whenChanged',
            'uSNCreated', 'uSNChanged', 'systemFlags', 'instanceType', 
            'objectClass', 'objectCategory', 'distinguishedName'
        }
        
        # Required attributes for containers/OUs - basic set
        REQUIRED_ATTRIBUTES = {'cn', 'objectClass', 'objectCategory'}
        
        # Validate required attributes first
        validation_errors = []
        for attr_name, new_values in self.editable_container_props.items():
            old_values = self.container_props.get(attr_name, [])
            if old_values == new_values:
                continue
                
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
        for attr_name, new_values in self.editable_container_props.items():
            old_values = self.container_props.get(attr_name, [])
            
            # Skip if values haven't changed or read-only
            if old_values == new_values or attr_name in READ_ONLY_ATTRIBUTES:
                continue
            
            try:
                # Handle empty values (delete attribute)
                if not new_values or (len(new_values) == 1 and not new_values[0].strip()):
                    modifications.append((ldap.MOD_DELETE, attr_name, None))
                else:
                    # Filter out empty strings and encode for LDAP
                    encoded_values = []
                    for value in new_values:
                        if value.strip():
                            encoded_values.append(value.encode('utf-8'))
                    
                    if encoded_values:
                        modifications.append((ldap.MOD_REPLACE, attr_name, encoded_values))
                    else:
                        modifications.append((ldap.MOD_DELETE, attr_name, None))
                        
            except Exception as e:
                self.logger.error(f"Error preparing modification for {attr_name}: {e}")
                continue
        
        # Check for ObjectTab protection changes
        protection_changes_made = False
        protection_success_messages = []
        protection_error_messages = []
        
        if hasattr(self, 'object_tab') and self.object_tab:
            prot_success, prot_message = self.object_tab.apply_protection_changes()
            if prot_message:  # prot_message is None if no change was needed
                protection_changes_made = True
                if prot_success:
                    protection_success_messages.append(prot_message)
                else:
                    protection_error_messages.append(prot_message)
        
        # Apply LDAP attribute modifications if any exist
        ldap_success = True
        if modifications:
            ldap_success, message = update_object_attributes(self.samba_conn, self.container_dn, modifications)
            
            if ldap_success:
                # Update local properties with changes
                self.container_props.update(self.editable_container_props)
                self.logger.info(f"Successfully applied {len(modifications)} LDAP changes to container {self.container_dn}")
            else:
                self.logger.error(f"Failed to apply LDAP changes to container {self.container_dn}: {message}")
        
        # Show results to user
        if protection_error_messages or not ldap_success:
            # Show errors
            error_parts = []
            if not ldap_success:
                error_parts.append(f"LDAP changes failed: {message}")
            if protection_error_messages:
                error_parts.append("Protection changes: " + "; ".join(protection_error_messages))
                
            QMessageBox.critical(
                self, 
                self.i18n.get_string("dialog.common.error.title"),
                "\n\n".join(error_parts)
            )
        elif modifications or protection_changes_made:
            # Show success
            success_parts = []
            if modifications:
                success_parts.append(f"Applied {len(modifications)} attribute changes")
            if protection_success_messages:
                success_parts.append("; ".join(protection_success_messages))
                
            QMessageBox.information(
                self, 
                self.i18n.get_string("dialog.common.success.title"),
                ". ".join(success_parts) + "."
            )
            self.logger.info(f"Successfully applied changes to container {self.container_dn}")
        else:
            # No changes
            QMessageBox.information(
                self, 
                self.i18n.get_string("dialog.common.info.title"),
                self.i18n.get_string("container_properties.apply.no_changes")
            )
