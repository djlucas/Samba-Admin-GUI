#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/find_dialog.py
#
# Description:
# This file contains the dialog for finding objects in Active Directory.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QLineEdit, QPushButton, QComboBox, QLabel, QFrame, QTabWidget,
    QTableWidget, QHeaderView, QTableWidgetItem, QTextEdit, QGroupBox
)
from PyQt5.QtCore import Qt
import ldap
import ldap.dn

from i18n_manager import I18nManager
from samba_backend import BASE_DN, find_objects, get_base_dn

class FindObjectsDialog(QDialog):
    """Dialog for finding Active Directory objects."""
    def __init__(self, samba_conn, search_base_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.search_base_dn = search_base_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setMinimumSize(750, 500)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._initial_setup()

    def _create_widgets(self):
        # Top line widgets
        self.find_label = QLabel("Find:")
        self.find_combo = QComboBox()
        self.in_label = QLabel("In:")
        self.in_combo = QComboBox()
        self.in_combo.setMinimumWidth(200)
        self.browse_btn = QPushButton("Browse...")

        # Tabs
        self.tab_widget = QTabWidget()
        self.find_details_tab = QWidget() # This will be renamed dynamically
        self.advanced_tab = QWidget()

        # Widgets for the main find tab
        self.name_label = QLabel("Name:")
        self.name_edit = QLineEdit()
        self.description_label = QLabel("Description:")
        self.description_edit = QLineEdit()

        # Widgets for the advanced tab
        self.ldap_filter_edit = QTextEdit()
        self.ldap_filter_edit.setMaximumHeight(120)
        self.ldap_filter_edit.setPlaceholderText("Enter custom LDAP filter (e.g., (objectClass=user))")
        
        self.search_base_combo = QComboBox()
        self.search_base_combo.setEditable(True)
        self.search_base_combo.setMinimumWidth(300)
        
        self.search_scope_combo = QComboBox()
        self.search_scope_combo.addItems(["Subtree", "One Level", "Base Object"])
        self.search_scope_combo.setCurrentText("Subtree")
        
        self.attributes_edit = QLineEdit()
        self.attributes_edit.setPlaceholderText("cn,displayName,description (leave empty for default)")
        
        # Sample queries for user convenience
        self.sample_queries_combo = QComboBox()
        self.sample_queries_combo.addItems([
            "Select sample query...",
            "All users: (objectClass=user)",
            "All groups: (objectClass=group)", 
            "All computers: (objectClass=computer)",
            "Enabled users: (&(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))",
            "Disabled users: (&(objectClass=user)(userAccountControl:1.2.840.113556.1.4.803:=2))",
            "Groups with members: (&(objectClass=group)(member=*))",
            "Empty groups: (&(objectClass=group)(!(member=*)))",
            "Service accounts: (&(objectClass=user)(servicePrincipalName=*))"
        ])

        # Buttons on the right
        self.find_now_btn = QPushButton("Find Now")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.clear_all_btn = QPushButton("Clear All")
        self.search_icon_label = QLabel() # Placeholder for search icon

        # Results table
        self.results_table = QTableWidget()

    def _create_layout(self):
        main_layout = QHBoxLayout(self)

        # --- Left Panel (Inputs and Results) ---
        left_panel_layout = QVBoxLayout()

        # Top line layout
        top_line_layout = QHBoxLayout()
        top_line_layout.addWidget(self.find_label)
        top_line_layout.addWidget(self.find_combo)
        top_line_layout.addWidget(self.in_label)
        top_line_layout.addWidget(self.in_combo, 1)
        top_line_layout.addWidget(self.browse_btn)
        left_panel_layout.addLayout(top_line_layout)

        # --- Tab Widget ---
        find_details_layout = QFormLayout(self.find_details_tab)
        find_details_layout.addRow(self.name_label, self.name_edit)
        find_details_layout.addRow(self.description_label, self.description_edit)

        advanced_layout = QVBoxLayout(self.advanced_tab)
        
        # Sample queries group
        sample_group = QGroupBox("Sample Queries")
        sample_layout = QVBoxLayout(sample_group)
        sample_layout.addWidget(self.sample_queries_combo)
        advanced_layout.addWidget(sample_group)
        
        # Custom query group
        query_group = QGroupBox("Custom LDAP Query")
        query_layout = QFormLayout(query_group)
        query_layout.addRow("LDAP Filter:", self.ldap_filter_edit)
        query_layout.addRow("Search Base:", self.search_base_combo)
        query_layout.addRow("Search Scope:", self.search_scope_combo)  
        query_layout.addRow("Attributes:", self.attributes_edit)
        advanced_layout.addWidget(query_group)
        
        advanced_layout.addStretch()
        
        self.tab_widget.addTab(self.find_details_tab, "") # Title set dynamically
        self.tab_widget.addTab(self.advanced_tab, "Advanced")
        left_panel_layout.addWidget(self.tab_widget)

        # Results table
        left_panel_layout.addWidget(self.results_table)
        self._setup_results_table()

        # --- Right Panel (Buttons) ---
        right_panel_layout = QVBoxLayout()
        right_panel_layout.addWidget(self.find_now_btn)
        right_panel_layout.addWidget(self.stop_btn)
        right_panel_layout.addWidget(self.clear_all_btn)
        right_panel_layout.addStretch()
        right_panel_layout.addWidget(self.search_icon_label)
        right_panel_layout.addStretch()

        main_layout.addLayout(left_panel_layout, 4)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        main_layout.addLayout(right_panel_layout, 1)

    def _connect_signals(self):
        self.find_combo.currentIndexChanged.connect(self._on_find_type_changed)
        self.find_now_btn.clicked.connect(self._on_find_now_clicked)
        self.sample_queries_combo.currentTextChanged.connect(self._on_sample_query_selected)
        
        # Add Enter key handling for search fields
        self.name_edit.returnPressed.connect(self._on_find_now_clicked)
        self.description_edit.returnPressed.connect(self._on_find_now_clicked)
        
        # Note: QTextEdit doesn't have returnPressed signal, so we don't add it for ldap_filter_edit
        # Users can still use Ctrl+Enter or the Find Now button for advanced searches

    def _initial_setup(self):
        self.find_combo.addItems([
            "Users, Contacts, and Groups",
            "Computers",
            "Shared Folders",
            "Organizational Units",
            "Custom Search",
            "Common Queries"
        ])

        display_path = self._format_dn_for_display(self.search_base_dn)
        self.in_combo.addItem(display_path, self.search_base_dn)
        
        # Populate advanced tab search bases
        self.search_base_combo.addItem(display_path, self.search_base_dn)
        
        # Add common container bases if available
        if self.search_base_dn:
            common_containers = [
                f"CN=Users,{self.search_base_dn}",
                f"CN=Computers,{self.search_base_dn}", 
                f"CN=Builtin,{self.search_base_dn}",
                f"OU=Domain Controllers,{self.search_base_dn}"
            ]
            for container_dn in common_containers:
                container_display = self._format_dn_for_display(container_dn)
                self.search_base_combo.addItem(container_display, container_dn)
        
        # Set default search base for advanced tab
        self.search_base_combo.setCurrentText(display_path)

        self._on_find_type_changed(0)

    def _on_find_type_changed(self, index):
        find_type = self.find_combo.currentText()
        self.setWindowTitle(f"Find {find_type}")
        self.tab_widget.setTabText(0, find_type)

    def _on_find_now_clicked(self):
        self.stop_btn.setEnabled(True)
        self.results_table.setRowCount(0)  # Clear previous results

        current_tab_index = self.tab_widget.currentIndex()
        
        if current_tab_index == 0:  # Standard search tab
            search_base = self.in_combo.currentData()
            object_type = self.find_combo.currentText()
            name = self.name_edit.text()
            description = self.description_edit.text()
            
            results = find_objects(self.samba_conn, search_base, object_type, name, description)
        else:  # Advanced tab
            results = self._perform_advanced_search()

        for item in results:
            row_position = self.results_table.rowCount()
            self.results_table.insertRow(row_position)
            
            # Store the full object data in the first column's UserRole
            name_item = QTableWidgetItem(item.get('name', ''))
            name_item.setData(Qt.UserRole, item)  # Store full object data
            self.results_table.setItem(row_position, 0, name_item)
            
            # A more sophisticated type determination would be needed here
            object_classes = item.get('objectClass', ['Unknown'])
            object_type = object_classes[-1] if object_classes else 'Unknown'
            self.results_table.setItem(row_position, 1, QTableWidgetItem(object_type))
            self.results_table.setItem(row_position, 2, QTableWidgetItem(item.get('description', '')))

        self.stop_btn.setEnabled(False)

    def _on_sample_query_selected(self, text):
        """Handle sample query selection."""
        if text.startswith("Select sample query"):
            return
        
        # Extract the LDAP filter from the sample text (after the colon)
        if ": " in text:
            ldap_filter = text.split(": ", 1)[1]
            self.ldap_filter_edit.setPlainText(ldap_filter)

    def _perform_advanced_search(self):
        """Perform custom LDAP search using advanced parameters."""
        from samba_backend import get_paged_results
        
        # Get search parameters
        ldap_filter = self.ldap_filter_edit.toPlainText().strip()
        if not ldap_filter:
            self.logger.warning("No LDAP filter provided for advanced search")
            return []
        
        # Get search base - use current data if available, otherwise text
        search_base = self.search_base_combo.currentData()
        if not search_base:
            search_base = self.search_base_combo.currentText()
            # Convert display format back to DN if needed
            if "/" in search_base and "." in search_base:
                search_base = self.search_base_dn  # Fall back to default
        
        # Get search scope
        scope_text = self.search_scope_combo.currentText()
        if scope_text == "One Level":
            scope = ldap.SCOPE_ONELEVEL
        elif scope_text == "Base Object":
            scope = ldap.SCOPE_BASE
        else:  # Default to Subtree
            scope = ldap.SCOPE_SUBTREE
        
        # Get attributes
        attributes_text = self.attributes_edit.text().strip()
        if attributes_text:
            attributes = [attr.strip() for attr in attributes_text.split(',')]
        else:
            attributes = ['cn', 'ou', 'dc', 'displayName', 'description', 'distinguishedName', 'objectClass']
        
        self.logger.info(f"Advanced search: base='{search_base}', filter='{ldap_filter}', scope={scope}")
        
        try:
            res = get_paged_results(self.samba_conn, search_base, scope, ldap_filter, attributes)
            
            objects = []
            for child_dn, entry in res:
                if isinstance(entry, dict):
                    name_attr = entry.get('displayName') or entry.get('ou') or entry.get('cn')
                    if name_attr:
                        obj_data = {
                            'name': name_attr[0].decode('utf-8'),
                            'dn': child_dn,
                            'objectClass': [oc.decode('utf-8') for oc in entry.get('objectClass', [])]
                        }
                        if 'description' in entry:
                            obj_data['description'] = entry['description'][0].decode('utf-8')
                        objects.append(obj_data)
            return objects
        except ldap.LDAPError as e:
            self.logger.error(f"LDAP error during advanced search: {e}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Search Error", f"LDAP search failed: {e}")
            return []

    def _format_dn_for_display(self, dn_string):
        if not dn_string:
            return ""
        
        base_dn = get_base_dn(self.samba_conn)
        if not base_dn:
            return dn_string
            
        domain_parts = [p.split('=')[1] for p in base_dn.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)

        if dn_string.lower() == base_dn.lower():
            return domain

        try:
            dn_struct = ldap.dn.str2dn(dn_string)
            base_dn_struct = ldap.dn.str2dn(base_dn)

            relative_dn_struct = [rdn for rdn in dn_struct if rdn not in base_dn_struct]
            
            path_parts = []
            for rdn_part in reversed(relative_dn_struct):
                path_parts.append(rdn_part[0][1])

            if not path_parts:
                return domain
            
            return f"{domain}/{'/'.join(path_parts)}"
        except Exception:
            return dn_string

    def _setup_results_table(self):
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Name", "Type", "Description"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results_table.verticalHeader().hide()
    
    def get_selected_object(self):
        """Get the selected object data from the search results."""
        selected_items = self.results_table.selectedItems()
        if not selected_items:
            return None
        
        # Get the first column item which contains the stored object data
        row = selected_items[0].row()
        name_item = self.results_table.item(row, 0)
        if name_item:
            return name_item.data(Qt.UserRole)
        return None
