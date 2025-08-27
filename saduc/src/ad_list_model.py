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
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()
        self._data = []
        self._header_keys = [
            "table.header.name",
            "table.header.type",
            "table.header.description"
        ]
        self.header_map = {
            "table.header.name": "name",
            "table.header.type": "objectClass",
            "table.header.description": "description",
            "table.header.business phone": "telephoneNumber",
            "table.header.city": "l",
            "table.header.company": "company",
            "table.header.country/region": "c",
            "table.header.department": "department",
            "table.header.display name": "displayName",
            "table.header.e-mail address": "mail",
            "table.header.exchange alias": "mailNickname",
            "table.header.exchange mailbox store": "mDBUseDefaults",
            "table.header.first name": "givenName",
            "table.header.instant messaging home server": "msRTCSIP-PrimaryHomeServer",
            "table.header.instant messaging url": "msRTCSIP-PrimaryUserAddress",
            "table.header.job title": "title",
            "table.header.last name": "sn",
            "table.header.modified": "whenChanged",
            "table.header.office": "physicalDeliveryOfficeName",
            "table.header.phonetic company name": "msDS-PhoneticCompanyName",
            "table.header.phonetic department": "msDS-PhoneticDepartmentName",
            "table.header.phonetic display name": "msDS-PhoneticDisplayName",
            "table.header.phonetic first name": "msDS-PhoneticFirstName",
            "table.header.phonetic last name": "msDS-PhoneticLastName",
            "table.header.pre-windows 2000 logon name": "sAMAccountName",
            "table.header.state": "st",
            "table.header.target address": "targetAddress",
            "table.header.user logon name": "userPrincipalName",
            "table.header.x.400 e-mail address": "x400Address",
            "table.header.zip code": "postalCode"
        }
        self._icons = {
            "User": "user.png", "Disabled User": "user_disable.png",
            "Security Group": "group.png", "Computer": "computer.png",
            "Domain Controller": "dns.png", "Organizational Unit": "folder_ou.png",
            "Container": "folder.png", "Contact": "contact.png",
            "Group Policy Object": "group_policy.png", "Printer": "printer.png",
            "Shared Folder": "folder_shared.png", "Domain": "domain.png",
            "Foreign Security Principal": "user_foreign.png", "Unknown": "question_mark.png"
        }
        self.icon_cache = {}
        self._load_icons()

    def _load_icons(self):
        for name, path in self._icons.items():
            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', path)
            if os.path.exists(icon_path):
                self.icon_cache[name] = QIcon(icon_path)

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._header_keys)

    def _get_object_type(self, item):
        object_classes = item.get('objectClass', [])
        if not object_classes: return "Unknown"
        if 'groupPolicyContainer' in object_classes: return "Group Policy Object"
        if 'foreignSecurityPrincipal' in object_classes: return "Foreign Security Principal"
        if 'group' in object_classes: return "Security Group"
        if 'computer' in object_classes: return "Computer"
        if 'printQueue' in object_classes: return "Printer"
        if 'contact' in object_classes: return "Contact"
        if 'user' in object_classes:
            uac = int(item.get('userAccountControl', '0'))
            return "Disabled User" if uac & UAC_ACCOUNT_DISABLED else "User"
        if 'organizationalUnit' in object_classes: return "Organizational Unit"
        if 'container' in object_classes: return "Container"
        return object_classes[-1]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < self.rowCount()):
            return QVariant()

        item = self._data[index.row()]
        header_key = self._header_keys[index.column()]
        data_key = self.header_map.get(header_key)

        if role == Qt.DisplayRole:
            if data_key == "objectClass":
                return self._get_object_type(item)
            return item.get(data_key, '')
        elif role == Qt.DecorationRole and index.column() == 0:
            obj_type = self._get_object_type(item)
            return self.icon_cache.get(obj_type, self.icon_cache.get("Unknown"))

        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(self._header_keys):
                return self.i18n.get_string(self._header_keys[section])
        return QVariant()

    def sort(self, column, order):
        self.beginResetModel()
        reverse = (order == Qt.DescendingOrder)
        header_key = self._header_keys[column]
        data_key = self.header_map.get(header_key)

        if data_key == "objectClass":
            key_func = lambda item: self._get_object_type(item).lower()
        else:
            key_func = lambda item: str(item.get(data_key, '')).lower()

        self._data.sort(key=key_func, reverse=reverse)
        self.endResetModel()

    def set_header_keys(self, header_keys):
        self.beginResetModel()
        self._header_keys = header_keys
        self.endResetModel()

    def get_header_keys(self):
        return self._header_keys

    def setData(self, data, advanced_view=False):
        self.beginResetModel()
        if data is None:
            self._data = []
        elif advanced_view:
            self._data = data
        else:
            self._data = [item for item in data if not item.get('showInAdvancedViewOnly', False)]
        self.endResetModel()

    def clear_data(self):
        self.setData(None)

    def get_object_data(self, index):
        if index.isValid() and 0 <= index.row() < len(self._data):
            return self._data[index.row()]
        return None
