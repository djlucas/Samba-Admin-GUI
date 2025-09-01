# src/user_dialogs.py

import ldap.dn
import logging
import os
from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QFormLayout, QLineEdit, QCheckBox,
    QLabel, QComboBox, QFrame, QHBoxLayout, QMessageBox, QSpacerItem, QVBoxLayout, QGridLayout,
    QDialog, QDialogButtonBox, QGroupBox, QRadioButton
)
from PyQt5.QtCore import Qt, pyqtSignal, QRegExp, QVariant
from PyQt5.QtGui import QIcon, QRegExpValidator, QPixmap

from i18n_manager import I18nManager
from samba_backend import BASE_DN, get_forest_root_info

# --- New User Wizard Page 1 ---
class NewUserPage1(QWizardPage):
    """
    The first page of the New User Wizard.
    Contains fields for user name details and logon names.
    This class is now configurable to be reused by the Copy User wizard.
    """
    def __init__(self, parent=None, page_title_key="dialog.new_user.page1.title", page_subtitle_key="dialog.new_user.page1.subtitle", intro_text_key="dialog.new_user.page1.intro_text", intro_text_args=None, icon_path="src/res/icons/user_add.png", container_dn=None, samba_conn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.logger = logging.getLogger("saduc_app.NewUserPage1")
        self.samba_conn = samba_conn

        self.setTitle(self.i18n.get_string(page_title_key))
        self.setSubTitle(self.i18n.get_string(page_subtitle_key))

        mainLayout = QVBoxLayout()
        mainLayout.setSpacing(10)

        # --- Top Section ---
        headerLayout = QHBoxLayout()
        iconLabel = QLabel()
        
        # Use an absolute path for the icon
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', os.path.basename(icon_path))
        iconLabel.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))

        intro_text = self.i18n.get_string(intro_text_key)
        if intro_text_args:
            try:
                intro_text = intro_text.format(*intro_text_args)
            except (IndexError, KeyError, ValueError) as e:
                # If formatting fails, use the raw text
                self.logger.warning(f"String formatting failed for {intro_text_key}: {e}")
                pass

        introTextLabel = QLabel(intro_text)
        introTextLabel.setStyleSheet("font-weight: bold; font-size: 14pt;")

        # Get base DN dynamically - Note: This needs samba_conn which isn't available here
        # So we'll pass None and handle it in _format_dn_for_display
        createInLabel = QLabel(self._format_dn_for_display(container_dn, BASE_DN))

        headerLayout.addWidget(iconLabel)
        headerLayout.addWidget(introTextLabel)
        headerLayout.addStretch()
        headerLayout.addWidget(createInLabel)

        headerSeparator = QFrame()
        headerSeparator.setFrameShape(QFrame.HLine)

        mainLayout.addLayout(headerLayout)
        mainLayout.addWidget(headerSeparator)

        # --- Name Fields (Using QGridLayout for precise alignment) ---
        nameGridLayout = QGridLayout()
        nameGridLayout.setHorizontalSpacing(10)
        nameGridLayout.setVerticalSpacing(5)

        self.firstNameInput = QLineEdit()
        self.lastNameInput = QLineEdit()
        self.initialsInput = QLineEdit()
        self.fullNameInput = QLineEdit()

        self.initialsInput.setMaxLength(4)

        self.firstNameInput.textChanged.connect(self._update_all_fields)
        self.firstNameInput.textChanged.connect(self.completeChanged)
        self.lastNameInput.textChanged.connect(self._update_all_fields)
        self.lastNameInput.textChanged.connect(self.completeChanged)
        self.initialsInput.textChanged.connect(self._update_full_name)

        nameGridLayout.addWidget(QLabel(self.i18n.get_string("dialog.new_user.page1.first_name")), 0, 0, Qt.AlignLeft)
        nameGridLayout.addWidget(self.firstNameInput, 0, 1, 1, 1)
        nameGridLayout.addWidget(QLabel(self.i18n.get_string("dialog.new_user.page1.initials")), 0, 2, Qt.AlignLeft)
        nameGridLayout.addWidget(self.initialsInput, 0, 3, 1, 1)

        nameGridLayout.addWidget(QLabel(self.i18n.get_string("dialog.new_user.page1.last_name")), 1, 0, Qt.AlignLeft)
        nameGridLayout.addWidget(self.lastNameInput, 1, 1, 1, 3)

        nameGridLayout.addWidget(QLabel(self.i18n.get_string("dialog.new_user.page1.full_name")), 2, 0, Qt.AlignLeft)
        nameGridLayout.addWidget(self.fullNameInput, 2, 1, 1, 3)

        nameGridLayout.setColumnStretch(1, 1)
        nameGridLayout.setColumnStretch(3, 0)

        mainLayout.addLayout(nameGridLayout)

        # --- Logon Name Section (Using QGridLayout for precise alignment) ---
        logonSeparator = QFrame()
        logonSeparator.setFrameShape(QFrame.HLine)
        mainLayout.addWidget(logonSeparator)

        logonGridLayout = QGridLayout()
        logonGridLayout.setHorizontalSpacing(10)
        logonGridLayout.setVerticalSpacing(5)

        self.userLogonNameInput = QLineEdit()
        self.upnDomainDropdown = QComboBox()
        self._populate_upn_domains()

        self.userLogonNameInput.textChanged.connect(self.completeChanged)
        self.preWin2kLogonInput = QLineEdit()
        self.preWin2kLogonInput.textChanged.connect(self.completeChanged)

        logonNameLayout = QHBoxLayout()
        logonNameLayout.addWidget(self.userLogonNameInput, 1)
        logonNameLayout.addWidget(self.upnDomainDropdown)

        logonGridLayout.addWidget(QLabel(self.i18n.get_string("dialog.new_user.page1.user_logon_name")), 0, 0, Qt.AlignLeft)
        logonGridLayout.addLayout(logonNameLayout, 1, 0)

        roNetbiosDomainInput = QLineEdit(self.i18n.get_string("dialog.new_user.page1.pre_win2k_domain"))
        roNetbiosDomainInput.setReadOnly(True)
        roNetbiosDomainInput.setEnabled(False)

        preWin2kLogonLayout = QHBoxLayout()
        preWin2kLogonLayout.addWidget(roNetbiosDomainInput, 0)
        preWin2kLogonLayout.addWidget(self.preWin2kLogonInput, 1)

        logonGridLayout.addWidget(QLabel(self.i18n.get_string("dialog.new_user.page1.pre_win2k_logon_name")), 2, 0, Qt.AlignLeft)
        logonGridLayout.addLayout(preWin2kLogonLayout, 3, 0)

        logonGridLayout.setColumnStretch(0, 1)

        mainLayout.addLayout(logonGridLayout)
        mainLayout.addStretch()

        self.setLayout(mainLayout)

        self.registerField("firstName", self.firstNameInput)
        self.registerField("initials", self.initialsInput)
        self.registerField("lastName", self.lastNameInput)
        self.registerField("fullName", self.fullNameInput)
        self.registerField("userLogonName", self.userLogonNameInput)
        self.registerField("upnDomain", self.upnDomainDropdown, "currentText")
        self.registerField("preWin2kLogon", self.preWin2kLogonInput)

    def _populate_upn_domains(self):
        """Populate UPN domain dropdown with actual domain names from AD."""
        try:
            # Try to get domain info from multiple sources
            domain_dn = None
            
            # First try BASE_DN
            if BASE_DN:
                domain_dn = BASE_DN
                self.logger.debug(f"Using BASE_DN: {BASE_DN}")
            else:
                # Try to get forest root info directly using the connection
                if self.samba_conn:
                    try:
                        forest_info = get_forest_root_info(self.samba_conn)
                        if forest_info and forest_info.get('dn'):
                            domain_dn = forest_info['dn']
                            self.logger.debug(f"Got domain DN from forest info: {domain_dn}")
                    except Exception as e:
                        self.logger.debug(f"Could not get forest info: {e}")
                else:
                    self.logger.debug("No samba connection available")
            
            if domain_dn:
                # Extract domain from DN (e.g., "DC=home,DC=lucasit,DC=com" -> "home.lucasit.com")
                domain_parts = [p.split('=')[1] for p in domain_dn.split(',') if p.lower().startswith('dc=')]
                primary_domain = ".".join(domain_parts)
                
                if primary_domain:
                    self.upnDomainDropdown.addItem(f"@{primary_domain}")
                    self.logger.debug(f"Added primary domain: @{primary_domain}")
                    
                    # Try to get additional UPN suffixes from forest info
                    if self.samba_conn:
                        try:
                            forest_info = get_forest_root_info(self.samba_conn)
                            if forest_info and forest_info.get('name') and forest_info['name'] != primary_domain:
                                # Add forest root domain if different
                                self.upnDomainDropdown.addItem(f"@{forest_info['name']}")
                                self.logger.debug(f"Added forest domain: @{forest_info['name']}")
                        except Exception as e:
                            self.logger.debug(f"Could not get additional forest info: {e}")
                        
                else:
                    # No domain parts found - this is a serious problem
                    self.logger.error(f"Could not extract domain from DN '{domain_dn}' - AD connection may be broken")
                    self._add_error_indicator()
            else:
                # No domain info available - this is a serious problem
                self.logger.error("No domain information available - AD connection may be broken")
                self._add_error_indicator()
                
        except Exception as e:
            self.logger.error(f"Failed to populate UPN domains - AD connection may be broken: {e}")
            self._add_error_indicator()
    
    def _add_error_indicator(self):
        """Add error indicator when domain information cannot be retrieved."""
        self.upnDomainDropdown.addItem("@ERROR - Cannot retrieve domain info")
        self.upnDomainDropdown.setEnabled(False)

    def _format_dn_for_display(self, dn, base_dn):
        if not dn:
            return ""
        
        if not base_dn:
            # If base_dn is None, just return the container DN as-is
            return dn
            
        domain_parts = [p.split('=')[1] for p in base_dn.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)

        try:
            dn_struct = ldap.dn.str2dn(dn)
            base_dn_struct = ldap.dn.str2dn(base_dn)

            relative_dn_struct = [rdn for rdn in dn_struct if rdn not in base_dn_struct]
            
            path_parts = []
            for rdn_part in reversed(relative_dn_struct):
                path_parts.append(rdn_part[0][1])

            if not path_parts:
                return f"Create in: {domain}"
            
            return f"Create in: {domain}/{'/'.join(path_parts)}"
        except Exception:
            return f"Create in: {dn}"

    def _update_all_fields(self):
        first = self.firstNameInput.text().strip()
        last = self.lastNameInput.text().strip()

        self._update_full_name()

        if first and last:
            logonName = (first[0] + last).lower()
            self.userLogonNameInput.setText(logonName)

            pre2kName = logonName.replace(" ", "")[:15]
            self.preWin2kLogonInput.setText(pre2kName)
        else:
            self.userLogonNameInput.clear()
            self.preWin2kLogonInput.clear()

    def _update_full_name(self):
        first = self.firstNameInput.text().strip()
        last = self.lastNameInput.text().strip()
        initials = self.initialsInput.text().strip()

        fullNameParts = []
        if first:
            fullNameParts.append(first)
        if initials:
            fullNameParts.append(initials)
        if last:
            fullNameParts.append(last)

        self.fullNameInput.setText(" ".join(fullNameParts))

    def isComplete(self):
        return all([
            self.firstNameInput.text(),
            self.lastNameInput.text(),
            self.userLogonNameInput.text(),
            self.preWin2kLogonInput.text()
        ])

    def pre_populate_fields(self, data):
        # This page is NOT pre-populated for a Copy User action
        # The user must provide a new identity.
        pass


