# src/shared_folder_dialogs.py

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDialogButtonBox, QFrame, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from i18n_manager import I18nManager


class NewSharedFolderDialog(QDialog):
    """Simple dialog for creating a new shared folder object."""
    
    def __init__(self, parent=None, container_dn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.container_dn = container_dn
        
        self.setWindowTitle(self.i18n.get_string("dialog.new_shared_folder.title"))
        self.setModal(True)
        self.setFixedSize(400, 220)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Header section with icon and "Create in" info
        header_layout = QHBoxLayout()
        
        # Shared folder icon
        icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'folder_shared.png')
        icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        header_layout.addWidget(icon_label)
        
        # Create in label
        create_in_text = self.i18n.get_string("dialog.new_shared_folder.create_in").format(self.container_dn or "Unknown")
        create_in_label = QLabel(create_in_text)
        header_layout.addWidget(create_in_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.HLine)
        separator1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator1)
        
        # Name input
        name_label = QLabel(self.i18n.get_string("dialog.new_shared_folder.name_label"))
        layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)
        
        # Network path input
        path_label = QLabel(self.i18n.get_string("dialog.new_shared_folder.network_path_label"))
        layout.addWidget(path_label)
        
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(self.i18n.get_string("dialog.new_shared_folder.network_path_placeholder"))
        layout.addWidget(self.path_input)
        
        # Warning note
        warning_label = QLabel(self.i18n.get_string("dialog.new_shared_folder.validation_warning"))
        warning_label.setStyleSheet("color: #666666; font-style: italic;")
        layout.addWidget(warning_label)
        
        # Big spacer for normal sized dialog
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout.addItem(spacer)
        
        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
    def get_shared_folder_data(self):
        """Return the shared folder data collected from the dialog."""
        return {
            'name': self.name_input.text().strip(),
            'network_path': self.path_input.text().strip(),
            'container_dn': self.container_dn
        }