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
    QAction, QActionGroup, QMessageBox, QStackedWidget, QListView, QStyledItemDelegate, QStyle
)
from PyQt5.QtCore import Qt, QSize, QTimer, QModelIndex, QRect
from PyQt5.QtGui import QFontMetrics, QIcon

from i18n_manager import I18nManager
from samba_backend import get_all_objects_in_dn
from ad_tree_model import ADTreeModel
from ad_list_model import ADListModel

from tree_menu_manager import TreeMenuManager
from list_menu_manager import ListMenuManager
import main_window_actions as actions
from saved_searches_dialog import SavedSearchesDialog
from sagui_config import config_manager

class SmallIconDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size = 24
        self.padding = 4
        self.gap = 6
        self.row_height = 32

    def paint(self, painter, option, index):
        # Draw background and selection
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        # Draw the icon
        icon = index.data(Qt.DecorationRole)
        if icon and not icon.isNull():
            icon_rect = QRect(
                option.rect.x() + self.padding,
                option.rect.y() + (option.rect.height() - self.icon_size) // 2,
                self.icon_size,
                self.icon_size
            )
            icon.paint(painter, icon_rect, Qt.AlignCenter)

        # Draw the text
        text = index.data(Qt.DisplayRole)
        if text:
            # Use the appropriate text color
            if option.state & QStyle.State_Selected:
                painter.setPen(option.palette.highlightedText().color())
            else:
                painter.setPen(option.palette.text().color())

            painter.setFont(option.font)

            text_rect = QRect(
                option.rect.x() + self.padding + self.icon_size + self.gap,
                option.rect.y(),
                option.rect.width() - (self.padding + self.icon_size + self.gap + self.padding),
                option.rect.height()
            )
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

    def sizeHint(self, option, index):
        # For icon view mode, we need to return a reasonable size
        text = index.data(Qt.DisplayRole) or ""

        if hasattr(option, 'fontMetrics'):
            metrics = option.fontMetrics
        else:
            metrics = QFontMetrics(option.font)

        text_width = metrics.width(text)
        total_width = self.padding + self.icon_size + self.gap + text_width + self.padding

        # Ensure minimum width for proper display
        min_width = max(total_width, 100)  # Minimum 100px wide

        return QSize(min_width, self.row_height)

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
        
        # Set window icon
        from icon_utils import set_window_icon
        set_window_icon(self, use_search_icon=False)

        self.advancedFeaturesAction = None
        self.tree_menu_manager = TreeMenuManager(self)
        self.list_menu_manager = ListMenuManager(self)
        self.should_auto_expand = True

        self.small_icon_delegate = SmallIconDelegate(self)
        self.default_delegate = QStyledItemDelegate(self)

        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._create_central_widget_layout()
        self._setup_tree_view_model()
        self._setup_table_view_model()

        self.treePane.clicked.connect(self._on_tree_item_clicked)
        self.logger.debug("SADUCMainWindow: Tree view 'clicked' signal connected to slot.")

        self.listPane.clicked.connect(self._on_table_item_clicked)
        self.iconView.clicked.connect(self._on_table_item_clicked)
        self.logger.debug("SADUCMainWindow: Table view 'clicked' signal connected to slot.")

        self.currentContainerDN = None
        self.current_selected_dn = None

        self.setUnifiedTitleAndToolBarOnMac(True)
        self.logger.debug("SADUCMainWindow: Main window initialized.")

    def _create_menu_bar(self):
        """
        Sets up the application's menu bar with File, Action, and View menus.
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

        self.actionMenu = menuBar.addMenu(self.i18n.get_string("menu.action"))
        self.logger.debug("SADUCMainWindow: 'Action' menu created.")

        viewMenu = menuBar.addMenu(self.i18n.get_string("menu.view"))
        
        addRemoveColumnsAction = QAction(self.i18n.get_string("view_menu.add_remove_columns"), self)
        addRemoveColumnsAction.triggered.connect(partial(actions.on_view_add_remove_columns_action_triggered, self))
        viewMenu.addAction(addRemoveColumnsAction)
        
        viewMenu.addSeparator()

        viewModeGroup = QActionGroup(self)
        self.largeIconsAction = QAction(self.i18n.get_string("view_menu.large_icons"), self, checkable=True)
        self.largeIconsAction.triggered.connect(lambda: self._set_list_view_mode('large_icons'))
        viewModeGroup.addAction(self.largeIconsAction)
        viewMenu.addAction(self.largeIconsAction)

        self.smallIconsAction = QAction(self.i18n.get_string("view_menu.small_icons"), self, checkable=True)
        self.smallIconsAction.triggered.connect(lambda: self._set_list_view_mode('small_icons'))
        viewModeGroup.addAction(self.smallIconsAction)
        viewMenu.addAction(self.smallIconsAction)

        self.listAction = QAction(self.i18n.get_string("view_menu.list"), self, checkable=True)
        self.listAction.triggered.connect(lambda: self._set_list_view_mode('list'))
        viewModeGroup.addAction(self.listAction)
        viewMenu.addAction(self.listAction)

        self.detailsAction = QAction(self.i18n.get_string("view_menu.details"), self, checkable=True)
        self.detailsAction.setChecked(True)
        self.detailsAction.triggered.connect(lambda: self.stackedListWidget.setCurrentWidget(self.listPane))
        viewModeGroup.addAction(self.detailsAction)
        viewMenu.addAction(self.detailsAction)

        viewMenu.addSeparator()

        self.objectsAsContainersAction = QAction(self.i18n.get_string("menu.view.objects_as_containers"), self, checkable=True)
        self.objectsAsContainersAction.setStatusTip(self.i18n.get_string("menu.view.objects_as_containers.status_tip"))
        self.objectsAsContainersAction.triggered.connect(partial(actions.on_view_objects_as_containers_toggled, self))
        viewMenu.addAction(self.objectsAsContainersAction)
        
        self.advancedFeaturesAction = QAction(self.i18n.get_string("menu.view.advanced"), self, checkable=True)
        self.advancedFeaturesAction.setStatusTip(self.i18n.get_string("menu.view.advanced.status_tip"))
        self.advancedFeaturesAction.triggered.connect(partial(actions.on_advanced_features_toggled, self))
        viewMenu.addAction(self.advancedFeaturesAction)

        filterOptionsAction = QAction(self.i18n.get_string("view_menu.filter_options"), self)
        filterOptionsAction.triggered.connect(partial(actions.on_stub_action_triggered, self))
        viewMenu.addAction(filterOptionsAction)

        viewMenu.addSeparator()

        customizeAction = QAction(self.i18n.get_string("view_menu.customize"), self)
        customizeAction.triggered.connect(partial(actions.on_stub_action_triggered, self))
        viewMenu.addAction(customizeAction)

        self.logger.debug("SADUCMainWindow: 'View' menu created.")

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
        
        # Enable drag and drop for tree view (drop target)
        self.treePane.setAcceptDrops(True)
        self.treePane.setDropIndicatorShown(True)

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
        
        # Enable drag and drop for list view (drag source)
        self.listPane.setDragEnabled(True)
        self.listPane.setDragDropMode(QAbstractItemView.DragOnly)

        self.iconView = QListView()
        self.iconView.setObjectName("IconView")
        self.iconView.setMinimumSize(300, 100)
        self.iconView.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.iconView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.iconView.setWordWrap(True)
        self.iconView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.iconView.customContextMenuRequested.connect(self.list_menu_manager.on_list_context_menu)
        self.iconView.doubleClicked.connect(partial(actions.on_list_item_double_clicked, self))
        
        # Enable drag and drop for icon view (drag source)
        self.iconView.setDragEnabled(True)
        self.iconView.setDragDropMode(QAbstractItemView.DragOnly)

        self.stackedListWidget = QStackedWidget()
        self.stackedListWidget.addWidget(self.listPane)
        self.stackedListWidget.addWidget(self.iconView)

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
        rightSideSplitter.addWidget(self.stackedListWidget)
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

    def _set_list_view_mode(self, mode):
        self.stackedListWidget.setCurrentWidget(self.iconView)
        if mode == 'large_icons':
            self.iconView.setItemDelegate(self.default_delegate)
            self.iconView.setViewMode(QListView.IconMode)
            self.iconView.setIconSize(QSize(48, 48))
            self.iconView.setGridSize(QSize(90, 90))
            self.iconView.setFlow(QListView.LeftToRight)
            self.iconView.setWrapping(True)
            self.iconView.setResizeMode(QListView.Adjust)
            self.iconView.setUniformItemSizes(False)
        elif mode == 'small_icons':
            self.iconView.setItemDelegate(self.small_icon_delegate)
            self.iconView.setViewMode(QListView.IconMode)
            self.iconView.setIconSize(QSize(24, 24))
            self.iconView.setFlow(QListView.LeftToRight)
            self.iconView.setWrapping(True)
            self.iconView.setResizeMode(QListView.Adjust)
            self.iconView.setUniformItemSizes(False)
            self.iconView.setSpacing(2)
        elif mode == 'list':
            self.iconView.setItemDelegate(self.default_delegate)
            self.iconView.setViewMode(QListView.ListMode)
            self.iconView.setIconSize(QSize(24, 24))
            self.iconView.setUniformItemSizes(True)
            self.iconView.setGridSize(QSize(0, 28))
            self.iconView.setFlow(QListView.TopToBottom)
            self.iconView.setWrapping(False)
            self.iconView.setResizeMode(QListView.Fixed)

    def _setup_tree_view_model(self):
        """
        Creates and populates the ADTreeModel for the tree view.
        """
        self.logger.debug("SADUCMainWindow: Setting up tree view model.")
        self.should_auto_expand = True
        advanced_view_enabled = self.advancedFeaturesAction.isChecked() if self.advancedFeaturesAction else False
        objects_as_containers_enabled = self.objectsAsContainersAction.isChecked() if self.objectsAsContainersAction else False
        self.adModel = ADTreeModel(self.samba_conn, self.connected_server, advanced_view=advanced_view_enabled)
        self.adModel.set_show_objects_as_containers(objects_as_containers_enabled)
        self.treePane.setModel(self.adModel)
        self.adModel.modelReset.connect(self._expand_tree_after_reset)
        self.adModel.rowsInserted.connect(self._on_rows_inserted)
        self.adModel.dragDropCompleted.connect(self._on_drag_drop_completed)
        self._expand_tree_after_reset()
        self.logger.debug("SADUCMainWindow: Tree view model set.")

    def _expand_tree_after_reset(self):
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
        self.iconView.setModel(self.tableModel)
        self.logger.debug("SADUCMainWindow: Table view model set.")

    def _on_rows_inserted(self, parent, first, last):
        """
        Automatically expand children of the domain root after they are fetched.
        """
        if not self.should_auto_expand:
            return

        saduc_root_index = self.adModel.index(0, 0, QModelIndex())
        domain_index = self.adModel.index(1, 0, saduc_root_index)
        if parent == domain_index:
            for row in range(first, last + 1):
                child_index = self.adModel.index(row, 0, parent)
                if child_index.isValid():
                    self.treePane.expand(child_index)
            self.should_auto_expand = False

    def _on_tree_item_clicked(self, index):
        """
        Slot to handle clicks on the tree view.
        It updates the table view and action pane based on the clicked item.
        """
        if not index.isValid():
            return

        tree_item = index.internalPointer()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        
        # Update the Action menu based on the selected container
        self._update_action_menu(tree_item)

        if 'saducRoot' in obj_classes:
            self.tableModel.clear_data()
            self._clear_layout(self.listActionLayout)
            self._clear_layout(self.itemActionLayout)
            self.statusBar().showMessage(self.i18n.get_string("main.status_bar_ready"))
            return

        if 'savedQueriesRoot' in obj_classes:
            self.logger.info("Saved Queries root item clicked. Showing empty list.")
            self.tableModel.clear_data()
            self._clear_layout(self.listActionLayout)
            self._clear_layout(self.itemActionLayout)
            self.statusBar().showMessage("Select a saved query to execute it.")
            return
        
        if 'savedQuery' in obj_classes:
            self.logger.info(f"Saved query item clicked: {tree_item.data()}")
            self._execute_saved_query_from_tree(tree_item)
            return

        self.currentContainerDN = tree_item.dn()
        container_name = tree_item.data()
        self.logger.info(f"Tree item clicked: '{container_name}' (DN: {self.currentContainerDN})")

        self.tableModel.clear_data()
        self._clear_layout(self.listActionLayout)
        self._clear_layout(self.itemActionLayout)
        self.statusBar().showMessage(self.i18n.get_text("status.loading", container_name))

        try:
            # Get the list of LDAP attribute names from the table model's header map
            attributes_to_fetch = [
                self.tableModel.header_map[key]
                for key in self.tableModel.get_header_keys()
                if key in self.tableModel.header_map
            ]

            list_data = get_all_objects_in_dn(self.samba_conn, self.currentContainerDN, attributes=attributes_to_fetch)

            advanced_view_enabled = self.advancedFeaturesAction.isChecked()
            self.tableModel.setData(list_data, advanced_view=advanced_view_enabled)
            self.tableModel.sort(0, Qt.AscendingOrder)
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
            "action_pane.menu.new_computer": actions.on_new_computer_action_triggered,
            "action_pane.menu.new_printer": actions.on_new_printer_action_triggered
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
    
    def _open_saved_searches_dialog(self):
        """Open the saved searches dialog."""
        try:
            dialog = SavedSearchesDialog(self)
            dialog.execute_search.connect(self._execute_saved_search)
            dialog.show()
        except Exception as e:
            self.logger.error(f"Failed to open saved searches dialog: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open saved searches dialog: {e}")
    
    def _execute_saved_search(self, search_data):
        """Execute a saved search from the saved searches dialog."""
        try:
            from find_dialog import FindObjectsDialog
            
            # Create a find dialog and populate it with the search data
            find_dialog = FindObjectsDialog(self.samba_conn, self.currentContainerDN or "", self)
            
            # TODO: Set the search parameters in the find dialog
            # This would require extending FindObjectsDialog to accept search data
            find_dialog.show()
            
            self.logger.info(f"Executing saved search: {search_data.get('name', 'Unknown')}")
            
        except Exception as e:
            self.logger.error(f"Failed to execute saved search: {e}")
            QMessageBox.critical(self, "Error", f"Failed to execute saved search: {e}")
    
    def _execute_saved_query_from_tree(self, tree_item):
        """Execute a saved query directly from tree selection."""
        try:
            # Extract search name from the DN
            search_name = tree_item.data()
            
            # Load the search data
            search_data = config_manager.load_search(search_name)
            if not search_data:
                QMessageBox.warning(self, "Error", f"Could not load saved search '{search_name}'.")
                return
            
            # Execute the search and display results in the main list
            self._execute_search_in_main_list(search_data)
            
            # Update status bar
            self.statusBar().showMessage(f"Executed saved query: {search_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to execute saved query from tree: {e}")
            QMessageBox.critical(self, "Error", f"Failed to execute saved query: {e}")
    
    def _execute_search_in_main_list(self, search_data):
        """Execute a search and display results in the main object list."""
        try:
            from samba_backend import get_paged_results
            import ldap
            
            # Extract search parameters
            ldap_filter = search_data.get('filter', '(objectClass=*)')
            search_base = search_data.get('searchBase', 'auto')
            attributes = search_data.get('attributes', ['cn', 'displayName', 'description', 'distinguishedName', 'objectClass'])
            
            # Ensure objectClass is always included for proper type detection
            if 'objectClass' not in attributes:
                attributes.append('objectClass')
            
            # Use current domain base if search_base is 'auto'
            if search_base == 'auto':
                from samba_backend import get_base_dn
                search_base = get_base_dn(self.samba_conn)
            
            self.logger.info(f"Executing search: filter='{ldap_filter}', base='{search_base}'")
            
            # Perform the search
            results = get_paged_results(self.samba_conn, search_base, ldap.SCOPE_SUBTREE, ldap_filter, attributes)
            
            # Process results for display
            objects = []
            for dn, attrs in results:
                if dn is None:
                    continue
                    
                obj = {'dn': dn}
                for attr, values in attrs.items():
                    if isinstance(values, list) and values:
                        # Decode bytes values
                        decoded_values = []
                        for value in values:
                            if isinstance(value, bytes):
                                try:
                                    decoded_values.append(value.decode('utf-8'))
                                except UnicodeDecodeError:
                                    decoded_values.append(str(value))
                            else:
                                decoded_values.append(str(value))
                        obj[attr] = decoded_values[0] if len(decoded_values) == 1 else decoded_values
                    elif values:
                        obj[attr] = values
                
                # Add proper name field that ADListModel expects
                obj['name'] = obj.get('cn', obj.get('displayName', obj.get('sAMAccountName', 'Unknown')))
                
                # Ensure objectClass is a list for ADListModel._get_object_type()
                object_classes = obj.get('objectClass', [])
                if isinstance(object_classes, str):
                    obj['objectClass'] = [object_classes]
                elif not isinstance(object_classes, list):
                    obj['objectClass'] = []
                
                
                objects.append(obj)
            
            # Update the table model with search results
            self.tableModel.setData(objects)
            self.logger.info(f"Search completed: found {len(objects)} objects")
            
            # Clear action panes since we're showing search results
            self._clear_layout(self.listActionLayout)
            self._clear_layout(self.itemActionLayout)
            
        except Exception as e:
            self.logger.error(f"Failed to execute search in main list: {e}")
            QMessageBox.critical(self, "Error", f"Search failed: {e}")

    def _update_action_menu(self, tree_item=None):
        """Update the Action menu to match the current container context."""
        # Clear current Action menu
        self.actionMenu.clear()
        
        if not tree_item:
            # Get currently selected tree item
            current_index = self.treePane.currentIndex()
            if not current_index.isValid():
                return
            tree_item = current_index.internalPointer()
            if not tree_item:
                return
        
        current_dn = tree_item.dn()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        
        # Import actions here to avoid circular imports
        import main_window_actions as actions
        from functools import partial
        
        # Build the same menu as the context menu for this container type
        if 'saducRoot' in obj_classes:
            self._populate_saduc_root_action_menu(current_dn)
        elif 'savedQueriesRoot' in obj_classes:
            self._populate_saved_queries_action_menu(current_dn)
        elif 'savedQueriesFolder' in obj_classes:
            self._populate_saved_queries_folder_action_menu(current_dn)
        elif 'domainDns' in obj_classes:
            self._populate_domain_action_menu(current_dn)
        elif 'organizationalUnit' in obj_classes:
            self._populate_ou_action_menu(current_dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._populate_container_action_menu(current_dn)
    
    def _populate_saduc_root_action_menu(self, dn):
        """Populate Action menu for SADUC root."""
        import main_window_actions as actions
        from functools import partial
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self))
        self.actionMenu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self))
        self.actionMenu.addSeparator()
        self.actionMenu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self))
        self.actionMenu.addAction(self.i18n.get_string("context_menu.export_list"), partial(actions.on_export_list_action_triggered, self))
    
    def _populate_saved_queries_action_menu(self, dn):
        """Populate Action menu for saved queries root."""
        import main_window_actions as actions
        from functools import partial
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self))
        self.actionMenu.addSeparator()
        
        new_menu = self.actionMenu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self))
        
        self.actionMenu.addSeparator()
        self.actionMenu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self))
    
    def _populate_saved_queries_folder_action_menu(self, dn):
        """Populate Action menu for saved queries folder."""
        import main_window_actions as actions
        from functools import partial
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self))
        self.actionMenu.addSeparator()
        
        new_menu = self.actionMenu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self))
        
        self.actionMenu.addSeparator()
        self.actionMenu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self))
    
    def _populate_domain_action_menu(self, dn):
        """Populate Action menu for domain container."""
        import main_window_actions as actions
        from functools import partial
        from PyQt5.QtWidgets import QAction
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self, dn))
        self.actionMenu.addAction(find_action)
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self))
        self.actionMenu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self))
        self.actionMenu.addAction(self.i18n.get_string("context_menu.raise_domain_level"), partial(actions.on_raise_domain_functional_level_action_triggered, self))
        self.actionMenu.addAction(self.i18n.get_string("context_menu.operations_masters"), partial(actions.on_operations_masters_action_triggered, self))
        self.actionMenu.addSeparator()
        
        new_menu = self.actionMenu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_action_menu(new_menu)
        
        self.actionMenu.addSeparator()
        self.actionMenu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self))
    
    def _populate_ou_action_menu(self, dn):
        """Populate Action menu for OU container."""
        import main_window_actions as actions
        from functools import partial
        from PyQt5.QtWidgets import QAction
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self))
        self.actionMenu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self, dn))
        self.actionMenu.addAction(find_action)
        
        self.actionMenu.addSeparator()
        new_menu = self.actionMenu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_action_menu(new_menu)
        
        self.actionMenu.addSeparator()
        self.actionMenu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self))
    
    def _populate_container_action_menu(self, dn):
        """Populate Action menu for regular container."""
        import main_window_actions as actions
        from functools import partial
        from PyQt5.QtWidgets import QAction
        
        self.actionMenu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self, dn))
        self.actionMenu.addAction(find_action)
        
        self.actionMenu.addSeparator()
        new_menu = self.actionMenu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_action_menu(new_menu, is_container=True)
        
        self.actionMenu.addSeparator()
        self.actionMenu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self))
    
    def _populate_new_action_menu(self, new_menu, is_container=False):
        """Populate the New submenu in Action menu."""
        import main_window_actions as actions
        from functools import partial
        from samba_backend import get_schema_structural_classes
        
        # Add standard object types
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_computer"), partial(actions.on_new_computer_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("context_menu.new_contact"), partial(actions.on_new_contact_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_group"), partial(actions.on_new_group_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("context_menu.new_inetorgperson"), partial(actions.on_new_inetorgperson_action_triggered, self))
        if not is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_ou"), partial(actions.on_new_ou_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_printer"), partial(actions.on_new_printer_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("context_menu.new_shared_folder"), partial(actions.on_new_shared_folder_action_triggered, self))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_user"), partial(actions.on_new_user_action_triggered, self))
        
        # Add dynamic schema-extended objects
        try:
            if hasattr(self, 'samba_conn') and self.samba_conn:
                structural_classes = get_schema_structural_classes(self.samba_conn)
                if structural_classes:
                    new_menu.addSeparator()
                    for class_info in structural_classes:
                        menu_text = f"{class_info['display_name']}..."
                        action = partial(
                            actions.on_new_generic_object_action_triggered,
                            self,
                            class_info['class_name'],
                            class_info['display_name'],
                            class_info['naming_attribute'],
                            class_info.get('is_complex', False),
                            class_info.get('required_attributes', None)
                        )
                        new_menu.addAction(menu_text, action)
        except Exception as e:
            self.logger.warning(f"Could not load schema extensions for menu: {e}")

    def _on_drag_drop_completed(self, success_count, total_count, message):
        """Handle drag and drop completion signal from tree model."""
        from PyQt5.QtWidgets import QMessageBox
        
        if success_count == total_count and success_count > 0:
            # All successful
            QMessageBox.information(self, self.i18n.get_string("dialog.common.success.title"), message)
        elif success_count > 0:
            # Partial success
            QMessageBox.warning(self, "Partial Success", message)
        else:
            # All failed
            QMessageBox.critical(self, self.i18n.get_string("dialog.common.error.title"), message)
        
        # Refresh the current container to reflect changes
        self.refresh_current_container()