# --- New User Wizard Page 2 ---
class NewUserPage2(QWizardPage):
    """
    The second page of the New User Wizard.
    Contains password fields and options.
    """
    def __init__(self, parent=None, page_title_key="dialog.new_user.page2.title", page_subtitle_key="dialog.new_user.page2.subtitle"):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.setTitle(self.i18n.get_string(page_title_key))
        self.setSubTitle(self.i18n.get_string(page_subtitle_key))

        layout = QFormLayout()
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.passwordInput = QLineEdit()
        self.passwordInput.setEchoMode(QLineEdit.Password)
        self.passwordInput.textChanged.connect(self.completeChanged)

        self.passwordConfirmInput = QLineEdit()
        self.passwordConfirmInput.setEchoMode(QLineEdit.Password)
        self.passwordConfirmInput.textChanged.connect(self.completeChanged)

        self.passwordMismatchLabel = QLabel(self.i18n.get_string("dialog.new_user.page2.password_mismatch"))
        self.passwordMismatchLabel.setStyleSheet("color: red;")
        self.passwordMismatchLabel.hide()

        layout.addRow(self.i18n.get_string("dialog.new_user.page2.password_label"), self.passwordInput)
        layout.addRow(self.i18n.get_string("dialog.new_user.page2.confirm_password_label"), self.passwordConfirmInput)
        layout.addRow("", self.passwordMismatchLabel)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addRow(separator)

        self.userChangePasswordCheck = QCheckBox(self.i18n.get_string("dialog.new_user.page2.user_must_change_password"))
        self.userChangePasswordCheck.setChecked(True)

        self.userCannotChangePasswordCheck = QCheckBox(self.i18n.get_string("dialog.new_user.page2.user_cannot_change_password"))
        self.passwordNeverExpiresCheck = QCheckBox(self.i18n.get_string("dialog.new_user.page2.password_never_expires"))
        self.accountDisabledCheck = QCheckBox(self.i18n.get_string("dialog.new_user.page2.account_disabled"))

        self.userCannotChangePasswordCheck.stateChanged.connect(self._handle_password_options)
        self.passwordNeverExpiresCheck.stateChanged.connect(self._handle_password_options)

        layout.addRow(self.userChangePasswordCheck)
        layout.addRow(self.userCannotChangePasswordCheck)
        layout.addRow(self.passwordNeverExpiresCheck)
        layout.addRow(self.accountDisabledCheck)

        self.setLayout(layout)

        self.registerField("password", self.passwordInput)
        self.registerField("userChangePassword", self.userChangePasswordCheck)
        self.registerField("userCannotChangePassword", self.userCannotChangePasswordCheck)
        self.registerField("passwordNeverExpires", self.passwordNeverExpiresCheck)
        self.registerField("accountDisabled", self.accountDisabledCheck)


    def isComplete(self):
        password = self.passwordInput.text()
        confirm = self.passwordConfirmInput.text()

        is_complete = bool(password and password == confirm)

        if not is_complete:
            if password or confirm:
                self.passwordMismatchLabel.show()
            else:
                self.passwordMismatchLabel.hide()
        else:
            self.passwordMismatchLabel.hide()

        return is_complete

    def _handle_password_options(self, state):
        if self.userCannotChangePasswordCheck.isChecked() or self.passwordNeverExpiresCheck.isChecked():
            self.userChangePasswordCheck.setEnabled(False)
            self.userChangePasswordCheck.setChecked(False)
        else:
            self.userChangePasswordCheck.setEnabled(True)

    def pre_populate_fields(self, data):
        # We don't pre-populate the password fields for security
        self.userChangePasswordCheck.setChecked(data.get('user_must_change_password', False))
        self.userCannotChangePasswordCheck.setChecked(data.get('user_cannot_change_password', False))
        self.passwordNeverExpiresCheck.setChecked(data.get('password_never_expires', False))
        self.accountDisabledCheck.setChecked(data.get('account_is_disabled', False))


