from PyQt5.QtWidgets import QMenu, QAction
from functools import partial
import main_window_actions as actions

UAC_ACCOUNT_DISABLED = 0x0002

class ListMenuManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.i18n = main_window.i18n

    def on_list_context_menu(self, position):
        self.main_window.logger.info("List context menu requested.")
        index = self.main_window.listPane.indexAt(position)
        menu = QMenu()
        
        if not index.isValid():
            # Right-click on empty space - show container menu
            self._build_container_context_menu(menu)
        else:
            selected_object_data = self.main_window.tableModel.get_object_data(index)
            if not selected_object_data:
                self.main_window.logger.warning("No valid data for selected table item.")
                return

            obj_classes = selected_object_data.get('objectClass', [])

            if 'user' in obj_classes and 'computer' not in obj_classes:
                self._build_user_menu(menu, selected_object_data)
            elif 'computer' in obj_classes:
                self._build_computer_menu(menu, selected_object_data)
            elif 'group' in obj_classes:
                self._build_group_menu(menu)
            elif 'contact' in obj_classes:
                self._build_contact_menu(menu)

        if not menu.isEmpty():
            menu.exec_(self.main_window.listPane.viewport().mapToGlobal(position))

    def _build_user_menu(self, menu, user_data):
        uac = int(user_data.get('userAccountControl', '0'))
        is_disabled = bool(uac & UAC_ACCOUNT_DISABLED)

        menu.addAction(self.i18n.get_string("context_menu.copy"), partial(actions.on_copy_user_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.remove_from_group"), partial(actions.on_remove_from_group_action_triggered, self.main_window))
        
        if is_disabled:
            menu.addAction(self.i18n.get_string("context_menu.enable_account"), partial(actions.on_enable_user_action_triggered, self.main_window))
        else:
            menu.addAction(self.i18n.get_string("context_menu.disable_account"), partial(actions.on_disable_user_action_triggered, self.main_window))

        menu.addAction(self.i18n.get_string("context_menu.reset_password"), partial(actions.on_reset_password_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.open_home_page"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.send_mail"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addSeparator()
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.cut"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.delete"), partial(actions.on_delete_user_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.rename"), partial(actions.on_rename_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_container_context_menu(self, menu):
        """Build context menu for empty space (container actions) - should match the tree container menu."""
        # Get the currently selected tree item to determine what container we're in
        current_tree_index = self.main_window.treePane.currentIndex()
        if not current_tree_index.isValid():
            return
        
        tree_item = current_tree_index.internalPointer()
        if not tree_item:
            return
            
        current_dn = tree_item.dn()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        
        # Build the same menu as the tree context menu for this container type
        if 'saducRoot' in obj_classes:
            self._build_saduc_root_container_menu(menu, current_dn)
        elif 'savedQueriesRoot' in obj_classes:
            self._build_saved_queries_container_menu(menu, current_dn)
        elif 'savedQueriesFolder' in obj_classes:
            self._build_saved_queries_folder_container_menu(menu, current_dn)
        elif 'domainDns' in obj_classes:
            self._build_domain_container_menu(menu, current_dn)
        elif 'organizationalUnit' in obj_classes:
            self._build_ou_container_menu(menu, current_dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._build_ldap_container_menu(menu, current_dn)
    
    def _build_saduc_root_container_menu(self, menu, dn):
        """Build menu for SADUC root container."""
        menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        menu.addSeparator()
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.export_list"), partial(actions.on_export_list_action_triggered, self.main_window))
    
    def _build_saved_queries_container_menu(self, menu, dn):
        """Build menu for saved queries root container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_saved_queries_folder_container_menu(self, menu, dn):
        """Build menu for saved queries folder container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_domain_container_menu(self, menu, dn):
        """Build menu for domain container."""
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
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ou_container_menu(self, menu, dn):
        """Build menu for OU container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ldap_container_menu(self, menu, dn):
        """Build menu for regular LDAP container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu, is_container=True)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _populate_new_menu(self, new_menu, is_container=False):
        """Populate the New submenu with object creation options."""
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_computer"), partial(actions.on_new_computer_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_contact"), partial(actions.on_new_contact_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_group"), partial(actions.on_new_group_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_inetorgperson"), partial(actions.on_new_inetorgperson_action_triggered, self.main_window))
        if not is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_ou"), partial(actions.on_new_ou_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_user"), partial(actions.on_new_user_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_shared_folder"), partial(actions.on_new_shared_folder_action_triggered, self.main_window))
    
    def _populate_view_menu(self, view_menu):
        """Populate the View submenu with view options."""
        view_menu.addAction(self.i18n.get_string("context_menu.view_add_remove_columns"), partial(actions.on_view_add_remove_columns_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_large_icons"), partial(actions.on_view_large_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_small_icons"), partial(actions.on_view_small_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_list"), partial(actions.on_view_list_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_detail"), partial(actions.on_view_detail_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_filter_options"), partial(actions.on_view_filter_options_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_customize"), partial(actions.on_view_customize_action_triggered, self.main_window))

    def _build_computer_menu(self, menu, selected_object_data):
        uac = int(selected_object_data.get('userAccountControl', '0'))
        is_dc = bool(uac & 8192)  # UAC_SERVER_TRUST_ACCOUNT
        is_disabled = bool(uac & UAC_ACCOUNT_DISABLED)

        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.remove_from_group"), partial(actions.on_remove_from_group_action_triggered, self.main_window))
        
        if not is_dc:
            if is_disabled:
                menu.addAction(self.i18n.get_string("context_menu.enable_account"), partial(actions.on_enable_computer_action_triggered, self.main_window))
            else:
                menu.addAction(self.i18n.get_string("context_menu.disable_account"), partial(actions.on_disable_computer_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.reset_account"), partial(actions.on_reset_account_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        menu.addSeparator()
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.cut"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.delete"), partial(actions.on_delete_user_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_container_context_menu(self, menu):
        """Build context menu for empty space (container actions) - should match the tree container menu."""
        # Get the currently selected tree item to determine what container we're in
        current_tree_index = self.main_window.treePane.currentIndex()
        if not current_tree_index.isValid():
            return
        
        tree_item = current_tree_index.internalPointer()
        if not tree_item:
            return
            
        current_dn = tree_item.dn()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        
        # Build the same menu as the tree context menu for this container type
        if 'saducRoot' in obj_classes:
            self._build_saduc_root_container_menu(menu, current_dn)
        elif 'savedQueriesRoot' in obj_classes:
            self._build_saved_queries_container_menu(menu, current_dn)
        elif 'savedQueriesFolder' in obj_classes:
            self._build_saved_queries_folder_container_menu(menu, current_dn)
        elif 'domainDns' in obj_classes:
            self._build_domain_container_menu(menu, current_dn)
        elif 'organizationalUnit' in obj_classes:
            self._build_ou_container_menu(menu, current_dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._build_ldap_container_menu(menu, current_dn)
    
    def _build_saduc_root_container_menu(self, menu, dn):
        """Build menu for SADUC root container."""
        menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        menu.addSeparator()
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.export_list"), partial(actions.on_export_list_action_triggered, self.main_window))
    
    def _build_saved_queries_container_menu(self, menu, dn):
        """Build menu for saved queries root container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_saved_queries_folder_container_menu(self, menu, dn):
        """Build menu for saved queries folder container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_domain_container_menu(self, menu, dn):
        """Build menu for domain container."""
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
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ou_container_menu(self, menu, dn):
        """Build menu for OU container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ldap_container_menu(self, menu, dn):
        """Build menu for regular LDAP container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu, is_container=True)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _populate_new_menu(self, new_menu, is_container=False):
        """Populate the New submenu with object creation options."""
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_computer"), partial(actions.on_new_computer_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_contact"), partial(actions.on_new_contact_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_group"), partial(actions.on_new_group_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_inetorgperson"), partial(actions.on_new_inetorgperson_action_triggered, self.main_window))
        if not is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_ou"), partial(actions.on_new_ou_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_user"), partial(actions.on_new_user_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_shared_folder"), partial(actions.on_new_shared_folder_action_triggered, self.main_window))
    
    def _populate_view_menu(self, view_menu):
        """Populate the View submenu with view options."""
        view_menu.addAction(self.i18n.get_string("context_menu.view_add_remove_columns"), partial(actions.on_view_add_remove_columns_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_large_icons"), partial(actions.on_view_large_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_small_icons"), partial(actions.on_view_small_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_list"), partial(actions.on_view_list_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_detail"), partial(actions.on_view_detail_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_filter_options"), partial(actions.on_view_filter_options_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_customize"), partial(actions.on_view_customize_action_triggered, self.main_window))

    def _build_group_menu(self, menu):
        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.remove_from_group"), partial(actions.on_remove_from_group_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.send_mail"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addSeparator()
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.cut"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.delete"), partial(actions.on_delete_user_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.rename"), partial(actions.on_rename_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_container_context_menu(self, menu):
        """Build context menu for empty space (container actions) - should match the tree container menu."""
        # Get the currently selected tree item to determine what container we're in
        current_tree_index = self.main_window.treePane.currentIndex()
        if not current_tree_index.isValid():
            return
        
        tree_item = current_tree_index.internalPointer()
        if not tree_item:
            return
            
        current_dn = tree_item.dn()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        
        # Build the same menu as the tree context menu for this container type
        if 'saducRoot' in obj_classes:
            self._build_saduc_root_container_menu(menu, current_dn)
        elif 'savedQueriesRoot' in obj_classes:
            self._build_saved_queries_container_menu(menu, current_dn)
        elif 'savedQueriesFolder' in obj_classes:
            self._build_saved_queries_folder_container_menu(menu, current_dn)
        elif 'domainDns' in obj_classes:
            self._build_domain_container_menu(menu, current_dn)
        elif 'organizationalUnit' in obj_classes:
            self._build_ou_container_menu(menu, current_dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._build_ldap_container_menu(menu, current_dn)
    
    def _build_saduc_root_container_menu(self, menu, dn):
        """Build menu for SADUC root container."""
        menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        menu.addSeparator()
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.export_list"), partial(actions.on_export_list_action_triggered, self.main_window))
    
    def _build_saved_queries_container_menu(self, menu, dn):
        """Build menu for saved queries root container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_saved_queries_folder_container_menu(self, menu, dn):
        """Build menu for saved queries folder container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_domain_container_menu(self, menu, dn):
        """Build menu for domain container."""
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
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ou_container_menu(self, menu, dn):
        """Build menu for OU container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ldap_container_menu(self, menu, dn):
        """Build menu for regular LDAP container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu, is_container=True)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _populate_new_menu(self, new_menu, is_container=False):
        """Populate the New submenu with object creation options."""
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_computer"), partial(actions.on_new_computer_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_contact"), partial(actions.on_new_contact_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_group"), partial(actions.on_new_group_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_inetorgperson"), partial(actions.on_new_inetorgperson_action_triggered, self.main_window))
        if not is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_ou"), partial(actions.on_new_ou_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_user"), partial(actions.on_new_user_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_shared_folder"), partial(actions.on_new_shared_folder_action_triggered, self.main_window))
    
    def _populate_view_menu(self, view_menu):
        """Populate the View submenu with view options."""
        view_menu.addAction(self.i18n.get_string("context_menu.view_add_remove_columns"), partial(actions.on_view_add_remove_columns_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_large_icons"), partial(actions.on_view_large_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_small_icons"), partial(actions.on_view_small_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_list"), partial(actions.on_view_list_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_detail"), partial(actions.on_view_detail_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_filter_options"), partial(actions.on_view_filter_options_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_customize"), partial(actions.on_view_customize_action_triggered, self.main_window))

    def _build_contact_menu(self, menu):
        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.remove_from_group"), partial(actions.on_remove_from_group_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.open_home_page"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.send_mail"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addSeparator()
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.cut"), partial(actions.on_stub_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.delete"), partial(actions.on_delete_user_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.rename"), partial(actions.on_rename_action_triggered, self.main_window))
        menu.addSeparator()
        properties_action = QAction(self.i18n.get_string("context_menu.properties"), self.main_window)
        font = properties_action.font()
        font.setBold(True)
        properties_action.setFont(font)
        properties_action.triggered.connect(partial(actions.on_properties_action_triggered, self.main_window))
        menu.addAction(properties_action)

    def _build_container_context_menu(self, menu):
        """Build context menu for empty space (container actions) - should match the tree container menu."""
        # Get the currently selected tree item to determine what container we're in
        current_tree_index = self.main_window.treePane.currentIndex()
        if not current_tree_index.isValid():
            return
        
        tree_item = current_tree_index.internalPointer()
        if not tree_item:
            return
            
        current_dn = tree_item.dn()
        obj_classes = tree_item.object_class() if isinstance(tree_item.object_class(), list) else [tree_item.object_class()]
        
        # Build the same menu as the tree context menu for this container type
        if 'saducRoot' in obj_classes:
            self._build_saduc_root_container_menu(menu, current_dn)
        elif 'savedQueriesRoot' in obj_classes:
            self._build_saved_queries_container_menu(menu, current_dn)
        elif 'savedQueriesFolder' in obj_classes:
            self._build_saved_queries_folder_container_menu(menu, current_dn)
        elif 'domainDns' in obj_classes:
            self._build_domain_container_menu(menu, current_dn)
        elif 'organizationalUnit' in obj_classes:
            self._build_ou_container_menu(menu, current_dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._build_ldap_container_menu(menu, current_dn)
    
    def _build_saduc_root_container_menu(self, menu, dn):
        """Build menu for SADUC root container."""
        menu.addAction(self.i18n.get_string("context_menu.change_domain"), partial(actions.on_change_domain_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("action_pane.menu.change_dc"), partial(actions.on_change_dc_action_triggered, self.main_window))
        menu.addSeparator()
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.export_list"), partial(actions.on_export_list_action_triggered, self.main_window))
    
    def _build_saved_queries_container_menu(self, menu, dn):
        """Build menu for saved queries root container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_saved_queries_folder_container_menu(self, menu, dn):
        """Build menu for saved queries folder container."""
        menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
        menu.addSeparator()
        
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        new_menu.addAction(self.i18n.get_string("context_menu.new_query"), partial(actions.on_new_query_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_folder"), partial(actions.on_new_folder_action_triggered, self.main_window))
        
        view_menu = menu.addMenu(self.i18n.get_string("context_menu.view"))
        self._populate_view_menu(view_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_domain_container_menu(self, menu, dn):
        """Build menu for domain container."""
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
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ou_container_menu(self, menu, dn):
        """Build menu for OU container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.move"), partial(actions.on_move_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _build_ldap_container_menu(self, menu, dn):
        """Build menu for regular LDAP container."""
        menu.addAction(self.i18n.get_string("context_menu.delegate_control"), partial(actions.on_delegate_control_action_triggered, self.main_window))
        
        find_action = QAction(self.i18n.get_string("action_pane.menu.find_user"), self.main_window)
        find_action.triggered.connect(lambda: actions.on_find_user_action_triggered(self.main_window, dn))
        menu.addAction(find_action)
        
        menu.addSeparator()
        new_menu = menu.addMenu(self.i18n.get_string("context_menu.new"))
        self._populate_new_menu(new_menu, is_container=True)
        
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
    
    def _populate_new_menu(self, new_menu, is_container=False):
        """Populate the New submenu with object creation options."""
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_computer"), partial(actions.on_new_computer_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_contact"), partial(actions.on_new_contact_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_group"), partial(actions.on_new_group_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_inetorgperson"), partial(actions.on_new_inetorgperson_action_triggered, self.main_window))
        if not is_container:
            new_menu.addAction(self.i18n.get_string("context_menu.new_ou"), partial(actions.on_new_ou_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("action_pane.menu.new_user"), partial(actions.on_new_user_action_triggered, self.main_window))
        new_menu.addAction(self.i18n.get_string("context_menu.new_shared_folder"), partial(actions.on_new_shared_folder_action_triggered, self.main_window))
    
    def _populate_view_menu(self, view_menu):
        """Populate the View submenu with view options."""
        view_menu.addAction(self.i18n.get_string("context_menu.view_add_remove_columns"), partial(actions.on_view_add_remove_columns_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_large_icons"), partial(actions.on_view_large_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_small_icons"), partial(actions.on_view_small_icons_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_list"), partial(actions.on_view_list_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_detail"), partial(actions.on_view_detail_action_triggered, self.main_window))
        view_menu.addSeparator()
        view_menu.addAction(self.i18n.get_string("context_menu.view_filter_options"), partial(actions.on_view_filter_options_action_triggered, self.main_window))
        view_menu.addAction(self.i18n.get_string("context_menu.view_customize"), partial(actions.on_view_customize_action_triggered, self.main_window))