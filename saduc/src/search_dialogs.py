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
    QGroupBox, QCheckBox, QComboBox, QMessageBox, QProgressBar, QTextEdit,
    QSplitter, QFrame, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
    QWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence, QTextCharFormat, QColor, QTextCursor

from i18n_manager import I18nManager
from search_backend import search_users, search_groups, search_containers

logger = logging.getLogger("saduc_app.search_dialogs")

class ValidatedToken(QWidget):
    """A widget representing a single validated name token."""

    def __init__(self, display_name, match_object, parent_dialog):
        super().__init__()
        self.display_name = display_name
        self.match_object = match_object
        self.parent_dialog = parent_dialog

        # Create the layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(2)

        # Create the label with blue styling
        self.label = QLabel(display_name + ";")
        self.label.setStyleSheet("""
            QLabel {
                color: blue;
                text-decoration: underline;
                background-color: #f0f8ff;
                border: 1px solid #add8e6;
                border-radius: 3px;
                padding: 2px 4px;
            }
        """)

        # Create remove button (small X)
        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(16, 16)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #ff5252;
            }
        """)
        self.remove_btn.clicked.connect(self.remove_token)

        layout.addWidget(self.label)
        layout.addWidget(self.remove_btn)

        # Make the whole widget clickable
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def mousePressEvent(self, event):
        """Handle mouse clicks to select the token."""
        # Visual feedback for selection could be added here
        super().mousePressEvent(event)

    def remove_token(self):
        """Remove this token from the dialog."""
        self.parent_dialog.remove_validated_token(self)

    def show_context_menu(self, position):
        """Show context menu for the token."""
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        remove_action = menu.addAction(self.parent_dialog.i18n.get_string("dialog.common.remove"))
        remove_action.triggered.connect(self.remove_token)
        menu.exec_(self.mapToGlobal(position))

class TokenTextEdit(QTextEdit):
    """A QTextEdit that displays validated names as removable tokens."""

    def __init__(self, parent_dialog):
        super().__init__()
        self.parent_dialog = parent_dialog
        self.setAcceptRichText(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Don't add newline, trigger name checking instead
            self.parent_dialog._check_names()
            event.accept()
        else:
            super().keyPressEvent(event)

    def insertTokenWidget(self, display_name, match_object):
        """Insert a token widget at the current cursor position."""
        cursor = self.textCursor()

        # Create a simple text representation with styling
        token_text = f"{display_name}; "
        cursor.insertText(token_text)

        # Apply blue formatting to just the name part
        cursor.setPosition(cursor.position() - len(token_text))
        cursor.setPosition(cursor.position() + len(display_name), QTextCursor.KeepAnchor)

        # Create blue format
        blue_format = QTextCharFormat()
        blue_format.setForeground(QColor(0, 0, 255))
        blue_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        blue_format.setBackground(QColor(240, 248, 255))  # Light blue background

        cursor.setCharFormat(blue_format)

        # Move cursor to end
        cursor.setPosition(cursor.position() + len("; "))
        self.setTextCursor(cursor)

        # Track this token
        start_pos = cursor.position() - len(token_text)
        end_pos = start_pos + len(display_name)
        self.parent_dialog.validated_ranges.append((start_pos, end_pos, display_name))

    def mousePressEvent(self, event):
        """Handle mouse clicks to select tokens."""
        # Get click position
        cursor = self.cursorForPosition(event.pos())
        click_pos = cursor.position()

        # Check if we clicked in a validated range
        for start, end, display_name in self.parent_dialog.validated_ranges:
            if start <= click_pos < end:
                # Select the entire token
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                self.setTextCursor(cursor)
                return

        # If not in a validated range, use normal behavior
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Show custom context menu for tokens."""
        cursor = self.cursorForPosition(event.pos())
        click_pos = cursor.position()

        # Check if we clicked on a validated token
        for start, end, display_name in self.parent_dialog.validated_ranges:
            if start <= click_pos < end:
                from PyQt5.QtWidgets import QMenu
                menu = QMenu(self)
                remove_action = menu.addAction(self.parent_dialog.i18n.get_string("dialog.common.remove"))
                remove_action.triggered.connect(lambda: self._remove_token(display_name))
                menu.exec_(event.globalPos())
                return

        # Default context menu for non-token areas
        super().contextMenuEvent(event)

    def _remove_token(self, display_name):
        """Remove a token by display name."""
        self.parent_dialog._remove_token_by_name(display_name)

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
            QMessageBox.information(self, self.i18n.get_string("search_dialog.search_title"), 
                                   self.i18n.get_string("search_dialog.enter_name_message"))
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
        QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                             self.i18n.get_string("search_dialog.search_failed_message").format(error_msg))

class GroupPickerDialog(ObjectPickerDialog):
    """Dialog for picking group objects."""

    def __init__(self, samba_conn, parent=None):
        super().__init__(samba_conn, "Select Group", parent)

    def perform_search(self):
        """Perform group search."""
        name_filter = self.name_edit.text().strip()
        if not name_filter:
            QMessageBox.information(self, self.i18n.get_string("search_dialog.search_title"), 
                                   self.i18n.get_string("search_dialog.enter_name_message"))
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
        QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                             self.i18n.get_string("search_dialog.search_failed_message").format(error_msg))

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
        QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                             self.i18n.get_string("search_dialog.search_failed_message").format(error_msg))