# --- New User Wizard Page 3 (Final Summary Page) ---
class NewUserPage3(QWizardPage):
    def __init__(self, parent=None, page_title_key="dialog.new_user.page3.title", page_subtitle_key="dialog.new_user.page3.subtitle", summary_intro_key="dialog.new_user.page3.summary_intro", summary_full_name_key="dialog.new_user.page3.summary_full_name", summary_user_logon_key="dialog.new_user.page3.summary_user_logon", icon_path="src/res/icons/user_add.png"):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.summary_intro_key = summary_intro_key
        self.summary_full_name_key = summary_full_name_key
        self.summary_user_logon_key = summary_user_logon_key
        self.setTitle(self.i18n.get_string(page_title_key))
        self.setSubTitle(self.i18n.get_string(page_subtitle_key))

        mainLayout = QVBoxLayout()

        headerLayout = QHBoxLayout()
        iconLabel = QLabel()
        # Use an absolute path for the icon
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', os.path.basename(icon_path))
        iconLabel.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        createInLabel = QLabel() # Will be set in initializePage

        headerLayout.addWidget(iconLabel)
        headerLayout.addWidget(createInLabel)
        headerLayout.addStretch()

        headerSeparator = QFrame()
        headerSeparator.setFrameShape(QFrame.HLine)

        mainLayout.addLayout(headerLayout)
        mainLayout.addWidget(headerSeparator)

        self.summaryLabel = QLabel()
        self.summaryLabel.setWordWrap(True)
        mainLayout.addWidget(self.summaryLabel)
        mainLayout.addStretch()

        self.setLayout(mainLayout)

    def initializePage(self):
        full_name = self.wizard().field("fullName")
        user_logon_name = self.wizard().field("userLogonName")
        upn_domain = self.wizard().field("upnDomain")

        change_password_checked = self.wizard().field("userChangePassword")
        cannot_change_password_checked = self.wizard().field("userCannotChangePassword")
        never_expires_checked = self.wizard().field("passwordNeverExpires")
        account_disabled_checked = self.wizard().field("accountDisabled")

        summary_text_parts = [
            self.i18n.get_string(self.summary_intro_key),
            self.i18n.get_text(self.summary_full_name_key, full_name),
            self.i18n.get_text(self.summary_user_logon_key, user_logon_name, upn_domain)
        ]

        password_options = []
        if change_password_checked:
            password_options.append(self.i18n.get_string("dialog.new_user.page3.user_must_change_password_option"))
        if cannot_change_password_checked:
            password_options.append(self.i18n.get_string("dialog.new_user.page3.user_cannot_change_password_option"))
        if never_expires_checked:
            password_options.append(self.i18n.get_string("dialog.new_user.page3.password_never_expires_option"))
        if account_disabled_checked:
            password_options.append(self.i18n.get_string("dialog.new_user.page3.account_disabled_option"))

        if password_options:
            summary_text_parts.append("<br>" + "<br>".join(password_options))

        self.summaryLabel.setText("".join(summary_text_parts))


