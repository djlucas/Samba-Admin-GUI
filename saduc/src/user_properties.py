#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/user_properties.py
#
# Description:
# Complete user properties dialog with all standard ADUC tabs and fields
#
# -----------------------------------------------------------------------------

import logging
import ldap.dn
import os
import copy
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QCheckBox, QPushButton, QDialogButtonBox, QListWidget,
    QComboBox, QTextEdit, QGroupBox, QGridLayout, QLabel, QSpinBox,
    QListWidgetItem, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QRadioButton, QDateTimeEdit
)
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QIcon, QPixmap

from i18n_manager import I18nManager
from samba_backend import get_user_properties, BASE_DN, get_group_properties, update_object_attributes, get_group_by_rid, get_upn_suffixes, get_netbios_name, get_all_user_attributes_with_schema_info, get_base_dn, get_user_certificates
from rotating_tab_widget import RotatingTabWidget
from tab_styles import STYLE_DEFAULT
from shared_properties_tabs import ObjectTab, SecurityTab, ComPlusTab, MemberOfTab, AddressTab, TelephonesTab, OrganizationTab, PasswordReplicationTab, EmailTab
from attribute_editor import AttributeEditorTab

# Constants for userAccountControl bits
UAC_ACCOUNT_DISABLED = 0x0002
UAC_DONT_EXPIRE_PASSWORD = 0x10000
UAC_PASSWORD_CANT_CHANGE = 0x0040
UAC_ENCRYPTED_TEXT_PASSWORD_ALLOWED = 0x0080
UAC_SMARTCARD_REQUIRED = 0x40000
UAC_TRUSTED_FOR_DELEGATION = 0x80000
UAC_NOT_DELEGATED = 0x100000
UAC_USE_DES_KEY_ONLY = 0x200000
UAC_DONT_REQUIRE_PREAUTH = 0x400000
UAC_PASSWORD_EXPIRED = 0x800000
UAC_TRUSTED_TO_AUTHENTICATE_FOR_DELEGATION = 0x1000000

