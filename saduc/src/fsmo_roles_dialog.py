# Operations Masters Dialog
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QPushButton, QMessageBox, QGroupBox, QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
from i18n_manager import I18nManager
from samba_backend import get_fsmo_role_holders, transfer_fsmo_role, seize_fsmo_role
import os

class FSMORolesDialog(QDialog):
    """Operations Masters dialog for managing all five FSMO roles."""

    def __init__(self, parent=None, samba_conn=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.samba_conn = samba_conn
        self.parent_window = parent

        # Get current DC name from connection
        self.current_dc = self._get_current_dc_name()
        self.roles_info = {}

        self.setWindowTitle(self.i18n.get_string("dialog.operations_masters.title"))
        self.setModal(True)
        self.setFixedSize(600, 500)

        self._setup_ui()
        self._load_fsmo_roles()

    def _get_current_dc_name(self):
        """Extract DC name from current connection."""
        try:
            # Get server name from connection URI
            if hasattr(self.samba_conn, '_uri'):
                uri = self.samba_conn._uri
                if '://' in uri:
                    server = uri.split('://')[1].split(':')[0]
                    return server.upper()

        except Exception:
            pass

        return "CURRENT-DC"

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header info
        header_label = QLabel(self.i18n.get_string("dialog.operations_masters.header"))
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        layout.addSpacing(15)

        # Roles display area
        roles_group = QGroupBox(self.i18n.get_string("dialog.operations_masters.roles_group"))
        roles_layout = QVBoxLayout(roles_group)

        # Create text area for displaying all roles
        self.roles_text = QTextEdit()
        self.roles_text.setReadOnly(True)
        self.roles_text.setMinimumHeight(300)

        # Set monospace font for better alignment
        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Courier", 10)
        self.roles_text.setFont(font)

        roles_layout.addWidget(self.roles_text)
        layout.addWidget(roles_group)

        layout.addSpacing(10)

        # Current server info
        current_server_layout = QHBoxLayout()
        current_server_layout.addWidget(QLabel(self.i18n.get_string("dialog.operations_masters.current_server")))

        self.current_server_label = QLabel(self.current_dc)
        font = QFont()
        font.setBold(True)
        self.current_server_label.setFont(font)
        current_server_layout.addWidget(self.current_server_label)
        current_server_layout.addStretch()

        layout.addLayout(current_server_layout)

        layout.addSpacing(10)

        # Buttons
        button_layout = QHBoxLayout()

        self.transfer_button = QPushButton(self.i18n.get_string("dialog.operations_masters.button.transfer"))
        self.transfer_button.clicked.connect(self._transfer_roles)

        self.seize_button = QPushButton(self.i18n.get_string("dialog.operations_masters.button.seize"))
        self.seize_button.clicked.connect(self._seize_roles)

        self.refresh_button = QPushButton(self.i18n.get_string("dialog.operations_masters.button.refresh"))
        self.refresh_button.clicked.connect(self._load_fsmo_roles)

        self.close_button = QPushButton(self.i18n.get_string("dialog.common.button.close"))
        self.close_button.clicked.connect(self.accept)

        button_layout.addWidget(self.transfer_button)
        button_layout.addWidget(self.seize_button)
        button_layout.addStretch()
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def _load_fsmo_roles(self):
        """Load FSMO role information from the domain."""
        try:
            success, roles_info = get_fsmo_role_holders(self.samba_conn)

            if not success:
                QMessageBox.critical(self, 
                    self.i18n.get_string("dialog.common.error.title"),
                    self.i18n.get_string("dialog.operations_masters.error.load_failed"))
                return

            self.roles_info = roles_info
            self._update_roles_display()

        except Exception as e:
            QMessageBox.critical(self, 
                self.i18n.get_string("dialog.common.error.title"),
                self.i18n.get_text("dialog.operations_masters.error.exception", str(e)))

    def _update_roles_display(self):
        """Update the roles display text area."""
        html_content = "<table border='0' cellpadding='8' cellspacing='0' width='100%'>"

        # Define all five FSMO roles
        fsmo_roles = [
            ("Schema Master", "Forest", "Controls schema modifications for the entire forest"),
            ("Domain Naming Master", "Forest", "Controls addition and removal of domains in the forest"), 
            ("PDC Emulator", "Domain", "Handles password changes, account lockouts, and time synchronization"),
            ("RID Master", "Domain", "Allocates RID pools to domain controllers for creating security principals"),
            ("Infrastructure Master", "Domain", "Updates cross-domain group and user references")
        ]

        for role_name, scope, description in fsmo_roles:
            holder = "Unknown"

            # Find the holder in our loaded data
            for key, value in self.roles_info.items():
                if role_name in key:
                    if isinstance(value, dict):
                        holder = value.get('holder', 'Unknown')
                    else:
                        holder = str(value)
                    break

            # Determine if role is held by current server
            is_current = (holder.upper() == self.current_dc.upper())
            holder_color = "#0066CC" if is_current else "#000000"

            html_content += f"""
            <tr>
                <td width='30%'><b>{role_name}</b></td>
                <td width='15%'><i>{scope}</i></td>
                <td width='35%' style='color: {holder_color}'><b>{holder}</b></td>
                <td width='20%'>{'✓ Current' if is_current else ''}</td>
            </tr>
            <tr>
                <td colspan='4' style='padding-left: 20px; color: #666666; font-size: 9pt;'>{description}</td>
            </tr>
            <tr><td colspan='4'>&nbsp;</td></tr>
            """

        html_content += "</table>"
        self.roles_text.setHtml(html_content)

    def _transfer_roles(self):
        """Transfer all roles to the current server."""
        # Count how many roles would be transferred
        transfer_count = 0
        roles_to_transfer = []

        for role_name, scope, description in [
            ("Schema Master", "Forest", "Controls schema modifications"),
            ("Domain Naming Master", "Forest", "Controls domain addition/removal"),
            ("PDC Emulator", "Domain", "Handles password changes"),
            ("RID Master", "Domain", "Allocates RID pools"),
            ("Infrastructure Master", "Domain", "Updates cross-domain references")
        ]:
            holder = "Unknown"
            for key, value in self.roles_info.items():
                if role_name in key:
                    if isinstance(value, dict):
                        holder = value.get('holder', 'Unknown')
                    else:
                        holder = str(value)
                    break

            if holder.upper() != self.current_dc.upper():
                transfer_count += 1
                roles_to_transfer.append(role_name)

        if transfer_count == 0:
            QMessageBox.information(self, 
                self.i18n.get_string("dialog.operations_masters.title"),
                self.i18n.get_string("dialog.operations_masters.all_roles_current"))
            return

        # Confirm the transfer
        reply = QMessageBox.question(self, 
            self.i18n.get_string("dialog.operations_masters.transfer_all.confirm.title"),
            self.i18n.get_text("dialog.operations_masters.transfer_all.confirm.text", 
                              str(transfer_count), self.current_dc),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        # Perform transfers
        success_count = 0
        failed_roles = []

        for role_name in roles_to_transfer:
            try:
                # Map display names to backend keys
                role_key = self._get_backend_role_key(role_name)
                success, message = transfer_fsmo_role(role_key, self.current_dc)

                if success:
                    success_count += 1
                else:
                    failed_roles.append(f"{role_name}: {message}")

            except Exception as e:
                failed_roles.append(f"{role_name}: {str(e)}")

        # Show results
        if success_count == transfer_count:
            QMessageBox.information(self, 
                self.i18n.get_string("dialog.common.success.title"),
                self.i18n.get_text("dialog.operations_masters.transfer_all.success", str(success_count)))
        else:
            error_msg = self.i18n.get_text("dialog.operations_masters.transfer_all.partial", 
                                          str(success_count), str(len(failed_roles)))
            if failed_roles:
                error_msg += "\n\n" + "\n".join(failed_roles)
            QMessageBox.warning(self, 
                self.i18n.get_string("dialog.operations_masters.title"),
                error_msg)

        # Refresh display
        self._load_fsmo_roles()

    def _seize_roles(self):
        """Seize all roles to the current server (emergency operation)."""
        # Show warning
        reply = QMessageBox.warning(self, 
            self.i18n.get_string("dialog.operations_masters.seize_all.warning.title"),
            self.i18n.get_text("dialog.operations_masters.seize_all.warning.text", self.current_dc),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        # Perform seizures for all roles
        role_names = ["Schema Master", "Domain Naming Master", "PDC Emulator", "RID Master", "Infrastructure Master"]
        success_count = 0
        failed_roles = []

        for role_name in role_names:
            try:
                role_key = self._get_backend_role_key(role_name)
                success, message = seize_fsmo_role(role_key, self.current_dc)

                if success:
                    success_count += 1
                else:
                    failed_roles.append(f"{role_name}: {message}")

            except Exception as e:
                failed_roles.append(f"{role_name}: {str(e)}")

        # Show results
        if success_count == len(role_names):
            QMessageBox.information(self, 
                self.i18n.get_string("dialog.common.success.title"),
                self.i18n.get_text("dialog.operations_masters.seize_all.success", str(success_count)))
        else:
            error_msg = self.i18n.get_text("dialog.operations_masters.seize_all.partial", 
                                          str(success_count), str(len(failed_roles)))
            if failed_roles:
                error_msg += "\n\n" + "\n".join(failed_roles)
            QMessageBox.warning(self, 
                self.i18n.get_string("dialog.operations_masters.title"),
                error_msg)

        # Refresh display
        self._load_fsmo_roles()

    def _get_backend_role_key(self, display_name):
        """Map display role names to backend keys."""
        role_map = {
            "Schema Master": "schema",
            "Domain Naming Master": "naming", 
            "PDC Emulator": "pdc",
            "RID Master": "rid",
            "Infrastructure Master": "infrastructure"
        }
        return role_map.get(display_name, display_name.lower().replace(" ", "_"))