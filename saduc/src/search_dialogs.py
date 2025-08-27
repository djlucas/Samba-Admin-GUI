#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/search_dialogs.py
#
# Description:
# Reusable search and picker dialogs for various AD object types.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QDialogButtonBox,
    QGroupBox, QCheckBox, QComboBox, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon

from i18n_manager import I18nManager
from search_backend import search_users, search_groups, search_containers

logger = logging.getLogger("saduc_app.search_dialogs")

class SearchWorker(QThread):
    """Worker thread for performing searches without blocking the UI."""
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, search_func, *args, **kwargs):
        super().__init__()
        self.search_func = search_func
        self.args = args
        self.kwargs = kwargs
        
    def run(self):
        try:
            results = self.search_func(*self.args, **self.kwargs)
            self.results_ready.emit(results)
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.error_occurred.emit(str(e))

class ObjectPickerDialog(QDialog):
    """Base class for object picker dialogs."""
    
    def __init__(self, samba_conn, title="Select Object", parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.i18n = I18nManager()
        self.selected_object = None
        self.search_worker = None
        
        self.setWindowTitle(title)
        self.setMinimumSize(600, 450)
        self.resize(700, 500)
        
        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._setup_table()
        
    def _create_widgets(self):
        """Create UI widgets - to be overridden by subclasses."""
        # Search controls
        self.search_group = QGroupBox("Search Criteria")
        self.name_edit = QLineEdit()
        self.search_btn = QPushButton("Search")
        self.clear_btn = QPushButton("Clear")
        
        # Progress indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("")
        
        # Results table
        self.results_table = QTableWidget()
        
        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        
    def _create_layout(self):
        """Create the dialog layout."""
        main_layout = QVBoxLayout(self)
        
        # Search controls layout
        search_layout = QFormLayout(self.search_group)
        search_layout.addRow("Name:", self.name_edit)
        
        # Search buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.search_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        search_layout.addRow(button_layout)
        
        main_layout.addWidget(self.search_group)
        
        # Progress bar
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        
        # Results table
        main_layout.addWidget(QLabel("Search Results:"))
        main_layout.addWidget(self.results_table, 1)  # Give it stretch factor
        
        # Dialog buttons
        main_layout.addWidget(self.button_box)
        
    def _connect_signals(self):
        """Connect widget signals."""
        self.search_btn.clicked.connect(self.perform_search)
        self.clear_btn.clicked.connect(self.clear_search)
        self.name_edit.returnPressed.connect(self.perform_search)
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.itemDoubleClicked.connect(self.accept)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
    def _setup_table(self):
        """Setup the results table - to be overridden by subclasses."""
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Name", "Type", "Description"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        
        # Column sizing
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        self.results_table.verticalHeader().hide()
        
    def perform_search(self):
        """Perform the search - to be implemented by subclasses."""
        pass
        
    def clear_search(self):
        """Clear search criteria and results."""
        self.name_edit.clear()
        self.results_table.setRowCount(0)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        self.selected_object = None
        self.status_label.setText("")
        
    def _on_selection_changed(self):
        """Handle table selection changes."""
        selected_items = self.results_table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            self.selected_object = self.results_table.item(row, 0).data(Qt.UserRole)
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
        else:
            self.selected_object = None
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            
    def _populate_table(self, results):
        """Populate the table with search results."""
        self.results_table.setRowCount(len(results))
        
        for row, obj in enumerate(results):
            # Name column
            name_item = QTableWidgetItem(obj.get('display_name', ''))
            name_item.setData(Qt.UserRole, obj)  # Store full object data
            self.results_table.setItem(row, 0, name_item)
            
            # Type column
            type_item = QTableWidgetItem(obj.get('object_type', ''))
            self.results_table.setItem(row, 1, type_item)
            
            # Description column
            description = ""
            if 'description' in obj and obj['description']:
                description = obj['description'][0] if isinstance(obj['description'], list) else obj['description']
            desc_item = QTableWidgetItem(description)
            self.results_table.setItem(row, 2, desc_item)
            
        self.status_label.setText(f"Found {len(results)} objects")
        
    def _show_progress(self, message):
        """Show progress indicator."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.status_label.setText(message)
        self.search_btn.setEnabled(False)
        
    def _hide_progress(self):
        """Hide progress indicator."""
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)
        
    def get_selected_object(self):
        """Get the selected object data."""
        return self.selected_object

class UserPickerDialog(ObjectPickerDialog):
    """Dialog for picking user objects."""
    
    def __init__(self, samba_conn, parent=None):
        super().__init__(samba_conn, "Select User", parent)
        
    def _create_widgets(self):
        super()._create_widgets()
        self.enabled_only_check = QCheckBox("Enabled users only")
        self.enabled_only_check.setChecked(True)
        
    def _create_layout(self):
        """Create the dialog layout with user-specific controls."""
        main_layout = QVBoxLayout(self)
        
        # Search controls layout
        search_layout = QFormLayout(self.search_group)
        search_layout.addRow("Name:", self.name_edit)
        search_layout.addRow("", self.enabled_only_check)
        
        # Search buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.search_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        search_layout.addRow(button_layout)
        
        main_layout.addWidget(self.search_group)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(QLabel("Search Results:"))
        main_layout.addWidget(self.results_table, 1)
        main_layout.addWidget(self.button_box)
        
    def _setup_table(self):
        """Setup the results table for users."""
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Name", "Type", "Username", "Email"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        
        self.results_table.verticalHeader().hide()
        
    def perform_search(self):
        """Perform user search."""
        name_filter = self.name_edit.text().strip()
        if not name_filter:
            QMessageBox.information(self, "Search", "Please enter a name to search for.")
            return
            
        self._show_progress("Searching for users...")
        
        # Start search in worker thread
        self.search_worker = SearchWorker(
            search_users, 
            self.samba_conn,
            name_filter=name_filter,
            enabled_only=self.enabled_only_check.isChecked()
        )
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.error_occurred.connect(self._on_search_error)
        self.search_worker.start()
        
    def _populate_table(self, results):
        """Populate the table with user search results."""
        self.results_table.setRowCount(len(results))
        
        for row, obj in enumerate(results):
            # Name column
            name_item = QTableWidgetItem(obj.get('display_name', ''))
            name_item.setData(Qt.UserRole, obj)
            self.results_table.setItem(row, 0, name_item)
            
            # Type column
            type_item = QTableWidgetItem(obj.get('object_type', ''))
            self.results_table.setItem(row, 1, type_item)
            
            # Username column
            username = ""
            if 'sAMAccountName' in obj and obj['sAMAccountName']:
                username = obj['sAMAccountName'][0] if isinstance(obj['sAMAccountName'], list) else obj['sAMAccountName']
            username_item = QTableWidgetItem(username)
            self.results_table.setItem(row, 2, username_item)
            
            # Email column
            email = ""
            if 'mail' in obj and obj['mail']:
                email = obj['mail'][0] if isinstance(obj['mail'], list) else obj['mail']
            email_item = QTableWidgetItem(email)
            self.results_table.setItem(row, 3, email_item)
            
        self.status_label.setText(f"Found {len(results)} users")
        
    def _on_search_results(self, results):
        """Handle search results."""
        self._hide_progress()
        self._populate_table(results)
        
    def _on_search_error(self, error_msg):
        """Handle search errors."""
        self._hide_progress()
        QMessageBox.critical(self, "Search Error", f"Search failed: {error_msg}")

class GroupPickerDialog(ObjectPickerDialog):
    """Dialog for picking group objects."""
    
    def __init__(self, samba_conn, parent=None):
        super().__init__(samba_conn, "Select Group", parent)
        
    def perform_search(self):
        """Perform group search."""
        name_filter = self.name_edit.text().strip()
        if not name_filter:
            QMessageBox.information(self, "Search", "Please enter a name to search for.")
            return
            
        self._show_progress("Searching for groups...")
        
        self.search_worker = SearchWorker(
            search_groups, 
            self.samba_conn,
            name_filter=name_filter
        )
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.error_occurred.connect(self._on_search_error)
        self.search_worker.start()
        
    def _on_search_results(self, results):
        """Handle search results."""
        self._hide_progress()
        self._populate_table(results)
        
    def _on_search_error(self, error_msg):
        """Handle search errors."""
        self._hide_progress()
        QMessageBox.critical(self, "Search Error", f"Search failed: {error_msg}")

class ContainerBrowserDialog(ObjectPickerDialog):
    """Dialog for browsing and selecting containers/OUs."""
    
    def __init__(self, samba_conn, parent=None):
        super().__init__(samba_conn, "Select Location", parent)
        
    def _setup_table(self):
        """Setup the results table for containers."""
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Name", "Type", "Path"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        self.results_table.verticalHeader().hide()
        
    def perform_search(self):
        """Perform container search."""
        name_filter = self.name_edit.text().strip()
        
        self._show_progress("Searching for containers...")
        
        self.search_worker = SearchWorker(
            search_containers, 
            self.samba_conn,
            name_filter=name_filter
        )
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.error_occurred.connect(self._on_search_error)
        self.search_worker.start()
        
    def _populate_table(self, results):
        """Populate the table with container search results."""
        self.results_table.setRowCount(len(results))
        
        for row, obj in enumerate(results):
            # Name column
            name_item = QTableWidgetItem(obj.get('display_name', ''))
            name_item.setData(Qt.UserRole, obj)
            self.results_table.setItem(row, 0, name_item)
            
            # Type column
            type_item = QTableWidgetItem(obj.get('object_type', ''))
            self.results_table.setItem(row, 1, type_item)
            
            # Path column (DN)
            path_item = QTableWidgetItem(obj.get('dn', ''))
            self.results_table.setItem(row, 2, path_item)
            
        self.status_label.setText(f"Found {len(results)} containers")
        
    def _on_search_results(self, results):
        """Handle search results."""
        self._hide_progress()
        self._populate_table(results)
        
    def _on_search_error(self, error_msg):
        """Handle search errors."""
        self._hide_progress()
        QMessageBox.critical(self, "Search Error", f"Search failed: {error_msg}")