class PrincipalPickerDialog(ObjectPickerDialog):
    """Dialog for picking user or group objects (principals)."""

    def __init__(self, samba_conn, parent=None):
        super().__init__(samba_conn, "Select User, Computer, Service Account, or Group", parent)

    def _create_widgets(self):
        super()._create_widgets()
        # Add object type filter
        self.type_combo = QComboBox()
        self.type_combo.addItem("Users", "user")
        self.type_combo.addItem("Groups", "group") 
        self.type_combo.addItem("All", "all")
        self.type_combo.setCurrentText("All")

        self.enabled_only_check = QCheckBox("Enabled accounts only")
        self.enabled_only_check.setChecked(True)

    def _create_layout(self):
        """Create the dialog layout with principal-specific controls."""
        main_layout = QVBoxLayout(self)

        # Search controls layout
        search_layout = QFormLayout(self.search_group)
        search_layout.addRow("Name:", self.name_edit)
        search_layout.addRow("Object type:", self.type_combo)
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
        """Setup the results table for principals."""
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Name", "Type", "Account Name", "Description"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setAlternatingRowColors(True)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        self.results_table.verticalHeader().hide()

    def perform_search(self):
        """Perform principal search."""
        name_filter = self.name_edit.text().strip()
        if not name_filter:
            QMessageBox.information(self, self.i18n.get_string("search_dialog.search_title"), 
                                   self.i18n.get_string("search_dialog.enter_name_message"))
            return

        object_type = self.type_combo.currentData()
        enabled_only = self.enabled_only_check.isChecked()

        self._show_progress("Searching for principals...")

        # Import search functions
        from search_backend import search_users, search_groups

        if object_type == "user":
            search_func = search_users
            search_args = (self.samba_conn, None, name_filter, enabled_only)
        elif object_type == "group":
            search_func = search_groups 
            search_args = (self.samba_conn, None, name_filter)
        else:  # "all"
            # Search all types and combine results
            self._search_all_types(name_filter, enabled_only)
            return

        self.search_worker = SearchWorker(search_func, *search_args)
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.error_occurred.connect(self._on_search_error)
        self.search_worker.start()

    def _search_all_types(self, name_filter, enabled_only):
        """Search all object types and combine results."""
        from search_backend import search_users, search_groups

        # This is a simplified version - in practice you'd want to run these in parallel
        try:
            results = []

            # Search users
            try:
                user_results = search_users(self.samba_conn, None, name_filter, enabled_only)
                if user_results:
                    results.extend(user_results)
            except Exception as e:
                logger.error(f"Error searching users: {e}")

            # Search groups  
            try:
                group_results = search_groups(self.samba_conn, None, name_filter)
                if group_results:
                    results.extend(group_results)
            except Exception as e:
                logger.error(f"Error searching groups: {e}")

            self._hide_progress()
            self._populate_table(results)

        except Exception as e:
            self._hide_progress()
            QMessageBox.critical(self, "Search Error", f"Search failed: {str(e)}")

    def _populate_table(self, results):
        """Populate the table with principal search results."""
        self.results_table.setRowCount(len(results))

        for row, obj in enumerate(results):
            # Name column
            name_item = QTableWidgetItem(obj.get('display_name', obj.get('name', '')))
            name_item.setData(Qt.UserRole, obj)
            self.results_table.setItem(row, 0, name_item)

            # Type column
            type_item = QTableWidgetItem(obj.get('object_type', ''))
            self.results_table.setItem(row, 1, type_item)

            # Account name column
            account_name = obj.get('sAMAccountName', obj.get('username', ''))
            account_item = QTableWidgetItem(account_name)
            self.results_table.setItem(row, 2, account_item)

            # Description column
            desc_item = QTableWidgetItem(obj.get('description', ''))
            self.results_table.setItem(row, 3, desc_item)

        self.status_label.setText(f"Found {len(results)} objects")

    def _on_search_results(self, results):
        """Handle search results."""
        self._hide_progress()
        self._populate_table(results)

    def _on_search_error(self, error_msg):
        """Handle search errors."""
        self._hide_progress()
        QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                             self.i18n.get_string("search_dialog.search_failed_message").format(error_msg))