class UserPropertiesDialog(QDialog):
    """Complete dialog for viewing and editing user properties."""

    def __init__(self, samba_conn, user_dn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.user_dn = user_dn
        self.is_advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.user_props = {}
        self.schema_info = {}
        self.editable_user_props = {}
        self.display_name = ""  # Will be set when loading user data

        # Window title will be set after loading user data
        self.setMinimumSize(400, 500)
        self.resize(450, 600)

        self._create_widgets()
        self._create_layout()
        self._load_user_data()
        self._connect_change_signals()

    def _create_widgets(self):
        """Create all widgets for the dialog"""
        self.tab_widget = RotatingTabWidget(logger=self.logger)
        self.tab_widget.setTabStyle(STYLE_DEFAULT)

        # Create all tabs
        self._create_general_tab()
        self.tab_widget.addTab(AddressTab(self.user_props), self.i18n.get_string("user_properties.tab.address"))
        self._create_account_tab()
        self._create_profile_tab()
        self.tab_widget.addTab(TelephonesTab(self.user_props), self.i18n.get_string("user_properties.tab.telephones"))
        self.tab_widget.addTab(OrganizationTab(self.user_props), self.i18n.get_string("user_properties.tab.organization"))

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        
        # Initially disable Apply button until changes are made
        self.apply_button = self.button_box.button(QDialogButtonBox.Apply)
        self.apply_button.setEnabled(False)

    def _create_general_tab(self):
        """Create the General tab"""
        self.general_tab = QWidget()
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("user_properties.tab.general"))

        layout = QVBoxLayout(self.general_tab)

        # User icon and display name header
        header_layout = QHBoxLayout()

        # User icon
        icon_label = QLabel()
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'user.png')
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                # Scale the icon to 32x32 if it's larger
                scaled_pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_label.setPixmap(scaled_pixmap)
            else:
                # Fallback text if icon doesn't load
                icon_label.setText("👤")
                icon_label.setStyleSheet("font-size: 24px;")
        except Exception as e:
            self.logger.error(f"Failed to load user icon: {e}")
            # Fallback text if icon file doesn't exist
            icon_label.setText("👤")
            icon_label.setStyleSheet("font-size: 24px;")

        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(40, 40)

        # Display name label (will be updated when data loads)
        self.display_name_header = QLabel("")
        self.display_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")

        header_layout.addWidget(icon_label)
        header_layout.addWidget(self.display_name_header)
        header_layout.addStretch()

        # Separator line
        separator = QLabel()
        separator.setFrameStyle(QLabel.HLine | QLabel.Sunken)
        separator.setLineWidth(1)

        layout.addLayout(header_layout)
        layout.addWidget(separator)

        # Personal Information Group
        personal_group = QGroupBox(self.i18n.get_string("user_properties.group.personal_info"))
        personal_layout = QFormLayout(personal_group)

        # First name and initials on same row
        name_layout = QHBoxLayout()
        self.first_name_edit = QLineEdit()
        self.initials_edit = QLineEdit()
        self.initials_edit.setMaxLength(6)
        self.initials_edit.setMaximumWidth(80)  # Make initials field smaller

        name_layout.addWidget(self.first_name_edit)
        name_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.initials")))
        name_layout.addWidget(self.initials_edit)

        self.last_name_edit = QLineEdit()
        self.display_name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.office_edit = QLineEdit()

        personal_layout.addRow(self.i18n.get_string("user_properties.label.first_name"), name_layout)
        personal_layout.addRow(self.i18n.get_string("user_properties.label.last_name"), self.last_name_edit)
        personal_layout.addRow(self.i18n.get_string("user_properties.label.display_name"), self.display_name_edit)
        personal_layout.addRow(self.i18n.get_string("user_properties.label.description"), self.description_edit)
        personal_layout.addRow(self.i18n.get_string("user_properties.label.office"), self.office_edit)

        # Contact Information Group
        contact_group = QGroupBox(self.i18n.get_string("user_properties.group.contact_info"))
        contact_layout = QFormLayout(contact_group)

        self.telephone_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.web_page_edit = QLineEdit()

        contact_layout.addRow(self.i18n.get_string("user_properties.label.telephone"), self.telephone_edit)
        contact_layout.addRow(self.i18n.get_string("user_properties.label.email"), self.email_edit)
        contact_layout.addRow(self.i18n.get_string("user_properties.label.web_page"), self.web_page_edit)

        layout.addWidget(personal_group)
        layout.addWidget(contact_group)
        layout.addStretch()

    

    def _create_account_tab(self):
        """Create the Account tab"""
        self.account_tab = QWidget()
        self.tab_widget.addTab(self.account_tab, self.i18n.get_string("user_properties.tab.account"))

        layout = QVBoxLayout(self.account_tab)

        # User logon information
        logon_group = QGroupBox(self.i18n.get_string("user_properties.group.logon_info"))
        logon_layout = QVBoxLayout(logon_group)

        self.user_logon_name_edit = QLineEdit()
        self.domain_combo = QComboBox()
        self.user_logon_name_pre2000_edit = QLineEdit()

        # UPN Suffix layout
        upn_layout = QHBoxLayout()
        upn_layout.addWidget(self.user_logon_name_edit)
        upn_layout.addWidget(self.domain_combo)

        logon_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.user_logon_name")))
        logon_layout.addLayout(upn_layout)
        logon_layout.addSpacing(10)
        logon_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.user_logon_name_pre2000")))
        
        pre2k_layout = QHBoxLayout()
        netbios_name = get_netbios_name(self.samba_conn)
        netbios_label = QLineEdit(f"{netbios_name}\\")
        netbios_label.setReadOnly(True)
        netbios_label.setStyleSheet("background-color: #f0f0f0; border: none;")
        pre2k_layout.addWidget(netbios_label)
        pre2k_layout.addWidget(self.user_logon_name_pre2000_edit)
        logon_layout.addLayout(pre2k_layout)

        # Logon hours and Log On To sections with separators
        logon_section = QHBoxLayout()
        self.logon_hours_btn = QPushButton(self.i18n.get_string("user_properties.button.logon_hours"))
        self.log_on_to_btn = QPushButton(self.i18n.get_string("user_properties.button.log_on_to"))
        logon_section.addWidget(self.logon_hours_btn)
        logon_section.addWidget(self.log_on_to_btn)
        logon_section.addStretch()

        # Unlock account checkbox
        self.unlock_account_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.unlock_account"))

        # Account options
        options_group = QGroupBox(self.i18n.get_string("user_properties.group.account_options"))
        options_layout = QVBoxLayout(options_group)

        self.user_must_change_password_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.must_change_password"))
        self.user_cannot_change_password_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.cannot_change_password"))
        self.password_never_expires_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.password_never_expires"))
        self.reversible_encryption_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.reversible_encryption"))
        self.account_disabled_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.account_disabled"))
        self.smartcard_required_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.smartcard_required"))
        self.account_trusted_for_delegation_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.trusted_for_delegation"))
        self.account_sensitive_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.account_sensitive"))
        self.use_des_encryption_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.use_des_encryption"))
        self.not_require_preauth_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.not_require_preauth"))

        options_layout.addWidget(self.user_must_change_password_check)
        options_layout.addWidget(self.user_cannot_change_password_check)
        options_layout.addWidget(self.password_never_expires_check)
        options_layout.addWidget(self.reversible_encryption_check)
        options_layout.addWidget(self.account_disabled_check)
        options_layout.addWidget(self.smartcard_required_check)
        options_layout.addWidget(self.account_trusted_for_delegation_check)
        options_layout.addWidget(self.account_sensitive_check)
        options_layout.addWidget(self.use_des_encryption_check)
        options_layout.addWidget(self.not_require_preauth_check)

        options_scroll_area = QScrollArea()
        options_scroll_area.setWidget(options_group)
        options_scroll_area.setWidgetResizable(True)
        options_scroll_area.setFixedHeight(140)

        # Account expires
        expires_group = QGroupBox(self.i18n.get_string("user_properties.group.account_expires"))
        expires_layout = QVBoxLayout(expires_group)

        self.never_expires_radio = QRadioButton(self.i18n.get_string("user_properties.radio.never_expires"))
        self.never_expires_radio.setChecked(True)

        end_of_layout = QHBoxLayout()
        self.end_of_radio = QRadioButton(self.i18n.get_string("user_properties.radio.end_of"))
        self.expire_date_edit = QDateTimeEdit()
        self.expire_date_edit.setCalendarPopup(True)
        self.expire_date_edit.setEnabled(False)

        self.end_of_radio.toggled.connect(self.expire_date_edit.setEnabled)

        end_of_layout.addWidget(self.end_of_radio)
        end_of_layout.addWidget(self.expire_date_edit)
        end_of_layout.addStretch()

        expires_layout.addWidget(self.never_expires_radio)
        expires_layout.addLayout(end_of_layout)

        # Tab layout
        layout.addWidget(logon_group)
        layout.addLayout(logon_section)
        layout.addSpacing(20)
        layout.addWidget(self.unlock_account_check)
        layout.addSpacing(20)
        layout.addWidget(options_scroll_area)
        layout.addWidget(expires_group)
        layout.addStretch()

    def _create_profile_tab(self):
        """Create the Profile tab"""
        self.profile_tab = QWidget()
        self.tab_widget.addTab(self.profile_tab, self.i18n.get_string("user_properties.tab.profile"))

        layout = QVBoxLayout(self.profile_tab)

        # User profile
        profile_group = QGroupBox(self.i18n.get_string("user_properties.group.user_profile"))
        profile_layout = QFormLayout(profile_group)

        self.profile_path_edit = QLineEdit()
        self.logon_script_edit = QLineEdit()

        profile_layout.addRow(self.i18n.get_string("user_properties.label.profile_path"), self.profile_path_edit)
        profile_layout.addRow(self.i18n.get_string("user_properties.label.logon_script"), self.logon_script_edit)

        # Home folder
        home_group = QGroupBox(self.i18n.get_string("user_properties.group.home_folder"))
        home_layout = QVBoxLayout(home_group)

        self.local_path_radio = QCheckBox(self.i18n.get_string("user_properties.checkbox.local_path"))
        self.local_path_edit = QLineEdit()
        local_layout = QHBoxLayout()
        local_layout.addWidget(self.local_path_radio)
        local_layout.addWidget(self.local_path_edit)

        self.connect_radio = QCheckBox(self.i18n.get_string("user_properties.checkbox.connect"))
        self.drive_combo = QComboBox()
        drives = [f"{chr(i)}:" for i in range(ord('A'), ord('Z')+1)]
        self.drive_combo.addItems(drives)
        self.connect_path_edit = QLineEdit()

        connect_layout = QHBoxLayout()
        connect_layout.addWidget(self.connect_radio)
        connect_layout.addWidget(self.drive_combo)
        connect_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.to")))
        connect_layout.addWidget(self.connect_path_edit)

        home_layout.addLayout(local_layout)
        home_layout.addLayout(connect_layout)

        layout.addWidget(profile_group)
        layout.addWidget(home_group)
        layout.addStretch()

    

    def _create_com_plus_tab(self):
        """Create the COM+ tab"""
        self.com_plus_tab = QWidget()
        self.tab_widget.addTab(self.com_plus_tab, self.i18n.get_string("user_properties.tab.com_plus"))

        layout = QVBoxLayout(self.com_plus_tab)

        partition_header = QLabel(self.i18n.get_string("user_properties.title.com_partition_set"))
        partition_group = QGroupBox(self.i18n.get_string("user_properties.group.com_partition_set"))
        partition_layout = QVBoxLayout(partition_group)
        self.partition_combo = QComboBox()
        partition_layout.addWidget(self.partition_combo)

        layout.addWidget(partition_header)
        layout.addWidget(partition_group)
        layout.addStretch()

    def _create_layout(self):
        """Create the main dialog layout"""
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

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

    def _load_user_data(self):
        """Load user data from Active Directory, including schema info."""
        self.user_props, self.schema_info = get_all_user_attributes_with_schema_info(self.samba_conn, self.user_dn)
        if not self.user_props:
            self.logger.error(f"Could not load properties for user: {self.user_dn}")
            # Optionally, disable the dialog or show an error message
            return

        self.editable_user_props = copy.deepcopy(self.user_props)

        # Populate all the fields as before
        self._populate_all_tabs()

    def _populate_all_tabs(self):
        """Populate all tabs with data from self.user_props."""
        # General Tab
        self.first_name_edit.setText(self.user_props.get('givenName', [''])[0])
        self.initials_edit.setText(self.user_props.get('initials', [''])[0])
        self.last_name_edit.setText(self.user_props.get('sn', [''])[0])
        self.display_name_edit.setText(self.user_props.get('displayName', [''])[0])
        self.description_edit.setText(self.user_props.get('description', [''])[0])
        self.office_edit.setText(self.user_props.get('physicalDeliveryOfficeName', [''])[0])
        self.telephone_edit.setText(self.user_props.get('telephoneNumber', [''])[0])
        self.email_edit.setText(self.user_props.get('mail', [''])[0])
        self.web_page_edit.setText(self.user_props.get('wWWHomePage', [''])[0])

        # Address Tab is now a shared tab and loads its own data
        # Account Tab
        sam_account_name = self.user_props.get('sAMAccountName', [''])[0]
        upn = self.user_props.get('userPrincipalName', [''])[0]

        self.domain_combo.clear()
        base_dn = get_base_dn(self.samba_conn)
        if not base_dn:
            return dn_string
            
        domain_parts = [p.split('=')[1] for p in base_dn.split(',') if p.lower().startswith('dc=')]
        primary_domain = ".".join(domain_parts)
        all_suffixes = [primary_domain]
        additional_suffixes = get_upn_suffixes(self.samba_conn)
        if additional_suffixes:
            all_suffixes.extend(additional_suffixes)
        formatted_suffixes = sorted(list(set([f"@{s}" for s in all_suffixes])))
        self.domain_combo.addItems(formatted_suffixes)

        if '@' in upn:
            upn_name, upn_domain = upn.split('@', 1)
            self.user_logon_name_edit.setText(upn_name)
            domain_text = f"@{upn_domain}"
            if self.domain_combo.findText(domain_text) != -1:
                self.domain_combo.setCurrentText(domain_text)
        else:
            self.user_logon_name_edit.setText(sam_account_name)
            if self.domain_combo.count() > 0:
                self.domain_combo.setCurrentIndex(0)

        self.user_logon_name_pre2000_edit.setText(sam_account_name)

        uac = int(self.user_props.get('userAccountControl', ['0'])[0])
        self.account_disabled_check.setChecked(bool(uac & UAC_ACCOUNT_DISABLED))
        
        # "User must change password at next logon" is determined by pwdLastSet=0, not UAC flag
        pwd_last_set = self.user_props.get('pwdLastSet', ['1'])[0]
        must_change_password = (pwd_last_set == '0')
        
        self.user_must_change_password_check.setChecked(must_change_password)
        self.password_never_expires_check.setChecked(bool(uac & UAC_DONT_EXPIRE_PASSWORD))
        self.reversible_encryption_check.setChecked(bool(uac & UAC_ENCRYPTED_TEXT_PASSWORD_ALLOWED))
        self.user_cannot_change_password_check.setChecked(bool(uac & UAC_PASSWORD_CANT_CHANGE))
        self.smartcard_required_check.setChecked(bool(uac & UAC_SMARTCARD_REQUIRED))
        self.account_trusted_for_delegation_check.setChecked(bool(uac & UAC_TRUSTED_FOR_DELEGATION))
        self.account_sensitive_check.setChecked(bool(uac & UAC_NOT_DELEGATED))
        self.use_des_encryption_check.setChecked(bool(uac & UAC_USE_DES_KEY_ONLY))
        self.not_require_preauth_check.setChecked(bool(uac & UAC_DONT_REQUIRE_PREAUTH))

        account_expires = self.user_props.get('accountExpires', ['0'])[0]
        if account_expires and account_expires != '0' and account_expires != '9223372036854775807':
            self.end_of_radio.setChecked(True)
            self.expire_date_edit.setDateTime(QDateTime.currentDateTime())
        else:
            self.never_expires_radio.setChecked(True)

        # Profile Tab
        self.profile_path_edit.setText(self.user_props.get('profilePath', [''])[0])
        self.logon_script_edit.setText(self.user_props.get('scriptPath', [''])[0])
        home_directory = self.user_props.get('homeDirectory', [''])[0]
        home_drive = self.user_props.get('homeDrive', [''])[0]

        if home_drive and home_directory:
            self.connect_radio.setChecked(True)
            self.drive_combo.setCurrentText(home_drive)
            self.connect_path_edit.setText(home_directory)
        elif home_directory:
            self.local_path_radio.setChecked(True)
            self.local_path_edit.setText(home_directory)

        # Telephones Tab is now a shared tab and loads its own data
        # Organization Tab is now a shared tab and loads its own data

        # Update window title
        self.display_name = self.user_props.get('displayName', [''])[0] or self.user_props.get('cn', ['User'])[0]
        self.setWindowTitle(f"{self.display_name} Properties")
        self.display_name_header.setText(self.display_name)

        # Add tabs according to specified order
        if not self.is_advanced_view:
            # Normal view: Member Of, COM+
            self.tab_widget.addTab(MemberOfTab(self.samba_conn, self.user_dn, self.user_props, show_primary_group=True, change_callback=self._check_for_changes), self.i18n.get_string("user_properties.tab.member_of"))
            self.tab_widget.addTab(ComPlusTab(), self.i18n.get_string("user_properties.tab.com_plus"))
        else:
            # Advanced view: Row 2: Password Replication, Object, Security, COM+, Attribute Editor
            # Row 3: Organization, Published Certificates, Member Of, E-mail
            self.tab_widget.addTab(PasswordReplicationTab(self.samba_conn, self.user_dn), self.i18n.get_string("user_properties.tab.password_replication"))
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.user_dn, self.user_props), self.i18n.get_string("user_properties.tab.object"))
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.user_dn), self.i18n.get_string("user_properties.tab.security"))
            self.tab_widget.addTab(ComPlusTab(), self.i18n.get_string("user_properties.tab.com_plus"))
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.user_dn), "Attribute Editor")
            # Row 3 tabs
            self.tab_widget.addTab(PublishedCertificatesTab(self.samba_conn, self.user_dn), self.i18n.get_string("user_properties.tab.published_certificates"))
            self.tab_widget.addTab(MemberOfTab(self.samba_conn, self.user_dn, self.user_props, show_primary_group=True, change_callback=self._check_for_changes), self.i18n.get_string("user_properties.tab.member_of"))
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.user_dn, self.user_props), self.i18n.get_string("user_properties.tab.email"))

    def _connect_signals(self):
        """Connect all UI element signals to the attribute change handler."""
        self.widget_to_attribute_map = {
            self.first_name_edit: 'givenName',
            self.initials_edit: 'initials',
            self.last_name_edit: 'sn',
            self.display_name_edit: 'displayName',
            self.description_edit: 'description',
            self.office_edit: 'physicalDeliveryOfficeName',
            self.telephone_edit: 'telephoneNumber',
            self.email_edit: 'mail',
            self.web_page_edit: 'wWWHomePage',
            self.user_logon_name_edit: 'userPrincipalName', # Special handling for UPN
            self.user_logon_name_pre2000_edit: 'sAMAccountName',
            self.profile_path_edit: 'profilePath',
            self.logon_script_edit: 'scriptPath',
            self.local_path_edit: 'homeDirectory', # Special handling for home dir
            self.connect_path_edit: 'homeDirectory', # Special handling for home dir
            self.drive_combo: 'homeDrive',
        }

        for widget, attr_name in self.widget_to_attribute_map.items():
            if isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._on_attribute_change)
            elif isinstance(widget, QTextEdit):
                # QTextEdit doesn't have editingFinished, textChanged is the only option
                # for live updates. The alternative is to only update on apply/ok.
                widget.textChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QRadioButton):
                widget.toggled.connect(self._on_attribute_change)

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
            elif isinstance(sender, QCheckBox):
                new_value = 'TRUE' if sender.isChecked() else 'FALSE'
            elif isinstance(sender, QRadioButton) and sender.isChecked():
                # Special handling for radio buttons if needed
                pass

            # Update the editable properties dictionary
            if attr_name in self.editable_user_props:
                if self.editable_user_props[attr_name] != [new_value]:
                    self.logger.debug(f"Attribute '{attr_name}' changed from '{self.editable_user_props.get(attr_name, [''])[0]}' to '{new_value}'")
                    self.editable_user_props[attr_name] = [new_value]
            else:
                self.logger.debug(f"Attribute '{attr_name}' set to '{new_value}'")
                self.editable_user_props[attr_name] = [new_value]

    def _select_manager(self):
        """Open manager selection dialog."""
        from search_dialogs import UserPickerDialog
        
        dialog = UserPickerDialog(self.samba_conn, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_user = dialog.get_selected_object()
            if selected_user:
                # Update the manager field
                manager_dn = selected_user['dn']
                display_name = selected_user['display_name']
                
                self.manager_edit.setText(display_name)
                
                # Update the local properties
                self.editable_user_props['manager'] = [manager_dn]
                
                self.logger.info(f"Selected manager: {display_name} ({manager_dn})")

    def _validate_changes(self):
        """Validate all changes before applying to Active Directory."""
        errors = []
        
        # Define read-only attributes that should never be modified
        READ_ONLY_ATTRIBUTES = {
            'objectGUID', 'objectSid', 'sAMAccountType',
            'whenCreated', 'whenChanged', 'lastLogon', 'lastLogonTimestamp', 
            'lastLogoff', 'pwdLastSet', 'accountExpires', 'badPasswordTime',
            'uSNCreated', 'uSNChanged', 'logonCount', 'badPwdCount',
            'systemFlags', 'instanceType', 'objectClass', 'objectCategory',
            'primaryGroupID', 'primaryGroupToken', 'nextRid', 'revision',
            'distinguishedName', 'canonicalName', 'parentGUID', 'masteredBy'
        }
        
        # Required attributes that cannot be empty
        REQUIRED_ATTRIBUTES = {'cn', 'objectCategory', 'objectClass', 'sAMAccountName'}
        
        for attr_name, new_values in self.editable_user_props.items():
            # Skip unchanged attributes
            old_values = self.user_props.get(attr_name, [])
            if old_values == new_values:
                continue
            
            # Check for attempts to modify read-only attributes
            if attr_name in READ_ONLY_ATTRIBUTES:
                errors.append(self.i18n.get_text("user_properties.validation.readonly_attribute", attr_name))
                continue
            
            # Check required attributes are not empty
            if attr_name in REQUIRED_ATTRIBUTES:
                if not new_values or (len(new_values) == 1 and not new_values[0].strip()):
                    errors.append(self.i18n.get_text("user_properties.validation.required_attribute", attr_name))
                    continue
            
            # Email validation with improved requirements
            if attr_name == 'mail' and new_values and new_values[0]:
                email = new_values[0].strip()
                if email and '@' in email:
                    parts = email.split('@')
                    if len(parts) != 2:  # Must have exactly one @
                        errors.append(self.i18n.get_text("user_properties.validation.email_invalid", email))
                    else:
                        before_at, after_at = parts
                        # Check before @ has at least one alphanumeric
                        if not before_at or not any(c.isalnum() for c in before_at):
                            errors.append(self.i18n.get_text("user_properties.validation.email_before_at", email))
                        # Check after @ has at least one alphanumeric  
                        elif not after_at or not any(c.isalnum() for c in after_at):
                            errors.append(self.i18n.get_text("user_properties.validation.email_after_at", email))
                elif email:  # Non-empty but no @
                    errors.append(self.i18n.get_text("user_properties.validation.email_invalid", email))
            
            # sAMAccountName validation
            if attr_name == 'sAMAccountName' and new_values and new_values[0]:
                sam_name = new_values[0].strip()
                if not sam_name.replace('_', '').replace('-', '').isalnum():
                    errors.append(self.i18n.get_text("user_properties.validation.sam_invalid", sam_name))
        
        return errors
    
    def _build_modifications(self):
        """Build LDAP modification list from validated changes."""
        modifications = []
        
        for attr_name, new_values in self.editable_user_props.items():
            old_values = self.user_props.get(attr_name, [])
            
            # Skip if values haven't changed
            if old_values == new_values:
                continue
            
            try:
                # Handle empty values (delete attribute)
                if not new_values or (len(new_values) == 1 and not new_values[0].strip()):
                    modifications.append((ldap.MOD_DELETE, attr_name, None))
                else:
                    # Filter out empty strings and encode for LDAP
                    encoded_values = []
                    for value in new_values:
                        if value.strip():  # Only add non-empty values
                            encoded_values.append(value.encode('utf-8'))
                    
                    if encoded_values:
                        modifications.append((ldap.MOD_REPLACE, attr_name, encoded_values))
                    else:
                        modifications.append((ldap.MOD_DELETE, attr_name, None))
                        
            except Exception as e:
                self.logger.error(f"Error preparing modification for {attr_name}: {e}")
                continue
        
        return modifications
    
    def _reset_invalid_changes(self):
        """Reset editable properties back to original values."""
        self.editable_user_props = copy.deepcopy(self.user_props)
        # Refresh UI to show original values
        self._populate_tabs()

    def apply_changes(self):
        """Apply the changes made in the dialog to Active Directory."""
        self.logger.info("Applying changes for user to Active Directory")
        
        # First, validate all changes
        validation_errors = self._validate_changes()
        if validation_errors:
            error_msg = self.i18n.get_string("user_properties.validation.errors_header") + "\n\n" + "\n".join(validation_errors)
            QMessageBox.warning(
                self, 
                self.i18n.get_string("dialog.common.error.title"),
                error_msg
            )
            # Reset invalid changes back to original values
            self._reset_invalid_changes()
            return
        
        # Build list of LDAP modifications for valid changes
        modifications = self._build_modifications()
        
        # Apply modifications if any exist
        if modifications:
            success, message = update_object_attributes(self.samba_conn, self.user_dn, modifications)
            
            if success:
                # Update local properties with changes
                self.user_props.update(self.editable_user_props)
                
                QMessageBox.information(
                    self, 
                    self.i18n.get_string("dialog.common.success.title"),
                    self.i18n.get_text("user_properties.apply.success", str(len(modifications)))
                )
                
                self.logger.info(f"Successfully applied {len(modifications)} changes to user {self.user_dn}")
                # Apply Member Of tab changes if successful
                self._apply_member_of_changes()
                # Disable Apply button since changes have been applied
                self.apply_button.setEnabled(False)
            else:
                QMessageBox.critical(
                    self, 
                    self.i18n.get_string("dialog.common.error.title"),
                    self.i18n.get_string("user_properties.apply.error") + "\n\n" + message
                )
                # Reset back to original values on failure
                self._reset_invalid_changes()
                self.logger.error(f"Failed to apply changes to user {self.user_dn}: {message}")
        else:
            # Even if no property modifications, still apply Member Of changes
            member_of_changes_applied = self._apply_member_of_changes()
            # Disable Apply button if no changes were made
            if not member_of_changes_applied:
                self.apply_button.setEnabled(False)
    
    def _apply_member_of_changes(self):
        """Apply Member Of tab changes if any exist. Returns True if changes were applied."""
        changes_applied = False
        
        # Find the Member Of tab and apply its changes
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if hasattr(widget, 'apply_changes') and hasattr(widget, 'pending_additions'):
                # This is a Member Of tab with pending changes
                if widget.pending_additions or widget.pending_removals:
                    errors = widget.apply_changes()
                    changes_applied = True
                    
                    if errors:
                        # Show errors if any occurred
                        error_msg = "Some group membership changes failed:\n\n" + "\n".join(errors)
                        QMessageBox.warning(self, 
                            self.i18n.get_string("dialog.common.error.title"),
                            error_msg)
                    else:
                        self.logger.info("Successfully applied Member Of tab changes")
                        # Refresh the user properties to show updated membership
                        self._refresh_user_properties()
                        # Disable Apply button since changes have been applied
                        self.apply_button.setEnabled(False)
        
        return changes_applied
    
    def _refresh_user_properties(self):
        """Refresh all user properties from the directory and update all tabs."""
        # Reload user data from directory
        self.user_props, self.schema_info = get_all_user_attributes_with_schema_info(self.samba_conn, self.user_dn)
        if not self.user_props:
            self.logger.error(f"Could not refresh properties for user: {self.user_dn}")
            return
        
        # Update editable props with fresh data
        self.editable_user_props = copy.deepcopy(self.user_props)
        
        # Repopulate all tabs with fresh data
        self._populate_all_tabs()
        
        # Find Member Of tabs and refresh them with fresh data
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if hasattr(widget, '_load_membership_data'):
                # Update the parent_props reference to fresh data and reload
                widget.parent_props = self.user_props
                widget._load_membership_data()
    
    def _check_for_changes(self):
        """Check if there are any pending changes and update Apply button state."""
        has_changes = False
        
        # Check for property modifications
        modifications = self._build_modifications()
        if modifications:
            has_changes = True
        
        # Check for Member Of tab changes
        if not has_changes:
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if hasattr(widget, 'pending_additions') and hasattr(widget, 'pending_removals'):
                    if widget.pending_additions or widget.pending_removals:
                        has_changes = True
                        break
        
        # Enable/disable Apply button based on changes
        self.apply_button.setEnabled(has_changes)
    
    def _connect_change_signals(self):
        """Connect all input widgets to check for changes."""
        # Define potential widget names and connect them if they exist
        text_widget_names = [
            'first_name_edit', 'initials_edit', 'last_name_edit', 
            'display_name_edit', 'description_edit', 'office_edit',
            'telephone_edit', 'email_edit', 'web_page_edit',
            'user_logon_name_edit', 'user_logon_name_pre2000_edit',
            'profile_path_edit', 'logon_script_edit', 'local_path_edit',
            'connect_path_edit'
        ]
        
        for widget_name in text_widget_names:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                if hasattr(widget, 'textChanged'):
                    widget.textChanged.connect(self._check_for_changes)
        
        # Connect checkbox changes  
        checkbox_widget_names = [
            'user_must_change_password_check', 'user_cannot_change_password_check',
            'password_never_expires_check', 'account_disabled_check',
            'unlock_account_check', 'reversible_encryption_check',
            'smartcard_required_check', 'account_trusted_for_delegation_check',
            'account_sensitive_check', 'use_des_encryption_check'
        ]
        
        for widget_name in checkbox_widget_names:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                if hasattr(widget, 'toggled'):
                    widget.toggled.connect(self._check_for_changes)
        
        # Connect combo box changes
        combo_widget_names = ['domain_combo', 'drive_combo', 'partition_combo']
        
        for widget_name in combo_widget_names:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                if hasattr(widget, 'currentTextChanged'):
                    widget.currentTextChanged.connect(self._check_for_changes)
                elif hasattr(widget, 'currentIndexChanged'):
                    widget.currentIndexChanged.connect(self._check_for_changes)
    
    def accept(self):
        """Override accept to apply changes before closing."""
        # Apply changes first
        self.apply_changes()
        
        # Close the dialog
        super().accept()


class PublishedCertificatesTab(QWidget):
    """A tab to display published certificates for a user."""
    def __init__(self, samba_conn, user_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.user_dn = user_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        self._create_widgets()
        self._create_layout()
        self._load_certificates()

    def _create_widgets(self):
        self.info_label = QLabel(self.i18n.get_string("published_certificates.label.info"))
        self.info_label.setWordWrap(True)
        self.certs_table = QTableWidget()
        self.certs_table.setColumnCount(4)
        self.certs_table.setHorizontalHeaderLabels([
            self.i18n.get_string("published_certificates.header.issued_to"),
            self.i18n.get_string("published_certificates.header.issued_by"),
            self.i18n.get_string("published_certificates.header.intended_purposes"),
            self.i18n.get_string("published_certificates.header.expiration")
        ])
        self.certs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.certs_table.verticalHeader().hide()
        
        self.add_from_file_btn = QPushButton(self.i18n.get_string("published_certificates.button.add_from_file"))
        self.remove_btn = QPushButton(self.i18n.get_string("published_certificates.button.remove"))
        self.copy_to_btn = QPushButton(self.i18n.get_string("published_certificates.button.copy_to"))

    def _create_layout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.certs_table)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_from_file_btn)
        button_layout.addWidget(self.remove_btn)
        button_layout.addWidget(self.copy_to_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _load_certificates(self):
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            self.logger.warning("cryptography module not available - certificates cannot be parsed")
            self.info_label.setText("cryptography module required to display certificates")
            return
            
        certs = get_user_certificates(self.samba_conn, self.user_dn)
        self.certs_table.setRowCount(0)
        for cert_data in certs:
            try:
                cert = x509.load_der_x509_certificate(cert_data, default_backend())
                row = self.certs_table.rowCount()
                self.certs_table.insertRow(row)
                self.certs_table.setItem(row, 0, QTableWidgetItem(cert.subject.rfc4514_string()))
                self.certs_table.setItem(row, 1, QTableWidgetItem(cert.issuer.rfc4514_string()))
                self.certs_table.setItem(row, 2, QTableWidgetItem(""))  # Intended Purposes not easily available
                self.certs_table.setItem(row, 3, QTableWidgetItem(cert.not_valid_after.strftime("%Y-%m-%d %H:%M:%S")))
            except Exception as e:
                self.logger.error(f"Error parsing certificate: {e}")
                continue
