# Computer-specific dialog functions
from PyQt5.QtWidgets import QMessageBox
from i18n_manager import I18nManager

def DisableComputerDialog(parent, computer_name):
    i18n = I18nManager()
    title = i18n.get_string("dialog.disable_computer.title")
    message = i18n.get_text("dialog.disable_computer.message", computer_name)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)

def EnableComputerDialog(parent, computer_name):
    i18n = I18nManager()
    title = i18n.get_string("dialog.enable_computer.title")
    message = i18n.get_text("dialog.enable_computer.message", computer_name)
    return QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)