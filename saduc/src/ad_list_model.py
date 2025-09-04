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
        self._current_dn = None
        self._samba_conn = None
        self._advanced_view = False
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
            "inetOrgPerson": "user.png", "Disabled inetOrgPerson": "user_disable.png",
            "sambaSamAccount": "user.png", "Disabled sambaSamAccount": "user_disable.png",
            "Security Group": "group.png", "Computer": "computer.png", "Disabled Computer": "computer_disabled.png",
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
        if 'computer' in object_classes:
            try:
                uac_value = item.get('userAccountControl', '0')
                # Handle both string and int values
                if isinstance(uac_value, list):
                    uac_value = uac_value[0] if uac_value else '0'
                uac = int(uac_value)
                is_disabled = bool(uac & UAC_ACCOUNT_DISABLED)
                return "Disabled Computer" if is_disabled else "Computer"
            except (ValueError, TypeError) as e:
                computer_name = item.get('cn', item.get('sAMAccountName', 'Unknown'))
                self.logger.warning(f"Could not parse userAccountControl for computer '{computer_name}': {e}")
                return "Computer"
        if 'printQueue' in object_classes: return "Printer"
        if 'contact' in object_classes: return "Contact"
        if 'sambaSamAccount' in object_classes:
            try:
                uac_value = item.get('userAccountControl', '0')
                # Handle both string and int values
                if isinstance(uac_value, list):
                    uac_value = uac_value[0] if uac_value else '0'
                uac = int(uac_value)
                is_disabled = bool(uac & UAC_ACCOUNT_DISABLED)
                return "Disabled sambaSamAccount" if is_disabled else "sambaSamAccount"
            except (ValueError, TypeError) as e:
                person_name = item.get('cn', item.get('sAMAccountName', 'Unknown'))
                self.logger.warning(f"Could not parse userAccountControl for sambaSamAccount '{person_name}': {e}")
                return "sambaSamAccount"
        if 'inetOrgPerson' in object_classes:
            try:
                uac_value = item.get('userAccountControl', '0')
                # Handle both string and int values
                if isinstance(uac_value, list):
                    uac_value = uac_value[0] if uac_value else '0'
                uac = int(uac_value)
                is_disabled = bool(uac & UAC_ACCOUNT_DISABLED)
                return "Disabled inetOrgPerson" if is_disabled else "inetOrgPerson"
            except (ValueError, TypeError) as e:
                person_name = item.get('cn', item.get('sAMAccountName', 'Unknown'))
                self.logger.warning(f"Could not parse userAccountControl for inetOrgPerson '{person_name}': {e}")
                return "inetOrgPerson"
        if 'user' in object_classes:
            try:
                uac_value = item.get('userAccountControl', '0')
                # Handle both string and int values
                if isinstance(uac_value, list):
                    uac_value = uac_value[0] if uac_value else '0'
                uac = int(uac_value)
                is_disabled = bool(uac & UAC_ACCOUNT_DISABLED)
                return "Disabled User" if is_disabled else "User"
            except (ValueError, TypeError) as e:
                user_name = item.get('cn', item.get('sAMAccountName', 'Unknown'))
                self.logger.warning(f"Could not parse userAccountControl for user '{user_name}': {e}")
                return "User"
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
        elif role == Qt.EditRole and index.column() == 0:
            # For inline editing, return the current name value
            # Try displayName first, then cn, then name
            current_name = item.get('displayName', item.get('cn', item.get('name', '')))
            if isinstance(current_name, list):
                current_name = current_name[0] if current_name else ''
            return current_name
        elif role == Qt.DecorationRole and index.column() == 0:
            obj_type = self._get_object_type(item)
            return self.icon_cache.get(obj_type, self.icon_cache.get("Unknown"))

        return QVariant()
    
    def flags(self, index):
        """Return flags for the given index to enable/disable editing."""
        if not index.isValid():
            return Qt.NoItemFlags
        
        # Only allow editing of the name column (first column)
        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    def setData(self, index, value, role=Qt.EditRole):
        """Handle inline editing of items."""
        if not index.isValid() or role != Qt.EditRole:
            return False
        
        # Only allow editing the name column
        if index.column() != 0:
            return False
        
        item = self._data[index.row()]
        new_name = value.strip()
        
        # Don't change if the name is the same
        current_name = item.get('displayName', item.get('cn', ''))
        if isinstance(current_name, list):
            current_name = current_name[0] if current_name else ''
        
        if new_name == current_name or not new_name:
            return False
        
        # Perform the rename operation
        if self._samba_conn and item.get('distinguishedName'):
            try:
                # Determine object type for proper rename handling
                object_type = self._get_object_type(item).lower()
                object_classes = item.get('objectClass', [])
                
                if 'user' in object_classes and 'computer' not in object_classes:
                    object_type = 'user'
                elif 'group' in object_classes:
                    object_type = 'group'
                elif 'contact' in object_classes:
                    object_type = 'contact'
                elif 'inetorgperson' in object_classes:
                    object_type = 'inetOrgPerson'
                
                # Check if this object type should get the ObjectRenameDialog
                should_open_rename_dialog = object_type.lower() in ['user', 'inetorgperson', 'group', 'contact']
                
                if should_open_rename_dialog:
                    # First update the display name in the list
                    if object_type.lower() in ['user', 'inetorgperson', 'contact']:
                        item['displayName'] = [new_name] if isinstance(item.get('displayName'), list) else new_name
                    elif object_type.lower() == 'group':
                        item['cn'] = [new_name] if isinstance(item.get('cn'), list) else new_name
                    
                    # Emit dataChanged signal to update the list display
                    self.dataChanged.emit(index, index, [Qt.DisplayRole])
                    
                    # We need to fetch additional attributes that may not be in the cached data
                    # The list view doesn't fetch givenName/sn by default
                    try:
                        import ldap
                        # Get all attributes we might need for the rename dialog
                        needed_attrs = ['cn', 'displayName', 'givenName', 'sn', 'sAMAccountName', 
                                      'userPrincipalName', 'objectClass', 'distinguishedName']
                        
                        self.logger.info(f"Fetching comprehensive data for rename dialog: {item['distinguishedName']}")
                        fresh_res = self._samba_conn.search_s(item['distinguishedName'], ldap.SCOPE_BASE, 
                                                            '(objectClass=*)', needed_attrs)
                        
                        if fresh_res and fresh_res[0][1]:
                            fresh_data = fresh_res[0][1]
                            # Convert bytes to strings and handle lists properly
                            dialog_object_data = {}
                            for key, values in fresh_data.items():
                                if isinstance(values, list):
                                    dialog_object_data[key] = [v.decode('utf-8') if isinstance(v, bytes) else str(v) for v in values]
                                else:
                                    dialog_object_data[key] = [values.decode('utf-8') if isinstance(values, bytes) else str(values)]
                            
                            # Ensure we have the DN
                            dialog_object_data['distinguishedName'] = [item['distinguishedName']]
                            
                        else:
                            self.logger.warning("No fresh data returned, using cached data")
                            # Fallback: use cached data but ensure list format
                            dialog_object_data = {}
                            for key, value in item.items():
                                if isinstance(value, list):
                                    dialog_object_data[key] = value
                                else:
                                    dialog_object_data[key] = [str(value)] if value is not None else ['']
                    
                    except Exception as e:
                        self.logger.error(f"Error fetching fresh data: {e}, using cached data")
                        # Fallback: use cached data but ensure list format
                        dialog_object_data = {}
                        for key, value in item.items():
                            if isinstance(value, list):
                                dialog_object_data[key] = value
                            else:
                                dialog_object_data[key] = [str(value)] if value is not None else ['']
                    
                    # Log the data we're passing to debug
                    self.logger.info(f"Dialog data - cn: {dialog_object_data.get('cn')}, displayName: {dialog_object_data.get('displayName')}, givenName: {dialog_object_data.get('givenName')}, sn: {dialog_object_data.get('sn')}")
                    
                    # Now open ObjectRenameDialog for comprehensive rename
                    from user_dialogs import ObjectRenameDialog
                    dialog = ObjectRenameDialog(
                        parent=None,  # Will need to get proper parent
                        object_dn=item['distinguishedName'],
                        current_object_data=dialog_object_data,
                        object_type=object_type,
                        samba_conn=self._samba_conn
                    )
                    
                    # Update the displayName/cn field with the new name after dialog is populated
                    if hasattr(dialog, 'field_widgets'):
                        if object_type.lower() in ['user', 'inetorgperson', 'contact'] and 'displayName' in dialog.field_widgets:
                            dialog.field_widgets['displayName'].setText(new_name)
                        elif object_type.lower() == 'group' and 'cn' in dialog.field_widgets:
                            dialog.field_widgets['cn'].setText(new_name)
                    
                    if dialog.exec_() == dialog.Accepted:
                        self.logger.info(f"ObjectRenameDialog accepted for {object_type}")
                        
                        # Get the rename data from the dialog
                        rename_data = dialog.get_rename_data()
                        self.logger.info(f"Rename data from dialog: {rename_data}")
                        
                        if rename_data:
                            # Apply the comprehensive rename using the backend function
                            from samba_backend import rename_object_with_attributes_samba
                            success, message_key, extra = rename_object_with_attributes_samba(
                                self._samba_conn, 
                                item['distinguishedName'], 
                                rename_data, 
                                object_type
                            )
                            
                            if success:
                                # Update our local data with the new values
                                for key, value in rename_data.items():
                                    if key in item:
                                        item[key] = [value] if isinstance(item[key], list) else value
                                
                                # If the cn was changed, the DN has changed too - we need to update it
                                dn_changed = False
                                if 'cn' in rename_data and extra and len(extra) > 0:
                                    new_dn = extra[0]  # The new DN is returned in extra
                                    item['distinguishedName'] = new_dn
                                    dn_changed = True
                                    self.logger.info(f"Updated local DN to: {new_dn}")
                                
                                if dn_changed:
                                    # When DN changes, we need to refresh the entire container
                                    self.logger.info("DN changed - triggering container refresh")
                                    if self.parent() and hasattr(self.parent(), 'refresh_current_container'):
                                        self.parent().refresh_current_container()
                                    else:
                                        # Fallback to model reset
                                        self.beginResetModel()
                                        self.endResetModel()
                                else:
                                    # For attribute-only changes, a simple dataChanged is sufficient
                                    self.dataChanged.emit(index, index, [Qt.DisplayRole])
                                self.logger.info(f"Successfully applied comprehensive rename for {object_type}")
                                return True
                            else:
                                self.logger.error(f"Failed to apply comprehensive rename: {message_key}")
                                # TODO: Show error message to user
                                return False
                        else:
                            self.logger.warning("No rename data returned from dialog")
                            return True
                    else:
                        self.logger.info(f"ObjectRenameDialog cancelled for {object_type}")
                        return True  # Still return True since we updated the display name
                else:
                    # For other objects, do simple rename
                    if 'displayName' in item:
                        rename_data = {'displayName': new_name}
                    else:
                        rename_data = {'cn': new_name}
                    
                    # Import the comprehensive rename function
                    from samba_backend import rename_object_with_attributes_samba
                    success, message_key, extra = rename_object_with_attributes_samba(
                        self._samba_conn, 
                        item['distinguishedName'], 
                        rename_data, 
                        object_type
                    )
                    
                    if success:
                        # Update the local data to reflect the change
                        if 'displayName' in rename_data:
                            item['displayName'] = [new_name] if isinstance(item.get('displayName'), list) else new_name
                        if 'cn' in rename_data:
                            item['cn'] = [new_name] if isinstance(item.get('cn'), list) else new_name
                        
                        # Emit dataChanged signal
                        self.dataChanged.emit(index, index, [Qt.DisplayRole])
                        self.logger.info(f"Successfully renamed {object_type} to '{new_name}'")
                        return True
                    else:
                        self.logger.error(f"Failed to rename {object_type}: {message_key}")
                        return False
                    
            except Exception as e:
                self.logger.error(f"Error during inline rename: {e}")
                return False
        
        return False

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

    def setModelData(self, data, advanced_view=False):
        self.beginResetModel()
        if data is None:
            self._data = []
        elif advanced_view:
            self._data = data
        else:
            self._data = [item for item in data if not item.get('showInAdvancedViewOnly', False)]
        self.endResetModel()

    def clear_data(self):
        self.setModelData(None)

    def set_connection_info(self, samba_conn, current_dn, advanced_view=False):
        """Set the connection and current DN for refresh capability."""
        self._samba_conn = samba_conn
        self._current_dn = current_dn
        self._advanced_view = advanced_view

    def refresh_current_data(self):
        """Refresh the current data by reloading from the directory."""
        if not self._samba_conn or not self._current_dn:
            self.logger.warning("Cannot refresh: no connection or DN set")
            return False
        
        try:
            from samba_backend import get_all_objects_in_dn
            
            # Get the list of LDAP attribute names from the table model's header map
            attributes_to_fetch = [
                self.header_map[key]
                for key in self.get_header_keys()
                if key in self.header_map
            ]
            
            list_data = get_all_objects_in_dn(self._samba_conn, self._current_dn, attributes=attributes_to_fetch)
            self.setModelData(list_data, advanced_view=self._advanced_view)
            self.sort(0, Qt.AscendingOrder)
            
            self.logger.debug(f"Refreshed data for DN: {self._current_dn}, loaded {len(list_data)} objects")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to refresh data for DN '{self._current_dn}': {e}")
            return False

    def get_object_data(self, index):
        if index.isValid() and 0 <= index.row() < len(self._data):
            return self._data[index.row()]
        return None

    # Drag and Drop support
    def supportedDragActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return ['application/x-saduc-object-dn']

    def mimeData(self, indexes):
        from PyQt5.QtCore import QMimeData
        mime_data = QMimeData()
        
        # Get unique rows (in case multiple columns are selected)
        rows = set()
        for index in indexes:
            if index.isValid():
                rows.add(index.row())
        
        # Get DNs of dragged objects
        dns = []
        for row in rows:
            if row < len(self._data):
                obj_data = self._data[row]
                dn = obj_data.get('distinguishedName')
                if dn:
                    dns.append(dn)
        
        # Store DNs as MIME data
        if dns:
            mime_data.setData('application/x-saduc-object-dn', '\n'.join(dns).encode('utf-8'))
            # Also set text data for debugging
            mime_data.setText('\n'.join(dns))
        
        return mime_data
