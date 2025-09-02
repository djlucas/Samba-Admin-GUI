#!/usr/bin/env python3
# -*- coding-utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/shared_properties_tabs.py
#
# Description:
# This file contains reusable QWidget tabs for common properties dialogs,
# such as the Object and Security tabs.
#
# -----------------------------------------------------------------------------

import logging
import ldap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QGroupBox,
    QHBoxLayout, QPushButton, QComboBox, QTextEdit, QFrame, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QCheckBox, QListWidgetItem,
    QDateTimeEdit, QApplication, QDialog
)
from PyQt5.QtCore import Qt, QDateTime, QLocale, pyqtSignal
from i18n_manager import I18nManager
from samba_backend import (
    get_user_properties, get_group_properties, get_group_by_rid, 
    update_object_attributes, BASE_DN, get_base_dn,
    get_all_user_attributes_with_schema_info,
    get_all_group_attributes_with_schema_info,
    get_all_computer_attributes_with_schema_info,
    get_all_printer_attributes_with_schema_info,
    get_all_container_attributes_with_schema_info,
    get_all_contact_attributes_with_schema_info,
    get_nt_security_descriptor,
    get_rodc_password_replication_status,
    get_laps_info, set_laps_expiration,
    resolve_sid
)
from acl_utils import check_protection_from_deletion


