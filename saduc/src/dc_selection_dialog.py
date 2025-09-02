import subprocess
import logging
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QListWidget, QListWidgetItem, QPushButton, 
                            QMessageBox, QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


class DCDiscoveryThread(QThread):
    """Thread to discover domain controllers without blocking the UI."""
    
    dc_found = pyqtSignal(str, str)  # (dc_name, dc_info)
    discovery_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, samba_conn):
        super().__init__()
        self.samba_conn = samba_conn
        self.logger = logging.getLogger(__name__)
    
    def run(self):
        """Discover domain controllers using samba-tool."""
        try:
            # Get domain controllers using samba-tool
            cmd = ['samba-tool', 'domain', 'info', '--json']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                try:
                    domain_info = json.loads(result.stdout)
                    # Extract DC information - this might need adjustment based on actual output
                    if 'domain_controllers' in domain_info:
                        for dc in domain_info['domain_controllers']:
                            dc_name = dc.get('name', 'Unknown')
                            dc_info = f"{dc.get('site', 'Default-First-Site-Name')} - {dc.get('roles', [])}"
                            self.dc_found.emit(dc_name, dc_info)
                except json.JSONDecodeError:
                    self.logger.error("Failed to parse domain info JSON")
            
            # Also try alternative method using samba-tool sites
            try:
                cmd = ['samba-tool', 'sites', 'listservers', '--json']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    try:
                        sites_info = json.loads(result.stdout)
                        for site_name, site_data in sites_info.items():
                            if 'servers' in site_data:
                                for server in site_data['servers']:
                                    server_name = server.get('name', 'Unknown')
                                    server_info = f"{site_name} - DC"
                                    self.dc_found.emit(server_name, server_info)
                    except json.JSONDecodeError:
                        pass
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                self.logger.warning(f"Alternative DC discovery failed: {e}")
            
            self.discovery_complete.emit()
            
        except subprocess.TimeoutExpired:
            self.error_occurred.emit("Timeout while discovering domain controllers")
        except Exception as e:
            self.error_occurred.emit(f"Error discovering domain controllers: {str(e)}")


class DCSelectionDialog(QDialog):
    """Dialog for selecting a domain controller to connect to."""
    
    def __init__(self, samba_conn, current_server, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.current_server = current_server
        self.selected_dc = None
        self.logger = logging.getLogger(__name__)
        self.i18n = getattr(parent, 'i18n', None)
        
        self.setWindowTitle(self._get_string("dialog.dc.selection.title", "Change Domain Controller"))
        self.setModal(True)
        self.resize(500, 400)
        
        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._start_discovery()
    
    def _get_string(self, key, default=""):
        """Get localized string with fallback to default."""
        if self.i18n:
            return self.i18n.get_string(key, default)
        return default
    
    def _create_widgets(self):
        """Create dialog widgets."""
        current_text = self._get_string("dialog.dc.selection.current", "Current Domain Controller: {0}")
        self.current_label = QLabel(current_text.format(self.current_server))
        
        self.instruction_label = QLabel(self._get_string("dialog.dc.selection.instruction", 
                                                       "Select a domain controller to connect to:"))
        
        self.dc_list = QListWidget()
        self.dc_list.setSelectionMode(QListWidget.SingleSelection)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        self.status_label = QLabel(self._get_string("dialog.dc.selection.discovering", 
                                                   "Discovering domain controllers..."))
        
        # Buttons
        self.ok_button = QPushButton(self._get_string("dialog.common.ok", "OK"))
        self.cancel_button = QPushButton(self._get_string("dialog.common.cancel", "Cancel"))
        self.refresh_button = QPushButton(self._get_string("dialog.dc.selection.refresh", "Refresh"))
        
        self.ok_button.setEnabled(False)
        self.ok_button.setDefault(True)
    
    def _create_layout(self):
        """Create dialog layout."""
        layout = QVBoxLayout(self)
        
        layout.addWidget(self.current_label)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self.dc_list)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
    
    def _connect_signals(self):
        """Connect widget signals."""
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.refresh_button.clicked.connect(self._refresh_dc_list)
        self.dc_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.dc_list.itemDoubleClicked.connect(self._on_item_double_clicked)
    
    def _start_discovery(self):
        """Start domain controller discovery."""
        self.discovery_thread = DCDiscoveryThread(self.samba_conn)
        self.discovery_thread.dc_found.connect(self._add_dc_to_list)
        self.discovery_thread.discovery_complete.connect(self._discovery_finished)
        self.discovery_thread.error_occurred.connect(self._discovery_error)
        self.discovery_thread.start()
    
    def _add_dc_to_list(self, dc_name, dc_info):
        """Add discovered DC to the list."""
        item = QListWidgetItem(f"{dc_name} - {dc_info}")
        item.setData(Qt.UserRole, dc_name)
        
        # Mark current server
        if dc_name.lower() == self.current_server.lower():
            item.setText(f"{dc_name} - {dc_info} (Current)")
            item.setSelected(True)
        
        self.dc_list.addItem(item)
    
    def _discovery_finished(self):
        """Handle discovery completion."""
        self.progress_bar.setVisible(False)
        
        if self.dc_list.count() == 0:
            self.status_label.setText(self._get_string("dialog.dc.selection.none_found", 
                                                     "No domain controllers found. You can still enter a DC name manually."))
            # Add manual entry option
            manual_item = QListWidgetItem(self._get_string("dialog.dc.selection.manual", "[Enter DC name manually]"))
            manual_item.setData(Qt.UserRole, "MANUAL_ENTRY")
            self.dc_list.addItem(manual_item)
        else:
            found_text = self._get_string("dialog.dc.selection.found", "Found {0} domain controllers")
            self.status_label.setText(found_text.format(self.dc_list.count()))
    
    def _discovery_error(self, error_message):
        """Handle discovery error."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {error_message}")
        self.logger.error(f"DC discovery error: {error_message}")
        
        # Add manual entry option
        manual_item = QListWidgetItem(self._get_string("dialog.dc.selection.manual", "[Enter DC name manually]"))
        manual_item.setData(Qt.UserRole, "MANUAL_ENTRY")
        self.dc_list.addItem(manual_item)
    
    def _refresh_dc_list(self):
        """Refresh the domain controller list."""
        self.dc_list.clear()
        self.progress_bar.setVisible(True)
        self.status_label.setText(self._get_string("dialog.dc.selection.discovering", 
                                                 "Discovering domain controllers..."))
        self.ok_button.setEnabled(False)
        self._start_discovery()
    
    def _on_selection_changed(self):
        """Handle list selection change."""
        selected_items = self.dc_list.selectedItems()
        self.ok_button.setEnabled(len(selected_items) > 0)
        
        if selected_items:
            item = selected_items[0]
            dc_name = item.data(Qt.UserRole)
            
            if dc_name == "MANUAL_ENTRY":
                # Handle manual entry
                from PyQt5.QtWidgets import QInputDialog
                dc_name, ok = QInputDialog.getText(self, 
                                                 self._get_string("dialog.dc.selection.manual.title", "Enter Domain Controller"),
                                                 self._get_string("dialog.dc.selection.manual.prompt", "Domain Controller name or IP:"))
                if ok and dc_name.strip():
                    self.selected_dc = dc_name.strip()
                else:
                    self.dc_list.clearSelection()
                    self.ok_button.setEnabled(False)
            else:
                self.selected_dc = dc_name
    
    def _on_item_double_clicked(self, item):
        """Handle double-click on list item."""
        if self.ok_button.isEnabled():
            self.accept()
    
    def get_selected_dc(self):
        """Get the selected domain controller."""
        return self.selected_dc