# --- New User Wizard ---
class NewUserWizard(QWizard):
    """
    A multi-page wizard for creating a new user account.
    """
    def __init__(self, parent=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("dialog.new_user.title"))
        self.setWizardStyle(QWizard.ModernStyle)

        # Get samba connection from parent (main window)
        samba_conn = getattr(parent, 'samba_conn', None) if parent else None

        self.setPage(0, NewUserPage1(container_dn=container_dn, samba_conn=samba_conn))
        self.setPage(1, NewUserPage2())
        self.setPage(2, NewUserPage3())

        self.user_data = {}

    def accept(self):
        page1 = self.page(0)
        page2 = self.page(1)

        self.user_data = {
            'first_name': page1.firstNameInput.text(),
            'last_name': page1.lastNameInput.text(),
            'initials': page1.initialsInput.text(),
            'full_name': page1.fullNameInput.text(),
            'user_logon_name': page1.userLogonNameInput.text(),
            'upn_domain': page1.upnDomainDropdown.currentText(),
            'pre_win2k_logon': page1.preWin2kLogonInput.text(),
            'password': page2.passwordInput.text(),
            'password_never_expires': page2.passwordNeverExpiresCheck.isChecked(),
            'user_must_change_password': page2.userChangePasswordCheck.isChecked(),
            'user_cannot_change_password': page2.userCannotChangePasswordCheck.isChecked(),
            'account_is_disabled': page2.accountDisabledCheck.isChecked()
        }

        super().accept()

