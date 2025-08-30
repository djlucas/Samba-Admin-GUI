
import logging
from PyQt5.QtWidgets import QDialog, QMessageBox
from PyQt5.QtCore import Qt
from user_dialogs import NewUserWizard, CopyUserWizard, DeleteUserDialog, DisableUserDialog, NewGroupDialog, NewOUDialog, DeleteOUDialog, EnableUserDialog
from computer_dialogs import DisableComputerDialog, EnableComputerDialog
from password_reset_dialog import PasswordResetDialog
from samba_backend import create_user_samba, copy_user_samba, get_user_properties, create_group_samba, create_ou_samba, delete_user_samba, delete_ou_samba, disable_user_samba, enable_user_samba, disable_computer_samba, enable_computer_samba, reset_password_samba
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
            success, message_key, extra = create_user_samba(main_window.samba_conn, user_data)
            message = main_window.i18n.get_text(message_key, *extra)
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
    source_display_name = source_user_props.get('displayName', [source_username])[0] or source_username
    
    uac = int(source_user_props.get('userAccountControl', ['0'])[0])
    initial_data = {
        'user_must_change_password': False,
        'user_cannot_change_password': bool(uac & 0x0040),
        'password_never_expires': bool(uac & 0x10000),
        'account_is_disabled': bool(uac & 0x0002)
    }

    main_window.logger.info(f"Copy User action triggered for user: {source_display_name} ({source_username}).")
    wizard = CopyUserWizard(main_window, initial_data=initial_data, source_username=source_username, source_display_name=source_display_name, container_dn=main_window.currentContainerDN)
    if wizard.exec_() == QDialog.Accepted:
        main_window.logger.info("Copy User wizard was accepted.")
        user_data = wizard.user_data
        if user_data:
            user_data['container_dn'] = main_window.currentContainerDN
            main_window.logger.info(f"Copied user data collected from wizard: {user_data}")
            success, message_key, extra = copy_user_samba(main_window.samba_conn, main_window.current_selected_dn, user_data)
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
        success, message_key, extra = delete_user_samba(main_window.samba_conn, main_window.current_selected_dn)
        message = main_window.i18n.get_text(message_key, *extra)
        if success:
            QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
            main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
        else:
            QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
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
        success, message_key, extra = disable_user_samba(main_window.samba_conn, main_window.current_selected_dn)
        message = main_window.i18n.get_text(message_key, *extra)
        if success:
            QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
            main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
        else:
            QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
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
        success, message_key, extra = enable_user_samba(main_window.samba_conn, main_window.current_selected_dn)
        message = main_window.i18n.get_text(message_key, *extra)
        if success:
            QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
            main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
        else:
            QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
    else:
        main_window.logger.info(f"User cancelled enabling account for: {username}")

def on_disable_computer_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No computer selected for disabling.")
        return
    computer_name = main_window.tableModel.data(main_window.listPane.selectionModel().currentIndex(), Qt.DisplayRole)
    if DisableComputerDialog(main_window, computer_name) == QMessageBox.Yes:
        success, message_key, extra = disable_computer_samba(main_window.samba_conn, main_window.current_selected_dn)
        message = main_window.i18n.get_text(message_key, *extra)
        if success:
            QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
            main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
        else:
            QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)

