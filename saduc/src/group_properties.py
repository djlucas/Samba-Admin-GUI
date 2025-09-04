#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/group_properties.py
#
# Description:
# This file contains the dialog for viewing and editing group properties.
#
# -----------------------------------------------------------------------------

import logging
import ldap.dn
import os
import copy
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QRadioButton, QGroupBox, QHBoxLayout, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QPushButton, QFrame, QMessageBox, QTextEdit
)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt

from i18n_manager import I18nManager
from samba_backend import get_all_group_attributes_with_schema_info, BASE_DN, get_paged_results, get_base_dn, update_object_attributes
from rotating_tab_widget import RotatingTabWidget
from tab_styles import STYLE_DEFAULT
from shared_properties_tabs import ObjectTab, SecurityTab, ManagedByTab, MemberOfTab, EmailTab
from attribute_editor import AttributeEditorTab

# Constants for groupType bits
GROUP_TYPE_SECURITY = 0x80000000
GROUP_TYPE_UNIVERSAL = 0x00000008
GROUP_TYPE_GLOBAL = 0x00000002
GROUP_TYPE_DOMAIN_LOCAL = 0x00000004

# Constants for userAccountControl bits
UAC_ACCOUNT_DISABLED = 0x0002

class GroupPropertiesDialog(QDialog):
    """Dialog for viewing and editing group properties."""
    def __init__(self, samba_conn, group_dn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.group_dn = group_dn
        self.is_advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.group_props = {}
        self.schema_info = {}
        self.editable_group_props = {}
        
        # Track pending member changes
        self.pending_member_additions = set()  # Member DNs to add
        self.pending_member_removals = set()   # Member DNs to remove
        self.original_members = set()          # Original member DNs
        
        # Set base DN for path display
        self.base_dn = BASE_DN

        self.setWindowTitle(self.i18n.get_string("group_properties.window_title"))
        self.setMinimumSize(450, 400)

        self.icon_cache = {}
        self._load_icons()
        self._create_widgets()
        self._create_layout()
        self._load_group_data()
        self._connect_signals()

    def _load_icons(self):
        """Loads icons used for the members list."""
        icons = {
            "User": "user.png",
            "Disabled User": "user_disable.png",
            "Group": "group.png",
            "Computer": "computer.png",
            "Foreign Security Principal": "user_foreign.png",
            "Unknown": "question_mark.png"
        }
        for name, path in icons.items():
            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', path)
            if os.path.exists(icon_path):
                self.icon_cache[name] = QIcon(icon_path)
            else:
                self.logger.warning(f"Icon not found for {name} at {icon_path}")

    def _create_widgets(self):
        self.tab_widget = RotatingTabWidget(logger=self.logger)
        self.tab_widget.setTabStyle(STYLE_DEFAULT)
        
        # Tabs
        self.general_tab = QWidget()
        self.members_tab = QWidget()

        # General Tab Widgets
        self.group_icon_label = QLabel()
        self.group_name_header = QLabel()
        self.group_name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.group_scope_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.scope"))
        self.domain_local_radio = QRadioButton(self.i18n.get_string("group_properties.radio.domain_local"))
        self.global_radio = QRadioButton(self.i18n.get_string("group_properties.radio.global"))
        self.universal_radio = QRadioButton(self.i18n.get_string("group_properties.radio.universal"))
        self.group_type_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.type"))
        self.security_radio = QRadioButton(self.i18n.get_string("group_properties.radio.security"))
        self.distribution_radio = QRadioButton(self.i18n.get_string("group_properties.radio.distribution"))
        self.notes_edit = QTextEdit()

        # Members Tab Widgets
        self.members_table = QTableWidget()
        self.add_member_btn = QPushButton(self.i18n.get_string("group_properties.button.add"))
        self.remove_member_btn = QPushButton(self.i18n.get_string("group_properties.button.remove"))
        self.remove_member_btn.setEnabled(False)

        # Dialog Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        # Add tabs to the tab widget
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("group_properties.tab.general"))
        self.tab_widget.addTab(self.members_tab, self.i18n.get_string("group_properties.tab.members"))

        self._layout_general_tab()
        self._layout_members_tab()

    def _layout_general_tab(self):
        layout = QVBoxLayout(self.general_tab)

        # Header with icon and group name
        header_layout = QHBoxLayout()
        icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'group.png')
        self.group_icon_label.setPixmap(QIcon(icon_path).pixmap(32, 32))
        self.group_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.group_icon_label)
        header_layout.addWidget(self.group_name_header)
        header_layout.addStretch()

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)

        # Form fields
        form_layout = QFormLayout()
        form_layout.addRow(self.i18n.get_string("group_properties.label.group_name"), self.group_name_edit)
        form_layout.addRow(self.i18n.get_string("group_properties.label.description"), self.description_edit)
        form_layout.addRow(self.i18n.get_string("group_properties.label.email"), self.email_edit)

        # Group scope and type side by side
        scope_type_layout = QHBoxLayout()
        
        # Group scope (left side)
        scope_layout = QVBoxLayout()
        scope_layout.addWidget(self.domain_local_radio)
        scope_layout.addWidget(self.global_radio)
        scope_layout.addWidget(self.universal_radio)
        self.group_scope_box.setLayout(scope_layout)
        
        # Group type (right side)
        type_layout = QVBoxLayout()
        type_layout.addWidget(self.security_radio)
        type_layout.addWidget(self.distribution_radio)
        self.group_type_box.setLayout(type_layout)
        
        # Add both group boxes side by side
        scope_type_layout.addWidget(self.group_scope_box)
        scope_type_layout.addWidget(self.group_type_box)
        scope_type_layout.addStretch()

        # Notes field
        notes_layout = QVBoxLayout()
        notes_label = QLabel(self.i18n.get_string("group_properties.label.notes"))
        self.notes_edit.setFixedHeight(80)
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.notes_edit)

        # Put it all together
        layout.addLayout(header_layout)
        layout.addWidget(separator)
        layout.addLayout(form_layout)
        layout.addLayout(scope_type_layout)
        layout.addLayout(notes_layout)
        layout.addStretch()

    def _layout_members_tab(self):
        members_layout = QVBoxLayout(self.members_tab)
        
        # Add table
        members_layout.addWidget(self.members_table)
        self.members_table.setColumnCount(2)
        self.members_table.setHorizontalHeaderLabels([
            self.i18n.get_string("group_properties.header.name"),
            self.i18n.get_string("group_properties.header.folder")
        ])
        self.members_table.verticalHeader().hide()
        self.members_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        header_members = self.members_table.horizontalHeader()
        header_members.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_members.setSectionResizeMode(1, QHeaderView.Stretch)
        
        # Add buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_member_btn)
        button_layout.addWidget(self.remove_member_btn)
        button_layout.addStretch()
        members_layout.addLayout(button_layout)

    def _get_display_path_from_dn(self, dn_string):
        base_dn = get_base_dn(self.samba_conn)
        if not base_dn:
            return dn_string
            
        domain_parts = [p.split('=')[1] for p in base_dn.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)

        try:
            dn_parts = ldap.dn.str2dn(dn_string)
            if len(dn_parts) <= 1:
                return domain

            parent_dn_parts = dn_parts[1:]
            parent_dn_string = ldap.dn.dn2str(parent_dn_parts)

            base_dn_parts = ldap.dn.str2dn(base_dn)

            len_parent = len(parent_dn_parts)
            len_base = len(base_dn_parts)

            if len_parent < len_base:
                 relative_parts = parent_dn_parts
            else:
                if parent_dn_parts[len_parent-len_base:] == base_dn_parts:
                    relative_parts = parent_dn_parts[:len_parent-len_base]
                else:
                    relative_parts = parent_dn_parts

            if not relative_parts:
                return domain

            path_components = [rdn[0][1] for rdn in reversed(relative_parts)]
            return f"{domain}/{'/'.join(path_components)}"

        except Exception as e:
            self.logger.warning(f"Could not parse DN '{dn_string}' to create display path: {e}")
            try:
                return ldap.dn.dn2str(ldap.dn.str2dn(dn_string)[1:])
            except:
                return dn_string

    def _load_group_data(self):
        """Load group data from Active Directory, including schema info."""
        self.group_props, self.schema_info = get_all_group_attributes_with_schema_info(self.samba_conn, self.group_dn)
        if not self.group_props:
            self.logger.error(f"Could not load properties for group: {self.group_dn}")
            return

        self.editable_group_props = copy.deepcopy(self.group_props)
        self._populate_all_tabs()

    def _populate_all_tabs(self):
        """Populate all tabs with data from self.group_props."""
        group_props = self.group_props
        self.logger.debug(f"Group properties loaded: {group_props}")

        # General Tab
        cn = group_props.get('cn', [''])[0]
        self.group_name_header.setText(cn)
        self.group_name_edit.setText(cn)
        self.description_edit.setText(group_props.get('description', [''])[0])
        self.email_edit.setText(group_props.get('mail', [''])[0])
        self.notes_edit.setText(group_props.get('info', [''])[0])

        group_type = int(group_props.get('groupType', ['0'])[0])

        if group_type & GROUP_TYPE_SECURITY:
            self.security_radio.setChecked(True)
        else:
            self.distribution_radio.setChecked(True)

        if group_type & GROUP_TYPE_UNIVERSAL:
            self.universal_radio.setChecked(True)
        elif group_type & GROUP_TYPE_GLOBAL:
            self.global_radio.setChecked(True)
        elif group_type & GROUP_TYPE_DOMAIN_LOCAL:
            self.domain_local_radio.setChecked(True)

        # Members Tab
        self.members_table.setRowCount(0)

        # 1. Get secondary members from the 'member' attribute
        member_dns = group_props.get('member', [])
        self.logger.info(f"Found {len(member_dns)} secondary members in 'member' attribute for group {self.group_dn}.")

        # 2. Get primary members by searching for users/computers with the group's RID
        primary_member_dns = []
        group_rid = group_props.get('primaryGroupToken', [None])[0]
        if group_rid:
            self.logger.info(f"Group RID is {group_rid}. Searching for primary members.")
            primary_member_filter = f"(&(primaryGroupID={group_rid})(|(objectClass=user)(objectClass=computer)))"
            search_base = get_base_dn(self.samba_conn)
            if search_base:
                primary_members_results = get_paged_results(self.samba_conn, search_base, ldap.SCOPE_SUBTREE, primary_member_filter, []) # No attributes needed, just DNs
            else:
                primary_members_results = []
            primary_member_dns = [dn for dn, attrs in primary_members_results if dn is not None]
            self.logger.info(f"Found {len(primary_member_dns)} primary members for group RID {group_rid}.")

        # 3. Combine member lists and remove duplicates
        all_member_dns = list(set(member_dns + primary_member_dns))
        self.logger.info(f"Total unique members to fetch: {len(all_member_dns)}")
        
        # Initialize original members set for change tracking
        self.original_members = set(all_member_dns)
        # Clear pending changes
        self.pending_member_additions.clear()
        self.pending_member_removals.clear()

        # 4. Fetch details for all members individually to ensure robustness
        members = []
        if not all_member_dns:
            self.logger.info(f"Group {self.group_dn} has no members to display.")
        else:
            attributes = ['displayName', 'cn', 'objectClass', 'userAccountControl']
            for member_dn in all_member_dns:
                try:
                    # Use a SCOPE_BASE search for maximum efficiency and reliability
                    res = self.samba_conn.search_s(member_dn, ldap.SCOPE_BASE, '(objectClass=*)', attributes)
                    if res:
                        # search_s for SCOPE_BASE returns a list with one item: [(dn, attrs)]
                        members.append(res[0])
                except ldap.LDAPError as e:
                    self.logger.error(f"LDAP error fetching details for member DN '{member_dn}': {e}")

        self.logger.info(f"Fetched details for {len(members)} members of group {self.group_dn}")

        for member_dn, entry in members:
            if not isinstance(entry, dict):
                self.logger.warning(f"Skipping non-dict entry for member: {member_dn}")
                continue
            
            # Skip members that are staged for removal
            if member_dn in self.pending_member_removals:
                continue
                
            try:
                name = (entry.get('displayName') or entry.get('cn', [b'']))[0].decode('utf-8')
                obj_classes = [oc.decode('utf-8') for oc in entry.get('objectClass', [])]
                uac = int(entry.get('userAccountControl', [b'0'])[0].decode('utf-8'))

                icon_key = "Unknown"
                if 'foreignSecurityPrincipal' in obj_classes:
                    icon_key = "Foreign Security Principal"
                elif 'group' in obj_classes:
                    icon_key = "Group"
                elif 'computer' in obj_classes:
                    icon_key = "Computer" # No disabled state for computers in this view
                elif 'user' in obj_classes:
                    icon_key = "Disabled User" if (uac & UAC_ACCOUNT_DISABLED) else "User"

                icon = self.icon_cache.get(icon_key)
                name_item = QTableWidgetItem(name)
                if icon:
                    name_item.setIcon(icon)
                # Store the member DN in UserRole for later retrieval
                name_item.setData(Qt.UserRole, member_dn)

                row = self.members_table.rowCount()
                self.members_table.insertRow(row)
                self.members_table.setItem(row, 0, name_item)
                display_path = self._get_display_path_from_dn(member_dn)
                self.members_table.setItem(row, 1, QTableWidgetItem(display_path))

            except Exception as e:
                self.logger.error(f"Could not process member {member_dn}: {e}")

        # Add Member Of tab
        self.tab_widget.addTab(MemberOfTab(self.samba_conn, self.group_dn, group_props), self.i18n.get_string("group_properties.tab.member_of"))

        # Add Managed By tab
        self.tab_widget.addTab(ManagedByTab(self.samba_conn, group_props), self.i18n.get_string("computer_properties.tab.managed_by"))

        # Add advanced tabs if enabled
        if self.is_advanced_view:
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.group_dn, self.group_props), self.i18n.get_string("user_properties.tab.object"))
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.group_dn), self.i18n.get_string("user_properties.tab.security"))
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.group_dn), "Attribute Editor")
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.group_dn, self.group_props), self.i18n.get_string("user_properties.tab.email"))

    def _connect_signals(self):
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        
        # Initially disable Apply button until changes are made
        self.apply_button = self.button_box.button(QDialogButtonBox.Apply)
        self.apply_button.setEnabled(False)
        
        # Connect change signals
        self._connect_change_signals()
        
        # Members tab signals
        self.add_member_btn.clicked.connect(self._add_member)
        self.remove_member_btn.clicked.connect(self._remove_member)
        self.members_table.itemSelectionChanged.connect(self._on_member_selection_changed)

        self.widget_to_attribute_map = {
            self.group_name_edit: 'cn',
            self.description_edit: 'description',
            self.email_edit: 'mail',
            self.notes_edit: 'info',
            self.domain_local_radio: 'groupType',
            self.global_radio: 'groupType',
            self.universal_radio: 'groupType',
            self.security_radio: 'groupType',
            self.distribution_radio: 'groupType',
        }

        for widget, attr_name in self.widget_to_attribute_map.items():
            if isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._on_attribute_change)
            elif isinstance(widget, QTextEdit):
                widget.textChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QRadioButton):
                widget.toggled.connect(self._on_attribute_change)

    def _on_attribute_change(self):
        """Handle changes to any attribute field."""
        sender = self.sender()
        if sender in self.widget_to_attribute_map:
            attr_name = self.widget_to_attribute_map[sender]
            
            if attr_name == 'groupType':
                current_type = int(self.editable_group_props.get('groupType', ['0'])[0])
                
                # Handle scope
                if self.domain_local_radio.isChecked():
                    new_scope = GROUP_TYPE_DOMAIN_LOCAL
                elif self.global_radio.isChecked():
                    new_scope = GROUP_TYPE_GLOBAL
                elif self.universal_radio.isChecked():
                    new_scope = GROUP_TYPE_UNIVERSAL
                else: # default
                    new_scope = GROUP_TYPE_GLOBAL

                # Handle type
                if self.security_radio.isChecked():
                    new_type = GROUP_TYPE_SECURITY
                else:
                    new_type = 0
                
                new_value = str(new_type | new_scope)

            else: # For cn and description
                if isinstance(sender, QLineEdit):
                    new_value = sender.text()
                elif isinstance(sender, QTextEdit):
                    new_value = sender.toPlainText()
                else:
                    new_value = ''

            if self.editable_group_props.get(attr_name, [''])[0] != new_value:
                self.logger.debug(f"Attribute '{attr_name}' changed from '{self.editable_group_props.get(attr_name, [''])[0]}' to '{new_value}'")
                self.editable_group_props[attr_name] = [new_value]

    def _check_for_changes(self):
        """Check if there are any pending changes and update Apply button state."""
        has_changes = False
        
        # Simple comparison of original vs current values
        for attr_name, original_values in self.group_props.items():
            current_values = self.editable_group_props.get(attr_name, [])
            if current_values != original_values:
                has_changes = True
                break
        
        # Check for pending member changes
        if not has_changes:
            if self.pending_member_additions or self.pending_member_removals:
                has_changes = True
        
        # Enable/disable Apply button based on changes
        self.apply_button.setEnabled(has_changes)
    
    def _connect_change_signals(self):
        """Connect all input widgets to check for changes."""
        # Get all widgets that might exist and connect their change signals
        text_widget_names = [
            'group_name_edit', 'description_edit', 'email_edit', 'notes_edit'
        ]
        
        for widget_name in text_widget_names:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                if hasattr(widget, 'textChanged'):
                    widget.textChanged.connect(self._check_for_changes)
        
        # Connect checkbox changes  
        checkbox_widget_names = [
            'security_group_radio', 'distribution_group_radio'
        ]
        
        for widget_name in checkbox_widget_names:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                if hasattr(widget, 'toggled'):
                    widget.toggled.connect(self._check_for_changes)

    def apply_changes(self):
        """Apply the changes made in the dialog to Active Directory."""
        self.logger.info("Applying changes for group to Active Directory")
        
        # Build list of LDAP modifications
        modifications = []
        
        # Define read-only attributes
        READ_ONLY_ATTRIBUTES = {
            'objectGUID', 'objectSid', 'sAMAccountType',
            'whenCreated', 'whenChanged', 'lastLogon', 'lastLogonTimestamp', 
            'uSNCreated', 'uSNChanged', 'logonCount', 'badPwdCount',
            'systemFlags', 'instanceType', 'objectClass', 'objectCategory',
            'distinguishedName', 'canonicalName', 'parentGUID'
        }
        
        # Required attributes that cannot be empty
        REQUIRED_ATTRIBUTES = {'groupType', 'cn', 'objectCategory', 'objectClass', 'sAMAccountName'}
        
        # Validate required attributes first
        validation_errors = []
        for attr_name, new_values in self.editable_group_props.items():
            old_values = self.group_props.get(attr_name, [])
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
            self.editable_group_props = copy.deepcopy(self.group_props)
            self._populate_tabs()
            return
        
        # Build modifications for valid changes
        for attr_name, new_values in self.editable_group_props.items():
            old_values = self.group_props.get(attr_name, [])
            
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
        
        # Collect changes from tabs
        self._collect_tab_changes(modifications)
        
        # Required attributes that cannot be empty
        REQUIRED_ATTRIBUTES = {'groupType', 'cn', 'objectCategory', 'objectClass', 'sAMAccountName'}
        
        # Validate required attributes first
        validation_errors = []
        for attr_name, new_values in self.editable_group_props.items():
            old_values = self.group_props.get(attr_name, [])
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
            self.editable_group_props = copy.deepcopy(self.group_props)
            self._populate_tabs()
            return
        
        # Build modifications for valid changes
        for attr_name, new_values in self.editable_group_props.items():
            old_values = self.group_props.get(attr_name, [])
            
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
            success, message = update_object_attributes(self.samba_conn, self.group_dn, modifications)
            
            if success:
                # Update local properties with changes
                self.group_props.update(self.editable_group_props)
                
                QMessageBox.information(
                    self, 
                    self.i18n.get_string("dialog.common.success.title"),
                    self.i18n.get_text("group_properties.apply.success", str(len(modifications)))
                )
                
                self.logger.info(f"Successfully applied {len(modifications)} changes to group {self.group_dn}")
                # Apply member changes if successful
                self._apply_member_changes()
                # Disable Apply button since changes have been applied
                self.apply_button.setEnabled(False)
            else:
                QMessageBox.critical(
                    self, 
                    self.i18n.get_string("dialog.common.error.title"),
                    self.i18n.get_string("group_properties.apply.error") + "\n\n" + message
                )
                self.logger.error(f"Failed to apply changes to group {self.group_dn}: {message}")
        else:
            # Even if no property modifications, still apply member changes
            member_changes_applied = self._apply_member_changes()
            # Disable Apply button if no changes were made
            if not member_changes_applied:
                self.apply_button.setEnabled(False)
    
    def accept(self):
        """Override accept to apply changes before closing."""
        # Apply changes first
        self.apply_changes()
        
        # Close the dialog
        super().accept()
    
    def _apply_member_changes(self):
        """Apply all pending member changes to the directory. Returns True if changes were applied."""
        from samba_backend import add_user_to_group_samba, remove_user_from_group_samba
        
        changes_applied = False
        errors = []
        
        # Debug logging
        self.logger.info(f"Applying member changes: {len(self.pending_member_additions)} additions, {len(self.pending_member_removals)} removals")
        self.logger.info(f"Pending additions: {list(self.pending_member_additions)}")
        self.logger.info(f"Pending removals: {list(self.pending_member_removals)}")
        
        # Apply member additions
        for member_dn in self.pending_member_additions:
            try:
                success, message_key, extra = add_user_to_group_samba(self.samba_conn, member_dn, self.group_dn)
                if success:
                    self.logger.info(f"Applied addition: {member_dn} to group {self.group_dn}")
                    changes_applied = True
                else:
                    message = self.i18n.get_text(message_key, *extra) if extra else self.i18n.get_string(message_key)
                    errors.append(f"Failed to add member {member_dn}: {message}")
                    self.logger.error(f"Failed to add member {member_dn} to group {self.group_dn}: {message}")
            except Exception as e:
                errors.append(f"Failed to add member {member_dn}: {e}")
                self.logger.error(f"Failed to add member {member_dn} to group {self.group_dn}: {e}")
        
        # Apply member removals
        for member_dn in self.pending_member_removals:
            if not member_dn:  # Skip None values
                self.logger.error(f"Skipping None member_dn in removals")
                continue
            try:
                self.logger.info(f"Attempting to remove member: {member_dn}")
                success, message_key, extra = remove_user_from_group_samba(self.samba_conn, member_dn, self.group_dn)
                if success:
                    self.logger.info(f"Applied removal: {member_dn} from group {self.group_dn}")
                    changes_applied = True
                else:
                    message = self.i18n.get_text(message_key, *extra) if extra else self.i18n.get_string(message_key)
                    errors.append(f"Failed to remove member {member_dn}: {message}")
                    self.logger.error(f"Failed to remove member {member_dn} from group {self.group_dn}: {message}")
            except Exception as e:
                errors.append(f"Failed to remove member {member_dn}: {e}")
                self.logger.error(f"Failed to remove member {member_dn} from group {self.group_dn}: {e}")
        
        # Show errors if any occurred
        if errors:
            error_msg = "Some member changes failed:\n\n" + "\n".join(errors)
            QMessageBox.warning(self, 
                self.i18n.get_string("dialog.common.error.title"),
                error_msg)
        
        # Clear pending changes and reload if any changes were applied
        if changes_applied:
            self.pending_member_additions.clear()
            self.pending_member_removals.clear()
            # Refresh group data from AD to show current state
            self.group_props, self.schema_info = get_all_group_attributes_with_schema_info(self.samba_conn, self.group_dn)
            self.editable_group_props = copy.deepcopy(self.group_props)
            self._populate_all_tabs()
        
        return changes_applied
    
    def _collect_tab_changes(self, modifications):
        """Collect changes from individual tabs and add to modifications list."""
        import ldap
        
        # Check each tab in the tab widget for changes
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            
            # Check if this tab has a get_changes method
            if hasattr(tab, 'get_changes'):
                try:
                    tab_changes = tab.get_changes()
                    self.logger.info(f"Tab {i} ({type(tab).__name__}) returned changes: {tab_changes}")
                    
                    # Process each change from the tab
                    for attr_name, new_values in tab_changes.items():
                        old_values = self.group_props.get(attr_name, [])
                        
                        # Skip if values haven't changed
                        if old_values == new_values:
                            continue
                        
                        try:
                            # Handle empty values (delete attribute)
                            if not new_values:
                                modifications.append((ldap.MOD_DELETE, attr_name, None))
                                self.logger.info(f"Will delete attribute {attr_name}")
                            else:
                                # Encode values for LDAP
                                encoded_values = []
                                for value in new_values:
                                    if value:
                                        encoded_values.append(value.encode('utf-8'))
                                
                                if encoded_values:
                                    modifications.append((ldap.MOD_REPLACE, attr_name, encoded_values))
                                    self.logger.info(f"Will replace {attr_name} with {new_values}")
                                else:
                                    modifications.append((ldap.MOD_DELETE, attr_name, None))
                                    self.logger.info(f"Will delete attribute {attr_name}")
                                    
                        except Exception as e:
                            self.logger.error(f"Error preparing modification for {attr_name} from tab: {e}")
                            
                except Exception as e:
                    self.logger.error(f"Error getting changes from tab {i}: {e}")
    
    def _on_member_selection_changed(self):
        """Enable/disable Remove button based on selection."""
        selected_items = self.members_table.selectedItems()
        self.remove_member_btn.setEnabled(len(selected_items) > 0)
    
    def _add_member(self):
        """Add new members to the group (staged until Apply is clicked)."""
        from search_dialogs import StandardSearchDialog
        
        dialog = StandardSearchDialog(self.samba_conn, ['user', 'group', 'computer'], parent=self)
        
        if dialog.exec_() == QDialog.Accepted:
            selected_objects = dialog.get_selected_objects()
            if not selected_objects:
                return
            
            # Debug logging
            self.logger.debug(f"selected_objects type: {type(selected_objects)}")
            self.logger.debug(f"selected_objects length: {len(selected_objects)}")
            for i, obj in enumerate(selected_objects):
                self.logger.debug(f"Object {i}: type={type(obj)}, value={obj}")
                
            # Stage each selected object for addition
            added_count = 0
            for obj in selected_objects:
                obj_dn = obj['dn']
                obj_display = obj['display_text']
                
                # Check if already a member or already staged for addition
                current_members = self._get_current_display_members()
                if obj_dn in current_members:
                    QMessageBox.information(self, self.i18n.get_string("dialog.common.info.title"), 
                                          f"'{obj_display}' is already a member of this group.")
                    continue
                
                # Stage the addition
                self.pending_member_additions.add(obj_dn)
                self.pending_member_removals.discard(obj_dn)  # Remove from removals if it was there
                
                # Add to table with visual indicator
                self._add_member_to_table(obj_dn, obj_display)
                added_count += 1
                
            # Members added silently - no popup needed
            if added_count > 0:
                self._check_for_changes()  # Update Apply button state
    
    def _get_current_display_members(self):
        """Get the current set of members (original + additions - removals)."""
        current_members = self.original_members.copy()
        current_members.update(self.pending_member_additions)
        current_members.difference_update(self.pending_member_removals)
        return current_members
                
    def _add_member_to_table(self, member_dn, display_text=None):
        """Add a member to the members table."""
        if not display_text:
            # Try to get display name from DN
            try:
                import ldap
                attrs = ['cn', 'sAMAccountName', 'displayName', 'objectClass']
                res = self.samba_conn.search_s(member_dn, ldap.SCOPE_BASE, '(objectClass=*)', attrs)
                
                if res and res[0][1]:
                    attrs_dict = res[0][1]
                    cn = attrs_dict.get('cn', [b''])[0].decode('utf-8')
                    sam_account = attrs_dict.get('sAMAccountName', [b''])[0].decode('utf-8')
                    display_name = attrs_dict.get('displayName', [b''])[0].decode('utf-8')
                    object_classes = [cls.decode('utf-8') for cls in attrs_dict.get('objectClass', [])]
                    
                    # Determine object type
                    if 'user' in object_classes:
                        obj_type = 'User'
                    elif 'group' in object_classes:
                        obj_type = 'Group'
                    elif 'computer' in object_classes:
                        obj_type = 'Computer'
                    elif 'contact' in object_classes:
                        obj_type = 'Contact'
                    else:
                        obj_type = 'Object'
                        
                    # Create display text
                    display_text = display_name or cn or sam_account
                    if sam_account and sam_account != display_text:
                        display_text += f" ({sam_account})"
                    display_text += f" [{obj_type}]"
            except:
                # Fallback to DN
                display_text = member_dn.split(',')[0].split('=')[1] if '=' in member_dn else member_dn
        
        # Check if already in table
        for row in range(self.members_table.rowCount()):
            existing_item = self.members_table.item(row, 0)
            if existing_item and existing_item.data(Qt.UserRole) == member_dn:
                return  # Already in table
        
        # Add to table
        row = self.members_table.rowCount()
        self.members_table.insertRow(row)
        
        name_item = QTableWidgetItem(display_text)
        name_item.setData(Qt.UserRole, member_dn)
        self.members_table.setItem(row, 0, name_item)
        
        # Create path display using the same method as existing members
        display_path = self._get_display_path_from_dn(member_dn)
        self.members_table.setItem(row, 1, QTableWidgetItem(display_path))
    
    def _remove_member(self):
        """Remove selected members from the group (staged until Apply is clicked)."""
        selected_items = self.members_table.selectedItems()
        if not selected_items:
            return
        
        # Get all unique selected rows
        selected_rows = list(set(item.row() for item in selected_items))
        selected_rows.sort(reverse=True)  # Process in reverse order to avoid index shifting
        
        for row in selected_rows:
            member_item = self.members_table.item(row, 0)
            if not member_item:
                continue
            
            member_dn = member_item.data(Qt.UserRole)
            if not member_dn:  # Fix for NoneType error
                continue
                
            # Debug logging
            self.logger.info(f"Staging removal of member: {member_dn}")
            
            # Stage the removal
            if member_dn in self.pending_member_additions:
                # If it was a pending addition, just remove it from additions
                self.pending_member_additions.discard(member_dn)
                self.logger.info(f"Removed pending addition: {member_dn}")
            else:
                # If it's an original member, stage for removal and hide from UI
                self.pending_member_removals.add(member_dn)
                self.logger.info(f"Added to pending removals and hidden from UI: {member_dn}")
            
            # Remove from table immediately to hide it from UI
            self.members_table.removeRow(row)
        
        self._check_for_changes()  # Update Apply button state
        self._on_member_selection_changed()