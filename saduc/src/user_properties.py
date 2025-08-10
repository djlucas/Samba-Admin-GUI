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
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QLineEdit, QCheckBox, QPushButton, QDialogButtonBox, QListWidget,
    QComboBox, QTextEdit, QGroupBox, QGridLayout, QLabel, QSpinBox,
    QListWidgetItem, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QRadioButton, QDateTimeEdit
)
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QIcon, QPixmap

from i18n_manager import I18nManager
from samba_backend import get_user_properties

# Constants for userAccountControl bits
UAC_ACCOUNT_DISABLED = 0x0002
UAC_DONT_EXPIRE_PASSWORD = 0x10000
UAC_PASSWORD_CANT_CHANGE = 0x0040
UAC_SMARTCARD_REQUIRED = 0x40000
UAC_TRUSTED_FOR_DELEGATION = 0x80000
UAC_NOT_DELEGATED = 0x100000
UAC_USE_DES_KEY_ONLY = 0x200000
UAC_DONT_REQUIRE_PREAUTH = 0x400000
UAC_PASSWORD_EXPIRED = 0x800000
UAC_TRUSTED_TO_AUTHENTICATE_FOR_DELEGATION = 0x1000000

class UserPropertiesDialog(QDialog):
    """Complete dialog for viewing and editing user properties."""
    
    def __init__(self, samba_conn, user_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.user_dn = user_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        
        self.user_props = {}
        self.display_name = ""  # Will be set when loading user data
        
        # Window title will be set after loading user data
        self.setMinimumSize(400, 500)
        self.resize(650, 600)
        
        self._create_widgets()
        self._create_layout()
        self._load_user_data()
        
    def _create_widgets(self):
        """Create all widgets for the dialog"""
        self.tab_widget = QTabWidget()
        
        # Enable multi-row tabs
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setUsesScrollButtons(False)
        # Force tabs to wrap to multiple rows when needed
        self.tab_widget.setElideMode(Qt.ElideNone)
        
        # Create all tabs in two rows
        # First row: General, Address, Account, Profile
        self._create_general_tab()
        self._create_address_tab() 
        self._create_account_tab()
        self._create_profile_tab()
        
        # Second row: Telephones, Organization, Member Of, COM+
        self._create_telephones_tab()
        self._create_organization_tab()
        self._create_member_of_tab()
        self._create_com_plus_tab()
        
        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        
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
            pixmap = QPixmap("src/res/icons/user.png")
            if not pixmap.isNull():
                # Scale the icon to 32x32 if it's larger
                scaled_pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_label.setPixmap(scaled_pixmap)
            else:
                # Fallback text if icon doesn't load
                icon_label.setText("👤")
                icon_label.setStyleSheet("font-size: 24px;")
        except:
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
        
    def _create_address_tab(self):
        """Create the Address tab"""
        self.address_tab = QWidget()
        self.tab_widget.addTab(self.address_tab, self.i18n.get_string("user_properties.tab.address"))
        
        layout = QVBoxLayout(self.address_tab)
        
        form_layout = QFormLayout()
        
        self.street_edit = QTextEdit()
        self.street_edit.setMaximumHeight(60)
        self.po_box_edit = QLineEdit()
        self.city_edit = QLineEdit()
        self.state_edit = QLineEdit()
        self.zip_edit = QLineEdit()
        self.country_edit = QComboBox()
        self.country_edit.setEditable(True)
        
        # Add common countries - could be i18n'd too
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
        
    def _create_account_tab(self):
        """Create the Account tab"""
        self.account_tab = QWidget()
        self.tab_widget.addTab(self.account_tab, self.i18n.get_string("user_properties.tab.account"))
        
        layout = QVBoxLayout(self.account_tab)
        
        # User logon information
        logon_group = QGroupBox(self.i18n.get_string("user_properties.group.logon_info"))
        logon_layout = QGridLayout(logon_group)
        
        self.user_logon_name_edit = QLineEdit()
        self.domain_combo = QComboBox()
        # Domain will be populated from samba connection - no hardcoding
        
        self.user_logon_name_pre2000_edit = QLineEdit()
        
        logon_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.user_logon_name")), 0, 0)
        logon_layout.addWidget(self.user_logon_name_edit, 0, 1)
        logon_layout.addWidget(self.domain_combo, 0, 2)
        logon_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.user_logon_name_pre2000")), 1, 0)
        logon_layout.addWidget(self.user_logon_name_pre2000_edit, 1, 1, 1, 2)
        
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
        self.account_disabled_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.account_disabled"))
        self.smartcard_required_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.smartcard_required"))
        self.account_trusted_for_delegation_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.trusted_for_delegation"))
        self.account_sensitive_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.account_sensitive"))
        self.use_des_encryption_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.use_des_encryption"))
        self.not_require_preauth_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.not_require_preauth"))
        
        options_layout.addWidget(self.user_must_change_password_check)
        options_layout.addWidget(self.user_cannot_change_password_check)
        options_layout.addWidget(self.password_never_expires_check)
        options_layout.addWidget(self.account_disabled_check)
        options_layout.addWidget(self.smartcard_required_check)
        options_layout.addWidget(self.account_trusted_for_delegation_check)
        options_layout.addWidget(self.account_sensitive_check)
        options_layout.addWidget(self.use_des_encryption_check)
        options_layout.addWidget(self.not_require_preauth_check)
        
        # Account expires
        expires_group = QGroupBox(self.i18n.get_string("user_properties.group.account_expires"))
        expires_layout = QVBoxLayout(expires_group)
        
        self.never_expires_radio = QRadioButton(self.i18n.get_string("user_properties.radio.never_expires"))
        self.never_expires_radio.setChecked(True)
        
        end_of_layout = QHBoxLayout()
        self.end_of_radio = QRadioButton(self.i18n.get_string("user_properties.radio.end_of"))
        from PyQt5.QtWidgets import QDateTimeEdit
        self.expire_date_edit = QDateTimeEdit()
        self.expire_date_edit.setCalendarPopup(True)
        self.expire_date_edit.setEnabled(False)
        
        # Connect radio button to enable/disable date picker
        self.end_of_radio.toggled.connect(self.expire_date_edit.setEnabled)
        
        end_of_layout.addWidget(self.end_of_radio)
        end_of_layout.addWidget(self.expire_date_edit)
        end_of_layout.addStretch()
        
        expires_layout.addWidget(self.never_expires_radio)
        expires_layout.addLayout(end_of_layout)
        
        # Tab layout
        layout.addWidget(logon_group)
        layout.addLayout(logon_section)
        layout.addWidget(self.unlock_account_check)
        layout.addWidget(options_group)
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
        
    def _create_telephones_tab(self):
        """Create the Telephones tab"""
        self.telephones_tab = QWidget()
        self.tab_widget.addTab(self.telephones_tab, self.i18n.get_string("user_properties.tab.telephones"))
        
        layout = QVBoxLayout(self.telephones_tab)
        
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
        
    def _create_organization_tab(self):
        """Create the Organization tab"""
        self.organization_tab = QWidget()
        self.tab_widget.addTab(self.organization_tab, self.i18n.get_string("user_properties.tab.organization"))
        
        layout = QVBoxLayout(self.organization_tab)
        
        form_layout = QFormLayout()
        
        self.title_edit = QLineEdit()
        self.department_edit = QLineEdit()
        self.company_edit = QLineEdit()
        self.manager_edit = QLineEdit()
        
        # Manager selection button
        manager_layout = QHBoxLayout()
        manager_layout.addWidget(self.manager_edit)
        manager_button = QPushButton(self.i18n.get_string("user_properties.button.change"))
        manager_button.clicked.connect(self._select_manager)
        manager_layout.addWidget(manager_button)
        
        # Direct reports list
        self.direct_reports_list = QListWidget()
        self.direct_reports_list.setMaximumHeight(100)
        
        form_layout.addRow(self.i18n.get_string("user_properties.label.title"), self.title_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.department"), self.department_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.company"), self.company_edit)
        form_layout.addRow(self.i18n.get_string("user_properties.label.manager"), manager_layout)
        form_layout.addRow(self.i18n.get_string("user_properties.label.direct_reports"), self.direct_reports_list)
        
        layout.addLayout(form_layout)
        layout.addStretch()
        
    def _create_member_of_tab(self):
        """Create the Member Of tab"""
        self.member_of_tab = QWidget()
        self.tab_widget.addTab(self.member_of_tab, self.i18n.get_string("user_properties.tab.member_of"))
        
        layout = QVBoxLayout(self.member_of_tab)
        
        # Member of table with headers
        from PyQt5.QtWidgets import QHeaderView
        self.member_of_table = QTableWidget()
        self.member_of_table.setColumnCount(2)
        self.member_of_table.setHorizontalHeaderLabels([
            self.i18n.get_string("user_properties.header.name"),
            self.i18n.get_string("user_properties.header.folder")
        ])
        
        # Set column widths
        header = self.member_of_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.resizeSection(0, 150)  # Name column width
        
        # Buttons
        button_layout = QHBoxLayout()
        self.add_to_group_btn = QPushButton(self.i18n.get_string("user_properties.button.add"))
        self.remove_from_group_btn = QPushButton(self.i18n.get_string("user_properties.button.remove"))
        
        self.add_to_group_btn.clicked.connect(self._add_to_group)
        self.remove_from_group_btn.clicked.connect(self._remove_from_group)
        
        button_layout.addWidget(self.add_to_group_btn)
        button_layout.addWidget(self.remove_from_group_btn)
        button_layout.addStretch()
        
        # Primary group
        primary_layout = QHBoxLayout()
        self.primary_group_label = QLabel()
        self.set_primary_btn = QPushButton(self.i18n.get_string("user_properties.button.set_primary"))
        self.set_primary_btn.clicked.connect(self._set_primary_group)
        
        primary_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.primary_group")))
        primary_layout.addWidget(self.primary_group_label)
        primary_layout.addWidget(self.set_primary_btn)
        primary_layout.addStretch()
        
        layout.addWidget(self.member_of_table)
        layout.addLayout(button_layout)
        layout.addLayout(primary_layout)
        
    def _create_com_plus_tab(self):
        """Create the COM+ tab"""
        self.com_plus_tab = QWidget()
        self.tab_widget.addTab(self.com_plus_tab, self.i18n.get_string("user_properties.tab.com_plus"))
        
        layout = QVBoxLayout(self.com_plus_tab)
        
        # COM+ partition set
        partition_header = QLabel(self.i18n.get_string("user_properties.title.com_partition_set"))
        partition_group = QGroupBox(self.i18n.get_string("user_properties.group.com_partition_set"))
        partition_layout = QVBoxLayout(partition_group)
        self.partition_combo = QComboBox()
        partition_layout.addWidget(self.partition_combo)
        # will be populated later
        
        layout.addWidget(partition_header)
        layout.addWidget(partition_group)
        layout.addStretch()
        
    def _create_layout(self):
        """Create the main dialog layout"""
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)
        
    def _load_user_data(self):
        """Load user data from Active Directory"""
        self.user_props = get_user_properties(self.samba_conn, self.user_dn)
        if not self.user_props:
            self.logger.error(f"Could not load properties for user: {self.user_dn}")
            return
            
        # Get domain from samba connection for UPN dropdown
        if hasattr(self.samba_conn, 'domain') and self.samba_conn.domain:
            self.domain_combo.addItem(f"@{self.samba_conn.domain}")
            
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
        
        # Address Tab
        self.street_edit.setText(self.user_props.get('streetAddress', [''])[0])
        self.po_box_edit.setText(self.user_props.get('postOfficeBox', [''])[0])
        self.city_edit.setText(self.user_props.get('l', [''])[0])  # l = locality/city
        self.state_edit.setText(self.user_props.get('st', [''])[0])  # st = state
        self.zip_edit.setText(self.user_props.get('postalCode', [''])[0])
        self.country_edit.setCurrentText(self.user_props.get('co', [''])[0])  # co = country
        
        # Account Tab
        sam_account_name = self.user_props.get('sAMAccountName', [''])[0]
        upn = self.user_props.get('userPrincipalName', [''])[0]
        
        # Extract UPN parts
        if '@' in upn:
            upn_name, upn_domain = upn.split('@', 1)
            self.user_logon_name_edit.setText(upn_name)
            # Add the domain to combo if not already there
            domain_text = f"@{upn_domain}"
            if self.domain_combo.findText(domain_text) == -1:
                self.domain_combo.addItem(domain_text)
            self.domain_combo.setCurrentText(domain_text)
        else:
            # Fallback to sAMAccountName if UPN format is unusual
            self.user_logon_name_edit.setText(sam_account_name)
            
        self.user_logon_name_pre2000_edit.setText(sam_account_name)
        
        # Handle userAccountControl flags
        uac = int(self.user_props.get('userAccountControl', ['0'])[0])
        self.account_disabled_check.setChecked(bool(uac & UAC_ACCOUNT_DISABLED))
        self.password_never_expires_check.setChecked(bool(uac & UAC_DONT_EXPIRE_PASSWORD))
        self.user_cannot_change_password_check.setChecked(bool(uac & UAC_PASSWORD_CANT_CHANGE))
        self.smartcard_required_check.setChecked(bool(uac & UAC_SMARTCARD_REQUIRED))
        self.account_trusted_for_delegation_check.setChecked(bool(uac & UAC_TRUSTED_FOR_DELEGATION))
        self.account_sensitive_check.setChecked(bool(uac & UAC_NOT_DELEGATED))
        self.use_des_encryption_check.setChecked(bool(uac & UAC_USE_DES_KEY_ONLY))
        self.not_require_preauth_check.setChecked(bool(uac & UAC_DONT_REQUIRE_PREAUTH))
        
        # Handle account expiration
        account_expires = self.user_props.get('accountExpires', ['0'])[0]
        if account_expires and account_expires != '0' and account_expires != '9223372036854775807':
            # Account has expiration date
            self.end_of_radio.setChecked(True)
            # Convert Windows FILETIME to datetime if needed
            # This is a placeholder - actual conversion would be needed
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
            
        # Telephones Tab
        self.home_phone_edit.setText(self.user_props.get('homePhone', [''])[0])
        self.pager_edit.setText(self.user_props.get('pager', [''])[0])
        self.mobile_edit.setText(self.user_props.get('mobile', [''])[0])
        self.fax_edit.setText(self.user_props.get('facsimileTelephoneNumber', [''])[0])
        self.ip_phone_edit.setText(self.user_props.get('ipPhone', [''])[0])
        self.notes_edit.setText(self.user_props.get('info', [''])[0])
        
        # Organization Tab
        self.title_edit.setText(self.user_props.get('title', [''])[0])
        self.department_edit.setText(self.user_props.get('department', [''])[0])
        self.company_edit.setText(self.user_props.get('company', [''])[0])
        self.manager_edit.setText(self.user_props.get('manager', [''])[0])
        
        # Member Of Tab - populate group memberships with primary group
        self.member_of_table.setRowCount(0)  # Clear existing rows
        
        # Add primary group first
        primary_group_id = self.user_props.get('primaryGroupID', ['513'])[0]  # 513 = Domain Users
        primary_group_name = "Domain Users"  # Would resolve from RID in real implementation
        
        row = self.member_of_table.rowCount()
        self.member_of_table.insertRow(row)
        self.member_of_table.setItem(row, 0, QTableWidgetItem(primary_group_name))
        self.member_of_table.setItem(row, 1, QTableWidgetItem("Active Directory Domain Services Folder"))
        
        # Add other group memberships
        member_of = self.user_props.get('memberOf', [])
        for group_dn in member_of:
            # Extract CN from DN for display
            cn = group_dn.split(',')[0].replace('CN=', '') if 'CN=' in group_dn else group_dn
            row = self.member_of_table.rowCount()
            self.member_of_table.insertRow(row)
            self.member_of_table.setItem(row, 0, QTableWidgetItem(cn))
            self.member_of_table.setItem(row, 1, QTableWidgetItem("Active Directory Domain Services Folder"))
            
        # Set primary group label
        self.primary_group_label.setText(f"{primary_group_name} ({primary_group_id})")
        
        # Update window title and display name header
        self.display_name = self.user_props.get('displayName', [''])[0]
        if not self.display_name:
            # Fallback to CN if displayName is empty
            cn = self.user_props.get('cn', [''])[0]
            self.display_name = cn if cn else "User"
            
        self.setWindowTitle(f"{self.display_name} Properties")
        self.display_name_header.setText(self.display_name)
        
    def _select_manager(self):
        """Open dialog to select a manager"""
        # Placeholder - would open object picker dialog
        self.logger.info("Manager selection not implemented yet")
        
    def _add_to_group(self):
        """Add user to a group"""
        # Placeholder - would open group picker dialog
        self.logger.info("Add to group not implemented yet")
        
    def _remove_from_group(self):
        """Remove user from selected group"""
        current_row = self.member_of_table.currentRow()
        if current_row >= 0:
            # Don't allow removing primary group (first row)
            if current_row == 0:
                QMessageBox.warning(self, "Warning", "Cannot remove user from primary group.")
                return
            self.member_of_table.removeRow(current_row)
            
    def _set_primary_group(self):
        """Set primary group"""
        # Placeholder - would open group picker for primary group
        self.logger.info("Set primary group not implemented yet")
        
    def apply_changes(self):
        """Apply changes to the user object"""
        # This would collect all the form data and update the AD object
        self.logger.info("Apply changes clicked, implementation needed")
        # TODO: Implement actual LDAP modify operations
        pass

