from PyQt5.QtWidgets import QMenu, QAction
from functools import partial
import main_window_actions as actions

class ListMenuManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.i18n = main_window.i18n

    def on_list_context_menu(self, position):
        self.main_window.logger.info("List context menu requested.")
        index = self.main_window.listPane.indexAt(position)
        if not index.isValid():
            return

        selected_object_data = self.main_window.tableModel.get_object_data(index)
        if not selected_object_data:
            self.main_window.logger.warning("No valid data for selected table item.")
            return

        obj_classes = selected_object_data.get('objectClass', [])
        menu = QMenu()

        if 'user' in obj_classes and 'computer' not in obj_classes:
            self._build_user_menu(menu)
        elif 'computer' in obj_classes:
            self._build_computer_menu(menu, selected_object_data)
        elif 'group' in obj_classes:
            self._build_group_menu(menu)
        elif 'contact' in obj_classes:
            self._build_contact_menu(menu)

        if not menu.isEmpty():
            menu.exec_(self.main_window.listPane.viewport().mapToGlobal(position))

    def _build_user_menu(self, menu):
        menu.addAction(self.i18n.get_string("context_menu.copy"), partial(actions.on_copy_user_action_triggered, self.main_window))
        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
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

    def _build_computer_menu(self, menu, selected_object_data):
        uac = int(selected_object_data.get('userAccountControl', '0'))
        is_dc = bool(uac & 8192)  # UAC_SERVER_TRUST_ACCOUNT

        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
        if not is_dc:
            menu.addAction(self.i18n.get_string("context_menu.disable_account"), partial(actions.on_disable_user_action_triggered, self.main_window))
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

    def _build_group_menu(self, menu):
        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
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

    def _build_contact_menu(self, menu):
        menu.addAction(self.i18n.get_string("context_menu.add_to_group"), partial(actions.on_add_to_group_action_triggered, self.main_window))
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