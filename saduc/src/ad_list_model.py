#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/ad_list_model.py
#
# Description:
# This module provides the QAbstractTableModel for the list/table view that
# displays the contents of a selected container.
#
# -----------------------------------------------------------------------------

from PyQt5.QtCore import QAbstractTableModel, QVariant, Qt, QModelIndex
from PyQt5.QtGui import QIcon
from i18n_manager import I18nManager
import logging
import os

UAC_ACCOUNT_DISABLED = 0x0002

class ADListModel(QAbstractTableModel):
    """
    A custom QAbstractTableModel for displaying a list of AD objects.
    This model uses a fixed set of columns (Name, Type, Description) and
    determines the object type by inspecting its objectClass attribute.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        self._data = []
        # Use a fixed set of headers, similar to the default ADUC view.
        self._headers = [
            self.i18n.get_string("table.header.name"),
            self.i18n.get_string("table.header.type"),
            self.i18n.get_string("table.header.description")
        ]
        self._icons = {
            "User": "user.png",
            "Disabled User": "user_disable.png",
            "Security Group": "group.png",
            "Computer": "computer.png",
            "Domain Controller": "dns.png",
            "Organizational Unit": "folder_ou.png",
            "Container": "folder.png",
            "Contact": "contact.png",
            "Group Policy Object": "group_policy.png",
            "Printer": "printer.png",
            "Shared Folder": "folder_shared.png",
            "Domain": "domain.png",
            "Unknown": "question_mark.png"
        }
        self.icon_cache = {}
        self._load_icons()

    def _load_icons(self):
        for name, path in self._icons.items():
            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', path)
            if os.path.exists(icon_path):
                self.icon_cache[name] = QIcon(icon_path)
            else:
                self.logger.warning(f"Icon not found for {name} at {icon_path}")

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def _get_object_type(self, item):
        """
        Determines a user-friendly object type from its list of classes.
        The order of checks is important, as some objects (like DCs) can be
        both a 'user' and a 'computer'.
        """
        object_classes = item.get('objectClass', [])
        if not object_classes:
            return "Unknown"

        # More specific types first
        if 'groupPolicyContainer' in object_classes:
            return "Group Policy Object"
        if 'group' in object_classes:
            return "Security Group"
        if 'computer' in object_classes:
            # You can get more specific here by checking userAccountControl flags if needed
            return "Computer"
        if 'user' in object_classes:
            uac = int(item.get('userAccountControl', '0'))
            if uac & UAC_ACCOUNT_DISABLED:
                return "Disabled User"
            return "User"
        if 'organizationalUnit' in object_classes:
            return "Organizational Unit"
        if 'container' in object_classes:
            return "Container"
        
        # Fallback to the last class in the list (often the most specific)
        return object_classes[-1]


    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < self.rowCount()):
            return QVariant()

        item = self._data[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            if column == 0:  # Name column
                return item.get('name', '')
            elif column == 1:  # Type column
                return self._get_object_type(item)
            elif column == 2:  # Description column
                return item.get('description', '')
        elif role == Qt.DecorationRole:
            if column == 0:
                obj_type = self._get_object_type(item)
                return self.icon_cache.get(obj_type, self.icon_cache.get("Unknown"))

        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return QVariant()

    def sort(self, column, order):
        """Sorts the table by a given column."""
        self.beginResetModel()
        
        reverse = (order == Qt.DescendingOrder)
        
        # Define a key function based on the column index
        if column == 0: # Name
            key_func = lambda item: item.get('name', '').lower()
        elif column == 1: # Type
            key_func = lambda item: self._get_object_type(item).lower()
        elif column == 2: # Description
            key_func = lambda item: item.get('description', '').lower()
        else:
            # If column is invalid, just end the reset
            self.endResetModel()
            return

        self._data.sort(key=key_func, reverse=reverse)
        
        self.endResetModel()

    def setData(self, data):
        """
        Resets the model with new data from the backend.
        """
        self.beginResetModel()
        self._data = data if data is not None else []
        self.endResetModel()
        self.logger.debug(f"Model updated with {len(self._data)} items.")

    def clear_data(self):
        """
        Clears all data from the model.
        """
        self.setData(None)

    def get_object_data(self, index):
        """
        Returns the entire data dictionary for the object at a given index.
        """
        if index.isValid() and 0 <= index.row() < len(self._data):
            return self._data[index.row()]
        return None