# --- Configurable User Wizard ---
class ConfigurableUserWizard(QWizard):
    """
    A configurable multi-page wizard for creating user-like accounts.
    Can be used for regular users, inetOrgPerson, etc.
    """
    def __init__(self, parent=None, container_dn=None, window_title_key="dialog.new_user.title", 
                 page1_title_key="dialog.new_user.page1.title", page1_subtitle_key="dialog.new_user.page1.subtitle", 
                 page1_intro_key="dialog.new_user.page1.intro_text", icon_path="src/res/icons/user_add.png",
                 page2_title_key="dialog.new_user.page2.title", page2_subtitle_key="dialog.new_user.page2.subtitle",
                 page3_title_key="dialog.new_user.page3.title", page3_subtitle_key="dialog.new_user.page3.subtitle",
                 page3_summary_intro_key="dialog.new_user.page3.summary_intro", 
                 page3_summary_full_name_key="dialog.new_user.page3.summary_full_name",
                 page3_summary_user_logon_key="dialog.new_user.page3.summary_user_logon"):
        super().__init__(parent)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string(window_title_key))
        self.setWizardStyle(QWizard.ModernStyle)

        # Get samba connection from parent (main window)
        samba_conn = getattr(parent, 'samba_conn', None) if parent else None

        self.setPage(0, NewUserPage1(
            page_title_key=page1_title_key,
            page_subtitle_key=page1_subtitle_key, 
            intro_text_key=page1_intro_key,
            icon_path=icon_path,
            container_dn=container_dn,
            samba_conn=samba_conn
        ))
        self.setPage(1, NewUserPage2(
            page_title_key=page2_title_key,
            page_subtitle_key=page2_subtitle_key
        ))
        self.setPage(2, NewUserPage3(
            page_title_key=page3_title_key,
            page_subtitle_key=page3_subtitle_key,
            summary_intro_key=page3_summary_intro_key,
            summary_full_name_key=page3_summary_full_name_key,
            summary_user_logon_key=page3_summary_user_logon_key,
            icon_path=icon_path
        ))

        self.user_data = {}

    def accept(self):
        page1 = self.page(0)
        page2 = self.page(1)

        self.user_data = {
            'first_name': page1.firstNameInput.text(),
            'last_name': page1.lastNameInput.text(),
            'initials': page1.initialsInput.text(),
            'full_name': page1.fullNameInput.text(),
            'user_logon_name': page1.userLogonNameInput.text(),
            'upn_domain': page1.upnDomainDropdown.currentText(),
            'pre_win2k_logon': page1.preWin2kLogonInput.text(),
            'password': page2.passwordInput.text(),
            'password_never_expires': page2.passwordNeverExpiresCheck.isChecked(),
            'user_must_change_password': page2.userChangePasswordCheck.isChecked(),
            'user_cannot_change_password': page2.userCannotChangePasswordCheck.isChecked(),
            'account_is_disabled': page2.accountDisabledCheck.isChecked()
        }

        super().accept()

# --- Copy User Wizard ---
class CopyUserWizard(QWizard):
    """
    A wizard for copying a user, reusing the form pages.
    """
    def __init__(self, parent=None, initial_data=None, source_username=None, source_display_name=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        
        # Use display name for the UI, fallback to username if not provided
        display_name_for_ui = source_display_name or source_username
        
        # Set window title with display name
        title = self.i18n.get_string("dialog.copy_user.title")
        if display_name_for_ui:
            title += f" - {display_name_for_ui}"
        self.setWindowTitle(title)
        self.setWizardStyle(QWizard.ModernStyle)

        # Get samba connection from parent (main window)
        samba_conn = getattr(parent, 'samba_conn', None) if parent else None

        # Use the same pages but with different titles/subtitles
        self.setPage(0, NewUserPage1(
            page_title_key="dialog.copy_user.page1.title",
            page_subtitle_key="dialog.copy_user.page1.subtitle",
            intro_text_key="dialog.copy_user.page1.intro_text",
            intro_text_args=[display_name_for_ui],
            icon_path="src/res/icons/user_copy.png",
            container_dn=container_dn,
            samba_conn=samba_conn
        ))
        self.setPage(1, NewUserPage2(
            page_title_key="dialog.copy_user.page2.title",
            page_subtitle_key="dialog.copy_user.page2.subtitle"
        ))
        self.setPage(2, NewUserPage3(
            page_title_key="dialog.copy_user.page3.title",
            page_subtitle_key="dialog.copy_user.page3.subtitle",
            summary_intro_key="dialog.copy_user.page3.summary_intro",
            summary_full_name_key="dialog.copy_user.page3.summary_full_name",
            summary_user_logon_key="dialog.copy_user.page3.summary_user_logon",
            icon_path="src/res/icons/user_copy.png"
        ))

        self.user_data = {}

        if initial_data:
            self.page(1).pre_populate_fields(initial_data)

    def accept(self):
        page1 = self.page(0)
        page2 = self.page(1)

        self.user_data = {
            'first_name': page1.firstNameInput.text(),
            'last_name': page1.lastNameInput.text(),
            'initials': page1.initialsInput.text(),
            'full_name': page1.fullNameInput.text(),
            'user_logon_name': page1.userLogonNameInput.text(),
            'upn_domain': page1.upnDomainDropdown.currentText(),
            'pre_win2k_logon': page1.preWin2kLogonInput.text(),
            'password': page2.passwordInput.text(),
            'password_never_expires': page2.passwordNeverExpiresCheck.isChecked(),
            'user_must_change_password': page2.userChangePasswordCheck.isChecked(),
            'user_cannot_change_password': page2.userCannotChangePasswordCheck.isChecked(),
            'account_is_disabled': page2.accountDisabledCheck.isChecked()
        }

        super().accept()


# --- Custom Dialogs for Delete and Disable Actions ---
def DeleteUserDialog(parent, username):
    i18n = I18nManager()
    title = i18n.get_string("dialog.delete_user.title")
    message = i18n.get_text("dialog.delete_user.message", username)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)

