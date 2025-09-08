from PyQt5.QtWidgets import QMenu, QAction
from functools import partial
import main_window_actions as actions

class TreeMenuManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.i18n = main_window.i18n

    def on_tree_context_menu(self, position):
        self.main_window.logger.info("Tree context menu requested.")
        index = self.main_window.treePane.indexAt(position)
        if not index.isValid():
            return

        tree_item = index.internalPointer()
        dn = tree_item.dn()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        menu = QMenu()

        if 'saducRoot' in obj_classes:
            self._build_saduc_root_menu(menu, dn)
        elif 'savedQueriesRoot' in obj_classes:
            self._build_saved_queries_menu(menu, dn)
        elif 'savedQueriesFolder' in obj_classes:
            self._build_saved_queries_folder_menu(menu, dn)
        elif 'savedQuery' in obj_classes:
            self._build_saved_query_item_menu(menu, dn, tree_item)
        elif 'domainDns' in obj_classes:
            self._build_domain_menu(menu, dn)
        elif 'organizationalUnit' in obj_classes:
            self._build_ou_menu(menu, dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._build_container_menu(menu, dn)

        if not menu.isEmpty():
            # Get the global position  
            global_pos = self.main_window.treePane.viewport().mapToGlobal(position)

            # If click is in bottom quarter of the tree view, show menu above click point
            viewport_height = self.main_window.treePane.viewport().height()
            if position.y() > viewport_height * 0.75:  # Bottom quarter
                menu_size = menu.sizeHint()
                global_pos.setY(global_pos.y() - menu_size.height())

            menu.exec_(global_pos)

    def _populate_view_menu(self, view_menu):
        view_menu.addAction(self.i18n.get_string("context_menu.view_add_remove_columns"), partial(actions.on_view_add_remove_columns_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_large_icons"), partial(actions.on_view_large_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_small_icons"), partial(actions.on_view_small_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_list"), partial(actions.on_view_list_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_detail"), partial(actions.on_view_detail_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_filter_options"), partial(actions.on_view_filter_options_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_customize"), partial(actions.on_view_customize_action_triggered, self.main_window))

    def _build_saduc_root_menu(self, menu, dn):
        menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        menu.addSeparator()
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'saducRoot')
        menu.addSeparator()
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.export_list"), partial(actions.on_export_list_action_triggered, self.main_window))

    def _build_saved_queries_menu(self, menu, dn):
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'savedQueriesRoot')
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_container_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_saved_queries_folder_menu(self, menu, dn):
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'savedQueriesFolder')
        menu.addSeparator()
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.cut"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.copy"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.delete"), partial(actions.on_delete_saved_queries_folder_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.rename"), partial(actions.on_rename_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_container_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_domain_menu(self, menu, dn):
        self.main_window.currentContainerDN = dn
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.raise_domain_level"), partial(actions.on_raise_domain_functional_level_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.operations_masters"), partial(actions.on_operations_masters_action_triggered, self.main_window))
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu)
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'domainDns')
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_container_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_container_menu(self, menu, dn):
        self.main_window.currentContainerDN = dn
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu, is_container=True)
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'container')
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_container_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_ou_menu(self, menu, dn):
        self.main_window.currentContainerDN = dn
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu)
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'organizationalUnit')
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.cut"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.delete"), partial(actions.on_delete_container_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.rename"), partial(actions.on_rename_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_container_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _populate_new_menu(self, new_menu, is_container=False):
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_computer"), partial(actions.on_new_computer_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_contact"), partial(actions.on_new_contact_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_group"), partial(actions.on_new_group_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_inetorgperson"), partial(actions.on_new_inetorgperson_action_triggered, self.main_window))
        if is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_msds_keycredential"), partial(actions.on_new_msds_keycredential_action_triggered, self.main_window))
            new_menu.addAction(self.i18n.get_string("context_menu.new_msds_resourcepropertylist"), partial(actions.on_new_msds_resourcepropertylist_action_triggered, self.main_window))
            new_menu.addAction(self.i18n.get_string("context_menu.new_msds_shadowprincipalcontainer"), partial(actions.on_new_msds_shadowprincipalcontainer_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_msimaging_psps"), partial(actions.on_new_msimaging_psps_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_msmq_queue_alias"), partial(actions.on_new_msmq_queue_alias_action_triggered, self.main_window))
        if not is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_ou"), partial(actions.on_new_ou_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_user"), partial(actions.on_new_user_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_shared_folder"), partial(actions.on_new_shared_folder_action_triggered, self.main_window))

    def _populate_all_tasks_menu(self, all_tasks_menu, dn, object_type):
        # This is a generic placeholder. You can customize this based on object_type.
        if object_type in ['domainDns', 'organizationalUnit', 'container']:
            all_tasks_menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        if object_type == 'domainDns':
            all_tasks_menu.addAction(self.i18n.get_string("context_menu.raise_domain_level"), partial(actions.on_raise_domain_functional_level_action_triggered, self.main_window))
            all_tasks_menu.addAction(self.i18n.get_string("context_menu.operations_masters"), partial(actions.on_operations_masters_action_triggered, self.main_window))
        if object_type == 'saducRoot':
            all_tasks_menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
            all_tasks_menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        if object_type in ['savedQueriesRoot', 'savedQueriesFolder']:
            all_tasks_menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
            new_query_action = all_tasks_menu.addAction(self.i18n.get_string("context_menu.new_query"))
            new_query_action.triggered.connect(partial(actions.on_new_query_action_triggered, self.main_window))
            if object_type == 'savedQueriesFolder':
                all_tasks_menu.addSeparator()

    def _build_saved_query_item_menu(self, menu, dn, tree_item):
        """Build context menu for individual saved query items."""
        search_name = tree_item.data()

        # Execute action (bold, default)
        execute_action = QAction(f"Execute '{search_name}'", self.main_window)
        font = execute_action.font()
        font.setBold(True)
        execute_action.setFont(font)
        execute_action.triggered.connect(lambda: self.main_window._execute_saved_query_from_tree(tree_item))
        menu.addAction(execute_action)

        menu.addSeparator()

        # Management actions
        menu.addAction("Rename...", lambda: self._rename_saved_query(search_name))
        menu.addAction("Delete", lambda: self._delete_saved_query(search_name))

        menu.addSeparator()
        menu.addAction("Properties", lambda: self._show_saved_query_properties(search_name))

    def _rename_saved_query(self, old_name):
        """Rename a saved query."""
        from PyQt5.QtWidgets import QInputDialog
        from sagui_config import config_manager

        new_name, ok = QInputDialog.getText(
            self.main_window, "Rename Saved Query",
            f"Enter new name for '{old_name}':",
            text=old_name
        )

        if ok and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            try:
                # Load search data
                search_data = config_manager.load_search(old_name)
                if search_data:
                    # Save with new name
                    search_data['name'] = new_name
                    if config_manager.save_search(new_name, search_data):
                        # Delete old search
                        config_manager.delete_search(old_name)

                        # Refresh tree
                        self.main_window.treeModel.reset_and_fetch_root_info()

                        self.main_window.statusBar().showMessage(f"Renamed saved query to '{new_name}'")
                    else:
                        from PyQt5.QtWidgets import QMessageBox
                        QMessageBox.warning(self.main_window, "Error", "Failed to rename saved query.")

            except Exception as e:
                from PyQt5.QtWidgets import QMessageBox
                self.main_window.logger.error(f"Failed to rename saved query '{old_name}': {e}")
                QMessageBox.critical(self.main_window, "Error", f"Failed to rename saved query: {e}")

    def _delete_saved_query(self, search_name):
        """Delete a saved query."""
        from PyQt5.QtWidgets import QMessageBox
        from sagui_config import config_manager

        # Confirm deletion
        reply = QMessageBox.question(
            self.main_window, "Confirm Delete",
            f"Are you sure you want to delete the saved query '{search_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                if config_manager.delete_search(search_name):
                    # Refresh tree
                    self.main_window.treeModel.reset_and_fetch_root_info()
                    self.main_window.statusBar().showMessage(f"Deleted saved query '{search_name}'")
                else:
                    QMessageBox.warning(self.main_window, "Error", "Failed to delete saved query.")
            except Exception as e:
                self.main_window.logger.error(f"Failed to delete saved query '{search_name}': {e}")
                QMessageBox.critical(self.main_window, "Error", f"Failed to delete saved query: {e}")

    def _show_saved_query_properties(self, search_name):
        """Show properties dialog for a saved query."""
        from PyQt5.QtWidgets import QMessageBox
        from sagui_config import config_manager

        try:
            search_data = config_manager.load_search(search_name)
            if search_data:
                # Create a simple properties message
                props = f"""Name: {search_data.get('name', 'Unknown')}
Description: {search_data.get('description', 'No description')}
Object Class: {search_data.get('objectClass', 'Unknown')}
Search Base: {search_data.get('searchBase', 'Unknown')}
LDAP Filter: {search_data.get('filter', 'No filter')}
Attributes: {', '.join(search_data.get('attributes', []))}
Created: {search_data.get('created', 'Unknown')}
Last Used: {search_data.get('lastUsed', 'Unknown')}"""

                QMessageBox.information(self.main_window, f"Properties: {search_name}", props)
            else:
                QMessageBox.warning(self.main_window, "Error", "Could not load saved query properties.")

        except Exception as e:
            self.main_window.logger.error(f"Failed to show properties for '{search_name}': {e}")
            QMessageBox.critical(self.main_window, "Error", f"Failed to show properties: {e}")
