
import logging
from PyQt5.QtWidgets import QDialog, QMessageBox
from PyQt5.QtCore import Qt
from user_dialogs import NewUserWizard, CopyUserWizard, DeleteUserDialog, DisableUserDialog, NewGroupDialog, EnableUserDialog
from samba_backend import create_user_samba, copy_user_samba, get_user_properties, create_group_samba
from user_properties import UserPropertiesDialog
from computer_properties import ComputerPropertiesDialog
from group_properties import GroupPropertiesDialog
from contact_properties import ContactPropertiesDialog
from container_properties import ContainerPropertiesDialog
from printer_properties import PrinterPropertiesDialog
from find_dialog import FindObjectsDialog
from column_editor import ColumnEditorDialog

def on_new_user_action_triggered(main_window):
    main_window.logger.info("New User action triggered. Opening NewUserWizard.")
    wizard = NewUserWizard(main_window, container_dn=main_window.currentContainerDN)
    if wizard.exec_() == QDialog.Accepted:
        main_window.logger.info("New User wizard was accepted.")
        user_data = wizard.user_data
        if user_data:
            user_data['container_dn'] = main_window.currentContainerDN
            main_window.logger.info(f"User data collected from wizard: {user_data}")
            success, message_key = create_user_samba(main_window.samba_conn, user_data)
            message = main_window.i18n.get_string(message_key)
            if success:
                QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
                main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
            else:
                QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
    else:
        main_window.logger.info("New User wizard was rejected.")

def on_copy_user_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No user selected for copy.")
        return

    source_user_props = get_user_properties(main_window.samba_conn, main_window.current_selected_dn)
    if not source_user_props:
        QMessageBox.critical(main_window, "Error", "Could not fetch properties for the source user.")
        return

    source_username = source_user_props.get('sAMAccountName', [''])[0]
    
    uac = int(source_user_props.get('userAccountControl', ['0'])[0])
    initial_data = {
        'user_must_change_password': False,
        'user_cannot_change_password': bool(uac & 0x0040),
        'password_never_expires': bool(uac & 0x10000),
        'account_is_disabled': bool(uac & 0x0002)
    }

    main_window.logger.info(f"Copy User action triggered for user: {source_username}.")
    wizard = CopyUserWizard(main_window, initial_data=initial_data, source_username=source_username, container_dn=main_window.currentContainerDN)
    if wizard.exec_() == QDialog.Accepted:
        main_window.logger.info("Copy User wizard was accepted.")
        user_data = wizard.user_data
        if user_data:
            user_data['container_dn'] = main_window.currentContainerDN
            main_window.logger.info(f"Copied user data collected from wizard: {user_data}")
            success, message_key = copy_user_samba(main_window.samba_conn, source_username, user_data)
            message = main_window.i18n.get_text(message_key, user_data.get('full_name'))
            if success:
                QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
                main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
            else:
                QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
    else:
        main_window.logger.info("Copy User wizard was rejected.")

def on_delete_user_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No user selected for deletion.")
        return

    username = main_window.tableModel.data(main_window.listPane.selectionModel().currentIndex(), Qt.DisplayRole)
    main_window.logger.info(f"Delete User action triggered for user: {username}.")
    if DeleteUserDialog(main_window, username) == QMessageBox.Yes:
        main_window.logger.info(f"User confirmed deletion of: {username}")
        QMessageBox.information(main_window, "Not Implemented", f"Backend logic to delete '{username}' is not yet implemented.")
    else:
        main_window.logger.info(f"User cancelled deletion of: {username}")

def on_disable_user_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No user selected for disabling.")
        return
        
    username = main_window.tableModel.data(main_window.listPane.selectionModel().currentIndex(), Qt.DisplayRole)
    main_window.logger.info(f"Disable User action triggered for user: {username}.")
    if DisableUserDialog(main_window, username) == QMessageBox.Yes:
        main_window.logger.info(f"User confirmed disabling account for: {username}")
        QMessageBox.information(main_window, "Not Implemented", f"Backend logic to disable '{username}' is not yet implemented.")
    else:
        main_window.logger.info(f"User cancelled disabling account for: {username}")

def on_enable_user_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No user selected for enabling.")
        return
        
    username = main_window.tableModel.data(main_window.listPane.selectionModel().currentIndex(), Qt.DisplayRole)
    main_window.logger.info(f"Enable User action triggered for user: {username}.")
    if EnableUserDialog(main_window, username) == QMessageBox.Yes:
        main_window.logger.info(f"User confirmed enabling account for: {username}")
        QMessageBox.information(main_window, "Not Implemented", f"Backend logic to enable '{username}' is not yet implemented.")
    else:
        main_window.logger.info(f"User cancelled enabling account for: {username}")

def on_properties_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No item selected for properties.")
        return

    index = main_window.listPane.selectionModel().currentIndex()
    selected_object_data = main_window.tableModel.get_object_data(index)
    obj_classes = selected_object_data.get('objectClass', [])
    advanced_view_enabled = main_window.advancedFeaturesAction.isChecked()

    dialog = None
    if 'user' in obj_classes and 'computer' not in obj_classes:
        dialog = UserPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view_enabled, main_window)
    elif 'computer' in obj_classes:
        dialog = ComputerPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view_enabled, main_window)
    elif 'contact' in obj_classes:
        dialog = ContactPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view_enabled, main_window)
    elif 'group' in obj_classes:
        dialog = GroupPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view_enabled, main_window)
    elif 'printQueue' in obj_classes:
        dialog = PrinterPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view_enabled, main_window)
    elif 'container' in obj_classes or 'organizationalUnit' in obj_classes:
        dialog = ContainerPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view_enabled, main_window)

    if dialog:
        dialog.exec_()

