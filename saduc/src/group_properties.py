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
from samba_backend import get_all_group_attributes_with_schema_info, BASE_DN, get_paged_results, get_base_dn
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
        self.advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.group_props = {}
        self.schema_info = {}
        self.editable_group_props = {}

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
        self.description_edit = QTextEdit()
        self.group_scope_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.scope"))
        self.domain_local_radio = QRadioButton(self.i18n.get_string("group_properties.radio.domain_local"))
        self.global_radio = QRadioButton(self.i18n.get_string("group_properties.radio.global"))
        self.universal_radio = QRadioButton(self.i18n.get_string("group_properties.radio.universal"))
        self.group_type_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.type"))
        self.security_radio = QRadioButton(self.i18n.get_string("group_properties.radio.security"))
        self.distribution_radio = QRadioButton(self.i18n.get_string("group_properties.radio.distribution"))

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

        header_layout = QHBoxLayout()
        icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'group.png')
        self.group_icon_label.setPixmap(QIcon(icon_path).pixmap(32, 32))
        self.group_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.group_icon_label)
        header_layout.addWidget(self.group_name_header)
        header_layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)

        form_layout = QFormLayout()
        self.description_edit.setFixedHeight(60)
        form_layout.addRow(self.i18n.get_string("group_properties.label.group_name"), self.group_name_edit)
        form_layout.addRow(self.i18n.get_string("group_properties.label.description"), self.description_edit)

        scope_layout = QHBoxLayout()
        scope_layout.addWidget(self.domain_local_radio)
        scope_layout.addWidget(self.global_radio)
        scope_layout.addWidget(self.universal_radio)
        self.group_scope_box.setLayout(scope_layout)
        form_layout.addRow(self.group_scope_box)

        type_layout = QHBoxLayout()
        type_layout.addWidget(self.security_radio)
        type_layout.addWidget(self.distribution_radio)
        self.group_type_box.setLayout(type_layout)
        form_layout.addRow(self.group_type_box)

        layout.addLayout(header_layout)
        layout.addWidget(separator)
        layout.addLayout(form_layout)
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
        if self.advanced_view:
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.group_dn, self.group_props), self.i18n.get_string("user_properties.tab.object"))
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.group_dn), self.i18n.get_string("user_properties.tab.security"))
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.group_dn), "Attribute Editor")
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.group_dn, self.group_props), self.i18n.get_string("user_properties.tab.email"))

    def _connect_signals(self):
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        
        # Members tab signals
        self.add_member_btn.clicked.connect(self._add_member)
        self.remove_member_btn.clicked.connect(self._remove_member)
        self.members_table.itemSelectionChanged.connect(self._on_member_selection_changed)

        self.widget_to_attribute_map = {
            self.group_name_edit: 'cn',
            self.description_edit: 'description',
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

    def apply_changes(self):
        """Apply the changes made in the dialog to the local group object."""
        self.logger.info("Applying changes for group object (read-only mode)")
        
        # Properties are already updated via _on_attribute_change()
        # Just sync editable props to main props for other tabs
        self.group_props.update(self.editable_group_props)
        
        # Show read-only dialog but keep dialog open
        QMessageBox.information(
            self, 
            "Read-Only Mode", 
            "This application is currently in read-only mode. Changes cannot be saved to Active Directory."
        )
    
    def accept(self):
        """Override accept to show read-only dialog before closing."""
        # Sync editable props to main props
        self.group_props.update(self.editable_group_props)
        
        # Show read-only dialog
        QMessageBox.information(
            self, 
            "Read-Only Mode", 
            "This application is currently in read-only mode. Changes cannot be saved to Active Directory."
        )
        
        # Close the dialog
        super().accept()
    
    def _on_member_selection_changed(self):
        """Enable/disable Remove button based on selection."""
        selected_items = self.members_table.selectedItems()
        self.remove_member_btn.setEnabled(len(selected_items) > 0)
    
    def _add_member(self):
        """Add a new member to the group using the universal search dialog."""
        from find_dialog import FindObjectsDialog
        from samba_backend import get_base_dn
        
        # Use your existing universal search dialog
        search_base = get_base_dn(self.samba_conn)
        dialog = FindObjectsDialog(self.samba_conn, search_base, self)
        dialog.setWindowTitle("Find Objects to Add to Group")
        
        if dialog.exec_() == QDialog.Accepted:
            # Get selected items from the search results
            selected_items = dialog.results_table.selectedItems()
            if not selected_items:
                QMessageBox.information(self, "Add Member", "Please select an object to add to the group.")
                return
            
            # Get the selected row
            row = selected_items[0].row()
            member_name = dialog.results_table.item(row, 0).text()
            
            # We need to get the DN - this might need to be stored in the search results
            # For now, we'll use the name to construct a basic DN (this is a limitation we need to fix)
            QMessageBox.information(self, "Add Member", f"Selected: {member_name}\n\nNote: Need to enhance search dialog to return DN for proper membership management.")
            
            # TODO: Enhance FindObjectsDialog to store and return object DNs
            self.logger.info(f"Would add member {member_name} to group (need DN from search results)")
    
    def _remove_member(self):
        """Remove selected member from the group."""
        selected_items = self.members_table.selectedItems()
        if not selected_items:
            return
        
        # Get the selected row
        row = selected_items[0].row()
        member_item = self.members_table.item(row, 0)
        if not member_item:
            return
        
        member_dn = member_item.data(Qt.UserRole)
        member_name = member_item.text()
        
        # Confirm removal
        reply = QMessageBox.question(
            self, 
            "Remove Member", 
            f"Are you sure you want to remove '{member_name}' from this group?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remove from table
            self.members_table.removeRow(row)
            
            # Update local group properties
            current_members = self.editable_group_props.get('member', [])
            if isinstance(current_members[0], bytes) if current_members else False:
                current_members = [m.decode('utf-8') for m in current_members]
            
            if member_dn in current_members:
                current_members.remove(member_dn)
                self.editable_group_props['member'] = current_members
            
            self.logger.info(f"Removed member {member_name} from group (local update only)")
            
            # Update button state
            self._on_member_selection_changed()