def DisableUserDialog(parent, username):
    i18n = I18nManager()
    title = i18n.get_string("dialog.disable_user.title")
    message = i18n.get_text("dialog.disable_user.message", username)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)

def EnableUserDialog(parent, username):
    i18n = I18nManager()
    title = i18n.get_string("dialog.enable_user.title")
    message = i18n.get_text("dialog.enable_user.message", username)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)

# --- New Authentication Dialog ---
class UsernamePasswordDialog(QDialog):
    """
    A simple dialog to get username and password from the user.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.setWindowTitle(self.i18n.get_string("dialog.auth.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Get the domain and format it as a Kerberos realm (uppercase)
        self.realm = self._get_kerberos_realm()
        
        formLayout = QFormLayout()
        
        self.usernameInput = QLineEdit()
        self.passwordInput = QLineEdit()
        self.passwordInput.setEchoMode(QLineEdit.Password)

        # Use an QHBoxLayout to combine the username input and the realm label
        usernameLayout = QHBoxLayout()
        usernameLayout.addWidget(self.usernameInput, 1)
        
        realmLabel = QLabel(self.realm)
        realmLabel.setStyleSheet("font-weight: bold;")
        usernameLayout.addWidget(realmLabel)

        formLayout.addRow(self.i18n.get_string("dialog.auth.username"), usernameLayout)
        formLayout.addRow(self.i18n.get_string("dialog.auth.password"), self.passwordInput)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(formLayout)
        mainLayout.addWidget(self.buttonBox)
        
        self.setLayout(mainLayout)

    def _get_kerberos_realm(self):
        """Get the Kerberos realm from krb5.conf."""
        try:
            # Read the realm from krb5.conf
            with open('/etc/krb5.conf', 'r') as f:
                content = f.read()
            
            # Look for default_realm in [libdefaults] section
            lines = content.split('\n')
            in_libdefaults = False
            
            for line in lines:
                line = line.strip()
                
                if line.startswith('[libdefaults]'):
                    in_libdefaults = True
                    continue
                elif line.startswith('[') and in_libdefaults:
                    # Moved to different section
                    break
                
                if in_libdefaults and line.startswith('default_realm'):
                    # Extract realm value
                    if '=' in line:
                        realm = line.split('=')[1].strip()
                        return f"@{realm}"
            
        except Exception as e:
            pass
        
        # Fallback if krb5.conf can't be read
        return "@DOMAIN.COM"
    
    def get_credentials(self):
        username = self.usernameInput.text()
        return username, self.passwordInput.text()

# --- New Group Dialog ---
class NewGroupDialog(QDialog):
    """
    A dialog for creating a new group.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.setWindowTitle(self.i18n.get_string("dialog.new_group.title"))

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.group_name_edit = QLineEdit()
        form_layout.addRow(self.i18n.get_string("group_properties.label.group_name"), self.group_name_edit)

        # Group Scope
        self.group_scope_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.scope"))
        scope_layout = QHBoxLayout()
        self.domain_local_radio = QRadioButton(self.i18n.get_string("group_properties.radio.domain_local"))
        self.global_radio = QRadioButton(self.i18n.get_string("group_properties.radio.global"))
        self.universal_radio = QRadioButton(self.i18n.get_string("group_properties.radio.universal"))
        self.global_radio.setChecked(True) # Default scope
        scope_layout.addWidget(self.domain_local_radio)
        scope_layout.addWidget(self.global_radio)
        scope_layout.addWidget(self.universal_radio)
        self.group_scope_box.setLayout(scope_layout)
        form_layout.addRow(self.group_scope_box)

        # Group Type
        self.group_type_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.type"))
        type_layout = QHBoxLayout()
        self.security_radio = QRadioButton(self.i18n.get_string("group_properties.radio.security"))
        self.distribution_radio = QRadioButton(self.i18n.get_string("group_properties.radio.distribution"))
        self.security_radio.setChecked(True) # Default type
        type_layout.addWidget(self.security_radio)
        type_layout.addWidget(self.distribution_radio)
        self.group_type_box.setLayout(type_layout)
        form_layout.addRow(self.group_type_box)

        layout.addLayout(form_layout)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def get_group_data(self):
        scope = 'global'
        if self.domain_local_radio.isChecked():
            scope = 'local'
        elif self.universal_radio.isChecked():
            scope = 'universal'
        
        group_type = 'security'
        if self.distribution_radio.isChecked():
            group_type = 'distribution'

        return {
            'name': self.group_name_edit.text(),
            'scope': scope,
            'type': group_type
        }


