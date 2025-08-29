# Password Reset Dialog
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QCheckBox, QPushButton, QLabel, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from i18n_manager import I18nManager
import os

class PasswordResetDialog(QDialog):
    """Dialog for resetting a user's password."""
    
    def __init__(self, parent=None, username=""):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.username = username
        self.password = ""
        self.must_change_password = True
        
        self.setWindowTitle(self.i18n.get_string("dialog.reset_password.title"))
        self.setModal(True)
        self.setFixedSize(400, 250)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header with icon and text
        header_layout = QHBoxLayout()
        
        # Icon
        icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'key.png')
        if os.path.exists(abs_icon_path):
            icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        
        # Header text
        header_text = QLabel(self.i18n.get_text("dialog.reset_password.header", self.username))
        header_text.setWordWrap(True)
        
        header_layout.addWidget(icon_label)
        header_layout.addWidget(header_text)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Password form
        form_layout = QFormLayout()
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow(self.i18n.get_string("dialog.reset_password.new_password"), self.password_edit)
        
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow(self.i18n.get_string("dialog.reset_password.confirm_password"), self.confirm_password_edit)
        
        layout.addLayout(form_layout)
        
        # Options
        self.must_change_check = QCheckBox(self.i18n.get_string("dialog.reset_password.must_change"))
        self.must_change_check.setChecked(True)
        layout.addWidget(self.must_change_check)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton(self.i18n.get_string("dialog.common.ok"))
        self.ok_button.clicked.connect(self._on_ok_clicked)
        
        self.cancel_button = QPushButton(self.i18n.get_string("dialog.common.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Set focus
        self.password_edit.setFocus()
    
    def _on_ok_clicked(self):
        password = self.password_edit.text()
        confirm_password = self.confirm_password_edit.text()
        
        if not password:
            QMessageBox.warning(self, self.i18n.get_string("dialog.common.error.title"), 
                              self.i18n.get_string("dialog.reset_password.error.empty_password"))
            return
        
        if password != confirm_password:
            QMessageBox.warning(self, self.i18n.get_string("dialog.common.error.title"), 
                              self.i18n.get_string("dialog.reset_password.error.password_mismatch"))
            return
        
        if len(password) < 3:  # Basic validation
            QMessageBox.warning(self, self.i18n.get_string("dialog.common.error.title"), 
                              self.i18n.get_string("dialog.reset_password.error.password_too_short"))
            return
        
        self.password = password
        self.must_change_password = self.must_change_check.isChecked()
        self.accept()