def on_enable_computer_action_triggered(main_window):
    if not main_window.current_selected_dn:
        main_window.logger.warning("No computer selected for enabling.")
        return
    computer_name = main_window.tableModel.data(main_window.listPane.selectionModel().currentIndex(), Qt.DisplayRole)
    if EnableComputerDialog(main_window, computer_name) == QMessageBox.Yes:
        success, message_key, extra = enable_computer_samba(main_window.samba_conn, main_window.current_selected_dn)
        message = main_window.i18n.get_text(message_key, *extra)
        if success:
            QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
            main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
        else:
            QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)

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
    if not main_window.current_selected_dn:
        return
    username = main_window.tableModel.data(main_window.listPane.selectionModel().currentIndex(), Qt.DisplayRole)
    dialog = PasswordResetDialog(main_window, username)
    if dialog.exec_() == QDialog.Accepted:
        success, message_key, extra = reset_password_samba(main_window.samba_conn, main_window.current_selected_dn, dialog.password, dialog.must_change_password)
        message = main_window.i18n.get_text(message_key, *extra)
        if success:
            QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
            main_window._on_tree_item_clicked(main_window.treePane.currentIndex())
        else:
            QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)

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
    main_window.adModel.set_show_objects_as_containers(checked)


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
    main_window.logger.info("New OU action triggered. Opening NewOUDialog.")
    dialog = NewOUDialog(main_window, container_dn=main_window.currentContainerDN)
    if dialog.exec_() == QDialog.Accepted:
        main_window.logger.info("New OU dialog was accepted.")
        ou_data = dialog.get_ou_data()
        if ou_data and ou_data['name']:
            main_window.logger.info(f"OU data collected from dialog: {ou_data}")
            success, message_key, args = create_ou_samba(main_window.samba_conn, ou_data)
            message = main_window.i18n.get_text(message_key, *args)
            if success:
                QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
                # Refresh the tree model to show the new OU
                main_window.adModel.set_advanced_view(main_window.adModel.is_advanced_view)
            else:
                QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
        else:
            main_window.logger.info("New OU dialog was cancelled or no name was entered.")
    else:
        main_window.logger.info("New OU dialog was rejected.")

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
    """Handle delete action for containers and OUs."""
    if not main_window.currentContainerDN:
        main_window.logger.warning("No container/OU selected for deletion.")
        return
    
    # Get container/OU information
    try:
        import ldap
        from samba_backend import get_ldap_conn
        
        # Get connection (we can't use main_window.samba_conn if it's not available)
        samba_conn = main_window.samba_conn
        
        # Check what type of object this is
        res = samba_conn.search_s(main_window.currentContainerDN, ldap.SCOPE_BASE, '(objectClass=*)', ['objectClass', 'ou', 'cn', 'name'])
        if not res:
            QMessageBox.critical(main_window, "Error", "Could not find the selected object.")
            return
            
        obj_attrs = res[0][1]
        object_classes = [cls.decode('utf-8') for cls in obj_attrs.get('objectClass', [])]
        
        # Get object name
        obj_name = "Unknown"
        for attr in ['ou', 'cn', 'name']:
            if attr in obj_attrs:
                obj_name = obj_attrs[attr][0].decode('utf-8')
                break
        
        if 'organizationalUnit' in object_classes:
            # Handle OU deletion with enhanced checking
            main_window.logger.info(f"Delete OU action triggered for: {obj_name}")
            
            # First check if OU has children to determine dialog type
            has_children = False
            try:
                import ldap
                child_res = samba_conn.search_s(main_window.currentContainerDN, ldap.SCOPE_ONELEVEL, '(objectClass=*)', ['cn'])
                has_children = len(child_res) > 0
            except Exception as e:
                main_window.logger.warning(f"Could not check for child objects: {e}")
            
            # Show confirmation dialog with appropriate options
            delete_dialog = DeleteOUDialog(obj_name, has_children, main_window)
            if delete_dialog.exec_() != QDialog.Accepted:
                main_window.logger.info("OU deletion cancelled by user.")
                return
            
            # Get recursive delete preference from dialog
            recursive_delete = delete_dialog.is_recursive_delete()
            main_window.logger.info(f"OU deletion confirmed - Recursive: {recursive_delete}")
            
            # Attempt to delete the OU
            success, message_key, args = delete_ou_samba(samba_conn, main_window.currentContainerDN, recursive_delete)
            message = main_window.i18n.get_text(message_key, *args)
            
            if success:
                QMessageBox.information(main_window, main_window.i18n.get_string("dialog.common.success.title"), message)
                # Refresh the tree view to reflect the deletion
                main_window.adModel.set_advanced_view(main_window.adModel.is_advanced_view)
                main_window.logger.info(f"Successfully deleted OU: {obj_name}")
            else:
                # Show appropriate error message
                if "critical_ou_cannot_delete" in message_key:
                    QMessageBox.critical(main_window, "Cannot Delete System OU", 
                                       f"The OU '{obj_name}' is a critical system OU and cannot be deleted.")
                elif "ou_protected_from_deletion" in message_key:
                    QMessageBox.warning(main_window, "OU Protected", 
                                      f"The OU '{obj_name}' is protected from accidental deletion.\n\n"
                                      f"To delete this OU, first disable protection in its Object properties tab.")
                elif "ou_has_critical_children" in message_key:
                    critical_objects = args[1] if len(args) > 1 else "critical system objects"
                    QMessageBox.critical(main_window, "Cannot Delete OU", 
                                       f"The OU '{obj_name}' contains critical system objects that cannot be deleted:\n\n"
                                       f"{critical_objects}\n\n"
                                       f"These objects are essential to Active Directory operation.")
                elif "ou_has_protected_children" in message_key:
                    protected_objects = args[1] if len(args) > 1 else "protected objects"
                    QMessageBox.warning(main_window, "OU Contains Protected Objects", 
                                      f"The OU '{obj_name}' contains objects that are protected from accidental deletion:\n\n"
                                      f"{protected_objects}\n\n"
                                      f"Remove protection from these objects before deleting the OU.")
                elif "ou_recursive_delete_failed" in message_key:
                    failed_objects = args[1] if len(args) > 1 else "some objects"
                    QMessageBox.critical(main_window, "Recursive Delete Failed", 
                                       f"Failed to recursively delete OU '{obj_name}'.\n\n"
                                       f"Could not delete the following child objects:\n{failed_objects}\n\n"
                                       f"The OU and some child objects may still exist. Please check manually.")
                elif "ou_has_children" in message_key:
                    child_count = args[1] if len(args) > 1 else "some"
                    QMessageBox.warning(main_window, "OU Contains Objects", 
                                      f"The OU '{obj_name}' contains {child_count} objects and cannot be deleted.\n\n"
                                      f"Delete or move all objects from this OU before attempting to delete it.")
                else:
                    QMessageBox.critical(main_window, main_window.i18n.get_string("dialog.common.error.title"), message)
                main_window.logger.warning(f"Failed to delete OU: {message}")
        
        else:
            # Handle other container types (not yet implemented)
            QMessageBox.information(main_window, "Not Implemented", 
                                  f"Delete operation for '{obj_name}' (type: {', '.join(object_classes)}) is not yet implemented.")
    
    except Exception as e:
        main_window.logger.error(f"Error during delete operation: {e}")
        QMessageBox.critical(main_window, "Error", f"An error occurred during the delete operation:\n{str(e)}")