class StandardSearchDialog(QDialog):
    """
    Standard search dialog with name validation, object type configuration,
    and location selection. Replaces the old AddToGroupDialog with a more
    flexible, reusable approach.
    """

    def __init__(self, samba_conn, object_types=None, title=None, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.i18n = I18nManager()
        self.selected_objects = []

        # Configure object types
        self._configure_object_types(object_types)

        # Initialize current search location  
        from samba_backend import BASE_DN
        self.current_location_dn = BASE_DN

        # Set title
        if title:
            self.setWindowTitle(title)
        else:
            self._update_title()

        self.setModal(True)
        self.resize(500, 400)

        self._setup_ui()
        self._discover_object_types()
        self._update_location_display()

        # Keep track of validated names and their display names
        self.validated_names = {}  # original_name -> display_name mapping
        self.validated_ranges = []  # list of (start, end, display_name) tuples for protected ranges

    def _configure_object_types(self, object_types):
        """Configure which object types are available and selected."""
        # Define all possible object types with i18n strings
        all_types = {
            'user': {'label': self.i18n.get_string('object_type.users'), 'default_selected': False, 'objectClass': 'user'},
            'contact': {'label': self.i18n.get_string('object_type.contacts'), 'default_selected': False, 'objectClass': 'contact'},
            'computer': {'label': self.i18n.get_string('object_type.computers'), 'default_selected': False, 'objectClass': 'computer'}, 
            'group': {'label': self.i18n.get_string('object_type.groups'), 'default_selected': False, 'objectClass': 'group'},
            'serviceAccount': {'label': self.i18n.get_string('object_type.service_accounts'), 'default_selected': False, 'objectClass': 'user', 'filter_type': 'service_account'},
            'inetOrgPerson': {'label': self.i18n.get_string('object_type.inet_org_person'), 'default_selected': False, 'objectClass': 'inetOrgPerson'},
            'organizationalPerson': {'label': self.i18n.get_string('object_type.organizational_person'), 'default_selected': False, 'objectClass': 'organizationalPerson'}
        }

        # Extended types that may not exist in all schemas
        extended_types = {
            'msDS-GroupManagedServiceAccount': {'label': self.i18n.get_string('object_type.group_managed_service_accounts'), 'default_selected': False, 'objectClass': 'msDS-GroupManagedServiceAccount'},
            'msDS-ManagedServiceAccount': {'label': self.i18n.get_string('object_type.managed_service_accounts'), 'default_selected': False, 'objectClass': 'msDS-ManagedServiceAccount'},
            'msDS-Device': {'label': self.i18n.get_string('object_type.devices'), 'default_selected': False, 'objectClass': 'msDS-Device'}
        }

        self.all_possible_types = {**all_types, **extended_types}

        # Set which types are selected based on input
        if object_types:
            for obj_type in object_types:
                if obj_type in self.all_possible_types:
                    self.all_possible_types[obj_type]['default_selected'] = True
        else:
            # Default to common types if none specified
            for obj_type in ['user', 'contact', 'computer', 'group', 'serviceAccount']:
                if obj_type in self.all_possible_types:
                    self.all_possible_types[obj_type]['default_selected'] = True

        # Will be populated from schema discovery
        self.available_object_types = {}

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Object Type Section
        object_type_layout = QVBoxLayout()
        object_type_label = QLabel(self.i18n.get_string("search_dialog.select_object_type"))
        object_type_layout.addWidget(object_type_label)

        object_type_selection_layout = QHBoxLayout()
        self.object_type_display = QLineEdit()
        self.object_type_display.setReadOnly(True)
        self.object_types_btn = QPushButton(self.i18n.get_string("search_dialog.object_types_button"))
        self.object_types_btn.clicked.connect(self._select_object_types)
        object_type_selection_layout.addWidget(self.object_type_display)
        object_type_selection_layout.addWidget(self.object_types_btn)
        object_type_layout.addLayout(object_type_selection_layout)
        layout.addLayout(object_type_layout)

        # Location Section
        location_layout = QVBoxLayout()
        location_label = QLabel(self.i18n.get_string("search_dialog.from_location"))
        location_layout.addWidget(location_label)

        location_selection_layout = QHBoxLayout()
        self.location_display = QLineEdit()
        self.location_display.setReadOnly(True)
        self.locations_btn = QPushButton(self.i18n.get_string("search_dialog.locations_button"))
        self.locations_btn.clicked.connect(self._select_locations)
        location_selection_layout.addWidget(self.location_display)
        location_selection_layout.addWidget(self.locations_btn)
        location_layout.addLayout(location_selection_layout)
        layout.addLayout(location_layout)

        # Search Section
        search_label = QLabel(self.i18n.get_string("search_dialog.enter_object_names"))
        layout.addWidget(search_label)

        # Multi-line text input with Check Names button aligned to top
        search_input_layout = QHBoxLayout()

        # Create custom QTextEdit class for Enter key handling and protected text
        class SearchTextEdit(QTextEdit):
            def __init__(self, parent_dialog):
                super().__init__()
                self.parent_dialog = parent_dialog
                self.setContextMenuPolicy(Qt.CustomContextMenu)
                self.customContextMenuRequested.connect(self._show_context_menu)

            def keyPressEvent(self, event):
                if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    self.parent_dialog._check_names()
                elif event.key() in [Qt.Key_Backspace, Qt.Key_Delete]:
                    # Handle delete with token selection
                    if self._handle_token_deletion(event):
                        return  # Token was deleted
                    super().keyPressEvent(event)
                else:
                    super().keyPressEvent(event)

            def mousePressEvent(self, event):
                """Handle mouse clicks to select tokens."""
                # Get click position BEFORE calling super() to avoid cursor positioning issues
                cursor = self.cursorForPosition(event.pos())
                click_pos = cursor.position()

                # Check if we clicked in a validated range
                for start, end, display_name in self.parent_dialog.validated_ranges:
                    if start <= click_pos < end:
                        # Don't call super() - we'll handle the click ourselves
                        # Select the entire token
                        cursor.setPosition(start)
                        cursor.setPosition(end, QTextCursor.KeepAnchor)
                        self.setTextCursor(cursor)
                        return

                # If not in a validated range, use normal behavior
                super().mousePressEvent(event)

            def _handle_token_deletion(self, event):
                """Handle deletion of tokens or normal text."""
                cursor = self.textCursor()

                # Check if we have a selection
                if cursor.hasSelection():
                    # Check if the selection is a complete token
                    start = cursor.selectionStart()
                    end = cursor.selectionEnd()

                    for token_start, token_end, display_name in self.parent_dialog.validated_ranges:
                        if start == token_start and end == token_end:
                            # Complete token is selected - delete it
                            self._delete_entire_validated_entry(token_start, token_end, display_name)
                            return True
                else:
                    # No selection - check if we're adjacent to a token
                    pos = cursor.position()

                    for token_start, token_end, display_name in self.parent_dialog.validated_ranges:
                        if event.key() == Qt.Key_Backspace and pos == token_end:
                            # Backspace right after a token - delete the token
                            self._delete_entire_validated_entry(token_start, token_end, display_name)
                            return True
                        elif event.key() == Qt.Key_Delete and pos == token_start:
                            # Delete right before a token - delete the token
                            self._delete_entire_validated_entry(token_start, token_end, display_name)
                            return True
                        elif token_start <= pos < token_end:
                            # Cursor is inside a token - delete the entire token
                            self._delete_entire_validated_entry(token_start, token_end, display_name)
                            return True

                return False  # Allow normal deletion

            def _delete_entire_validated_entry(self, start, end, display_name):
                """Delete the entire validated entry including surrounding punctuation."""
                # Temporarily disconnect text change signal to prevent recursion
                self.textChanged.disconnect(self.parent_dialog._on_text_changed)

                try:
                    text = self.toPlainText()

                    # Find the actual position of the display name in current text
                    actual_start = text.find(display_name)
                    if actual_start == -1:
                        return  # Name not found, already deleted?

                    actual_end = actual_start + len(display_name)
                    delete_start = actual_start
                    delete_end = actual_end

                    # Check for semicolon and space after
                    if delete_end < len(text) and text[delete_end:delete_end+2] == '; ':
                        delete_end += 2
                    # Check for semicolon and space before (if no semicolon after)
                    elif delete_start > 1 and text[delete_start-2:delete_start] == '; ':
                        delete_start -= 2
                    # Handle case where it's the first item followed by a semicolon
                    elif delete_start == 0 and delete_end < len(text) and text[delete_end:delete_end+2] == '; ':
                        delete_end += 2

                    # Remove the entry
                    cursor = self.textCursor()
                    cursor.setPosition(delete_start)
                    cursor.setPosition(delete_end, QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()

                    # Position cursor at the deletion point
                    cursor.setPosition(delete_start)
                    self.setTextCursor(cursor)

                    # Remove from validated names and ranges, then recalculate all ranges
                    self.parent_dialog._remove_validated_entry(display_name)
                    self.parent_dialog._recalculate_validated_ranges()

                finally:
                    # Reconnect the signal
                    self.textChanged.connect(self.parent_dialog._on_text_changed)

            def _is_in_protected_range(self, pos):
                """Check if position is within a protected range."""
                for start, end, _ in self.parent_dialog.validated_ranges:
                    if start <= pos < end:
                        return True
                return False

            def _show_context_menu(self, position):
                """Show context menu for validated entries."""
                from PyQt5.QtWidgets import QMenu, QAction

                try:
                    # Get the cursor position at the click location
                    click_cursor = self.cursorForPosition(position)
                    click_pos = click_cursor.position()

                    logger.debug(f"Context menu requested at position {click_pos}, ranges: {self.parent_dialog.validated_ranges}")

                    # Check if we have a selected token or we're clicking on a validated range
                    validated_entry = None
                    entry_start = entry_end = 0

                    cursor = self.textCursor()
                    if cursor.hasSelection():
                        # Check if the selection matches a token
                        start = cursor.selectionStart()
                        end = cursor.selectionEnd()
                        for token_start, token_end, display_name in self.parent_dialog.validated_ranges:
                            if start == token_start and end == token_end:
                                validated_entry = display_name
                                entry_start, entry_end = start, end
                                break
                    else:
                        # Check if we're clicking on a validated range
                        for start, end, display_name in self.parent_dialog.validated_ranges:
                            if start <= click_pos < end:
                                validated_entry = display_name
                                entry_start, entry_end = start, end
                                logger.debug(f"Found validated entry: {validated_entry}")
                                break

                    if validated_entry:
                        menu = QMenu(self)
                        delete_action = QAction(f"Remove '{validated_entry}'", self)
                        delete_action.triggered.connect(lambda: self._delete_entire_validated_entry(entry_start, entry_end, validated_entry))
                        menu.addAction(delete_action)

                        # Show context menu at the clicked position
                        menu.exec_(self.mapToGlobal(position))
                    else:
                        logger.debug("No validated entry found, showing standard menu")
                        # Show default context menu for non-validated text
                        menu = self.createStandardContextMenu()
                        menu.exec_(self.mapToGlobal(position))

                except Exception as e:
                    logger.error(f"Error in context menu: {e}")

        # Create a custom QTextEdit for token-based input that looks like the original
        self.search_input = TokenTextEdit(self)
        self.search_input.setMaximumHeight(80)  # Approximately 4 lines
        self.search_input.setPlaceholderText(self.i18n.get_string("search_dialog.names_placeholder"))

        # List to track validated tokens
        self.validated_tokens = []

        # Initialize validated ranges and names
        self.validated_ranges = []
        self.validated_names = {}

        # Button layout (vertical alignment to top)
        button_layout = QVBoxLayout()
        self.check_names_btn = QPushButton(self.i18n.get_string("search_dialog.check_names_button"))
        self.check_names_btn.clicked.connect(self._check_names)
        button_layout.addWidget(self.check_names_btn)
        button_layout.addStretch()

        search_input_layout.addWidget(self.search_input)
        search_input_layout.addLayout(button_layout)
        layout.addLayout(search_input_layout)

        # Advanced button
        advanced_layout = QHBoxLayout()
        self.advanced_btn = QPushButton(self.i18n.get_string("search_dialog.advanced_button"))
        self.advanced_btn.clicked.connect(self._open_advanced_search)
        advanced_layout.addWidget(self.advanced_btn)
        advanced_layout.addStretch()
        layout.addLayout(advanced_layout)

        # Spacer before buttons
        layout.addStretch()

        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._accept_dialog)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def _discover_object_types(self):
        """Discover which object types are available in the schema."""
        try:
            from samba_backend import BASE_DN
            import ldap

            # Get the schema naming context
            schema_dn = None
            try:
                res = self.samba_conn.search_s('', ldap.SCOPE_BASE, '(objectClass=*)', ['schemaNamingContext'])
                if res and res[0][1].get('schemaNamingContext'):
                    schema_dn = res[0][1]['schemaNamingContext'][0].decode('utf-8')
            except:
                pass

            if not schema_dn:
                # Fallback to common schema DN pattern
                base_parts = BASE_DN.split(',')
                schema_dn = 'CN=Schema,CN=Configuration,' + ','.join(base_parts)

            # Query for object classes
            available_classes = set()
            try:
                search_filter = '(objectClass=classSchema)'
                attrs = ['cn', 'lDAPDisplayName']
                res = self.samba_conn.search_s(schema_dn, ldap.SCOPE_SUBTREE, search_filter, attrs)

                for dn, attrs_dict in res:
                    if attrs_dict:
                        cn = self._get_first_attr(attrs_dict, 'cn').lower()
                        ldap_name = self._get_first_attr(attrs_dict, 'lDAPDisplayName').lower()
                        available_classes.add(cn)
                        available_classes.add(ldap_name)

            except Exception as e:
                logger.warning(f"Could not query schema: {e}")
                # Add common classes as fallback
                available_classes.update(['user', 'group', 'computer', 'contact', 'inetorgperson', 'organizationalperson'])

            # Filter available types based on schema
            self.available_object_types = {}
            for obj_type, config in self.all_possible_types.items():
                object_class = config.get('objectClass', '').lower()
                if object_class in available_classes or obj_type in ['user', 'group', 'computer', 'contact']:  # Always include basic types
                    self.available_object_types[obj_type] = config

            # Update the object type display
            self._update_object_type_display()

        except Exception as e:
            logger.error(f"Error discovering object types: {e}")
            # Fallback to basic types
            basic_types = ['user', 'group', 'computer', 'contact']
            self.available_object_types = {k: v for k, v in self.all_possible_types.items() if k in basic_types}
            self._update_object_type_display()

    def _update_object_type_display(self):
        """Update the object type display text."""
        selected_types = [config['label'] for obj_type, config in self.available_object_types.items() if config.get('default_selected', False)]
        if selected_types:
            self.object_type_display.setText('; '.join(selected_types))
        else:
            self.object_type_display.setText(self.i18n.get_string("search_dialog.no_types_selected"))

        # Update title
        self._update_title()

    def _update_title(self):
        """Update the dialog title based on selected object types."""
        selected_types = [config['label'] for obj_type, config in self.available_object_types.items() if config.get('default_selected', False)]
        if selected_types:
            title = self.i18n.get_string("search_dialog.select_title_format").format(', '.join(selected_types))
        else:
            title = self.i18n.get_string("search_dialog.select_objects_title")
        self.setWindowTitle(title)

    def _update_location_display(self):
        """Update the location display text."""
        try:
            # Extract a readable name from the DN
            if self.current_location_dn:
                # Parse the DN to get a readable location name
                parts = self.current_location_dn.split(',')
                dc_parts = []
                ou_parts = []
                cn_parts = []

                for part in parts:
                    if part.strip().startswith('DC='):
                        dc_parts.append(part.strip()[3:])  # Remove 'DC=' prefix
                    elif part.strip().startswith('CN='):
                        cn_parts.append(part.strip()[3:])  # Remove 'CN=' prefix  
                    elif part.strip().startswith('OU='):
                        ou_parts.append(part.strip()[3:])  # Remove 'OU=' prefix

                # Build location text with proper formatting
                location_parts = []

                # Add domain first (most general)
                if dc_parts:
                    domain = '.'.join(dc_parts)  # DC parts in original order for proper domain format
                    location_parts.append(domain)

                # Then add CNs and OUs (most specific last)
                if cn_parts:
                    location_parts.extend(reversed(cn_parts))
                if ou_parts:
                    location_parts.extend(reversed(ou_parts))

                if location_parts:
                    location_text = '/'.join(location_parts)  # No spaces around slashes
                else:
                    location_text = self.current_location_dn
            else:
                location_text = self.i18n.get_string("search_dialog.entire_directory")

            self.location_display.setText(location_text)
        except Exception as e:
            logger.warning(f"Error updating location display: {e}")
            self.location_display.setText(self.current_location_dn or "")

    def _select_object_types(self):
        """Open dialog to select object types."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(self.i18n.get_string("search_dialog.select_object_types_title"))
        dialog.resize(300, 400)

        layout = QVBoxLayout()

        checkboxes = {}
        for obj_type, config in self.available_object_types.items():
            checkbox = QCheckBox(config['label'])
            checkbox.setChecked(config.get('default_selected', False))
            checkboxes[obj_type] = checkbox
            layout.addWidget(checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            # Update selected types
            for obj_type, checkbox in checkboxes.items():
                self.available_object_types[obj_type]['default_selected'] = checkbox.isChecked()

            self._update_object_type_display()

    def _select_locations(self):
        """Open dialog to select search location."""
        dialog = ADTreeBrowserDialog(self.samba_conn, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_dn = dialog.get_selected_dn()
            if selected_dn:
                self.current_location_dn = selected_dn
                self._update_location_display()

    def _on_text_changed(self):
        """Handle text changes in search input to clear formatting."""
        # Temporarily disconnect to avoid recursion
        self.search_input.textChanged.disconnect(self._on_text_changed)

        try:
            # Clear validation state when text changes
            cursor = self.search_input.textCursor()
            current_pos = cursor.position()

            # Check if we're in a protected range (validated name)
            in_protected_range = False
            for start, end, _ in self.validated_ranges:
                if start <= current_pos <= end:
                    in_protected_range = True
                    break

            if not in_protected_range:
                # Clear all formatting for new text
                text = self.search_input.toPlainText()
                self.search_input.clear()
                self.search_input.insertPlainText(text)
                # Reset validated data
                self.validated_names.clear()
                self.validated_ranges.clear()
        finally:
            # Reconnect the signal
            self.search_input.textChanged.connect(self._on_text_changed)

    def _check_names(self):
        """Check and validate the entered names."""
        # Get the plain text content
        text = self.search_input.toPlainText().strip()
        if not text:
            return

        # Extract only unvalidated text (text that's not in blue formatting)
        unvalidated_text = self._extract_unvalidated_text()
        if not unvalidated_text:
            return

        # Store current validated tokens before processing
        current_validated = dict(self.validated_names)

        # Split by semicolons and process each name
        names = [name.strip() for name in unvalidated_text.split(';') if name.strip()]

        # Process each new name
        for name in names:
            # Skip names that are already validated
            if not self._is_name_already_validated(name):
                self._resolve_name_to_token(name)

        # After processing, clean up the text to remove unvalidated portions
        self._cleanup_text_after_validation()

    def _extract_unvalidated_text(self):
        """Extract text that hasn't been validated yet."""
        full_text = self.search_input.toPlainText()

        # Remove validated tokens from the text to get only new input
        for start, end, display_name in self.validated_ranges:
            # Replace validated names and their semicolons with empty space
            token_text = display_name + "; "
            full_text = full_text.replace(token_text, "", 1)

        return full_text.strip()

    def _cleanup_text_after_validation(self):
        """Clean up the text by removing unvalidated portions and rebuilding tokens."""
        # Clear the entire text edit
        self.search_input.clear()

        # Clear validated ranges (will be rebuilt)
        self.validated_ranges.clear()

        # Re-add only validated tokens
        for display_name, match_object in self.validated_names.items():
            self.search_input.insertTokenWidget(display_name, match_object)

    def _resolve_name_to_token(self, name):
        """Resolve a name and create a validated token."""
        try:
            matches = self._search_for_name(name)

            if not matches:
                # No matches found
                QMessageBox.warning(self, self.i18n.get_string("search_dialog.name_not_found_title"), 
                                  self.i18n.get_string("search_dialog.name_not_found_message").format(name))
                return

            if len(matches) == 1:
                # Single match - auto-create token
                match = matches[0]
                display_name = self._get_display_name(match)
                self._create_validated_token(display_name, match)
            else:
                # Multiple matches - show picker
                selected_items = self._show_multiple_matches_dialog(name, matches)
                if selected_items:
                    # Create tokens for all selected items
                    for selected in selected_items:
                        display_name = self._get_display_name(selected)
                        self._create_validated_token(display_name, selected)

        except Exception as e:
            logger.error(f"Error resolving name '{name}': {e}")
            QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                               self.i18n.get_string("search_dialog.error_message").format(str(e)))

    def _create_validated_token(self, display_name, match_object):
        """Create a new validated token in the text edit."""
        # Debug logging
        logger.debug(f"_create_validated_token: display_name='{display_name}', match_object type={type(match_object)}")
        logger.debug(f"match_object content: {match_object}")

        # Add to TokenTextEdit
        self.search_input.insertTokenWidget(display_name, match_object)

        # Update validated_names for compatibility
        self.validated_names[display_name] = match_object

    def remove_validated_token(self, token):
        """Remove a validated token from the dialog."""
        if token in self.validated_tokens:
            self.validated_tokens.remove(token)
            self.search_layout.removeWidget(token)
            token.deleteLater()

            # Remove from validated_names
            if token.display_name in self.validated_names:
                del self.validated_names[token.display_name]

    def _is_name_already_validated(self, name):
        """Check if a name is already validated by checking validated_ranges."""
        for start, end, display_name in self.validated_ranges:
            if display_name == name:
                return True
        return False

    def _remove_token_by_name(self, display_name):
        """Remove a token by display name."""
        # Find and remove from validated_ranges
        self.validated_ranges = [(s, e, n) for s, e, n in self.validated_ranges if n != display_name]

        # Remove from validated_names
        if display_name in self.validated_names:
            del self.validated_names[display_name]

        # Remove from text and reformat
        self._refresh_tokens()

    def _refresh_tokens(self):
        """Refresh the text display by rebuilding all tokens."""
        # Clear the text edit
        self.search_input.clear()
        self.validated_ranges.clear()

        # Re-add all validated tokens
        for display_name, match_object in self.validated_names.items():
            self.search_input.insertTokenWidget(display_name, match_object)

    def get_selected_objects(self):
        """Return the selected LDAP objects for the calling dialog."""
        logger.debug(f"get_selected_objects called. validated_names has {len(self.validated_names)} entries")

        # Debug what's actually in validated_names
        for display_name, match_object in self.validated_names.items():
            logger.debug(f"validated_names['{display_name}'] = type={type(match_object)}, value={match_object}")

        objects = []

        for display_name, match_object in self.validated_names.items():
            # Ensure the object has the required keys for group_properties.py
            if isinstance(match_object, dict):
                # Add display_text if it doesn't exist
                if 'display_text' not in match_object:
                    match_object['display_text'] = display_name
                objects.append(match_object)
            else:
                logger.error(f"match_object is not a dict: type={type(match_object)}, value={match_object}")

        # Debug logging
        logger.debug(f"get_selected_objects returning {len(objects)} objects")
        for i, obj in enumerate(objects):
            logger.debug(f"Object {i}: type={type(obj)}, has_dn={'dn' in obj if isinstance(obj, dict) else 'NOT_DICT'}, has_display_text={'display_text' in obj if isinstance(obj, dict) else 'NOT_DICT'}")

        return objects

    def _resolve_name_with_position(self, name, position):
        """Resolve a name at a specific position and update display with validation."""
        try:
            matches = self._search_for_name(name)

            if not matches:
                # No matches found
                QMessageBox.warning(self, self.i18n.get_string("search_dialog.name_not_found_title"), 
                                  self.i18n.get_string("search_dialog.name_not_found_message").format(name))
                return

            if len(matches) == 1:
                # Single match - auto-select
                match = matches[0]
                display_name = self._get_display_name(match)
                self._replace_name_with_display_at_position(name, display_name, position)
                self.validated_names[display_name] = match
            else:
                # Multiple matches - show picker
                selected_items = self._show_multiple_matches_dialog(name, matches)
                if selected_items:
                    # Handle multiple selected items - replace the original name with all selections
                    for i, selected in enumerate(selected_items):
                        display_name = self._get_display_name(selected)
                        if i == 0:
                            # Replace the original name with the first selection
                            self._replace_name_with_display_at_position(name, display_name, position)
                            self.validated_names[display_name] = selected
                        else:
                            # Add additional selections at the end
                            text = self.search_input.toPlainText()
                            self.search_input.setPlainText(text + display_name + "; ")

                            # Apply blue formatting to the newly added name
                            start_pos = len(text)
                            cursor = self.search_input.textCursor()
                            cursor.setPosition(start_pos)
                            cursor.setPosition(start_pos + len(display_name), QTextCursor.KeepAnchor)

                            blue_format = QTextCharFormat()
                            blue_format.setForeground(QColor(0, 0, 255))
                            blue_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)
                            cursor.setCharFormat(blue_format)

                            # Track this as a validated range
                            self.validated_ranges.append((start_pos, start_pos + len(display_name), display_name))
                            self.validated_names[display_name] = selected

        except Exception as e:
            logger.error(f"Error resolving name '{name}': {e}")
            QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                               self.i18n.get_string("search_dialog.error_message").format(str(e)))

    def _resolve_name_with_display(self, name):
        """Resolve a name and update display with validation."""
        try:
            matches = self._search_for_name(name)

            if not matches:
                # No matches found
                QMessageBox.warning(self, self.i18n.get_string("search_dialog.name_not_found_title"), 
                                  self.i18n.get_string("search_dialog.name_not_found_message").format(name))
                return

            if len(matches) == 1:
                # Single match - auto-select
                match = matches[0]
                display_name = self._get_display_name(match)
                self._replace_name_with_display(name, display_name)
                self.validated_names[display_name] = match
            else:
                # Multiple matches - show picker
                selected_items = self._show_multiple_matches_dialog(name, matches)
                if selected_items:
                    # Handle multiple selected items - replace the original name with all selections
                    for i, selected in enumerate(selected_items):
                        display_name = self._get_display_name(selected)
                        if i == 0:
                            # Replace the original name with the first selection
                            self._replace_name_with_display(name, display_name)
                            self.validated_names[display_name] = selected
                        else:
                            # Add additional selections at the end
                            text = self.search_input.toPlainText()
                            self.search_input.setPlainText(text + display_name + "; ")

                            # Apply blue formatting to the newly added name
                            start_pos = len(text)
                            cursor = self.search_input.textCursor()
                            cursor.setPosition(start_pos)
                            cursor.setPosition(start_pos + len(display_name), QTextCursor.KeepAnchor)

                            blue_format = QTextCharFormat()
                            blue_format.setForeground(QColor(0, 0, 255))
                            blue_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)
                            cursor.setCharFormat(blue_format)

                            # Track this as a validated range
                            self.validated_ranges.append((start_pos, start_pos + len(display_name), display_name))
                            self.validated_names[display_name] = selected

        except Exception as e:
            logger.error(f"Error resolving name '{name}': {e}")
            QMessageBox.critical(self, self.i18n.get_string("search_dialog.error_title"), 
                               self.i18n.get_string("search_dialog.resolve_error").format(name, str(e)))

    def _search_for_name(self, name):
        """Search for objects matching the given name."""
        try:
            from samba_backend import BASE_DN
            import ldap

            # Build search filter based on selected object types
            object_class_filters = []
            selected_types = []
            for obj_type, config in self.available_object_types.items():
                if config.get('default_selected', False):
                    selected_types.append(obj_type)
                    obj_class = config['objectClass']
                    if config.get('filter_type') == 'service_account':
                        # Special handling for service accounts
                        object_class_filters.append(f'(&(objectClass={obj_class})(servicePrincipalName=*))')
                    else:
                        object_class_filters.append(f'(objectClass={obj_class})')

            logger.debug(f"Selected object types: {selected_types}")
            logger.debug(f"Available object types: {list(self.available_object_types.keys())}")

            if not object_class_filters:
                logger.warning("No object types selected for search - using default user search")
                # Fallback to basic user search
                object_class_filter = '(objectClass=user)'
            else:
                object_class_filter = '(|' + ''.join(object_class_filters) + ')'

            # Build name search filters - use wildcards for partial matching
            name_filters = [
                f'(sAMAccountName=*{name}*)',
                f'(cn=*{name}*)',
                f'(displayName=*{name}*)',
                f'(givenName=*{name}*)',
                f'(sn=*{name}*)'
            ]

            search_filter = f'(&{object_class_filter}(|{"".join(name_filters)}))'            
            logger.debug(f"Search filter: {search_filter}")

            attrs = ['cn', 'sAMAccountName', 'displayName', 'objectClass', 'distinguishedName', 'description', 'givenName', 'sn']

            search_dn = self.current_location_dn or BASE_DN
            logger.debug(f"Searching in: {search_dn}")
            res = self.samba_conn.search_s(search_dn, ldap.SCOPE_SUBTREE, search_filter, attrs)

            matches = []
            for dn, attrs_dict in res:
                if attrs_dict and isinstance(attrs_dict, dict):

                    match_obj = {
                        'dn': dn,
                        'cn': self._get_first_attr(attrs_dict, 'cn'),
                        'sAMAccountName': self._get_first_attr(attrs_dict, 'sAMAccountName'),
                        'displayName': self._get_first_attr(attrs_dict, 'displayName'),
                        'description': self._get_first_attr(attrs_dict, 'description'),
                        'objectClass': [self._decode_attr(cls) for cls in attrs_dict.get('objectClass', [])]
                    }
                    matches.append(match_obj)

            return matches

        except Exception as e:
            logger.error(f"Search error for name '{name}': {e}")
            return []

    def _decode_attr(self, attr_value):
        """Safely decode LDAP attribute value."""
        if isinstance(attr_value, bytes):
            return attr_value.decode('utf-8', errors='replace')
        return str(attr_value) if attr_value else ''

    def _get_first_attr(self, attrs_dict, attr_name):
        """Safely get the first value of an LDAP attribute."""
        attr_list = attrs_dict.get(attr_name, [])
        if attr_list and len(attr_list) > 0:
            return self._decode_attr(attr_list[0])
        return ''

    def _get_display_name(self, match_obj):
        """Get the best display name for an object."""
        display_name = match_obj.get('displayName') or match_obj.get('cn') or match_obj.get('sAMAccountName', '')
        return display_name.strip() if display_name else 'Unknown'

    def _show_multiple_matches_dialog(self, original_name, matches):
        """Show dialog to pick from multiple matches."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(self.i18n.get_string("search_dialog.multiple_matches_title"))
        dialog.resize(500, 300)

        layout = QVBoxLayout()

        label = QLabel(self.i18n.get_string("search_dialog.multiple_matches_message").format(original_name))
        layout.addWidget(label)

        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Allow multiple selections

        for match in matches:
            display_name = self._get_display_name(match)
            sam_account = match.get('sAMAccountName', '')
            obj_type = self._get_object_type_display(match['objectClass'])

            item_text = display_name
            if sam_account and sam_account != display_name:
                item_text += f" ({sam_account})"
            item_text += f" [{obj_type}]"

            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, match)
            list_widget.addItem(item)

        # Connect double-click to accept dialog
        list_widget.itemDoubleClicked.connect(dialog.accept)

        layout.addWidget(list_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        # Enable OK only when selection is made
        button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        list_widget.itemSelectionChanged.connect(
            lambda: button_box.button(QDialogButtonBox.Ok).setEnabled(len(list_widget.selectedItems()) > 0)
        )

        layout.addWidget(button_box)
        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted and list_widget.selectedItems():
            # Return all selected items
            return [item.data(Qt.UserRole) for item in list_widget.selectedItems()]

        return None

    def _get_object_type_display(self, object_classes):
        """Get display name for object type from object classes."""
        if 'user' in object_classes:
            return self.i18n.get_string('object_type.user')
        elif 'group' in object_classes:
            return self.i18n.get_string('object_type.group')
        elif 'computer' in object_classes:
            return self.i18n.get_string('object_type.computer')
        elif 'contact' in object_classes:
            return self.i18n.get_string('object_type.contact')
        else:
            return self.i18n.get_string('object_type.object')

    def _replace_name_with_display(self, original_name, display_name):
        """Replace the original name with validated display name and apply blue formatting."""
        # Find the position first
        text = self.search_input.toPlainText()
        start_pos = text.find(original_name)
        if start_pos == -1:
            return

        # Use the position-based method for consistency
        self._replace_name_with_display_at_position(original_name, display_name, start_pos)

    def _replace_name_with_display_at_position(self, original_name, display_name, position):
        """Replace the original name at specific position with validated display name and apply blue formatting."""
        # Temporarily disconnect text change signal to prevent recursion
        self.search_input.textChanged.disconnect(self._on_text_changed)

        try:
            # Use cursor-based replacement instead of selectAll to preserve formatting
            cursor = self.search_input.textCursor()

            # Select the original name at the specific position
            cursor.setPosition(position)
            cursor.setPosition(position + len(original_name), QTextCursor.KeepAnchor)

            # Always add semicolon after display name for proper separation
            display_with_semicolon = display_name + "; "

            # Replace the selected text
            cursor.insertText(display_with_semicolon)

            # Now apply blue formatting to just the display name part
            cursor.setPosition(position)
            cursor.setPosition(position + len(display_name), QTextCursor.KeepAnchor)

            # Create blue format
            blue_format = QTextCharFormat()
            blue_format.setForeground(QColor(0, 0, 255))  # Blue color
            blue_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)

            cursor.setCharFormat(blue_format)

            # Track this as a validated range (only the display name, not semicolon)
            self.validated_ranges.append((position, position + len(display_name), display_name))

        finally:
            # Reconnect the signal
            self.search_input.textChanged.connect(self._on_text_changed)

    def _remove_validated_entry(self, display_name):
        """Remove a validated entry from tracking."""
        # Remove from validated_names (find by display name in values)
        keys_to_remove = []
        for key, match_obj in self.validated_names.items():
            if self._get_display_name(match_obj) == display_name:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.validated_names[key]

        # Remove from validated_ranges
        self.validated_ranges = [
            (start, end, name) for start, end, name in self.validated_ranges 
            if name != display_name
        ]

    def _recalculate_validated_ranges(self):
        """Recalculate all validated ranges after text changes."""
        text = self.search_input.toPlainText()
        new_ranges = []

        for display_name in self.validated_names.keys():
            # Find the display name in the current text
            start_pos = text.find(display_name)
            if start_pos != -1:
                end_pos = start_pos + len(display_name)
                new_ranges.append((start_pos, end_pos, display_name))

                # Reapply blue formatting
                cursor = self.search_input.textCursor()
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                blue_format = QTextCharFormat()
                blue_format.setForeground(QColor(0, 0, 255))
                blue_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)
                cursor.setCharFormat(blue_format)

        self.validated_ranges = new_ranges

    def _is_name_already_validated(self, name):
        """Check if a name is already validated by checking validated_names and validated_ranges."""
        # Check if the name is already a validated display name
        if name in self.validated_names:
            return True

        # Check if the name is in any validated range
        for _, _, display_name in self.validated_ranges:
            if name == display_name:
                return True

        return False

    def _open_advanced_search(self):
        """Open advanced search dialog."""
        # Get selected object types for the advanced search
        selected_types = [obj_type for obj_type, config in self.available_object_types.items() if config.get('default_selected', False)]

        if not selected_types:
            QMessageBox.information(self, self.i18n.get_string("search_dialog.no_types_title"), 
                                   self.i18n.get_string("search_dialog.no_types_message"))
            return

        # Use PrincipalPickerDialog for advanced search
        dialog = PrincipalPickerDialog(self.samba_conn, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_obj = dialog.get_selected_object()
            if selected_obj:
                display_name = self._get_display_name(selected_obj)
                current_text = self.search_input.toPlainText().strip()

                if current_text:
                    new_text = current_text + "; " + display_name
                else:
                    new_text = display_name

                self.search_input.setPlainText(new_text)
                # Mark this name as validated
                self.validated_names[display_name] = selected_obj

    def _accept_dialog(self):
        """Accept the dialog and prepare selected objects."""
        self.selected_objects = []

        # Get all validated names - store the full LDAP objects, not just DNs
        for original_name, match_obj in self.validated_names.items():
            # Add display_text if it doesn't exist
            if 'display_text' not in match_obj:
                match_obj['display_text'] = original_name
            self.selected_objects.append(match_obj)  # Store full object, not just DN

        if not self.selected_objects:
            QMessageBox.warning(self, self.i18n.get_string("search_dialog.no_selection_title"), 
                               self.i18n.get_string("search_dialog.no_selection_message"))
            return

        self.accept()

    def get_selected_objects(self):
        """Return the list of selected object DNs."""
        return self.selected_objects


class ADTreeBrowserDialog(QDialog):
    """Tree-based browser for Active Directory locations using the existing AD tree model."""

    def __init__(self, samba_conn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.i18n = I18nManager()
        self.selected_dn = None

        self.setWindowTitle(self.i18n.get_string("search_dialog.select_location_title"))
        self.setModal(True)
        self.resize(500, 600)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel(self.i18n.get_string("search_dialog.select_location_instruction"))
        layout.addWidget(label)

        # Tree view with AD model
        from ad_tree_model import ADTreeModel
        from PyQt5.QtWidgets import QTreeView

        self.tree_view = QTreeView()

        # Set up the AD tree model - we need a connected_server parameter
        # For location browsing, we can use None or get it from samba_conn
        connected_server = getattr(self.samba_conn, 'host', None) or 'localhost'
        self.ad_model = ADTreeModel(self.samba_conn, connected_server, advanced_view=False)
        self.tree_view.setModel(self.ad_model)

        # Configure tree view
        self.tree_view.setRootIsDecorated(True)
        self.tree_view.setAlternatingRowColors(True)

        # Connect signals
        selection_model = self.tree_view.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed)

        self.tree_view.doubleClicked.connect(self.accept)

        # Expand to domain level and one level deeper
        from PyQt5.QtCore import QModelIndex
        root_index = self.ad_model.index(0, 0, QModelIndex())
        if root_index.isValid():
            self.tree_view.expand(root_index)
            # Expand first level children as well
            child_count = self.ad_model.rowCount(root_index)
            for i in range(min(child_count, 5)):  # Limit to first 5 children
                child_index = self.ad_model.index(i, 0, root_index)
                if child_index.isValid():
                    self.tree_view.expand(child_index)

        layout.addWidget(self.tree_view)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_selection_changed(self, selected, deselected):
        """Handle tree selection changes."""
        indexes = selected.indexes()
        if indexes:
            index = indexes[0]
            # Get the ADTreeItem from the model index
            item = index.internalPointer()
            if item and item.dn():
                self.selected_dn = item.dn()
                self.ok_button.setEnabled(True)
            else:
                self.selected_dn = None
                self.ok_button.setEnabled(False)
        else:
            self.selected_dn = None
            self.ok_button.setEnabled(False)

    def get_selected_dn(self):
        """Return the selected DN."""
        return self.selected_dn
