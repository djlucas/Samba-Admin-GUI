#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/column_editor.py
#
# Description:
# This file contains the dialog for adding and removing columns from the
# main view.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QFrame,
    QAbstractItemView, QLabel, QListWidgetItem
)
from PyQt5.QtCore import Qt
from i18n_manager import I18nManager

class ColumnEditorDialog(QDialog):
    """Dialog for adding and removing columns."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("view_menu.add_remove_columns"))
        self.setMinimumSize(500, 400)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._initial_setup()

    def _create_widgets(self):
        self.available_label = QLabel(self.i18n.get_string("column_editor.available"))
        self.available_list = QListWidget()
        self.add_btn = QPushButton(self.i18n.get_string("column_editor.add"))
        self.remove_btn = QPushButton(self.i18n.get_string("column_editor.remove"))

        self.displayed_label = QLabel(self.i18n.get_string("column_editor.displayed"))
        self.displayed_list = QListWidget()
        self.move_up_btn = QPushButton(self.i18n.get_string("column_editor.move_up"))
        self.move_down_btn = QPushButton(self.i18n.get_string("column_editor.move_down"))
        self.restore_defaults_btn = QPushButton(self.i18n.get_string("column_editor.restore_defaults"))

        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        top_layout = QHBoxLayout()
        available_layout = QVBoxLayout()
        available_layout.addWidget(self.available_label)
        available_layout.addWidget(self.available_list)
        top_layout.addLayout(available_layout)
        add_remove_layout = QVBoxLayout()
        add_remove_layout.addStretch()
        add_remove_layout.addWidget(self.add_btn)
        add_remove_layout.addWidget(self.remove_btn)
        add_remove_layout.addStretch()
        top_layout.addLayout(add_remove_layout)
        displayed_layout = QVBoxLayout()
        displayed_layout.addWidget(self.displayed_label)
        displayed_layout.addWidget(self.displayed_list)
        top_layout.addLayout(displayed_layout)
        move_layout = QVBoxLayout()
        move_layout.addStretch()
        move_layout.addWidget(self.move_up_btn)
        move_layout.addWidget(self.move_down_btn)
        move_layout.addStretch()
        move_layout.addWidget(self.restore_defaults_btn)
        top_layout.addLayout(move_layout)
        main_layout.addLayout(top_layout)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(button_layout)

    def _connect_signals(self):
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.add_btn.clicked.connect(self._add_item)
        self.remove_btn.clicked.connect(self._remove_item)
        self.move_up_btn.clicked.connect(self._move_up)
        self.move_down_btn.clicked.connect(self._move_down)
        self.restore_defaults_btn.clicked.connect(self._restore_defaults)
        self.displayed_list.itemSelectionChanged.connect(self._update_button_states)
        self.available_list.itemSelectionChanged.connect(self._update_button_states)

    def _initial_setup(self):
        self.all_column_keys = [
            "table.header.name", "table.header.type", "table.header.description",
            "table.header.business phone", "table.header.city", "table.header.company",
            "table.header.country/region", "table.header.department", "table.header.display name",
            "table.header.e-mail address", "table.header.exchange alias",
            "table.header.exchange mailbox store", "table.header.first name",
            "table.header.instant messaging home server", "table.header.instant messaging url",
            "table.header.job title", "table.header.last name", "table.header.modified",
            "table.header.office", "table.header.phonetic company name",
            "table.header.phonetic department", "table.header.phonetic display name",
            "table.header.phonetic first name", "table.header.phonetic last name",
            "table.header.pre-windows 2000 logon name", "table.header.state",
            "table.header.target address", "table.header.user logon name",
            "table.header.x.400 e-mail address", "table.header.zip code"
        ]
        self.default_column_keys = ["table.header.name", "table.header.type", "table.header.description"]

        self._populate_lists(self.default_column_keys)
        self._update_button_states()

    def _populate_lists(self, displayed_keys):
        self.displayed_list.clear()
        self.available_list.clear()

        for key in displayed_keys:
            item = QListWidgetItem(self.i18n.get_string(key))
            item.setData(Qt.UserRole, key)
            self.displayed_list.addItem(item)

        available_keys = [key for key in self.all_column_keys if key not in displayed_keys]

        # Sort available columns alphabetically by their translated text
        sorted_available = sorted(available_keys, key=lambda k: self.i18n.get_string(k))

        for key in sorted_available:
            item = QListWidgetItem(self.i18n.get_string(key))
            item.setData(Qt.UserRole, key)
            self.available_list.addItem(item)

    def _add_item(self):
        for item in self.available_list.selectedItems():
            self.displayed_list.addItem(QListWidgetItem(item))
            self.available_list.takeItem(self.available_list.row(item))
        self._update_button_states()

    def _remove_item(self):
        for item in self.displayed_list.selectedItems():
            self.available_list.addItem(QListWidgetItem(item))
            self.displayed_list.takeItem(self.displayed_list.row(item))
        self._update_button_states()

    def _move_up(self):
        selected_items = self.displayed_list.selectedItems()
        if not selected_items: return
        current_row = self.displayed_list.row(selected_items[0])
        if current_row > 0:
            item = self.displayed_list.takeItem(current_row)
            self.displayed_list.insertItem(current_row - 1, item)
            self.displayed_list.setCurrentItem(item)
        self._update_button_states()

    def _move_down(self):
        selected_items = self.displayed_list.selectedItems()
        if not selected_items: return
        current_row = self.displayed_list.row(selected_items[0])
        if current_row < self.displayed_list.count() - 1:
            item = self.displayed_list.takeItem(current_row)
            self.displayed_list.insertItem(current_row + 1, item)
            self.displayed_list.setCurrentItem(item)
        self._update_button_states()

    def _restore_defaults(self):
        self._populate_lists(self.default_column_keys)
        self._update_button_states()

    def _update_button_states(self):
        self.add_btn.setEnabled(len(self.available_list.selectedItems()) > 0)
        self.remove_btn.setEnabled(len(self.displayed_list.selectedItems()) > 0)
        selected_displayed = self.displayed_list.selectedItems()
        if not selected_displayed:
            self.move_up_btn.setEnabled(False)
            self.move_down_btn.setEnabled(False)
        else:
            current_row = self.displayed_list.row(selected_displayed[0])
            self.move_up_btn.setEnabled(current_row > 0)
            self.move_down_btn.setEnabled(current_row < self.displayed_list.count() - 1)

        current_keys = self.get_displayed_column_keys()
        self.restore_defaults_btn.setEnabled(current_keys != self.default_column_keys)

    def get_displayed_column_keys(self):
        return [self.displayed_list.item(i).data(Qt.UserRole) for i in range(self.displayed_list.count())]

    def set_displayed_columns(self, keys):
        self._populate_lists(keys)
        self._update_button_states()