def on_find_user_action_triggered(main_window, dn):
    main_window.logger.info(f"Find action triggered on DN: {dn}")
    dialog = FindObjectsDialog(main_window.samba_conn, search_base_dn=dn, parent=main_window)
    dialog.exec_()

def on_add_to_group_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Add to a group...' is not yet implemented.")

def on_reset_password_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Reset Password...' is not yet implemented.")

def on_move_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Move...' is not yet implemented.")

def on_rename_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Rename...' is not yet implemented.")

def on_stub_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "This feature is not yet implemented.")

def on_reset_account_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Reset Account' is not yet implemented.")

def on_change_domain_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Change Domain...' is not yet implemented.")

def on_refresh_action_triggered(main_window):
    main_window.logger.info("Refresh action triggered.")
    current_index = main_window.treePane.currentIndex()
    if current_index.isValid():
        main_window._on_tree_item_clicked(current_index)
    else:
        main_window.logger.warning("No item selected in the tree to refresh.")

def on_export_list_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Export List...' is not yet implemented.")

def on_import_query_definition_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Import Query Definition...' is not yet implemented.")

def on_delegate_control_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Delegate Control...' is not yet implemented.")

def on_raise_domain_functional_level_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Raise Domain functional level...' is not yet implemented.")

def on_operations_masters_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Operations Masters...' is not yet implemented.")

def on_new_folder_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Folder...' is not yet implemented.")

def on_view_add_remove_columns_action_triggered(main_window):
    dialog = ColumnEditorDialog(main_window)
    dialog.set_displayed_columns(main_window.tableModel.get_header_keys())
    if dialog.exec_() == QDialog.Accepted:
        new_column_keys = dialog.get_displayed_column_keys()
        main_window.tableModel.set_header_keys(new_column_keys)
        # Refresh the view to apply the new columns
        on_refresh_action_triggered(main_window)


def on_view_large_icons_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Large Icons' view is not yet implemented.")

def on_view_small_icons_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Small Icons' view is not yet implemented.")

def on_view_list_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'List' view is not yet implemented.")

def on_view_detail_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Detail' view is not yet implemented.")

def on_view_filter_options_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Filter options...' is not yet implemented.")

def on_view_customize_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Customize...' is not yet implemented.")


def on_view_objects_as_containers_toggled(main_window, checked):
    main_window.logger.info(f"'Objects as containers' toggled: {checked}")
    main_window.adModel.set_objects_as_containers(checked)


def on_advanced_features_toggled(main_window, checked):
    main_window.logger.info(f"Advanced features toggled: {checked}")
    main_window.adModel.set_advanced_view(checked)
    main_window._setup_tree_view_model()

def on_new_group_action_triggered(main_window):
    main_window.logger.info("New Group action triggered. Opening NewGroupDialog.")
    dialog = NewGroupDialog(main_window)
    if dialog.exec_() == QDialog.Accepted:
        main_window.logger.info("New Group dialog was accepted.")
        group_data = dialog.get_group_data()
        if group_data and group_data['name']:
            group_data['container_dn'] = main_window.currentContainerDN
            main_window.logger.info(f"Group data collected from dialog: {group_data}")
            success, message_key, args = create_group_samba(main_window.samba_conn, group_data)
            message = main_window.i18n.get_text(message_key, *args)
            if success:
                QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
                main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
            else:
                QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
        else:
            main_window.logger.info("New Group dialog was cancelled or no name was entered.")
    else:
        main_window.logger.info("New Group dialog was rejected.")

def on_new_computer_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Computer...' is not yet implemented.")

def on_new_ou_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Organizational Unit...' is not yet implemented.")

def on_new_contact_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Contact...' is not yet implemented.")

def on_new_printer_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Printer...' is not yet implemented.")

def on_new_shared_folder_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Shared Folder...' is not yet implemented.")

def on_new_inetorgperson_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New InetOrgPerson...' is not yet implemented.")

def on_new_msds_keycredential_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New msDS-KeyCredential...' is not yet implemented.")

def on_new_msds_resourcepropertylist_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New msDS-ResourcePropertyList...' is not yet implemented.")

def on_new_msds_shadowprincipalcontainer_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New msDS-ShadowPrincipalContainer...' is not yet implemented.")

def on_new_msimaging_psps_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New msImaging-PSPs...' is not yet implemented.")

def on_new_msmq_queue_alias_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New MSMQ Queue Alias...' is not yet implemented.")

def on_new_query_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'New Query...' is not yet implemented.")

def on_delete_container_action_triggered(main_window):
    QMessageBox.information(main_window, "Not Implemented", "'Delete' for containers is not yet implemented.")

from container_properties import ContainerPropertiesDialog

def on_container_properties_action_triggered(main_window):
    if not main_window.currentContainerDN:
        main_window.logger.warning("No container selected for properties.")
        return

    dialog = ContainerPropertiesDialog(main_window.samba_conn, main_window.currentContainerDN, main_window)
    dialog.exec_()

def on_change_dc_action_triggered(main_window):
    main_window.logger.info("Change Domain Controller action triggered.")
    QMessageBox.information(main_window, "Not Implemented", "Changing the domain controller is not yet implemented.")

def on_list_item_double_clicked(main_window, index):
    if not index.isValid():
        return

    main_window.current_selected_dn = main_window.tableModel.get_object_data(index).get('dn')
    on_properties_action_triggered(main_window)