from container_properties import ContainerPropertiesDialog

def on_container_properties_action_triggered(main_window):
    if not main_window.currentContainerDN:
        main_window.logger.warning("No container selected for properties.")
        return

    # Pass the correct advanced_view parameter from the main window's model
    advanced_view = main_window.adModel.is_advanced_view if hasattr(main_window.adModel, 'is_advanced_view') else False
    dialog = ContainerPropertiesDialog(main_window.samba_conn, main_window.currentContainerDN, advanced_view, main_window)
    dialog.exec_()

def on_change_dc_action_triggered(main_window):
    main_window.logger.info("Change Domain Controller action triggered.")
    QMessageBox.information(main_window, "Not Implemented", "Changing the domain controller is not yet implemented.")

def on_properties_action_triggered(main_window):
    """Open properties dialog for the currently selected object based on its object class."""
    if not main_window.current_selected_dn:
        main_window.logger.warning("No object selected for properties.")
        return

    # Get object data to determine the object class
    obj_data = None
    if hasattr(main_window, 'tableModel') and main_window.tableModel:
        for i in range(main_window.tableModel.rowCount()):
            row_data = main_window.tableModel.get_object_data(main_window.tableModel.index(i, 0))
            if row_data and row_data.get('dn') == main_window.current_selected_dn:
                obj_data = row_data
                break

    if not obj_data:
        main_window.logger.warning(f"Could not find object data for {main_window.current_selected_dn}")
        return

    object_class = obj_data.get('objectClass', [])
    if isinstance(object_class, str):
        object_class = [object_class]

    # Get advanced_view setting
    advanced_view = main_window.adModel.is_advanced_view if hasattr(main_window.adModel, 'is_advanced_view') else False

    # Open appropriate properties dialog based on object class
    if 'user' in object_class:
        dialog = UserPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)
    elif 'group' in object_class:
        dialog = GroupPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)
    elif 'computer' in object_class:
        dialog = ComputerPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)
    elif 'contact' in object_class:
        dialog = ContactPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)
    elif 'printQueue' in object_class:
        dialog = PrinterPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)
    elif 'organizationalUnit' in object_class or 'container' in object_class:
        dialog = ContainerPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)
    else:
        # Generic object - use container properties as fallback
        dialog = ContainerPropertiesDialog(main_window.samba_conn, main_window.current_selected_dn, advanced_view, main_window)

    dialog.exec_()

def on_list_item_double_clicked(main_window, index):
    if not index.isValid():
        return

    main_window.current_selected_dn = main_window.tableModel.get_object_data(index).get('dn')
    on_properties_action_triggered(main_window)
