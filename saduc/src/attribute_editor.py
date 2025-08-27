#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/attribute_editor.py
#
# Description:
# This file contains the Attribute Editor tab widget used in various
# properties dialogs.
#
# -----------------------------------------------------------------------------

import logging
import ldap
import ldap.sasl as sasl
import struct
from datetime import datetime, timezone, timedelta

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QLineEdit, QHBoxLayout, QLabel, QGroupBox, QTextEdit,
    QPushButton, QMenu, QWidgetAction, QStyle, QMessageBox, QInputDialog,
    QDialog, QDialogButtonBox, QFormLayout
)
from PyQt5.QtCore import Qt
from i18n_manager import I18nManager
from samba_backend import format_ldap_guid, get_paged_results, get_paged_results

# --- Custom Dialog for Editing Attributes ---
class AttributeEditDialog(QDialog):
    def __init__(self, attr_name, syntax, current_value, is_multi_valued, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()

        # Determine generic title from syntax
        title_key = "attribute_edit_dialog.title.default"
        if 'String' in syntax:
            title_key = "attribute_edit_dialog.title.string"
        elif 'Integer' in syntax:
            title_key = "attribute_edit_dialog.title.integer"
        elif 'Octet' in syntax:
            title_key = "attribute_edit_dialog.title.octet"
        elif 'Time' in syntax:
            title_key = "attribute_edit_dialog.title.utc_time"
        
        title = self.i18n.get_string(title_key)
        if is_multi_valued:
            prefix = self.i18n.get_string("attribute_edit_dialog.title.multi_valued_prefix")
            title = f"{prefix} {title}"
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)
        # Window title will be set after loading user data
        self.setMinimumSize(400, 100)
        # Attribute Name Display
        attr_layout = QHBoxLayout()
        attr_layout.addWidget(QLabel(self.i18n.get_string("attribute_edit_dialog.label.attribute")))
        attr_name_display = QLineEdit(attr_name)
        attr_name_display.setReadOnly(True)
        attr_name_display.setStyleSheet("background-color: #f0f0f0; border: none;")
        attr_layout.addWidget(attr_name_display)
        layout.addLayout(attr_layout)

        # Spacer
        layout.addSpacing(20)

        # Value Editor
        self.is_multi_valued = is_multi_valued
        value_layout = QVBoxLayout()
        value_layout.addWidget(QLabel(f"{self.i18n.get_string('table.header.value')}:"))

        if self.is_multi_valued:
            self.editor = QTextEdit()
            if current_value != self.i18n.get_string("attribute_editor.not_set"):
                 self.editor.setText('\n'.join(current_value.split('; ')))
            self.editor.setMinimumHeight(80)
            value_layout.addWidget(self.editor)
        else:
            self.editor = QLineEdit()
            if current_value != self.i18n.get_string("attribute_editor.not_set"):
                self.editor.setText(current_value)
            value_layout.addWidget(self.editor)
        
        layout.addLayout(value_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_value(self):
        if self.is_multi_valued:
            # Join multi-line text with the separator used for display
            return "; ".join(self.editor.toPlainText().splitlines())
        else:
            return self.editor.text()

# --- Custom Table Widget Item for Case-Insensitive Sorting ---
class CaseInsensitiveTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        return self.text().lower() < other.text().lower()

# --- Value Formatting Helpers ---

FILETIME_ATTRIBUTES = {
    'accountExpires', 'badPasswordTime', 'lastLogon', 'lastLogonTimestamp', 'pwdLastSet'
}
GENERALIZED_TIME_ATTRIBUTES = {
    'whenChanged', 'whenCreated'
}

UAC_FLAGS = {
    0x0001: "SCRIPT",
    0x0002: "ACCOUNTDISABLE",
    0x0008: "HOMEDIR_REQUIRED",
    0x0010: "LOCKOUT",
    0x0020: "PASSWD_NOTREQD",
    0x0040: "PASSWD_CANT_CHANGE",
    0x0080: "ENCRYPTED_TEXT_PWD_ALLOWED",
    0x0100: "TEMP_DUPLICATE_ACCOUNT",
    0x0200: "NORMAL_ACCOUNT",
    0x0800: "INTERDOMAIN_TRUST_ACCOUNT",
    0x1000: "WORKSTATION_TRUST_ACCOUNT",
    0x2000: "SERVER_TRUST_ACCOUNT",
    0x10000: "DONT_EXPIRE_PASSWORD",
    0x20000: "MNS_LOGON_ACCOUNT",
    0x40000: "SMARTCARD_REQUIRED",
    0x80000: "TRUSTED_FOR_DELEGATION",
    0x100000: "NOT_DELEGATED",
    0x200000: "USE_DES_KEY_ONLY",
    0x400000: "DONT_REQ_PREAUTH",
    0x800000: "PASSWORD_EXPIRED",
    0x1000000: "TRUSTED_TO_AUTH_FOR_DELEGATION",
}

SAM_ACCOUNT_TYPES = {
    0x0: "SAM_DOMAIN_OBJECT",
    0x10000000: "SAM_GROUP_OBJECT",
    0x10000001: "SAM_NON_SECURITY_GROUP_OBJECT",
    0x20000000: "SAM_ALIAS_OBJECT",
    0x20000001: "SAM_NON_SECURITY_ALIAS_OBJECT",
    0x30000000: "SAM_NORMAL_USER_ACCOUNT",
    0x30000001: "SAM_MACHINE_ACCOUNT",
    0x30000002: "SAM_TRUST_ACCOUNT",
    0x40000000: "SAM_APP_BASIC_GROUP",
    0x40000001: "SAM_APP_QUERY_GROUP",
    0x80000000: "SAM_ACCOUNT_TYPE_MAX",
}

PRIMARY_GROUP_IDS = {
    512: "GROUP_RID_ADMINS",
    513: "GROUP_RID_USERS",
    514: "GROUP_RID_GUESTS",
    515: "GROUP_RID_COMPUTERS",
    516: "GROUP_RID_CONTROLLERS",
    517: "GROUP_RID_CERT_ADMINS",
    518: "GROUP_RID_SCHEMA_ADMINS",
    519: "GROUP_RID_ENTERPRISE_ADMINS",
    520: "GROUP_RID_POLICY_ADMINS",
}

INSTANCE_TYPES = {
    0x1: "IT_UNINSTANTIATED",
    0x2: "IT_NC_HEAD",
    0x4: "IT_WRITE",
    0x8: "IT_NC_ABOVE",
    0x10: "IT_CONSTRUCTING",
    0x20: "IT_BREAKING",
    0x40: "IT_REMOVING",
}

SYNTAX_MAP = {
    "2.5.5.1": "attribute_edit_dialog.syntax.dn",
    "2.5.5.2": "attribute_edit_dialog.syntax.oid",
    "2.5.5.3": "attribute_edit_dialog.syntax.css",
    "2.5.5.4": "attribute_edit_dialog.syntax.cis",
    "2.5.5.5": "attribute_edit_dialog.syntax.ia5",
    "2.5.5.6": "attribute_edit_dialog.syntax.numeric",
    "2.5.5.7": "attribute_edit_dialog.syntax.dnwb",
    "2.5.5.8": "attribute_edit_dialog.syntax.bool",
    "2.5.5.9": "attribute_edit_dialog.syntax.int",
    "2.5.5.10": "attribute_edit_dialog.syntax.ocs",
    "2.5.5.11": "attribute_edit_dialog.syntax.utc",
    "2.5.5.12": "attribute_edit_dialog.syntax.us",
    "2.5.5.13": "attribute_edit_dialog.syntax.pa",
    "2.5.5.14": "attribute_edit_dialog.syntax.dns",
    "2.5.5.15": "attribute_edit_dialog.syntax.ntsd",
    "2.5.5.16": "attribute_edit_dialog.syntax.lii",
    "2.5.5.17": "attribute_edit_dialog.syntax.sid",
    "1.2.840.113556.1.4.906": "attribute_edit_dialog.syntax.dnb",
}

def _format_filetime(value_str):
    """Converts a Windows FILETIME string to a readable date/time in the local timezone."""
    try:
        filetime = int(value_str)
        if filetime == 0 or filetime == 9223372036854775807:
            return "Never"
        dt_utc = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=filetime / 10)
        dt_local = dt_utc.astimezone()
        return dt_local.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, OSError):
        return value_str