class ObjectTab(QWidget):
    """A reusable Object tab for properties dialogs."""
    
    def __init__(self, samba_conn, object_dn, parent_props, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.object_dn = object_dn
        self.parent_props = parent_props
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self._create_widgets()
        self._create_layout()
        self._load_object_data()

    def _create_widgets(self):
        self.canonical_name_edit = QLineEdit()
        self.canonical_name_edit.setReadOnly(True)
        self.object_class_label = QLabel()
        self.created_label = QLabel()
        self.modified_label = QLabel()
        self.current_usn_label = QLabel()
        self.original_usn_label = QLabel()
        self.protect_deletion_checkbox = QCheckBox(
            self.i18n.get_string("object_tab.checkbox.protect_from_deletion")
        )
        
        # Connect the checkbox to track changes (not apply immediately)
        self.protect_deletion_checkbox.stateChanged.connect(self._on_protection_checkbox_changed)

    def _create_layout(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.WrapLongRows)

        form_layout.addRow(QLabel(self.i18n.get_string("object_tab.label.object_class")), self.object_class_label)
        form_layout.addRow(QLabel(self.i18n.get_string("object_tab.label.created")), self.created_label)
        form_layout.addRow(QLabel(self.i18n.get_string("object_tab.label.modified")), self.modified_label)

        usn_group = QGroupBox(self.i18n.get_string("object_tab.groupbox.usn"))
        usn_layout = QFormLayout(usn_group)
        usn_layout.addRow(QLabel(self.i18n.get_string("object_tab.label.current_usn")), self.current_usn_label)
        usn_layout.addRow(QLabel(self.i18n.get_string("object_tab.label.original_usn")), self.original_usn_label)

        layout.addWidget(QLabel(self.i18n.get_string("object_tab.label.canonical_name")))
        layout.addWidget(self.canonical_name_edit)
        layout.addSpacing(10)
        layout.addLayout(form_layout)
        layout.addWidget(usn_group)
        layout.addSpacing(10)
        layout.addWidget(self.protect_deletion_checkbox)
        layout.addStretch()

    def _get_canonical_name(self, dn):
        """Converts a DN to a canonical name format."""
        base_dn = get_base_dn(self.samba_conn)
        if not base_dn:
            return dn
            
        domain_parts = [p.split('=')[1] for p in base_dn.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)
        try:
            # This is a simplified conversion and might need to be more robust
            # depending on the complexity of the DNs in the environment.
            parts = ldap.dn.str2dn(dn)
            # Filter out the domain components from the DN parts
            non_domain_parts = [rdn for rdn in parts if not rdn[0][0].lower().startswith('dc')]
            # Reverse the remaining parts and join them with slashes
            reversed_parts = reversed(non_domain_parts)
            path = '/'.join([rdn[0][1] for rdn in reversed_parts])
            return f"{domain}/{path}"
        except Exception as e:
            self.logger.error(f"Failed to parse DN: {dn}. Error: {e}")
            return dn

    def _format_timestamp(self, timestamp):
        """Formats an LDAP timestamp string into a locale-specific date/time."""
        self.logger.debug(f"Formatting timestamp: {timestamp}")
        if not timestamp or not timestamp.endswith('Z'):
            self.logger.warning(f"Invalid timestamp format: {timestamp}")
            return timestamp # Return original if format is unexpected
        try:
            # Manually parse the timestamp string
            year = int(timestamp[0:4])
            month = int(timestamp[4:6])
            day = int(timestamp[6:8])
            hour = int(timestamp[8:10])
            minute = int(timestamp[10:12])
            second = int(timestamp[12:14])

            dt = QDateTime(year, month, day, hour, minute, second, Qt.UTC)

            self.logger.debug(f"Parsed QDateTime: {dt.toString(Qt.ISODateWithMs)}")

            if dt.isValid():
                # Convert to local time and format according to the system's locale
                local_dt = dt.toLocalTime()
                self.logger.debug(f"Converted local QDateTime: {local_dt.toString(Qt.ISODateWithMs)}")
                return QLocale().toString(local_dt, QLocale.LongFormat)
            else:
                self.logger.warning(f"Could not parse timestamp: {timestamp}")
                return timestamp # Return original if parsing fails
        except Exception as e:
            self.logger.error(f"Could not format timestamp '{timestamp}': {e}")
            return timestamp

    def _load_object_data(self):
        object_class = self.parent_props.get('objectClass', [])

        if 'user' in object_class:
            obj_attrs, _ = get_all_user_attributes_with_schema_info(self.samba_conn, self.object_dn)
        elif 'group' in object_class:
            obj_attrs, _ = get_all_group_attributes_with_schema_info(self.samba_conn, self.object_dn)
        elif 'computer' in object_class:
            obj_attrs, _ = get_all_computer_attributes_with_schema_info(self.samba_conn, self.object_dn)
        elif 'printQueue' in object_class:
            obj_attrs, _ = get_all_printer_attributes_with_schema_info(self.samba_conn, self.object_dn)
        elif 'organizationalUnit' in object_class or 'container' in object_class:
            obj_attrs, _ = get_all_container_attributes_with_schema_info(self.samba_conn, self.object_dn)
        elif 'contact' in object_class:
            obj_attrs, _ = get_all_contact_attributes_with_schema_info(self.samba_conn, self.object_dn)
        else:
            obj_attrs = None

        if obj_attrs:
            self.canonical_name_edit.setText(self._get_canonical_name(self.object_dn))
            self.object_class_label.setText(obj_attrs.get('objectClass', [''])[-1])
            self.created_label.setText(self._format_timestamp(obj_attrs.get('whenCreated', [''])[0]))
            self.modified_label.setText(self._format_timestamp(obj_attrs.get('whenChanged', [''])[0]))
            self.current_usn_label.setText(obj_attrs.get('uSNChanged', [''])[0])
            self.original_usn_label.setText(obj_attrs.get('uSNCreated', [''])[0])
            # Check for protection from accidental deletion using real ACL analysis
            try:
                import ldap
                res = self.samba_conn.search_s(self.object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['nTSecurityDescriptor'])
                
                if res and 'nTSecurityDescriptor' in res[0][1]:
                    sd_data = res[0][1]['nTSecurityDescriptor'][0]
                    is_protected = check_protection_from_deletion(sd_data)
                    # Temporarily block signals to avoid triggering _on_protection_changed during loading
                    self.protect_deletion_checkbox.blockSignals(True)
                    self.protect_deletion_checkbox.setChecked(is_protected)
                    self.protect_deletion_checkbox.blockSignals(False)
                    self.logger.debug(f"Protection status for {self.object_dn}: {is_protected}")
                else:
                    self.protect_deletion_checkbox.blockSignals(True)
                    self.protect_deletion_checkbox.setChecked(False)
                    self.protect_deletion_checkbox.blockSignals(False)
                    self.logger.warning(f"Could not retrieve security descriptor for {self.object_dn}")
            except Exception as e:
                self.logger.error(f"Error checking protection status for {self.object_dn}: {e}")
                self.protect_deletion_checkbox.blockSignals(True)
                self.protect_deletion_checkbox.setChecked(False)
                self.protect_deletion_checkbox.blockSignals(False)

    def _on_protection_checkbox_changed(self, state):
        """Handle protection checkbox state changes - just track the change."""
        protect = (state == 2)  # Qt.Checked = 2
        self.logger.debug(f"Protection checkbox changed for {self.object_dn}: {'enabled' if protect else 'disabled'}")
        # The change will be applied when the parent dialog applies all changes
    
    def apply_protection_changes(self):
        """Apply protection changes if the checkbox state differs from current AD state.
        
        Returns:
            tuple: (success: bool, message: str) - Success status and user-friendly message
        """
        from acl_utils import set_protection_from_deletion, check_protection_from_deletion
        
        try:
            # Get current protection state from AD
            current_protected = False
            try:
                res = self.samba_conn.search_s(self.object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['nTSecurityDescriptor'])
                if res and 'nTSecurityDescriptor' in res[0][1]:
                    sd_data = res[0][1]['nTSecurityDescriptor'][0]
                    current_protected = check_protection_from_deletion(sd_data)
            except Exception as e:
                self.logger.warning(f"Could not check current protection state: {e}")
                
            # Get desired state from checkbox
            desired_protected = self.protect_deletion_checkbox.isChecked()
            
            # Apply change if needed
            if current_protected != desired_protected:
                self.logger.info(f"Applying protection change for {self.object_dn}: {current_protected} -> {desired_protected}")
                success = set_protection_from_deletion(self.samba_conn, self.object_dn, desired_protected)
                
                if success:
                    action = "enabled" if desired_protected else "disabled"
                    message = f"Protection from accidental deletion has been {action}."
                    self.logger.info(f"Successfully {action} protection for {self.object_dn}")
                    return True, message
                else:
                    self.logger.error(f"Failed to change protection for {self.object_dn}")
                    return False, "Failed to change protection from accidental deletion."
            else:
                # No change needed
                self.logger.debug(f"No protection change needed for {self.object_dn}")
                return True, None  # None means no change was made
                
        except Exception as e:
            self.logger.error(f"Exception applying protection changes for {self.object_dn}: {e}")
            return False, f"Error changing protection: {str(e)}"


class SecurityTab(QWidget):
    """A reusable, placeholder Security tab."""
    def __init__(self, samba_conn, object_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.object_dn = object_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        self.sd = None
        self.principals = {}

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._load_security_data()

    def _create_widgets(self):
        self.principals_list = QListWidget()
        self.add_button = QPushButton(self.i18n.get_string("security_tab.button.add"))
        self.remove_button = QPushButton(self.i18n.get_string("security_tab.button.remove"))
        self.remove_button.setEnabled(False)  # Initially disabled
        self.permissions_table = QTableWidget()
        self.advanced_button = QPushButton(self.i18n.get_string("security_tab.button.advanced"))

    def _create_layout(self):
        layout = QVBoxLayout(self)

        principals_group = QGroupBox(self.i18n.get_string("security_tab.groupbox.principals"))
        principals_layout = QVBoxLayout(principals_group)
        principals_layout.addWidget(self.principals_list)
        principals_buttons_layout = QHBoxLayout()
        principals_buttons_layout.addWidget(self.add_button)
        principals_buttons_layout.addWidget(self.remove_button)
        principals_buttons_layout.addStretch()
        principals_layout.addLayout(principals_buttons_layout)

        self.permissions_group = QGroupBox(self.i18n.get_string("security_tab.groupbox.permissions").format(""))
        permissions_layout = QVBoxLayout(self.permissions_group)
        self.permissions_table.setColumnCount(3)
        self.permissions_table.setHorizontalHeaderLabels(["Permission", "Allow", "Deny"])
        self.permissions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.permissions_table.verticalHeader().hide()
        permissions_layout.addWidget(self.permissions_table)

        note_label = QLabel(self.i18n.get_string("security_tab.label.note"))
        note_label.setWordWrap(True)
        permissions_layout.addWidget(note_label)
        permissions_layout.addWidget(self.advanced_button)

        layout.addWidget(principals_group)
        layout.addWidget(self.permissions_group)

    def _connect_signals(self):
        self.principals_list.itemSelectionChanged.connect(self._on_principal_selected)
        self.add_button.clicked.connect(self._add_principal)
        self.remove_button.clicked.connect(self._remove_principal)
        self.advanced_button.clicked.connect(self._open_advanced_security)

    def _load_security_data(self):
        self.sd = get_nt_security_descriptor(self.samba_conn, self.object_dn)
        if not self.sd:
            return

        dacl = self.sd['Dacl']
        for ace in dacl['Data']:
            sid = ace['Ace']['Sid'].formatCanonical()
            if sid not in self.principals:
                self.principals[sid] = []
            self.principals[sid].append(ace)

        for sid, aces in self.principals.items():
            principal = resolve_sid(self.samba_conn, sid)
            if principal == sid:
                principal = f"Account Unknown ({sid})"
            item = QListWidgetItem(principal)
            item.setData(Qt.UserRole, sid)
            self.principals_list.addItem(item)

    def _on_principal_selected(self):
        selected_items = self.principals_list.selectedItems()
        
        # Enable/disable Remove button based on selection
        self.remove_button.setEnabled(len(selected_items) > 0)
        
        if not selected_items:
            self.permissions_group.setTitle(self.i18n.get_string("security_tab.groupbox.permissions").format(""))
            self.permissions_table.setRowCount(0)
            return

        selected_item = selected_items[0]
        sid = selected_item.data(Qt.UserRole)
        principal_name = selected_item.text()
        aces = self.principals.get(sid, [])

        self.permissions_group.setTitle(self.i18n.get_string("security_tab.groupbox.permissions").format(principal_name))

        self.permissions_table.setRowCount(0)
        self._populate_permissions_table(aces)

    def _populate_permissions_table(self, aces):
        # Standard AD permissions - these are the common ones shown in ADUC
        permissions = {
            "Full Control": 0x001F01FF,  # GENERIC_ALL for AD objects
            "List Contents": 0x00000004,  # ADS_RIGHT_ACTRL_DS_LIST
            "Read All Properties": 0x00000010,  # ADS_RIGHT_DS_READ_PROP
            "Write All Properties": 0x00000020,  # ADS_RIGHT_DS_WRITE_PROP
            "Delete": 0x00010000,  # DELETE
            "Delete Subtree": 0x00000040,  # ADS_RIGHT_DS_DELETE_TREE
            "Read Permissions": 0x00020000,  # READ_CONTROL
            "Modify Permissions": 0x00040000,  # WRITE_DAC
            "Modify Owner": 0x00080000,  # WRITE_OWNER
            "Create All Child Objects": 0x00000001,  # ADS_RIGHT_DS_CREATE_CHILD
            "Delete All Child Objects": 0x00000002,  # ADS_RIGHT_DS_DELETE_CHILD
        }

        for name, value in permissions.items():
            row = self.permissions_table.rowCount()
            self.permissions_table.insertRow(row)

            permission_item = QTableWidgetItem(self.i18n.get_string(f"security_tab.permission.{name.lower().replace(' ', '_')}"))
            allow_checkbox = QCheckBox()
            deny_checkbox = QCheckBox()

            for ace in aces:
                mask = ace['Ace']['Mask']
                ace_type = ace['TypeName']

                if ace_type == 'ACCESS_ALLOWED_ACE':
                    if mask.hasPriv(value):
                        allow_checkbox.setChecked(True)
                else:
                    if mask.hasPriv(value):
                        deny_checkbox.setChecked(True)

            self.permissions_table.setItem(row, 0, permission_item)
            self.permissions_table.setCellWidget(row, 1, allow_checkbox)
            self.permissions_table.setCellWidget(row, 2, deny_checkbox)

    def _add_principal(self):
        """Add a new principal (user/group) to the security descriptor."""
        from search_dialogs import PrincipalPickerDialog
        
        # Use the principal picker dialog to select users/groups
        dialog = PrincipalPickerDialog(self.samba_conn, self)
        
        if dialog.exec_() == QDialog.Accepted:
            selected_object = dialog.get_selected_object()
            if not selected_object:
                QMessageBox.information(self, 
                    self.i18n.get_string("security_tab.add_principal.title"), 
                    self.i18n.get_string("security_tab.add_principal.select_prompt"))
                return
            
            principal_dn = selected_object.get('dn', '')
            principal_name = selected_object.get('name', selected_object.get('cn', [''])[0] if isinstance(selected_object.get('cn'), list) else selected_object.get('cn', ''))
            
            if not principal_dn:
                QMessageBox.warning(self, 
                    self.i18n.get_string("security_tab.add_principal.title"), 
                    self.i18n.get_string("security_tab.add_principal.no_info"))
                return
            
            # Add the principal to the ACL with Full Control permissions
            from acl_utils import add_principal_to_acl
            
            success = add_principal_to_acl(
                self.samba_conn, 
                self.parent_props.object_dn, 
                principal_dn, 
                permissions_mask=0x001F01FF  # Full Control
            )
            
            if success:
                QMessageBox.information(
                    self, 
                    self.i18n.get_string("dialog.common.success.title"), 
                    self.i18n.get_text("security_tab.add_principal.success", principal_name)
                )
                # Refresh the security display
                self._load_security_info()
            else:
                QMessageBox.critical(
                    self, 
                    self.i18n.get_string("dialog.common.error.title"), 
                    self.i18n.get_text("security_tab.add_principal.failed", principal_name)
                )

    def _remove_principal(self):
        """Remove the selected principal from the security descriptor."""
        selected_items = self.principals_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, 
                self.i18n.get_string("security_tab.remove_principal.title"), 
                self.i18n.get_string("security_tab.remove_principal.select_prompt"))
            return
        
        selected_item = selected_items[0]
        principal_name = selected_item.text()
        
        reply = QMessageBox.question(
            self, 
            self.i18n.get_string("security_tab.remove_principal.title"), 
            self.i18n.get_text("dialog.common.confirm_removal", principal_name) + "\n\n" +
            self.i18n.get_string("security_tab.remove_principal.warning"),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Get the principal's SID from the selected item's data
            principal_sid = selected_item.data(Qt.UserRole)
            if not principal_sid:
                QMessageBox.warning(self, 
                    self.i18n.get_string("security_tab.remove_principal.title"), 
                    self.i18n.get_string("security_tab.remove_principal.no_info"))
                return
            
            # Remove the principal from the ACL
            from acl_utils import remove_principal_from_acl_by_sid
            
            success = remove_principal_from_acl_by_sid(
                self.samba_conn, 
                self.parent_props.object_dn, 
                principal_sid
            )
            
            if success:
                QMessageBox.information(
                    self, 
                    self.i18n.get_string("dialog.common.success.title"), 
                    self.i18n.get_text("security_tab.remove_principal.success", principal_name)
                )
                # Refresh the security display
                self._load_security_info()
            else:
                QMessageBox.critical(
                    self, 
                    self.i18n.get_string("dialog.common.error.title"), 
                    self.i18n.get_text("security_tab.remove_principal.failed", principal_name)
                )

    def _open_advanced_security(self):
        """Open advanced security settings."""
        QMessageBox.information(
            self, 
            "Advanced Security", 
            "Advanced security settings provide detailed ACL management capabilities.\n\n"
            "This includes:\n"
            "• Detailed permission assignments\n"
            "• Inheritance settings\n"
            "• Audit settings\n"
            "• Ownership management\n\n"
            "For full security management, consider using specialized AD security tools "
            "or Windows RSAT for complex permission scenarios."
        )

class ManagedByTab(QWidget):
    """A reusable Managed By tab."""
    def __init__(self, samba_conn, parent_props, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.parent_props = parent_props
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._load_manager_data()

    def _create_widgets(self):
        self.manager_name_edit = QLineEdit()
        self.manager_name_edit.setReadOnly(True)
        self.change_manager_btn = QPushButton(self.i18n.get_string("user_properties.button.change"))
        self.clear_manager_btn = QPushButton(self.i18n.get_string("computer_properties.managed_by.button_clear"))
        self.manager_properties_btn = QPushButton(self.i18n.get_string("action_pane.menu.properties"))

        self.manager_office_label = QLabel()
        self.manager_street_edit = QTextEdit()
        self.manager_street_edit.setReadOnly(True)
        self.manager_city_label = QLabel()
        self.manager_state_label = QLabel()
        self.manager_country_label = QLabel()
        self.manager_telephone_label = QLabel()
        self.manager_fax_label = QLabel()

    def _create_layout(self):
        layout = QVBoxLayout(self)
        manager_group = QGroupBox()
        group_layout = QVBoxLayout(manager_group)

        name_form_layout = QFormLayout()
        name_form_layout.addRow(self.i18n.get_string("user_properties.label.name"), self.manager_name_edit)
        group_layout.addLayout(name_form_layout)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.change_manager_btn)
        button_layout.addWidget(self.manager_properties_btn)
        button_layout.addWidget(self.clear_manager_btn)
        group_layout.addLayout(button_layout)
        group_layout.addSpacing(15)

        pim_form_layout = QFormLayout()
        pim_form_layout.setVerticalSpacing(10)
        self.manager_street_edit.setFixedHeight(80)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.office"), self.manager_office_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.street"), self.manager_street_edit)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.city"), self.manager_city_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.state"), self.manager_state_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.country"), self.manager_country_label)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        pim_form_layout.addRow(separator)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.telephone"), self.manager_telephone_label)
        pim_form_layout.addRow(self.i18n.get_string("user_properties.label.fax"), self.manager_fax_label)
        group_layout.addLayout(pim_form_layout)

        layout.addWidget(manager_group)
        layout.addStretch()

    def _connect_signals(self):
        self.manager_name_edit.textChanged.connect(self._update_managed_by_buttons)
        self.change_manager_btn.clicked.connect(self._change_manager)

    def _load_manager_data(self):
        manager_dn = self.parent_props.get('managedBy', [None])[0]
        if manager_dn:
            manager_props = get_user_properties(self.samba_conn, manager_dn)
            if manager_props:
                self.manager_name_edit.setText(manager_props.get('displayName', [''])[0])
                self.manager_office_label.setText(manager_props.get('physicalDeliveryOfficeName', [''])[0])
                self.manager_street_edit.setText(manager_props.get('streetAddress', [''])[0])
                self.manager_city_label.setText(manager_props.get('l', [''])[0])
                self.manager_state_label.setText(manager_props.get('st', [''])[0])
                self.manager_country_label.setText(manager_props.get('co', [''])[0])
                self.manager_telephone_label.setText(manager_props.get('telephoneNumber', [''])[0])
                self.manager_fax_label.setText(manager_props.get('facsimileTelephoneNumber', [''])[0])
        self._update_managed_by_buttons()

    def _update_managed_by_buttons(self):
        has_manager = bool(self.manager_name_edit.text())
        self.manager_properties_btn.setEnabled(has_manager)
        self.clear_manager_btn.setEnabled(has_manager)

    def _change_manager(self):
        """Open manager selection dialog."""
        from search_dialogs import StandardSearchDialog
        
        self.logger.info("Opening manager selection dialog")
        dialog = StandardSearchDialog(self.samba_conn, ['user'], parent=self)
        while dialog.exec_() == QDialog.Accepted:
            selected_objects = dialog.get_selected_objects()
            self.logger.info(f"Dialog returned {len(selected_objects) if selected_objects else 0} objects")
            
            if not selected_objects:
                self.logger.info("No objects selected, breaking")
                break
            
            if len(selected_objects) > 1:
                self.logger.info(f"Too many selections: {len(selected_objects)}")
                QMessageBox.warning(dialog, "Too Many Selections", 
                                  "Please select only one manager. Multiple selections are not allowed.")
                # Don't close dialog, continue the loop to let user try again
                continue
            
            # Exactly one selection - process it
            selected_user = selected_objects[0]
            self.logger.info(f"Selected user object: {selected_user}")
            manager_dn = selected_user.get('dn', '')
            display_name = selected_user.get('display_text', selected_user.get('cn', ''))
            
            self.logger.info(f"Extracted - DN: '{manager_dn}', Display: '{display_name}'")
            
            if manager_dn:
                self.logger.info(f"Setting manager field to: '{display_name}'")
                self.manager_name_edit.setText(display_name)
                
                # Store the DN for potential write-back
                self.manager_dn = manager_dn
                
                # Mark the parent dialog as modified
                if hasattr(self.parent(), '_check_for_changes'):
                    self.parent()._check_for_changes()
                
                self.logger.info(f"Successfully selected manager: {display_name} ({manager_dn})")
            else:
                self.logger.warning("No manager DN found in selected object")
            
            # Successfully processed, break out of loop
            break

    def get_changes(self):
        """Return any changes made to the manager field."""
        changes = {}
        
        # Check if manager was changed
        original_manager_dn = self.parent_props.get('managedBy', [None])[0]
        current_manager_dn = getattr(self, 'manager_dn', None)
        
        if current_manager_dn != original_manager_dn:
            if current_manager_dn:
                changes['managedBy'] = [current_manager_dn]
            else:
                changes['managedBy'] = []  # Clear the manager
            
            self.logger.info(f"Manager change detected: {original_manager_dn} -> {current_manager_dn}")
        
        return changes


