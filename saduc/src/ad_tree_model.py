#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/ad_tree_model.py
#
# Description:
# This module provides the QAbstractItemModel for the hierarchical tree view
# of Active Directory objects. It handles lazy loading of tree nodes.
#
# -----------------------------------------------------------------------------

import logging
import os
from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt
from PyQt5.QtGui import QIcon
from samba_backend import get_forest_root_info, get_expandable_children, has_expandable_children

# --- ADTreeItem Class ---
class ADTreeItem:
    """A node in the AD tree, representing an LDAP object."""
    def __init__(self, data, parent=None, dn=None, object_class=None):
        self._parent = parent
        self._data = data
        self._dn = dn
        self._object_class = object_class
        self._children = []
        self._children_fetched = False
        # This flag determines if the item can have container children.
        # It's set during fetchMore. None means we haven't checked yet.
        self._has_sub_containers = None

    def append_child(self, item):
        self._children.append(item)

    def child(self, row):
        return self._children[row]

    def child_count(self):
        return len(self._children)

    def column_count(self):
        return 1

    def data(self):
        return self._data

    def parent(self):
        return self._parent

    def row(self):
        if self._parent:
            return self._parent._children.index(self)
        return 0

    def dn(self):
        return self._dn

    def set_dn(self, dn):
        self._dn = dn

    def object_class(self):
        return self._object_class

    def children_fetched(self):
        return self._children_fetched

    def set_children_fetched(self, value):
        self._children_fetched = value

    def set_has_sub_containers(self, value):
        self._has_sub_containers = value

    def has_sub_containers(self):
        return self._has_sub_containers


# --- ADTreeModel Class ---
class ADTreeModel(QAbstractItemModel):
    """
    A custom QAbstractItemModel for an Active Directory tree view.
    This model uses lazy loading to fetch children on demand, starting
    from the forest root.
    """
    def __init__(self, samba_conn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.samba_conn = samba_conn
        self.advanced_view = advanced_view

        # Create an invisible root item for our model
        self.root_item = ADTreeItem(None, dn=None)

        self._icons = {
            "domainDns": "domain.png",
            "organizationalUnit": "folder_ou.png",
            "container": "folder.png",
            "builtinDomain": "folder.png",
            "groupPolicyContainer": "group_policy.png",
            "default": "question_mark.png"
        }
        self.icon_cache = {}
        self._load_icons()

        # Populate the model starting from the forest root
        self._setup_model()
        self.logger.info("ADTreeModel: Model initialized.")

    def set_advanced_view(self, enabled):
        self.logger.info(f"Setting advanced view to: {enabled}")
        self.advanced_view = enabled
        self.beginResetModel()
        self.root_item = ADTreeItem(None, dn=None)
        self._setup_model()
        self.endResetModel()

    def _load_icons(self):
        for name, path in self._icons.items():
            icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', path)
            if os.path.exists(icon_path):
                self.icon_cache[name] = QIcon(icon_path)
            else:
                self.logger.warning(f"Icon not found for {name} at {icon_path}")

    def _get_icon_for_item(self, item):
        object_class = item.object_class()
        if isinstance(object_class, list):
            for oc in object_class:
                if oc in self.icon_cache:
                    return self.icon_cache[oc]
        elif object_class in self.icon_cache:
            return self.icon_cache[object_class]
        return self.icon_cache.get("default")

    def _setup_model(self):
        """
        Populates the first level of the tree with the forest root.
        """
        forest_root_data = get_forest_root_info(self.samba_conn)
        if forest_root_data:
            # The root is always the domain itself, regardless of view
            forest_root_item = ADTreeItem(forest_root_data['name'], parent=self.root_item, dn=forest_root_data['dn'], object_class='domainDns')
            forest_root_item.set_has_sub_containers(True) # Assume it has children to show the expander
            self.root_item.append_child(forest_root_item)
        else:
            self.logger.error("ADTreeModel: Could not retrieve forest root. Tree will be empty.")


    def columnCount(self, parent):
        return 1

    def data(self, index, role):
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.DisplayRole:
            return item.data()
        elif role == Qt.DecorationRole:
            return self._get_icon_for_item(item)
        
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        return QAbstractItemModel.flags(self, index)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return "Domain"
        return None

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = parent.internalPointer() if parent.isValid() else self.root_item

        if row >= 0 and row < parent_item.child_count():
            child_item = parent_item.child(row)
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent()

        if parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0

        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        return parent_item.child_count()

    def hasChildren(self, parent):
        if not parent.isValid(): # Invisible root
            return self.root_item.child_count() > 0

        item = parent.internalPointer()
        
        # If children have already been fetched, we know the answer
        if item.children_fetched():
            return item.child_count() > 0
        
        # If the has_sub_containers flag is set, use it
        if item.has_sub_containers() is not None:
            return item.has_sub_containers()

        # Fallback: check the backend directly
        return has_expandable_children(self.samba_conn, item.dn(), self.advanced_view)

    def canFetchMore(self, parent):
        if not parent.isValid():
            return False

        item = parent.internalPointer()
        # We can fetch more if children haven't been fetched AND we know it has children
        return not item.children_fetched() and self.hasChildren(parent)

    def fetchMore(self, parent_index):
        if not parent_index.isValid():
            parent_item = self.root_item
        else:
            if not self.canFetchMore(parent_index):
                return
            parent_item = parent_index.internalPointer()
        parent_dn = parent_item.dn()
        self.logger.debug(f"ADTreeModel: Fetching children for '{parent_dn}'.")
        
        child_data_list = get_expandable_children(self.samba_conn, parent_dn, self.advanced_view)

        if child_data_list:
            self.beginInsertRows(parent_index, 0, len(child_data_list) - 1)
            for child_data in child_data_list:
                child_item = ADTreeItem(child_data['name'], parent_item, child_data['dn'], object_class=child_data['objectClass'])
                # Set the flag so hasChildren() knows if this new item is expandable
                child_item.set_has_sub_containers(child_data['has_sub_containers'])
                parent_item.append_child(child_item)
            self.endInsertRows()
        
        parent_item.set_children_fetched(True)
        self.logger.debug(f"ADTreeModel: Fetched and added {len(child_data_list)} children for '{parent_dn}'.")

