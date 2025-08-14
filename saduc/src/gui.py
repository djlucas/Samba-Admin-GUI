#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/gui.py
#
# Description:
# This file contains the main window class for the SADUC application. It
# integrates the various UI components, data models, and backend connections
# to provide the core user interface and functionality.
#
# -----------------------------------------------------------------------------

import logging
from functools import partial
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QSizePolicy,
    QTreeView, QTableView, QAbstractItemView, QHeaderView,
    QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QMenu, QScrollArea, QFrame,
    QAction, QMessageBox
)
from PyQt5.QtCore import Qt, QSize, QTimer, QModelIndex

from i18n_manager import I18nManager
from samba_backend import get_all_objects_in_dn
from ad_tree_model import ADTreeModel
from ad_list_model import ADListModel

from tree_menu_manager import TreeMenuManager
from list_menu_manager import ListMenuManager
import main_window_actions as actions


# --- SADUCMainWindow Class ---
class SADUCMainWindow(QMainWindow):
    """
    The main application window for the SADUC tool.
    This window will contain the menu bar, toolbar, status bar,
    and the central pane with the tree view, list view, and action pane.
    """
    def __init__(self, samba_conn, connected_server, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.connected_server = connected_server
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.logger.debug("SADUCMainWindow: Initializing main window.")

        self.setWindowTitle(self.i18n.get_string("main.window_title"))
        self.setGeometry(100, 100, 1200, 800)

        self.advancedFeaturesAction = None
        self.tree_menu_manager = TreeMenuManager(self)
        self.list_menu_manager = ListMenuManager(self)

        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._create_central_widget_layout()
        self._setup_tree_view_model()
        self._setup_table_view_model()

        self.treePane.clicked.connect(self._on_tree_item_clicked)
        self.logger.debug("SADUCMainWindow: Tree view 'clicked' signal connected to slot.")

        self.listPane.clicked.connect(self._on_table_item_clicked)
        self.logger.debug("SADUCMainWindow: Table view 'clicked' signal connected to slot.")

        self.currentContainerDN = None
        self.current_selected_dn = None

        self.setUnifiedTitleAndToolBarOnMac(True)
        self.logger.debug("SADUCMainWindow: Main window initialized.")

    def _create_menu_bar(self):
        """
        Sets up the application's menu bar with basic File, Action, View, Window, Help menus.
        """
        self.logger.debug("SADUCMainWindow: Creating menu bar.")
        menuBar = self.menuBar()

        fileMenu = menuBar.addMenu(self.i18n.get_string("menu.file"))
        exitAction = QAction(self.i18n.get_string("menu.file.exit"), self)
        exitAction.setShortcut(self.i18n.get_string("menu.file.exit.shortcut"))
        exitAction.setStatusTip(self.i18n.get_string("menu.file.exit.status_tip"))
        exitAction.triggered.connect(self.close)
        fileMenu.addAction(exitAction)
        self.logger.debug("SADUCMainWindow: 'File' menu created.")

        menuBar.addMenu(self.i18n.get_string("menu.action"))
        self.logger.debug("SADUCMainWindow: 'Action' menu placeholder created.")

        viewMenu = menuBar.addMenu(self.i18n.get_string("menu.view"))
        self.advancedFeaturesAction = QAction(self.i18n.get_string("menu.view.advanced"), self, checkable=True)
        self.advancedFeaturesAction.setStatusTip(self.i18n.get_string("menu.view.advanced.status_tip"))
        self.advancedFeaturesAction.triggered.connect(partial(actions.on_advanced_features_toggled, self))
        viewMenu.addAction(self.advancedFeaturesAction)
        self.logger.debug("SADUCMainWindow: 'View' menu created.")

        menuBar.addMenu(self.i18n.get_string("menu.window"))
        self.logger.debug("SADUCMainWindow: 'Window' menu placeholder created.")

        menuBar.addMenu(self.i18n.get_string("menu.help"))
        self.logger.debug("SADUCMainWindow: 'Help' menu placeholder created.")

    def _create_tool_bar(self):
        """
        Sets up the application's toolbar (currently a placeholder).
        """
        self.logger.debug("SADUCMainWindow: Creating toolbar.")
        toolBar = self.addToolBar(self.i18n.get_string("main.toolbar.main"))
        toolBar.setIconSize(QSize(24, 24))
        self.logger.debug("SADUCMainWindow: Toolbar created.")

    def _create_status_bar(self):
        """
        Sets up the application's status bar.
        """
        self.logger.debug("SADUCMainWindow: Creating status bar.")
        self.statusBar().showMessage(self.i18n.get_string("main.status_bar_ready"))
        self.logger.debug("SADUCMainWindow: Status bar created.")

    def _create_central_widget_layout(self):
        """
        Sets up the central widget with the three main panes using QSplitter.
        """
        self.logger.debug("SADUCMainWindow: Creating central widget layout.")

        self.treePane = QTreeView()
        self.treePane.setObjectName("TreePane")
        self.treePane.setMinimumSize(150, 100)
        self.treePane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.treePane.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treePane.customContextMenuRequested.connect(self.tree_menu_manager.on_tree_context_menu)

        self.listPane = QTableView()
        self.listPane.setObjectName("ListPane")
        self.listPane.setMinimumSize(300, 100)
        self.listPane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.listPane.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.listPane.setShowGrid(False)
        self.listPane.verticalHeader().hide()
        self.listPane.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.listPane.setWordWrap(False)
        self.listPane.setSortingEnabled(True)
        self.listPane.setContextMenuPolicy(Qt.CustomContextMenu)
        self.listPane.customContextMenuRequested.connect(self.list_menu_manager.on_list_context_menu)
        self.listPane.doubleClicked.connect(partial(actions.on_list_item_double_clicked, self))

        self.actionPane = QWidget()
        self.actionPane.setObjectName("ActionPane")
        self.actionPane.setStyleSheet("background-color: white;")
        self.actionPane.setMinimumSize(100, 100)
        self.actionPane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.actionPaneLayout = QVBoxLayout()
        self.actionPane.setLayout(self.actionPaneLayout)
        actionPaneStaticTitle = QLabel(self.i18n.get_string("action_pane.static_title"))
        actionPaneStaticTitle.setStyleSheet("font-weight: bold; font-size: 14pt; padding: 5px;")
        self.actionPaneLayout.addWidget(actionPaneStaticTitle)

        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QFrame.NoFrame)
        scrollArea.setStyleSheet("QScrollArea { border: none; }")
        self.actionContentWidget = QWidget()
        self.actionContentLayout = QVBoxLayout(self.actionContentWidget)
        self.actionContentLayout.setContentsMargins(0, 0, 0, 0)
        self.actionContentLayout.setSpacing(0)
        scrollArea.setWidget(self.actionContentWidget)
        self.actionPaneLayout.addWidget(scrollArea)

        self.listActionLayout = QVBoxLayout()
        self.itemActionLayout = QVBoxLayout()
        self.actionContentLayout.addLayout(self.listActionLayout)
        self.actionContentLayout.addLayout(self.itemActionLayout)
        self.actionContentLayout.addStretch(1)

        mainSplitter = QSplitter(Qt.Horizontal)
        mainSplitter.addWidget(self.treePane)
        rightSideSplitter = QSplitter(Qt.Horizontal)
        rightSideSplitter.addWidget(self.listPane)
        rightSideSplitter.addWidget(self.actionPane)
        mainSplitter.addWidget(rightSideSplitter)
        self.setCentralWidget(mainSplitter)

        def set_initial_sizes():
            total_width = mainSplitter.width()
            left_pane_width = int(total_width * 0.20)
            middle_pane_width = int(total_width * 0.65)
            right_pane_width = total_width - left_pane_width - middle_pane_width
            mainSplitter.setSizes([left_pane_width, middle_pane_width + right_pane_width])
            rightSideSplitter.setSizes([middle_pane_width, right_pane_width])
            self.logger.info(f"Initial splitter sizes set to: {mainSplitter.sizes()}, {rightSideSplitter.sizes()}")

        QTimer.singleShot(0, set_initial_sizes)
        self.logger.debug("SADUCMainWindow: Central widget layout created.")

    def _clear_layout(self, layout):
        """
        Helper method to clear all items from a layout.
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _create_action_section(self, title, action_map=None):
        """
        Helper to create a dynamic action section with a title and a menu button.
        """
        sectionLayout = QHBoxLayout()
        titleLabel = QLabel(title)
        titleLabel.setStyleSheet("font-weight: bold;")
        sectionLayout.addWidget(titleLabel)
        sectionLayout.addStretch(1)

        actionButton = QPushButton(self.i18n.get_string("action_pane.button.actions"))
        actionMenu = QMenu()
        if action_map:
            for action_text_key, slot_method in action_map.items():
                action_text = self.i18n.get_string(action_text_key)
                action = QAction(action_text, self)
                if slot_method:
                    action.triggered.connect(partial(slot_method, self))
                else:
                    action.setEnabled(False)
                actionMenu.addAction(action)
        actionButton.setMenu(actionMenu)
        sectionLayout.addWidget(actionButton)
        return sectionLayout

    def _setup_tree_view_model(self):
        """
        Creates and populates the ADTreeModel for the tree view.
        """
        self.logger.debug("SADUCMainWindow: Setting up tree view model.")
        advanced_view_enabled = self.advancedFeaturesAction.isChecked() if self.advancedFeaturesAction else False
        self.adModel = ADTreeModel(self.samba_conn, self.connected_server, advanced_view=advanced_view_enabled)
        self.treePane.setModel(self.adModel)
        self.logger.debug("SADUCMainWindow: Tree view model set.")

        saduc_root_index = self.adModel.index(0, 0, QModelIndex())
        if saduc_root_index.isValid():
            self.treePane.expand(saduc_root_index)
            domain_index = self.adModel.index(1, 0, saduc_root_index)
            if domain_index.isValid():
                self.treePane.expand(domain_index)

    def _setup_table_view_model(self):
        """
        Creates an empty ADListModel for the table view.
        """
        self.logger.debug("SADUCMainWindow: Setting up table view model.")
        self.tableModel = ADListModel()
        self.listPane.setModel(self.tableModel)
        self.logger.debug("SADUCMainWindow: Table view model set.")

    def _on_tree_item_clicked(self, index):
        """
        Slot to handle clicks on the tree view.
        It updates the table view and action pane based on the clicked item.
        """
        if not index.isValid():
            return

        tree_item = index.internalPointer()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]

        if 'saducRoot' in obj_classes:
            self.tableModel.clear_data()
            self._clear_layout(self.listActionLayout)
            self._clear_layout(self.itemActionLayout)
            self.statusBar().showMessage(self.i18n.get_string("main.status_bar_ready"))
            return

        if 'savedQueriesRoot' in obj_classes:
            self.logger.info("Saved Queries item clicked. This is a local-only feature.")
            self.tableModel.clear_data()
            self._clear_layout(self.listActionLayout)
            self._clear_layout(self.itemActionLayout)
            self.statusBar().showMessage("Saved Queries (Not Implemented)")
            return

        self.currentContainerDN = tree_item.dn()
        container_name = tree_item.data()
        self.logger.info(f"Tree item clicked: '{container_name}' (DN: {self.currentContainerDN})")

        self.tableModel.clear_data()
        self._clear_layout(self.listActionLayout)
        self._clear_layout(self.itemActionLayout)
        self.statusBar().showMessage(self.i18n.get_text("status.loading", container_name))

        try:
            list_data = get_all_objects_in_dn(self.samba_conn, self.currentContainerDN)
            self.tableModel.setData(list_data)
            self.statusBar().showMessage(self.i18n.get_text("status.loaded_items", len(list_data), container_name))
        except Exception as e:
            self.logger.error(f"Failed to fetch objects for DN '{self.currentContainerDN}': {e}")
            QMessageBox.critical(self, self.i18n.get_string("dialog.common.error.title"),
                                 self.i18n.get_text("error.backend.fetch_failed", str(e)))
            self.statusBar().showMessage(self.i18n.get_string("main.status_bar_ready"))
            return

        action_map = {
            "action_pane.menu.new_user": actions.on_new_user_action_triggered,
            "action_pane.menu.new_group": actions.on_new_group_action_triggered,
            "action_pane.menu.new_computer": actions.on_new_computer_action_triggered
        }
        self.listActionLayout.addLayout(self._create_action_section(container_name, action_map))

        header = self.listPane.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.listPane.resizeColumnsToContents()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.listPane.setColumnWidth(0, int(self.listPane.width() * 0.3))
        self.listPane.setColumnWidth(1, int(self.listPane.width() * 0.2))

    def _on_table_item_clicked(self, index):
        """
        Slot to handle clicks on the table view.
        It updates the action pane with actions for the selected item.
        """
        if not index.isValid():
            return

        selected_object_data = self.tableModel.get_object_data(index)
        if not selected_object_data:
            self.logger.warning("No valid data for selected table item.")
            return

        name = selected_object_data.get('name', 'Unknown')
        self.current_selected_dn = selected_object_data.get('dn')
        obj_classes = selected_object_data.get('objectClass', [])
        self.logger.info(f"Table item clicked: '{name}' (DN: {self.current_selected_dn})")
        self.statusBar().showMessage(self.i18n.get_text("status.selected_item", name))

        self._clear_layout(self.itemActionLayout)

        action_map = {}
        if 'user' in obj_classes and 'computer' not in obj_classes:
            action_map = {
                "action_pane.menu.copy_user": actions.on_copy_user_action_triggered,
                "action_pane.menu.delete_user": actions.on_delete_user_action_triggered,
                "action_pane.menu.disable_user": actions.on_disable_user_action_triggered
            }
        elif 'computer' in obj_classes:
            action_map = {
                "action_pane.menu.disable_computer": None,
                "action_pane.menu.reset_computer_account": None
            }
        elif 'group' in obj_classes:
            action_map = {
                "action_pane.menu.delete_group": None
            }
        
        if action_map:
            self.itemActionLayout.addLayout(self._create_action_section(name, action_map))