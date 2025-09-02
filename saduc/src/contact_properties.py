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
import ldap
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QDialogButtonBox, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from i18n_manager import I18nManager
from samba_backend import get_all_contact_attributes_with_schema_info, update_object_attributes
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
        self.is_advanced_view = advanced_view
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

        if self.is_advanced_view:
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.contact_dn, self.contact_props), "Object")
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.contact_dn), "Security")
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.contact_dn), "Attribute Editor")
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.contact_dn, self.contact_props), self.i18n.get_string("user_properties.tab.email"))

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        # Initially disable the Apply button
        self.button_box.button(QDialogButtonBox.Apply).setEnabled(False)

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
        self.button_box.accepted.connect(self._accept_dialog)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        
        # Connect change signals for all editable widgets
        self._connect_change_signals()
    
    def _connect_change_signals(self):
        """Connect change signals from UI widgets to change detection."""
        # Map widgets to their corresponding LDAP attributes
        self.widget_to_attribute_map = {
            self.first_name_edit: 'givenName',
            self.initials_edit: 'initials', 
            self.last_name_edit: 'sn',
            self.display_name_edit: 'displayName',
            self.description_edit: 'description',
            self.office_edit: 'physicalDeliveryOfficeName',
            self.email_edit: 'mail'
        }
        
        # Connect textChanged signals
        for widget in self.widget_to_attribute_map.keys():
            if hasattr(widget, 'textChanged'):
                widget.textChanged.connect(self._on_widget_change)
    
    def _on_widget_change(self):
        """Handle widget value changes."""
        sender = self.sender()
        if sender in self.widget_to_attribute_map:
            attr_name = self.widget_to_attribute_map[sender]
            new_value = sender.text()
            
            # Update the editable properties
            self.editable_contact_props[attr_name] = [new_value] if new_value else []
            
            # Check for changes and enable/disable Apply button
            self._check_for_changes()
    
    def _check_for_changes(self):
        """Check if there are any changes and enable/disable the Apply button accordingly."""
        has_changes = False
        
        # Check if editable properties differ from original properties
        for attr_name, new_values in self.editable_contact_props.items():
            old_values = self.contact_props.get(attr_name, [])
            if old_values != new_values:
                has_changes = True
                break
        
        # Enable/disable the Apply button based on changes
        self.button_box.button(QDialogButtonBox.Apply).setEnabled(has_changes)

    def apply_changes(self):
        """Apply the changes made in the dialog to Active Directory."""
        self.logger.info("Applying changes for contact to Active Directory")
        
        # Build LDAP modifications
        modifications = []
        READ_ONLY_ATTRIBUTES = {
            'objectGUID', 'objectSid', 'whenCreated', 'whenChanged',
            'uSNCreated', 'uSNChanged', 'systemFlags', 'instanceType', 
            'objectClass', 'objectCategory', 'distinguishedName'
        }
        
        # Required attributes for contacts
        REQUIRED_ATTRIBUTES = {'cn', 'objectClass', 'objectCategory'}
        
        # Validate required attributes first
        validation_errors = []
        for attr_name, new_values in self.editable_contact_props.items():
            old_values = self.contact_props.get(attr_name, [])
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
            # Reset invalid changes back to original values
            self.editable_contact_props = copy.deepcopy(self.contact_props)
            self._populate_all_tabs()
            return
        
        # Build modifications for valid changes
        for attr_name, new_values in self.editable_contact_props.items():
            old_values = self.contact_props.get(attr_name, [])
            
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
        
        # Apply modifications if any exist
        if modifications:
            success, message = update_object_attributes(self.samba_conn, self.contact_dn, modifications)
            
            if success:
                # Reload data from Active Directory to get fresh state
                self._load_contact_data()
                
                # Disable the Apply button since changes are now saved
                self.button_box.button(QDialogButtonBox.Apply).setEnabled(False)
                
                QMessageBox.information(
                    self, 
                    self.i18n.get_string("dialog.common.success.title"),
                    f"Successfully applied {len(modifications)} changes."
                )
                self.logger.info(f"Successfully applied {len(modifications)} changes to contact {self.contact_dn}")
            else:
                QMessageBox.critical(
                    self, 
                    self.i18n.get_string("dialog.common.error.title"),
                    f"Failed to apply changes: {message}"
                )
                self.logger.error(f"Failed to apply changes to contact {self.contact_dn}: {message}")
        else:
            # No dialog shown for "no changes" case - just silently complete
            pass
    
    def _accept_dialog(self):
        """Handle OK button click - only apply changes if there are any."""
        # Check if there are any changes
        has_changes = False
        for attr_name, new_values in self.editable_contact_props.items():
            old_values = self.contact_props.get(attr_name, [])
            if old_values != new_values:
                has_changes = True
                break
        
        # Only apply changes if there are any
        if has_changes:
            self.apply_changes()
        
        # Close the dialog
        self.accept()
    
    def accept(self):
        """Override accept to close the dialog."""
        super().accept()

    def reject(self):
        super().reject()

