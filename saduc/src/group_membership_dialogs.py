# src/group_membership_dialogs.py

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDialogButtonBox, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QFrame, QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon

from i18n_manager import I18nManager
from find_dialog import FindObjectsDialog


class AddToGroupDialog(QDialog):
    """Dialog for adding users/objects to a group."""
    
    def __init__(self, samba_conn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.i18n = I18nManager()
        self.selected_objects = []
        
        self.setWindowTitle("Select Users, Contacts, Computers, Service Accounts, or Groups")
        self.setModal(True)
        self.resize(600, 500)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Instructions
        instruction_label = QLabel("Select the object types and locations you want to search:")
        layout.addWidget(instruction_label)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - object types (simplified for now)
        left_frame = QFrame()
        left_layout = QVBoxLayout()
        
        types_label = QLabel("Select this object type:")
        left_layout.addWidget(types_label)
        
        # For simplicity, we'll focus on users initially
        # This could be expanded to show checkboxes for different object types
        object_type_label = QLabel("Users, Contacts, Computers, Service Accounts, or Groups")
        left_layout.addWidget(object_type_label)
        
        left_frame.setLayout(left_layout)
        left_frame.setMaximumWidth(250)
        splitter.addWidget(left_frame)
        
        # Right side - search and results
        right_frame = QFrame()
        right_layout = QVBoxLayout()
        
        # Search section
        search_layout = QHBoxLayout()
        search_label = QLabel("Enter the object names to select:")
        right_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type names separated by semicolons")
        right_layout.addWidget(self.search_input)
        
        search_buttons_layout = QHBoxLayout()
        
        self.check_names_btn = QPushButton("Check Names")
        self.check_names_btn.clicked.connect(self._check_names)
        search_buttons_layout.addWidget(self.check_names_btn)
        
        self.advanced_btn = QPushButton("Advanced...")
        self.advanced_btn.clicked.connect(self._open_advanced_search)
        search_buttons_layout.addWidget(self.advanced_btn)
        
        search_buttons_layout.addStretch()
        right_layout.addLayout(search_buttons_layout)
        
        # Results list
        results_label = QLabel("Selected objects:")
        right_layout.addWidget(results_label)
        
        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        right_layout.addWidget(self.results_list)
        
        # Remove button
        remove_layout = QHBoxLayout()
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.setEnabled(False)
        remove_layout.addWidget(self.remove_btn)
        remove_layout.addStretch()
        right_layout.addLayout(remove_layout)
        
        right_frame.setLayout(right_layout)
        splitter.addWidget(right_frame)
        
        layout.addWidget(splitter)
        
        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept_dialog)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect selection change
        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
        
        self.setLayout(layout)
        
    def _check_names(self):
        """Check and resolve the entered names."""
        names_text = self.search_input.text().strip()
        if not names_text:
            return
            
        names = [name.strip() for name in names_text.split(';') if name.strip()]
        
        for name in names:
            self._resolve_and_add_name(name)
            
        # Clear the input after processing
        self.search_input.clear()
        
    def _resolve_and_add_name(self, name):
        """Resolve a name and add it to the results list."""
        try:
            # Search for the object by sAMAccountName or CN
            from samba_backend import BASE_DN
            import ldap
            
            # Try different search filters
            search_filters = [
                f'(&(|(objectClass=user)(objectClass=group)(objectClass=computer)(objectClass=contact))(sAMAccountName={name}))',
                f'(&(|(objectClass=user)(objectClass=group)(objectClass=computer)(objectClass=contact))(cn={name}))',
                f'(&(|(objectClass=user)(objectClass=group)(objectClass=computer)(objectClass=contact))(displayName={name}))'
            ]
            
            attrs = ['cn', 'sAMAccountName', 'displayName', 'objectClass', 'distinguishedName']
            
            for search_filter in search_filters:
                try:
                    res = self.samba_conn.search_s(BASE_DN, ldap.SCOPE_SUBTREE, search_filter, attrs)
                    if res:
                        for dn, attrs_dict in res:
                            if attrs_dict:
                                self._add_object_to_results(dn, attrs_dict)
                        return  # Found something, stop searching
                except ldap.LDAPError:
                    continue
                    
            # If we get here, object wasn't found
            QMessageBox.warning(self, "Name Not Found", f"The name '{name}' could not be found.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error resolving name '{name}': {str(e)}")
            
    def _add_object_to_results(self, dn, attrs_dict):
        """Add an object to the results list."""
        # Check if already in list
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            if item.data(Qt.UserRole) == dn:
                return  # Already in list
                
        # Get object info
        cn = attrs_dict.get('cn', [b''])[0].decode('utf-8')
        sam_account = attrs_dict.get('sAMAccountName', [b''])[0].decode('utf-8')
        display_name = attrs_dict.get('displayName', [b''])[0].decode('utf-8')
        object_classes = [cls.decode('utf-8') for cls in attrs_dict.get('objectClass', [])]
        
        # Determine object type
        if 'user' in object_classes:
            obj_type = 'User'
        elif 'group' in object_classes:
            obj_type = 'Group'
        elif 'computer' in object_classes:
            obj_type = 'Computer'
        elif 'contact' in object_classes:
            obj_type = 'Contact'
        else:
            obj_type = 'Object'
            
        # Create display text
        display_text = display_name or cn or sam_account
        if sam_account and sam_account != display_text:
            display_text += f" ({sam_account})"
        display_text += f" [{obj_type}]"
        
        # Add to list
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, dn)  # Store DN for later use
        self.results_list.addItem(item)
        
    def _open_advanced_search(self):
        """Open the advanced search dialog."""
        dialog = FindObjectsDialog(self.samba_conn, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            # TODO: Get selected objects from find dialog and add them
            # This requires enhancing FindObjectsDialog to return selected objects
            QMessageBox.information(self, "Info", "Advanced search integration coming soon...")
            
    def _remove_selected(self):
        """Remove selected items from the results list."""
        for item in self.results_list.selectedItems():
            row = self.results_list.row(item)
            self.results_list.takeItem(row)
            
    def _on_selection_changed(self):
        """Handle selection change in results list."""
        self.remove_btn.setEnabled(len(self.results_list.selectedItems()) > 0)
        
    def _accept_dialog(self):
        """Accept the dialog and prepare selected objects."""
        self.selected_objects = []
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            dn = item.data(Qt.UserRole)
            display_text = item.text()
            self.selected_objects.append({
                'dn': dn,
                'display_text': display_text
            })
            
        if not self.selected_objects:
            QMessageBox.warning(self, "No Selection", "Please select at least one object to add to the group.")
            return
            
        self.accept()
        
    def get_selected_objects(self):
        """Return the list of selected object DNs."""
        return self.selected_objects