class ComPlusTab(QWidget):
    """A reusable, placeholder COM+ tab."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()

        layout = QVBoxLayout(self)
        header = QLabel(self.i18n.get_string("user_properties.title.com_partition_set"))
        group = QGroupBox(self.i18n.get_string("user_properties.group.com_partition_set"))
        group_layout = QVBoxLayout(group)
        self.partition_combo = QComboBox()
        self.partition_combo.addItem("N/A") # Placeholder
        group_layout.addWidget(self.partition_combo)

        layout.addWidget(header)
        layout.addWidget(group)
        layout.addStretch()


class MemberOfTab(QWidget):
    """A reusable Member Of tab."""
    def __init__(self, samba_conn, object_dn, parent_props, show_primary_group=False, parent=None, change_callback=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.object_dn = object_dn
        self.parent_props = parent_props
        self.show_primary_group = show_primary_group
        self.change_callback = change_callback  # Callback to notify parent of changes
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        # Track pending changes
        self.pending_additions = set()  # Group DNs to add
        self.pending_removals = set()   # Group DNs to remove
        self.original_groups = set()    # Original group memberships

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._load_membership_data()

    def _create_widgets(self):
        self.member_of_table = QTableWidget()
        self.add_to_group_btn = QPushButton(self.i18n.get_string("user_properties.button.add"))
        self.remove_from_group_btn = QPushButton(self.i18n.get_string("user_properties.button.remove"))

        if self.show_primary_group:
            self.primary_group_label = QLabel()
            self.set_primary_btn = QPushButton(self.i18n.get_string("user_properties.button.set_primary"))

    def _create_layout(self):
        layout = QVBoxLayout(self)
        self.member_of_table.setColumnCount(2)
        self.member_of_table.setHorizontalHeaderLabels([
            self.i18n.get_string("user_properties.header.name"),
            self.i18n.get_string("user_properties.header.folder")
        ])
        self.member_of_table.setSortingEnabled(True)
        self.member_of_table.verticalHeader().hide()
        self.member_of_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        header = self.member_of_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.member_of_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_to_group_btn)
        button_layout.addWidget(self.remove_from_group_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        if self.show_primary_group:
            primary_layout = QHBoxLayout()
            primary_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.primary_group")))
            primary_layout.addWidget(self.primary_group_label)
            primary_layout.addWidget(self.set_primary_btn)
            primary_layout.addStretch()
            layout.addLayout(primary_layout)

    def _connect_signals(self):
        self.add_to_group_btn.clicked.connect(self._add_to_group)
        self.remove_from_group_btn.clicked.connect(self._remove_from_group)
        if self.show_primary_group:
            self.set_primary_btn.clicked.connect(self._set_primary_group)

    def _get_display_path_from_dn(self, dn_string):
        base_dn = get_base_dn(self.samba_conn)
        if not base_dn:
            return dn_string
            
        domain_parts = [p.split('=')[1] for p in base_dn.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)
        try:
            # We want the path of the container, so we strip the first RDN (the object itself)
            parent_dn_string = ldap.dn.dn2str(ldap.dn.str2dn(dn_string)[1:])

            # The base DN is also a string
            base_dn_string = base_dn

            # Check if the parent DN ends with the base DN, case-insensitively
            relative_dn_string = parent_dn_string
            if parent_dn_string.lower().endswith(base_dn_string.lower()):
                # Cut off the base DN part
                end_index = len(parent_dn_string) - len(base_dn_string)
                relative_dn_string = parent_dn_string[:end_index].rstrip(',')

            if not relative_dn_string:
                return domain

            # Convert the relative part back to a structure to reverse it
            relative_parts = ldap.dn.str2dn(relative_dn_string)
            path_components = [rdn[0][1] for rdn in reversed(relative_parts)]
            return f"{domain}/{'/'.join(path_components)}"

        except Exception as e:
            self.logger.warning(f"Could not parse DN '{dn_string}' to create display path: {e}")
            return dn_string # Fallback to the full DN

    def _load_membership_data(self):
        self.member_of_table.setRowCount(0)
        member_of_dns = self.parent_props.get('memberOf', [])

        if self.show_primary_group:
            primary_group_id = self.parent_props.get('primaryGroupID', ['513'])[0]
            primary_group_info = get_group_by_rid(self.samba_conn, primary_group_id)
            if not primary_group_info:
                fallback_base_dn = get_base_dn(self.samba_conn)
                if fallback_base_dn:
                    primary_group_info = {'dn': f"CN=Domain Users,CN=Users,{fallback_base_dn}", 'cn': 'Domain Users', 'displayName': 'Domain Users'}
                else:
                    primary_group_info = {'dn': 'CN=Domain Users,CN=Users', 'cn': 'Domain Users', 'displayName': 'Domain Users'}
            
            other_groups = []
            for group_dn in member_of_dns:
                if group_dn != primary_group_info['dn']:
                    group_props = get_group_properties(self.samba_conn, group_dn, ['cn', 'displayName'])
                    if group_props:
                        info = {'dn': group_dn, 'cn': group_props.get('cn', [group_dn])[0], 'displayName': group_props.get('displayName', [group_props.get('cn', [group_dn])[0]])[0]}
                        other_groups.append(info)
            
            all_groups = [primary_group_info] + other_groups
            self.primary_group_label.setText(primary_group_info.get('displayName', primary_group_info.get('cn', self.i18n.get_string("common.unknown"))))
        else:
            all_groups = []
            for group_dn in member_of_dns:
                group_props = get_group_properties(self.samba_conn, group_dn, ['cn', 'displayName'])
                if group_props:
                    info = {'dn': group_dn, 'cn': group_props.get('cn', [group_dn])[0], 'displayName': group_props.get('displayName', [group_props.get('cn', [group_dn])[0]])[0]}
                    all_groups.append(info)

        for group_info in all_groups:
            row = self.member_of_table.rowCount()
            self.member_of_table.insertRow(row)
            name = group_info.get('displayName', group_info.get('cn', self.i18n.get_string("common.unknown")))
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, group_info['dn'])
            self.member_of_table.setItem(row, 0, name_item)
            path_item = QTableWidgetItem(self._get_display_path_from_dn(group_info['dn']))
            self.member_of_table.setItem(row, 1, path_item)
        
        # Store original group memberships (excluding primary group if shown)
        if self.show_primary_group and all_groups:
            self.original_groups = {group['dn'] for group in all_groups[1:]}  # Skip primary group
        else:
            self.original_groups = {group['dn'] for group in all_groups}
        
        # Reset pending changes
        self.pending_additions.clear()
        self.pending_removals.clear()

    def _add_to_group(self):
        """Add this object to a selected group (staged until Apply/OK)."""
        from search_dialogs import StandardSearchDialog
        
        # Use the standard search dialog to select a group
        dialog = StandardSearchDialog(self.samba_conn, ['group'], parent=self)
        
        if dialog.exec_() == QDialog.Accepted:
            selected_objects = dialog.get_selected_objects()
            if not selected_objects:
                return
            
            added_count = 0
            for obj in selected_objects:
                obj_dn = obj.get('dn', '')
                obj_display = obj.get('display_text', obj.get('cn', ''))
                
                if not obj_dn:
                    continue
                
                # Check if already a member or pending addition
                current_groups = self._get_current_display_groups()
                if obj_dn in current_groups:
                    QMessageBox.information(self, 
                        self.i18n.get_string("dialog.common.info.title"), 
                        f"This object is already a member of group '{obj_display}'.")
                    continue
                
                # Stage the addition
                self.pending_additions.add(obj_dn)
                self.pending_removals.discard(obj_dn)  # Remove from removals if it was there
                added_count += 1
            
            # Update the display to show the pending changes
            if added_count > 0:
                self._refresh_display()
            
            # Mark parent dialog as modified
            if hasattr(self.parent_props, 'mark_modified'):
                self.parent_props.mark_modified()
            
            # Notify parent dialog of changes
            if self.change_callback:
                self.change_callback()
    
    def _get_current_display_groups(self):
        """Get the current set of groups (original + additions - removals)."""
        current_groups = self.original_groups.copy()
        current_groups.update(self.pending_additions)
        current_groups.difference_update(self.pending_removals)
        return current_groups
    
    def _refresh_display(self):
        """Refresh the table display to show current groups including pending changes."""
        from samba_backend import get_group_properties
        
        # Clear the table
        self.member_of_table.setRowCount(0)
        
        # Get current groups (original + pending changes)
        current_groups = self._get_current_display_groups()
        
        # Add primary group if showing primary group
        if self.show_primary_group:
            primary_group_id = self.parent_props.get('primaryGroupID', ['513'])[0]
            primary_group_info = get_group_by_rid(self.samba_conn, primary_group_id)
            if primary_group_info:
                primary_group_dn = primary_group_info['dn']
                # Add primary group to current groups
                current_groups.add(primary_group_dn)
        
        # Display all groups with visual indicators for pending changes
        for group_dn in current_groups:
            # Skip groups that are staged for removal - they should not appear in UI
            if group_dn in self.pending_removals:
                continue
                
            group_props = get_group_properties(self.samba_conn, group_dn, ['cn', 'displayName'])
            if group_props:
                row = self.member_of_table.rowCount()
                self.member_of_table.insertRow(row)
                
                # Group name without change indicators
                display_name = group_props.get('displayName', [group_props.get('cn', [group_dn])[0]])[0]
                
                name_item = QTableWidgetItem(display_name)
                name_item.setData(Qt.UserRole, group_dn)
                self.member_of_table.setItem(row, 0, name_item)
                
                path_item = QTableWidgetItem(self._get_display_path_from_dn(group_dn))
                self.member_of_table.setItem(row, 1, path_item)
    
    def apply_changes(self):
        """Apply all pending group membership changes to the directory."""
        from samba_backend import add_user_to_group_samba, remove_user_from_group_samba
        
        errors = []
        
        # Apply additions
        for group_dn in self.pending_additions:
            try:
                add_user_to_group_samba(self.samba_conn, self.object_dn, group_dn)
                self.logger.info(f"Applied addition: {self.object_dn} to group {group_dn}")
            except Exception as e:
                errors.append(f"Failed to add to group {group_dn}: {e}")
                self.logger.error(f"Failed to add {self.object_dn} to group {group_dn}: {e}")
        
        # Apply removals
        for group_dn in self.pending_removals:
            try:
                remove_user_from_group_samba(self.samba_conn, self.object_dn, group_dn)
                self.logger.info(f"Applied removal: {self.object_dn} from group {group_dn}")
            except Exception as e:
                errors.append(f"Failed to remove from group {group_dn}: {e}")
                self.logger.error(f"Failed to remove {self.object_dn} from group {group_dn}: {e}")
        
        # Clear pending changes if all succeeded
        if not errors:
            self.pending_additions.clear()
            self.pending_removals.clear()
            # Reload to get current state
            self._load_membership_data()
        
        return errors

    def _remove_from_group(self):
        """Remove this object from selected groups (staged until Apply/OK)."""
        selected_items = self.member_of_table.selectedItems()
        if not selected_items:
            return
        
        # Get all unique selected rows
        selected_rows = list(set(item.row() for item in selected_items))
        selected_rows.sort(reverse=True)  # Process in reverse order to avoid index shifting
        
        for row in selected_rows:
            group_item = self.member_of_table.item(row, 0)
            if not group_item:
                continue
            
            group_dn = group_item.data(Qt.UserRole)
            if not group_dn:
                continue
            
            # Check if this is the primary group (can't be removed)
            if self.show_primary_group:
                from samba_backend import get_group_by_rid
                primary_group_id = self.parent_props.get('primaryGroupID', ['513'])[0]
                primary_group_info = get_group_by_rid(self.samba_conn, primary_group_id)
                if primary_group_info and group_dn == primary_group_info['dn']:
                    QMessageBox.warning(self, self.i18n.get_string("dialog.common.error.title"), "Cannot remove an object from its primary group. Change the primary group first.")
                    continue
            
            # Stage the removal
            if group_dn in self.pending_additions:
                # If it was a pending addition, just remove it from additions
                self.pending_additions.discard(group_dn)
                self.logger.info(f"Removed pending addition: {group_dn}")
            else:
                # If it's an original group, mark for removal and hide from UI
                self.pending_removals.add(group_dn)
                self.logger.info(f"Added to pending removals and hidden from UI: {group_dn}")
            
            # Remove from table immediately to hide it from UI
            self.member_of_table.removeRow(row)
        
        # Mark parent dialog as modified and notify of changes
        if hasattr(self.parent_props, 'mark_modified'):
            self.parent_props.mark_modified()
        
        if self.change_callback:
            self.change_callback()

    def _set_primary_group(self):
        current_row = self.member_of_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a group to set as primary.")
            return
        selected_item = self.member_of_table.item(current_row, 0)
        group_dn = selected_item.data(Qt.UserRole)
        group_props = get_group_properties(self.samba_conn, group_dn, ['primaryGroupToken'])
        if not group_props or 'primaryGroupToken' not in group_props:
            QMessageBox.critical(self, "Error", f"Could not retrieve the group RID for {group_dn}.")
            return
        new_primary_id = group_props['primaryGroupToken'][0]
        modifications = [(ldap.MOD_REPLACE, 'primaryGroupID', [new_primary_id.encode('utf-8')])]
        success, message = update_object_attributes(self.samba_conn, self.object_dn, modifications)
        if success:
            QMessageBox.information(self, "Success", "Primary group updated successfully.")
            self._load_membership_data()
        else:
            QMessageBox.critical(self, "Error", f"Failed to update primary group: {message}")


class AddressTab(QWidget):
    """A reusable Address tab."""
    def __init__(self, parent_props, parent=None):
        super().__init__(parent)
        self.parent_props = parent_props
        self.i18n = I18nManager()

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.street_edit = QTextEdit()
        self.street_edit.setMaximumHeight(60)
        self.po_box_edit = QLineEdit()
        self.city_edit = QLineEdit()
        self.state_edit = QLineEdit()
        self.zip_edit = QLineEdit()
        self.country_edit = QComboBox()
        self.country_edit.setEditable(True)

        countries = ["", "United States", "Canada", "United Kingdom", "Germany", 
                     "France", "Australia", "Other"]
        self.country_edit.addItems(countries)

        form_layout.addRow(self.i18n.get_string("user_properties.label.street"), self.street_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.po_box"), self.po_box_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.city"), self.city_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.state"), self.state_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.zip"), self.zip_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.country"), self.country_edit)

        layout.addLayout(form_layout)
        layout.addStretch()

        self._load_address_data()

    def _load_address_data(self):
        self.street_edit.setText(self.parent_props.get('streetAddress', [''])[0])
        self.po_box_edit.setText(self.parent_props.get('postOfficeBox', [''])[0])
        self.city_edit.setText(self.parent_props.get('l', [''])[0])
        self.state_edit.setText(self.parent_props.get('st', [''])[0])
        self.zip_edit.setText(self.parent_props.get('postalCode', [''])[0])
        self.country_edit.setCurrentText(self.parent_props.get('co', [''])[0])


class TelephonesTab(QWidget):
    """A reusable Telephones tab."""
    def __init__(self, parent_props, parent=None):
        super().__init__(parent)
        self.parent_props = parent_props
        self.i18n = I18nManager()

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.home_phone_edit = QLineEdit()
        self.pager_edit = QLineEdit()
        self.mobile_edit = QLineEdit()
        self.fax_edit = QLineEdit()
        self.ip_phone_edit = QLineEdit()
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(100)

        form_layout.addRow(self.i18n.get_string("user_properties.label.home_phone"), self.home_phone_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.pager"), self.pager_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.mobile"), self.mobile_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.fax"), self.fax_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.ip_phone"), self.ip_phone_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.notes"), self.notes_edit)

        layout.addLayout(form_layout)
        layout.addStretch()

        self._load_telephones_data()

    def _load_telephones_data(self):
        self.home_phone_edit.setText(self.parent_props.get('homePhone', [''])[0])
        self.pager_edit.setText(self.parent_props.get('pager', [''])[0])
        self.mobile_edit.setText(self.parent_props.get('mobile', [''])[0])
        self.fax_edit.setText(self.parent_props.get('facsimileTelephoneNumber', [''])[0])
        self.ip_phone_edit.setText(self.parent_props.get('ipPhone', [''])[0])
        self.notes_edit.setText(self.parent_props.get('info', [''])[0])


class OrganizationTab(QWidget):
    """A reusable Organization tab."""
    def __init__(self, parent_props, parent=None):
        super().__init__(parent)
        self.parent_props = parent_props
        self.i18n = I18nManager()

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.title_edit = QLineEdit()
        self.department_edit = QLineEdit()
        self.company_edit = QLineEdit()
        self.manager_edit = QLineEdit()

        manager_layout = QHBoxLayout()
        manager_layout.addWidget(self.manager_edit)
        manager_button = QPushButton(self.i18n.get_string("user_properties.button.change"))
        manager_button.clicked.connect(self._select_manager)
        manager_layout.addWidget(manager_button)

        self.direct_reports_list = QListWidget()
        self.direct_reports_list.setMaximumHeight(100)

        form_layout.addRow(self.i18n.get_string("user_properties.label.title"), self.title_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.department"), self.department_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.company"), self.company_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.manager"), manager_layout)
        form_layout.addRow(self.i18n.get_string("user_properties.label.direct_reports"), self.direct_reports_list)

        layout.addLayout(form_layout)
        layout.addStretch()

        self._load_organization_data()

    def _load_organization_data(self):
        self.title_edit.setText(self.parent_props.get('title', [''])[0])
        self.department_edit.setText(self.parent_props.get('department', [''])[0])
        self.company_edit.setText(self.parent_props.get('company', [''])[0])
        self.manager_edit.setText(self.parent_props.get('manager', [''])[0])

    def _select_manager(self):
        """Open manager selection dialog."""
        from search_dialogs import StandardSearchDialog
        
        dialog = StandardSearchDialog(self.samba_conn, ['user'], parent=self)
        if dialog.exec_() == QDialog.Accepted:
            selected_objects = dialog.get_selected_objects()
            if selected_objects:
                # Take only the first selected user (limit to one)
                selected_user = selected_objects[0]
                manager_dn = selected_user.get('dn', '')
                display_name = selected_user.get('display_text', selected_user.get('cn', ''))
                
                if manager_dn:
                    self.manager_edit.setText(display_name)
                    
                    # Store the DN for potential write-back
                    self.manager_dn = manager_dn
                    
                    self.logger.info(f"Selected manager: {display_name} ({manager_dn})")


class PasswordReplicationTab(QWidget):
    """A reusable Password Replication tab."""
    def __init__(self, samba_conn, object_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.object_dn = object_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self._create_widgets()
        self._create_layout()
        self._load_replication_data()

    def _create_widgets(self):
        self.info_label = QLabel(self.i18n.get_string("password_replication.label.info"))
        self.info_label.setWordWrap(True)
        self.rodc_list = QTableWidget()
        self.rodc_list.setColumnCount(2)
        self.rodc_list.setHorizontalHeaderLabels([
            self.i18n.get_string("password_replication.header.name"),
            self.i18n.get_string("password_replication.header.site")
        ])
        self.rodc_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.rodc_list.verticalHeader().hide()

    def _create_layout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.rodc_list)

    def _load_replication_data(self):
        rodc_list = get_rodc_password_replication_status(self.samba_conn, self.object_dn)
        self.rodc_list.setRowCount(0)
        for rodc in rodc_list:
            row = self.rodc_list.rowCount()
            self.rodc_list.insertRow(row)
            self.rodc_list.setItem(row, 0, QTableWidgetItem(rodc['name']))
            self.rodc_list.setItem(row, 1, QTableWidgetItem(rodc['site']))


class EmailTab(QWidget):
    """A tab for managing email addresses and proxy addresses."""
    def __init__(self, samba_conn, object_dn, object_props, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.object_dn = object_dn
        self.object_props = object_props
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self._create_widgets()
        self._create_layout()
        self._load_email_data()

    def _create_widgets(self):
        # Primary SMTP address
        self.primary_smtp_label = QLabel(self.i18n.get_string("email.label.primary_smtp"))
        self.primary_smtp_edit = QLineEdit()
        
        # SMTP aliases (multi-line)
        self.smtp_aliases_label = QLabel(self.i18n.get_string("email.label.smtp_aliases"))
        self.smtp_aliases_edit = QTextEdit()
        self.smtp_aliases_edit.setMaximumHeight(100)
        
        # SIP address
        self.sip_label = QLabel(self.i18n.get_string("email.label.sip"))
        self.sip_edit = QLineEdit()
        
        # X.400 address
        self.x400_label = QLabel(self.i18n.get_string("email.label.x400"))
        self.x400_edit = QLineEdit()
        
        # X.500 address
        self.x500_label = QLabel(self.i18n.get_string("email.label.x500"))
        self.x500_edit = QLineEdit()

    def _create_layout(self):
        layout = QFormLayout(self)
        
        layout.addRow(self.primary_smtp_label, self.primary_smtp_edit)
        layout.addRow(self.smtp_aliases_label, self.smtp_aliases_edit)
        layout.addRow(self.sip_label, self.sip_edit)
        layout.addRow(self.x400_label, self.x400_edit)
        layout.addRow(self.x500_label, self.x500_edit)

    def _load_email_data(self):
        """Load email addresses from proxyAddresses attribute."""
        proxy_addresses = self.object_props.get('proxyAddresses', [])
        
        primary_smtp = ""
        smtp_aliases = []
        sip_address = ""
        x400_address = ""
        x500_address = ""
        
        for proxy_addr_bytes in proxy_addresses:
            proxy_addr = proxy_addr_bytes.decode('utf-8') if isinstance(proxy_addr_bytes, bytes) else proxy_addr_bytes
            
            if proxy_addr.startswith('SMTP:'):  # Primary SMTP (uppercase)
                primary_smtp = proxy_addr[5:]  # Remove 'SMTP:' prefix
            elif proxy_addr.startswith('smtp:'):  # Alias SMTP (lowercase)
                smtp_aliases.append(proxy_addr[5:])  # Remove 'smtp:' prefix
            elif proxy_addr.startswith('SIP:') or proxy_addr.startswith('sip:'):
                sip_address = proxy_addr[4:]  # Remove 'SIP:' or 'sip:' prefix
            elif proxy_addr.startswith('X400:') or proxy_addr.startswith('x400:'):
                x400_address = proxy_addr[5:]  # Remove 'X400:' or 'x400:' prefix
            elif proxy_addr.startswith('X500:') or proxy_addr.startswith('x500:'):
                x500_address = proxy_addr[5:]  # Remove 'X500:' or 'x500:' prefix
        
        # Populate the UI
        self.primary_smtp_edit.setText(primary_smtp)
        self.smtp_aliases_edit.setPlainText('\n'.join(smtp_aliases))
        self.sip_edit.setText(sip_address)
        self.x400_edit.setText(x400_address)
        self.x500_edit.setText(x500_address)
    
    @staticmethod
    def should_show_for_object(object_props):
        """Check if this tab should be shown for the given object."""
        return 'proxyAddresses' in object_props and object_props['proxyAddresses']


class LAPSTab(QWidget):
    """A tab for Local Administrator Password Solution (LAPS) management."""
    def __init__(self, samba_conn, computer_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.computer_dn = computer_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        self.is_password_visible = False

        self._create_widgets()
        self._create_layout()
        self._load_laps_data()
        self._connect_signals()

    def _create_widgets(self):
        # Title label
        self.title_label = QLabel(self.i18n.get_string("laps.title"))
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        
        # Current expiration
        self.current_exp_label = QLabel(self.i18n.get_string("laps.label.current_expiration"))
        self.current_exp_edit = QLineEdit()
        self.current_exp_edit.setReadOnly(True)
        
        # Set new expiration
        self.set_exp_label = QLabel(self.i18n.get_string("laps.label.set_expiration"))
        self.set_exp_edit = QDateTimeEdit()
        self.set_exp_edit.setDateTime(QDateTime.currentDateTime())
        self.set_exp_edit.setCalendarPopup(True)
        
        self.expire_now_btn = QPushButton(self.i18n.get_string("laps.button.expire_now"))
        
        # Admin account name
        self.admin_account_label = QLabel(self.i18n.get_string("laps.label.admin_account"))
        self.admin_account_edit = QLineEdit()
        self.admin_account_edit.setReadOnly(True)
        
        # Admin password
        self.admin_password_label = QLabel(self.i18n.get_string("laps.label.admin_password"))
        self.admin_password_edit = QLineEdit()
        self.admin_password_edit.setReadOnly(True)
        self.admin_password_edit.setEchoMode(QLineEdit.Password)
        
        # Password buttons
        self.copy_password_btn = QPushButton(self.i18n.get_string("laps.button.copy_password"))
        self.show_password_btn = QPushButton(self.i18n.get_string("laps.button.show_password"))

    def _create_layout(self):
        layout = QVBoxLayout(self)
        
        # Title
        layout.addWidget(self.title_label)
        layout.addSpacing(10)
        
        # Current expiration
        layout.addWidget(self.current_exp_label)
        layout.addWidget(self.current_exp_edit)
        layout.addSpacing(10)
        
        # Set new expiration with button
        layout.addWidget(self.set_exp_label)
        exp_layout = QHBoxLayout()
        exp_layout.addWidget(self.set_exp_edit)
        exp_layout.addWidget(self.expire_now_btn)
        layout.addLayout(exp_layout)
        layout.addSpacing(10)
        
        # Admin account
        layout.addWidget(self.admin_account_label)
        layout.addWidget(self.admin_account_edit)
        layout.addSpacing(10)
        
        # Admin password with buttons
        layout.addWidget(self.admin_password_label)
        layout.addWidget(self.admin_password_edit)
        
        password_btn_layout = QHBoxLayout()
        password_btn_layout.addWidget(self.copy_password_btn)
        password_btn_layout.addWidget(self.show_password_btn)
        password_btn_layout.addStretch()
        layout.addLayout(password_btn_layout)
        
        layout.addStretch()

    def _load_laps_data(self):
        """Load LAPS information from Active Directory."""
        laps_info = get_laps_info(self.samba_conn, self.computer_dn)
        
        # Current expiration
        if laps_info['password_expiration']:
            exp_str = laps_info['password_expiration'].strftime("%Y-%m-%d %H:%M:%S")
            self.current_exp_edit.setText(exp_str)
        else:
            self.current_exp_edit.setText("")
        
        # Admin account name - only show if LAPS is configured
        self.admin_account_edit.setText(laps_info['admin_account'] if laps_info['admin_account'] else "")
        
        # Password
        password = laps_info['password']
        self.admin_password_edit.setText(password)
        
        # Enable/disable buttons based on password availability
        has_password = bool(password)
        self.copy_password_btn.setEnabled(has_password)
        self.show_password_btn.setEnabled(has_password)

    def _connect_signals(self):
        self.expire_now_btn.clicked.connect(self._expire_now)
        self.copy_password_btn.clicked.connect(self._copy_password)
        self.show_password_btn.clicked.connect(self._toggle_password_visibility)

    def _expire_now(self):
        """Set LAPS password expiration to now."""
        from datetime import datetime
        now = datetime.now()
        
        if set_laps_expiration(self.samba_conn, self.computer_dn, now):
            self.current_exp_edit.setText(now.strftime("%Y-%m-%d %H:%M:%S"))
            QMessageBox.information(self, "Success", "LAPS password expiration set to now. The password will be updated on the next LAPS policy refresh.")
        else:
            QMessageBox.warning(self, "Error", "Failed to update LAPS password expiration.")

    def _copy_password(self):
        """Copy the LAPS password to clipboard."""
        password = self.admin_password_edit.text()
        if password:
            clipboard = QApplication.clipboard()
            clipboard.setText(password)
            QMessageBox.information(self, "Success", "Password copied to clipboard.")

    def _toggle_password_visibility(self):
        """Toggle between showing and hiding the password."""
        if self.is_password_visible:
            self.admin_password_edit.setEchoMode(QLineEdit.Password)
            self.show_password_btn.setText(self.i18n.get_string("laps.button.show_password"))
            self.is_password_visible = False
        else:
            self.admin_password_edit.setEchoMode(QLineEdit.Normal)
            self.show_password_btn.setText(self.i18n.get_string("laps.button.hide_password"))
            self.is_password_visible = True
