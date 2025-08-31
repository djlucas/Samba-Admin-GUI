# Computer-specific dialog functions
import os
import ldap.dn
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
    QLabel, QFrame, QDialogButtonBox, QMessageBox, QPushButton, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from i18n_manager import I18nManager
from samba_backend import BASE_DN, get_group_by_rid

def DisableComputerDialog(parent, computer_name):
    i18n = I18nManager()
    title = i18n.get_string("dialog.disable_computer.title")
    message = i18n.get_text("dialog.disable_computer.message", computer_name)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)

def EnableComputerDialog(parent, computer_name):
    i18n = I18nManager()
    title = i18n.get_string("dialog.enable_computer.title")
    message = i18n.get_text("dialog.enable_computer.message", computer_name)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)


# --- New Computer Dialog ---
class NewComputerDialog(QDialog):
    """
    A dialog for creating a new computer account.
    """
    def __init__(self, parent=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.container_dn = container_dn or BASE_DN
        self.logger = logging.getLogger("saduc_app.NewComputerDialog")
        self.parent = parent  # Store parent to access samba_conn

        self.setWindowTitle(self.i18n.get_string("dialog.new_computer.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(450, 350)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self):
        """Create all widgets for the dialog"""
        # Header section
        self.header_layout = QHBoxLayout()
        
        # Computer icon
        self.icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'computer.png')
        try:
            self.icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        except:
            # If icon doesn't exist, create a placeholder
            self.icon_label.setText("💻")
            self.icon_label.setStyleSheet("font-size: 24px;")
        
        # "Create in" label
        self.create_in_label = QLabel(self._format_dn_for_display(self.container_dn))
        
        self.header_layout.addWidget(self.icon_label)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.create_in_label)
        
        # Separator
        self.header_separator = QFrame()
        self.header_separator.setFrameShape(QFrame.HLine)
        
        # Form fields
        self.form_layout = QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        self.computer_name_edit = QLineEdit()
        self.computer_name_edit.textChanged.connect(self._update_pre2k_name)
        self.computer_name_edit.textChanged.connect(self._validate_input)
        
        self.pre2k_name_edit = QLineEdit()
        self.pre2k_name_edit.textChanged.connect(self._validate_input)
        
        # Store selected group DN
        self.selected_group_dn = None
        
        self.form_layout.addRow(self.i18n.get_string("dialog.new_computer.label.computer_name"), self.computer_name_edit)
        self.form_layout.addRow(self.i18n.get_string("dialog.new_computer.label.pre2k_name"), self.pre2k_name_edit)
        
        # User or group section
        self.user_group_layout = QHBoxLayout()
        self.user_group_edit = QLineEdit()
        self._populate_domain_computers_group()
        self.user_group_edit.setReadOnly(True)
        
        self.change_button = QPushButton(self.i18n.get_string("dialog.new_computer.button.change"))
        self.change_button.clicked.connect(self._select_group)
        
        self.user_group_layout.addWidget(self.user_group_edit)
        self.user_group_layout.addWidget(self.change_button)
        
        self.form_layout.addRow(self.i18n.get_string("dialog.new_computer.label.user_or_group"), self.user_group_layout)
        
        # Pre-Windows 2000 checkbox
        self.pre2k_checkbox = QCheckBox(self.i18n.get_string("dialog.new_computer.checkbox.pre2k"))
        
        # Bottom separator
        self.bottom_separator = QFrame()
        self.bottom_separator.setFrameShape(QFrame.HLine)
        
        # Button box
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        
    def _create_layout(self):
        """Create the main dialog layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        main_layout.addLayout(self.header_layout)
        main_layout.addWidget(self.header_separator)
        main_layout.addLayout(self.form_layout)
        main_layout.addWidget(self.pre2k_checkbox)
        main_layout.addStretch()
        main_layout.addWidget(self.bottom_separator)
        main_layout.addWidget(self.button_box)
        
    def _connect_signals(self):
        """Connect signals to slots"""
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        # Initial validation
        self._validate_input()
    
    def _populate_domain_computers_group(self):
        """Populate the Domain Computers group field using actual group lookup."""
        try:
            # Get samba connection from parent
            samba_conn = getattr(self.parent, 'samba_conn', None) if self.parent else None
            if samba_conn:
                # Domain Computers has well-known RID 515
                group_info = get_group_by_rid(samba_conn, 515)
                if group_info:
                    group_name = group_info.get('displayName') or group_info.get('cn', 'Domain Computers')
                    self.user_group_edit.setText(group_name)
                    self.selected_group_dn = group_info.get('dn')
                    self.logger.debug(f"Found Domain Computers group: {group_name} (DN: {self.selected_group_dn})")
                    return
                    
            # Fallback to i18n string if lookup fails
            self.user_group_edit.setText(self.i18n.get_string("dialog.new_computer.default.domain_computers"))
            self.logger.debug("Using fallback Domain Computers text")
            
        except Exception as e:
            self.logger.debug(f"Error looking up Domain Computers group: {e}")
            # Fallback to i18n string
            self.user_group_edit.setText(self.i18n.get_string("dialog.new_computer.default.domain_computers"))
    
    def _select_group(self):
        """Open a group picker dialog to select a different group for the computer."""
        try:
            from search_dialogs import GroupPickerDialog
            samba_conn = getattr(self.parent, 'samba_conn', None) if self.parent else None
            if not samba_conn:
                QMessageBox.warning(self, 
                    self.i18n.get_string("dialog.common.error.title"),
                    "No connection available to search for groups."
                )
                return
                
            # Open group picker dialog
            group_picker = GroupPickerDialog(samba_conn, self)
            if group_picker.exec_() == QDialog.Accepted:
                selected_group = group_picker.get_selected_object()
                if selected_group:
                    # Update display with group name
                    group_name = selected_group.get('display_name', '')
                    self.user_group_edit.setText(group_name)
                    
                    # Store the group DN for creation
                    self.selected_group_dn = selected_group.get('dn', '')
                    self.logger.debug(f"Selected group: {group_name} (DN: {self.selected_group_dn})")
                self.logger.info(f"User selected group: {group_name}")
                
        except Exception as e:
            self.logger.error(f"Error in group selection: {e}")
            QMessageBox.warning(self, 
                self.i18n.get_string("dialog.common.error.title"),
                f"Error selecting group: {e}"
            )
        
    def _format_dn_for_display(self, dn):
        """Format DN for display in the 'Create in' label."""
        if not dn:
            return self.i18n.get_string("dialog.new_computer.create_in_unknown")
            
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
                return self.i18n.get_text("dialog.new_computer.create_in_domain", domain)
            else:
                return self.i18n.get_text("dialog.new_computer.create_in_path", domain, '/'.join(path_parts))
                
        except Exception as e:
            self.logger.debug(f"Error formatting DN for display: {e}")
            return self.i18n.get_text("dialog.new_computer.create_in_fallback", dn)
    
    def _update_pre2k_name(self):
        """Auto-update pre-Windows 2000 computer name based on computer name."""
        computer_name = self.computer_name_edit.text().strip().upper()
        if computer_name:
            # Add $ suffix for computer accounts and limit to 15 characters
            pre2k_name = computer_name[:14] + "$"
            self.pre2k_name_edit.setText(pre2k_name)
        else:
            self.pre2k_name_edit.clear()
    
    def _validate_input(self):
        """Validate input and enable/disable OK button."""
        computer_name_valid = bool(self.computer_name_edit.text().strip())
        pre2k_name_valid = bool(self.pre2k_name_edit.text().strip())
        
        is_valid = computer_name_valid and pre2k_name_valid
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(is_valid)
    
    def get_computer_data(self):
        """Return the computer data entered by the user."""
        return {
            'computer_name': self.computer_name_edit.text().strip(),
            'pre2k_name': self.pre2k_name_edit.text().strip(),
            'user_or_group': self.user_group_edit.text().strip(),
            'group_dn': self.selected_group_dn,
            'is_pre2k_computer': self.pre2k_checkbox.isChecked(),
            'container_dn': self.container_dn
        }