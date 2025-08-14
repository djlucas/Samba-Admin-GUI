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
        elif 'domainDns' in obj_classes:
            self._build_domain_menu(menu, dn)
        elif 'organizationalUnit' in obj_classes:
            self._build_ou_menu(menu, dn)
        elif 'container' in obj_classes or 'builtinDomain' in obj_classes:
            self._build_container_menu(menu, dn)

        if not menu.isEmpty():
            menu.exec_(self.main_window.treePane.viewport().mapToGlobal(position))

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
        all_tasks_menu = menu.addMenu(self.i18n.get_string("context_menu.all_tasks"))
        self._populate_all_tasks_menu(all_tasks_menu, dn, 'savedQueriesRoot')
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.refresh"), partial(actions.on_refresh_action_triggered, self.main_window))
        menu.addSeparator()
        menu.addAction(self.i18n.get_string("context_menu.properties"), partial(actions.on_container_properties_action_triggered, self.main_window))

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
        menu.addAction(self.i18n.get_string("context_menu.properties"), partial(actions.on_container_properties_action_triggered, self.main_window))

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
        menu.addAction(self.i18n.get_string("context_menu.properties"), partial(actions.on_container_properties_action_triggered, self.main_window))

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
        new_menu.addAction(self.i18n.get_string("context_menu.new_printer"), partial(actions.on_new_printer_action_triggered, self.main_window))
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
        if object_type == 'savedQueriesRoot':
            all_tasks_menu.addAction(self.i18n.get_string("context_menu.import_query"), partial(actions.on_import_query_definition_action_triggered, self.main_window))
            new_query_action = all_tasks_menu.addAction(self.i18n.get_string("context_menu.new_query"))
            new_query_action.triggered.connect(partial(actions.on_new_query_action_triggered, self.main_window))