def _format_generalized_time(value_str):
    """Converts a Generalized Time string (YYYYMMDDHHMMSS.fZ) to a readable date/time."""
    try:
        if '.' in value_str:
            main_part, fractional_part = value_str.split('.')
            fractional_part = fractional_part.rstrip('Z')
            micros = int(fractional_part.ljust(6, '0'))
        else:
            main_part = value_str.rstrip('Z')
            micros = 0
        dt_utc = datetime.strptime(main_part, '%Y%m%d%H%M%S').replace(microsecond=micros, tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        return dt_local.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, IndexError):
        return value_str

def _format_sid(value):
    """Converts a binary SID to its string representation."""
    if not isinstance(value, bytes):
        return str(value)
    try:
        revision = value[0]
        num_sub_authorities = value[1]
        authority = int.from_bytes(value[2:8], 'big')
        sid_parts = [f'S-{revision}-{authority}']
        for i in range(num_sub_authorities):
            offset = 8 + (i * 4)
            sub_authority = int.from_bytes(value[offset:offset+4], 'little')
            sid_parts.append(str(sub_authority))
        return ''.join(sid_parts)
    except (IndexError, struct.error):
        return value.hex()

def _format_uac(value_str):
    try:
        uac_val = int(value_str)
        flags = [name for flag, name in UAC_FLAGS.items() if uac_val & flag]
        return f"0x{uac_val:x} = ({'|'.join(flags)})"
    except (ValueError, TypeError):
        return value_str

