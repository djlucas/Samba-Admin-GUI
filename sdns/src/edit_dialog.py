#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SDNS (Samba DNS Management)
#
# src/edit_dialog.py
#
# Description:
# Dialog for viewing/editing individual DNS records
#
# -----------------------------------------------------------------------------

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
import ldap

class EditDialog(QDialog):
    def __init__(self, zone_dn, record_name, ldap_conn, logger, parent=None):
        super().__init__(parent)
        self.zone_dn = zone_dn
        self.record_name = record_name
        self.ldap_conn = ldap_conn
        self.logger = logger

        self.setWindowTitle(f"Edit Record: {record_name}")
        self.resize(400, 200)

        layout = QVBoxLayout()

        layout.addWidget(QLabel(f"Zone DN: {zone_dn}"))
        layout.addWidget(QLabel(f"Record: {record_name}"))

        self.name_field = QLineEdit(record_name)
        layout.addWidget(QLabel("Record Name"))
        layout.addWidget(self.name_field)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_record)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def save_record(self):
        new_name = self.name_field.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Validation Error", "Record name cannot be empty.")
            return

        old_dn = f"DC={self.record_name},{self.zone_dn}"
        new_rdn = f"DC={new_name}"

        try:
            self.ldap_conn.rename_s(old_dn, new_rdn)
            self.logger.info(f"Renamed record: {old_dn} → {new_rdn}")
            QMessageBox.information(self, "Success", f"Record renamed to: {new_name}")
            self.accept()
        except ldap.LDAPError as e:
            self.logger.error(f"Failed to rename record: {e}")
            QMessageBox.critical(self, "Error", f"Could not rename record:\n{e}")