class NewOUDialog(QDialog):
    """
    A dialog for creating a new Organizational Unit.
    """
    def __init__(self, parent=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.container_dn = container_dn or BASE_DN
        
        self.setWindowTitle(self.i18n.get_string("dialog.new_ou.title"))
        self.setMinimumSize(400, 300)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # Header section with icon and "Create in" info
        header_layout = QHBoxLayout()
        
        # OU icon
        icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'folder_ou.png')
        icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        
        header_layout.addWidget(icon_label)
        header_layout.addStretch()
        
        # "Create in" label
        create_in_label = QLabel(f"Create in: {self._format_dn_for_display(self.container_dn)}")
        create_in_label.setAlignment(Qt.AlignRight)
        header_layout.addWidget(create_in_label)
        
        main_layout.addLayout(header_layout)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.HLine)
        separator1.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator1)

        # Name field
        form_layout = QFormLayout()
        self.ou_name_edit = QLineEdit()
        self.ou_name_edit.textChanged.connect(self._validate_input)
        form_layout.addRow(self.i18n.get_string("dialog.new_ou.label.name"), self.ou_name_edit)
        
        main_layout.addLayout(form_layout)

        # Protection checkbox
        self.protect_checkbox = QCheckBox(self.i18n.get_string("dialog.new_ou.checkbox.protect"))
        self.protect_checkbox.setChecked(True)  # Default to yes
        main_layout.addWidget(self.protect_checkbox)

        # Extra space
        main_layout.addStretch()

        # Bottom separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator2)

        # Buttons
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        main_layout.addWidget(self.buttonBox)

        self._validate_input()

    def _format_dn_for_display(self, dn):
        """Format DN for user display, showing only the CN part."""
        if not dn:
            return ""
        try:
            parsed = ldap.dn.explode_dn(dn, notypes=True)
            return parsed[0] if parsed else dn
        except:
            return dn

    def _validate_input(self):
        name_valid = bool(self.ou_name_edit.text().strip())
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(name_valid)

    def get_ou_data(self):
        return {
            'name': self.ou_name_edit.text().strip(),
            'container_dn': self.container_dn,
            'protect_from_deletion': self.protect_checkbox.isChecked()
        }


class DeleteOUDialog(QDialog):
    """Dialog for confirming OU deletion."""
    
    def __init__(self, ou_name, has_children=False, parent=None):
        super().__init__(parent)
        self.ou_name = ou_name
        self.has_children = has_children
        self.i18n = I18nManager()
        
        self.setWindowTitle("Confirm Delete OU")
        self.setModal(True)
        self.setFixedSize(400, 200 if has_children else 150)
        
        layout = QVBoxLayout(self)
        
        # Warning message
        warning_label = QLabel(f"Are you sure you want to delete the OU '{ou_name}'?")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        
        # Additional warning
        warning2_label = QLabel("This action cannot be undone.")
        warning2_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(warning2_label)
        
        # Recursive deletion checkbox (only shown if OU has children)
        self.recursive_checkbox = None
        if has_children:
            layout.addSpacing(10)
            
            info_label = QLabel("This OU contains child objects.")
            info_label.setStyleSheet("color: #666; font-style: italic;")
            layout.addWidget(info_label)
            
            self.recursive_checkbox = QCheckBox("Delete all child objects (recursive delete)")
            self.recursive_checkbox.setStyleSheet("font-weight: bold; color: #d32f2f;")
            layout.addWidget(self.recursive_checkbox)
            
            warning3_label = QLabel("⚠ WARNING: This will permanently delete ALL contents including nested OUs, users, computers, and other objects!")
            warning3_label.setWordWrap(True)
            warning3_label.setStyleSheet("color: #d32f2f; font-size: 10px; background-color: #ffebee; padding: 5px; border: 1px solid #ffcdd2;")
            layout.addWidget(warning3_label)
        
        layout.addStretch()
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Yes | QDialogButtonBox.No,
            Qt.Horizontal, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Make "No" the default
        button_box.button(QDialogButtonBox.No).setDefault(True)
        button_box.button(QDialogButtonBox.Yes).setText("Delete")
        button_box.button(QDialogButtonBox.No).setText("Cancel")
        
        layout.addWidget(button_box)
    
    def is_recursive_delete(self):
        """Return True if recursive delete was selected."""
        return self.recursive_checkbox is not None and self.recursive_checkbox.isChecked()