def _format_sam_account_type(value_str):
    try:
        val = int(value_str)
        name = SAM_ACCOUNT_TYPES.get(val, "UNKNOWN")
        return f"{val} = ({name})"
    except (ValueError, TypeError):
        return value_str

def _format_primary_group_id(value_str):
    try:
        val = int(value_str)
        name = PRIMARY_GROUP_IDS.get(val, "UNKNOWN")
        return f"{val} = ({name})"
    except (ValueError, TypeError):
        return value_str

def _format_instance_type(value_str):
    try:
        val = int(value_str)
        flags = [name for flag, name in INSTANCE_TYPES.items() if val & flag]
        return f"0x{val:x} = ({'|'.join(flags)})"
    except (ValueError, TypeError):
        return value_str

class AttributeEditorTab(QWidget):
    """A reusable Attribute Editor tab."""
    def __init__(self, samba_conn, object_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.object_dn = object_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        self.all_attributes = {}
        self.schema_attributes = {}

        self._create_widgets()
        self._create_layout()
        self.edit_button.clicked.connect(self._edit_attribute)
        self._load_and_populate_attributes()

    def _create_widgets(self):
        self.attributes_table = QTableWidget()
        self.attributes_table.setColumnCount(3)
        self.attributes_table.setHorizontalHeaderLabels([self.i18n.get_string("table.header.name"), self.i18n.get_string("table.header.value"), self.i18n.get_string("table.header.syntax")])
        
        header = self.attributes_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.attributes_table.setColumnWidth(0, 150)
        self.attributes_table.setColumnWidth(1, 150)
        self.attributes_table.setColumnWidth(2, 150)

        self.attributes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.attributes_table.setSortingEnabled(True)
        self.attributes_table.setWordWrap(False)
        self.attributes_table.setTextElideMode(Qt.ElideRight)
        self.attributes_table.verticalHeader().hide()
        self.attributes_table.verticalHeader().setDefaultSectionSize(self.fontMetrics().height() + 4)
        self.attributes_table.itemDoubleClicked.connect(self._edit_attribute)

        self.edit_button = QPushButton(self.i18n.get_string("attribute_editor.edit"))
        self.filter_button = QPushButton(self.i18n.get_string("attribute_editor.filter"))
        self._create_filter_menu()

    def _create_filter_menu(self):
        self.filter_menu = QMenu(self)

        self.show_with_values_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.show_with_values"))
        self.show_with_values_action.setCheckable(True)

        self.show_writable_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.show_writable"))
        self.show_writable_action.setCheckable(True)

        self.filter_menu.addSeparator()

        show_attributes_label = QLabel(self.i18n.get_string("attribute_editor.filter.show_attributes"))
        show_attributes_label.setStyleSheet("padding: 5px; color: grey;")
        show_attributes_action = QWidgetAction(self)
        show_attributes_action.setDefaultWidget(show_attributes_label)
        self.filter_menu.addAction(show_attributes_action)

        self.mandatory_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.mandatory"))
        self.mandatory_action.setCheckable(True)
        self.mandatory_action.setChecked(True)

        self.optional_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.optional"))
        self.optional_action.setCheckable(True)
        self.optional_action.setChecked(True)

        self.filter_menu.addSeparator()

        show_ro_label = QLabel(self.i18n.get_string("attribute_editor.filter.show_ro"))
        show_ro_label.setStyleSheet("padding: 5px; color: grey;")
        show_ro_action = QWidgetAction(self)
        show_ro_action.setDefaultWidget(show_ro_label)
        self.filter_menu.addAction(show_ro_action)

        self.constructed_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.constructed"))
        self.constructed_action.setCheckable(True)

        self.backlinks_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.backlinks"))
        self.backlinks_action.setCheckable(True)

        self.system_only_action = self.filter_menu.addAction(self.i18n.get_string("attribute_editor.filter.system_only"))
        self.system_only_action.setCheckable(True)

        self.filter_button.setMenu(self.filter_menu)

        # Connect actions to the filter slot
        for action in self.filter_menu.actions():
            if isinstance(action, QWidgetAction):
                continue
            action.triggered.connect(self._apply_filter)

    def _create_layout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.attributes_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.edit_button)
        button_layout.addStretch()
        button_layout.addWidget(self.filter_button)
        layout.addLayout(button_layout)

    def _edit_attribute(self):
        selected_items = self.attributes_table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        attr_name = self.attributes_table.item(row, 0).text()
        current_value = self.attributes_table.item(row, 1).text()
        syntax = self.attributes_table.item(row, 2).text()

        schema_info = self.schema_attributes.get(attr_name, {})
        is_multi_valued = not schema_info.get('is_single_valued', True)

        dialog = AttributeEditDialog(attr_name, syntax, current_value, is_multi_valued, self)
        if dialog.exec_() == QDialog.Accepted:
            new_value = dialog.get_value()
            if new_value != current_value:
                # Here you would typically update the attribute in the directory
                # For now, we just update the table
                self.attributes_table.item(row, 1).setText(new_value)
                self.logger.info(f"Attribute '{attr_name}' value changed to '{new_value}' (UI only).")

    def _load_and_populate_attributes(self):
        try:
            res = self.samba_conn.search_s(self.object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['*', '+'])
            if not res:
                self.logger.warning(f"No attributes found for DN: {self.object_dn}")
                return
            self.all_attributes = res[0][1]
            self.schema_attributes = self._get_schema_attributes()
            self._populate_table()
        except ldap.LDAPError as e:
            self.logger.error(f"LDAP error fetching attributes for '{self.object_dn}': {e}")

    def _get_schema_attributes(self):
        schema_attributes = {}
        try:
            root_dse = self.samba_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ["schemaNamingContext"])
            schema_dn = root_dse[0][1]["schemaNamingContext"][0].decode('utf-8')
            
            initial_classes = [oc.decode('utf-8') for oc in self.all_attributes.get('objectClass', [])]
            classes_to_process = list(initial_classes)
            processed_classes = set()
            must_contain_attrs = set()
            may_contain_attrs = set()

            while classes_to_process:
                oc = classes_to_process.pop(0)
                if oc in processed_classes:
                    continue
                processed_classes.add(oc)

                try:
                    attributes_to_fetch = ["mustContain", "mayContain", "systemMustContain", "systemMayContain", "subClassOf"]
                    class_schema_result = self.samba_conn.search_s(schema_dn, ldap.SCOPE_ONELEVEL, f"(&(objectClass=classSchema)(lDAPDisplayName={oc}))", attributes_to_fetch)
                    
                    if class_schema_result:
                        class_attrs = class_schema_result[0][1]
                        must_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('mustContain', [])])
                        must_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('systemMustContain', [])])
                        may_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('mayContain', [])])
                        may_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('systemMayContain', [])])
                        parent_classes = [parent.decode('utf-8') for parent in class_attrs.get('subClassOf', [])]
                        classes_to_process.extend(parent_classes)
                except ldap.NO_SUCH_OBJECT:
                    self.logger.warning(f"Could not find schema for objectClass '{oc}'.")
            
            class_schema_attrs = must_contain_attrs | may_contain_attrs
            all_attrs_on_object = set(self.all_attributes.keys())
            total_attrs_to_populate = class_schema_attrs | all_attrs_on_object

            all_attr_schemas_raw = get_paged_results(
                self.samba_conn,
                schema_dn,
                ldap.SCOPE_ONELEVEL,
                "(objectClass=attributeSchema)",
                ["lDAPDisplayName", "attributeSyntax", "isSingleValued", "systemFlags"]
            )

            all_attr_schemas = {
                attr_data['lDAPDisplayName'][0].decode('utf-8'): attr_data
                for _, attr_data in all_attr_schemas_raw if 'lDAPDisplayName' in attr_data
            }

            for attr_name in total_attrs_to_populate:
                attr_schema = all_attr_schemas.get(attr_name)
                if attr_schema:
                    syntax_oid = attr_schema.get('attributeSyntax', [b''])[0].decode('utf-8')
                    system_flags_raw = attr_schema.get('systemFlags', [b'0'])
                    system_flags = int(system_flags_raw[0].decode('utf-8')) if system_flags_raw else 0
                    
                    schema_attributes[attr_name] = {
                        "attributeSyntax": self.i18n.get_string(SYNTAX_MAP.get(syntax_oid, syntax_oid)),
                        "is_single_valued": attr_schema.get('isSingleValued', [b'FALSE'])[0].decode('utf-8').upper() == 'TRUE',
                        "is_read_only": (system_flags & 0x8) != 0,
                        "is_mandatory": attr_name in must_contain_attrs,
                        "is_constructed": (system_flags & 0x1) != 0,
                        "is_backlink": (system_flags & 0x2) != 0,
                        "is_system_only": (system_flags & 0x10) != 0,
                    }
        except ldap.LDAPError as e:
            self.logger.error(f"LDAP error fetching schema attributes: {e}")
        return schema_attributes

    def _populate_table(self):
        self.attributes_table.setRowCount(0)
        self.attributes_table.setSortingEnabled(False)

        all_attr_names = set(self.all_attributes.keys()) | set(self.schema_attributes.keys())

        for attr in sorted(list(all_attr_names)):
            values = self.all_attributes.get(attr)
            schema_info = self.schema_attributes.get(attr, {})

            row_pos = self.attributes_table.rowCount()
            self.attributes_table.insertRow(row_pos)

            self.attributes_table.setItem(row_pos, 0, CaseInsensitiveTableWidgetItem(attr))

            display_value = self.i18n.get_string("attribute_editor.not_set")
            if values:
                try:
                    if attr == 'objectGUID':
                        display_value = format_ldap_guid(values)
                    elif attr == 'objectSid':
                        display_value = _format_sid(values[0])
                    elif attr in FILETIME_ATTRIBUTES:
                        display_value = _format_filetime(values[0].decode())
                    elif attr in GENERALIZED_TIME_ATTRIBUTES:
                        display_value = _format_generalized_time(values[0].decode())
                    elif attr == 'userAccountControl':
                        display_value = _format_uac(values[0].decode())
                    elif attr == 'sAMAccountType':
                        display_value = _format_sam_account_type(values[0].decode())
                    elif attr == 'primaryGroupID':
                        display_value = _format_primary_group_id(values[0].decode())
                    elif attr == 'instanceType':
                        display_value = _format_instance_type(values[0].decode())
                    else:
                        decoded_values = [v.decode('utf-8', errors='replace') for v in values]
                        display_value = "; ".join(decoded_values)
                except (UnicodeDecodeError, AttributeError):
                    if len(values) == 1 and isinstance(values[0], bytes):
                        display_value = self.i18n.get_text("attribute_editor.binary_data", len(values[0]))
                    else:
                        display_value = str(values)
                except Exception as e:
                    self.logger.warning(f"Could not format attribute '{attr}': {e}")
                    display_value = str(values)
            
            self.attributes_table.setItem(row_pos, 1, QTableWidgetItem(display_value))

            syntax = schema_info.get('attributeSyntax', '')
            self.attributes_table.setItem(row_pos, 2, QTableWidgetItem(syntax))

        self.attributes_table.setSortingEnabled(True)
        self.attributes_table.sortByColumn(0, Qt.AscendingOrder)
        self._apply_filter()

    def _apply_filter(self):
        show_only_with_values = self.show_with_values_action.isChecked()
        show_only_writable = self.show_writable_action.isChecked()
        show_mandatory = self.mandatory_action.isChecked()
        show_optional = self.optional_action.isChecked()
        show_constructed = self.constructed_action.isChecked()
        show_backlinks = self.backlinks_action.isChecked()
        show_system_only = self.system_only_action.isChecked()

        for i in range(self.attributes_table.rowCount()):
            attr_item = self.attributes_table.item(i, 0)
            value_item = self.attributes_table.item(i, 1)
            attr_name = attr_item.text()
            schema_info = self.schema_attributes.get(attr_name, {})

            # Get attribute properties from schema
            has_value = value_item.text() != self.i18n.get_string("attribute_editor.not_set")
            is_writable = not schema_info.get('is_read_only', True)
            is_mandatory = schema_info.get('is_mandatory', False)
            is_constructed = schema_info.get('is_constructed', False)
            is_backlink = schema_info.get('is_backlink', False)
            is_system_only = schema_info.get('is_system_only', False)
            # An attribute is optional if it's not mandatory or another special type (but can be a system attribute)
            is_optional = not (is_mandatory or is_constructed or is_backlink)

            # --- New, clearer filter logic ---
            category_match = False
            if is_mandatory and show_mandatory:
                category_match = True
            elif is_optional and show_optional:
                category_match = True
            elif is_constructed and show_constructed:
                category_match = True
            elif is_backlink and show_backlinks:
                category_match = True
            
            # Special case for system-only: only show if it doesn't fit a more specific category
            if is_system_only and show_system_only and not category_match:
                category_match = True

            value_match = not (show_only_with_values and not has_value)
            writable_match = not (show_only_writable and not is_writable)

            show_row = category_match and value_match and writable_match

            self.attributes_table.setRowHidden(i, not show_row)
