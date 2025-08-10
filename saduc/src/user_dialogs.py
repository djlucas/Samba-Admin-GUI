# src/user_dialogs.py

import ldap.dn
from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QFormLayout, QLineEdit, QCheckBox,
    QLabel, QComboBox, QFrame, QHBoxLayout, QMessageBox, QSpacerItem, QVBoxLayout, QGridLayout,
    QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QRegExp, QVariant
from PyQt5.QtGui import QIcon, QRegExpValidator, QPixmap

from i18n_manager import I18nManager
from samba_backend import BASE_DN

# --- New User Wizard Page 1 ---
class NewUserPage1(QWizardPage):
    """
    The first page of the New User Wizard.
    Contains fields for user name details and logon names.
    This class is now configurable to be reused by the Copy User wizard.
    """
    def __init__(self, parent=None, page_title_key="dialog.new_user.page1.title", page_subtitle_key="dialog.new_user.page1.subtitle", intro_text_key="dialog.new_user.page1.intro_text", intro_text_args=None, icon_path="src/res/icons/user_add.png", container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()

        self.setTitle(self.i18n.get_string(page_title_key))
        self.setSubTitle(self.i18n.get_string(page_subtitle_key))

        mainLayout = QVBoxLayout()
        mainLayout.setSpacing(10)

        # --- Top Section ---
        headerLayout = QHBoxLayout()
        iconLabel = QLabel()
        iconLabel.setPixmap(QIcon(icon_path).pixmap(32, 32))

        intro_text = self.i18n.get_string(intro_text_key)
        if intro_text_args:
            intro_text = intro_text % tuple(intro_text_args)

        introTextLabel = QLabel(intro_text)
        introTextLabel.setStyleSheet("font-weight: bold; font-size: 14pt;")

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
        self.upnDomainDropdown.addItem(self.i18n.get_string("dialog.new_user.page1.upn_domain_1"))
        self.upnDomainDropdown.addItem(self.i18n.get_string("dialog.new_user.page1.upn_domain_2"))

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
        self.registerField("upnDomain", self.upnDomainDropdown)
        self.registerField("preWin2kLogon", self.preWin2kLogonInput)

    def _format_dn_for_display(self, dn, base_dn):
        if not dn:
            return ""
        
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.setTitle(self.i18n.get_string("dialog.new_user.page2.title"))
        self.setSubTitle(self.i18n.get_string("dialog.new_user.page2.subtitle"))

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.setTitle(self.i18n.get_string("dialog.new_user.page3.title"))
        self.setSubTitle(self.i18n.get_string("dialog.new_user.page3.subtitle"))

        mainLayout = QVBoxLayout()

        headerLayout = QHBoxLayout()
        iconLabel = QLabel()
        iconLabel.setPixmap(QIcon('src/res/icons/user_add.png').pixmap(32, 32))
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
            self.i18n.get_string("dialog.new_user.page3.summary_intro"),
            self.i18n.get_text("dialog.new_user.page3.summary_full_name", full_name),
            self.i18n.get_text("dialog.new_user.page3.summary_user_logon", user_logon_name, upn_domain)
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

        self.setPage(0, NewUserPage1(container_dn=container_dn))
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

# --- Copy User Wizard ---
class CopyUserWizard(QWizard):
    """
    A wizard for copying a user, reusing the form pages.
    """
    def __init__(self, parent=None, initial_data=None, source_username=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.setWindowTitle(self.i18n.get_string("dialog.copy_user.title"))
        self.setWizardStyle(QWizard.ModernStyle)

        # Use the same pages but with different titles/subtitles
        self.setPage(0, NewUserPage1(
            page_title_key="dialog.copy_user.page1.title",
            page_subtitle_key="dialog.copy_user.page1.subtitle",
            intro_text_key="dialog.copy_user.page1.intro_text",
            intro_text_args=[source_username],
            icon_path="src/res/icons/user_copy.png",
            container_dn=container_dn
        ))
        self.setPage(1, NewUserPage2())
        self.setPage(2, NewUserPage3())

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
        domain_parts = BASE_DN.split(',')
        domain_name = ".".join([part.split('=')[1] for part in domain_parts if part.startswith('dc=')])
        self.realm = f"@{domain_name.upper()}"
        
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

    def get_credentials(self):
        username = self.usernameInput.text()
        return username, self.passwordInput.text()