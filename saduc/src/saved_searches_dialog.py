"""
Saved Searches Dialog

Manages saved LDAP search queries for SADUC.
"""

import logging
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon

from i18n_manager import I18nManager
from sagui_config import config_manager


class SavedSearchesDialog(QDialog):
    """Dialog for managing saved LDAP searches"""
    
    # Signal emitted when a search should be executed
    execute_search = pyqtSignal(dict)  # search_data
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.i18n = I18nManager()
        
        self.setWindowTitle('Saved Searches')
        self.setModal(True)
        self.resize(800, 600)
        
        # Set dialog icon
        from icon_utils import set_window_icon
        set_window_icon(self, use_search_icon=True)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the basic user interface"""
        layout = QVBoxLayout(self)
        
        # Search list
        self.search_list = QListWidget()
        layout.addWidget(self.search_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)
        
        self.execute_button = QPushButton('Execute')
        self.execute_button.setDefault(True)
        button_layout.addWidget(self.execute_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton('Close')
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
        
        # Connect signals
        self.execute_button.clicked.connect(self.execute_selected_search)
        self.search_list.itemDoubleClicked.connect(self.execute_selected_search)
        self.search_list.currentItemChanged.connect(self.on_selection_changed)
        
        self.load_searches()
    
    def load_searches(self):
        """Load saved searches into the list"""
        try:
            searches = config_manager.list_saved_searches()
            for search_meta in searches:
                self.search_list.addItem(search_meta['name'])
            
            # Enable/disable execute button based on selection
            self.execute_button.setEnabled(len(searches) > 0)
            if searches:
                self.search_list.setCurrentRow(0)
                
        except Exception as e:
            self.logger.error(f"Failed to load searches: {e}")
            self.execute_button.setEnabled(False)
    
    def on_selection_changed(self, current, previous):
        """Handle selection changes in the search list"""
        self.execute_button.setEnabled(current is not None)
    
    def execute_selected_search(self):
        """Execute the currently selected search"""
        current_item = self.search_list.currentItem()
        if not current_item:
            return
        
        search_name = current_item.text()
        
        try:
            search_data = config_manager.load_search(search_name)
            if search_data:
                # Emit signal to parent to execute the search
                self.execute_search.emit(search_data)
                self.accept()  # Close the dialog
            else:
                self.logger.error(f"Failed to load search data for '{search_name}'")
                
        except Exception as e:
            self.logger.error(f"Error executing search '{search_name}': {e}")