# --- New Contact Dialog ---
class NewContactDialog(QDialog):
    """
    A dialog for creating a new contact.
    Based on the project outline specification.
    """
    def __init__(self, parent=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.container_dn = container_dn or BASE_DN
        self.logger = logging.getLogger("saduc_app.NewContactDialog")

        self.setWindowTitle(self.i18n.get_string("dialog.new_contact.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(400, 300)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Create all widgets for the dialog"""
        # Header section
        self.header_layout = QHBoxLayout()
        
        # Contact icon
        self.icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'contact.png')
        try:
            self.icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        except:
            # If icon doesn't exist, create a placeholder
            self.icon_label.setText("📧")
            self.icon_label.setStyleSheet("font-size: 24px;")
        
        # Create contact label
        self.intro_label = QLabel(self.i18n.get_string("dialog.new_contact.intro_text"))
        self.intro_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        
        # "Create in" label
        self.create_in_label = QLabel(self._format_dn_for_display(self.container_dn))
        
        self.header_layout.addWidget(self.icon_label)
        self.header_layout.addWidget(self.intro_label)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.create_in_label)
        
        # Separator
        self.header_separator = QFrame()
        self.header_separator.setFrameShape(QFrame.HLine)
        
        # Form fields
        self.form_layout = QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        self.first_name_edit = QLineEdit()
        self.first_name_edit.textChanged.connect(self._update_display_name)
        self.first_name_edit.textChanged.connect(self._validate_input)
        
        self.initials_edit = QLineEdit()
        self.initials_edit.setMaxLength(6)
        self.initials_edit.setMaximumWidth(80)
        self.initials_edit.textChanged.connect(self._update_display_name)
        
        self.last_name_edit = QLineEdit()
        self.last_name_edit.textChanged.connect(self._update_display_name)
        self.last_name_edit.textChanged.connect(self._validate_input)
        
        self.display_name_edit = QLineEdit()
        
        # Create layout for first name and initials
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.first_name_edit)
        name_layout.addWidget(QLabel(self.i18n.get_string("dialog.new_contact.label.initials")))
        name_layout.addWidget(self.initials_edit)
        
        self.form_layout.addRow(self.i18n.get_string("dialog.new_contact.label.first_name"), name_layout)
        self.form_layout.addRow(self.i18n.get_string("dialog.new_contact.label.last_name"), self.last_name_edit)
        self.form_layout.addRow(self.i18n.get_string("dialog.new_contact.label.display_name"), self.display_name_edit)
        
        # Button box
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        
    def _create_layout(self):
        """Create the main dialog layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        main_layout.addLayout(self.header_layout)
        main_layout.addWidget(self.header_separator)
        main_layout.addLayout(self.form_layout)
        main_layout.addStretch()
        main_layout.addWidget(self.button_box)
        
    def _connect_signals(self):
        """Connect signals to slots"""
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        # Initial validation
        self._validate_input()
        
    def _format_dn_for_display(self, dn):
        """Format DN for display in the 'Create in' label."""
        if not dn:
            return self.i18n.get_string("dialog.new_contact.create_in_unknown")
            
        try:
            # Extract domain from DN
            domain_parts = [p.split('=')[1] for p in dn.split(',') if p.lower().startswith('dc=')]
            domain = ".".join(domain_parts)
            
            # Parse the DN to get container path
            dn_struct = ldap.dn.str2dn(dn)
            path_parts = []
            
            for rdn_part in reversed(dn_struct):
                if rdn_part[0][0].lower() != 'dc':  # Skip domain components
                    path_parts.append(rdn_part[0][1])
            
            if not path_parts:
                return self.i18n.get_text("dialog.new_contact.create_in_domain", domain)
            else:
                return self.i18n.get_text("dialog.new_contact.create_in_path", domain, '/'.join(path_parts))
                
        except Exception as e:
            self.logger.debug(f"Error formatting DN for display: {e}")
            return self.i18n.get_text("dialog.new_contact.create_in_fallback", dn)
    
    def _update_display_name(self):
        """Auto-update display name based on first name, initials, and last name."""
        first = self.first_name_edit.text().strip()
        initials = self.initials_edit.text().strip()
        last = self.last_name_edit.text().strip()
        
        display_parts = []
        if first:
            display_parts.append(first)
        if initials:
            display_parts.append(initials)
        if last:
            display_parts.append(last)
            
        self.display_name_edit.setText(" ".join(display_parts))
    
    def _validate_input(self):
        """Validate input and enable/disable OK button."""
        # At least first name or last name must be provided
        first_name_valid = bool(self.first_name_edit.text().strip())
        last_name_valid = bool(self.last_name_edit.text().strip())
        
        is_valid = first_name_valid or last_name_valid
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(is_valid)
    
    def get_contact_data(self):
        """Return the contact data entered by the user."""
        return {
            'first_name': self.first_name_edit.text().strip(),
            'initials': self.initials_edit.text().strip(), 
            'last_name': self.last_name_edit.text().strip(),
            'display_name': self.display_name_edit.text().strip(),
            'container_dn': self.container_dn
        }
