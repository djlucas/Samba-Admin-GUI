# src/generic_object_dialogs.py

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDialogButtonBox, QFrame, QSpacerItem, QSizePolicy,
    QWizard, QWizardPage, QFormLayout, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from i18n_manager import I18nManager


class GenericObjectDialog(QDialog):
    """Simple dialog for creating generic schema-extended objects."""

    def __init__(self, parent=None, container_dn=None, object_class=None, display_name=None, naming_attribute='cn'):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.container_dn = container_dn
        self.object_class = object_class
        self.display_name = display_name or object_class
        self.naming_attribute = naming_attribute

        self.setWindowTitle(self.i18n.get_text("dialog.generic_object.title", self.display_name))
        self.setModal(True)
        self.setFixedSize(400, 180)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Header section with icon and "Create in" info
        header_layout = QHBoxLayout()

        # Generic object icon
        icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'generic_object.png')
        icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        header_layout.addWidget(icon_label)

        # Create in label
        create_in_text = self.i18n.get_text("dialog.generic_object.create_in", self.container_dn or "Unknown")
        create_in_label = QLabel(create_in_text)
        header_layout.addWidget(create_in_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.HLine)
        separator1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator1)

        # Name input (using the naming attribute)
        name_label_text = self.i18n.get_text("dialog.generic_object.name_label", self.naming_attribute.upper())
        name_label = QLabel(name_label_text)
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        # Big spacer for normal sized dialog
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout.addItem(spacer)

        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # Set focus to the input field
        self.name_input.setFocus()

    def get_object_data(self):
        """Return the object data collected from the dialog."""
        return {
            'object_class': self.object_class,
            'naming_attribute': self.naming_attribute,
            'naming_value': self.name_input.text().strip(),
            'container_dn': self.container_dn
        }


class GenericObjectWizardPage1(QWizardPage):
    """First page of the generic object wizard - collect naming attribute."""

    def __init__(self, object_class, display_name, naming_attribute, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.object_class = object_class
        self.display_name = display_name
        self.naming_attribute = naming_attribute

        self.setTitle(self.i18n.get_text("dialog.generic_object_wizard.step1.title", self.display_name))
        self.setSubTitle(self.i18n.get_text("dialog.generic_object_wizard.step1.subtitle", self.display_name))

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Header section with icon and attribute info
        header_layout = QHBoxLayout()

        # Generic object icon
        icon_label = QLabel()
        abs_icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'generic_object.png')
        icon_label.setPixmap(QIcon(abs_icon_path).pixmap(32, 32))
        header_layout.addWidget(icon_label)

        # Attribute info layout
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # Attribute name line
        attr_name_text = self.i18n.get_text("dialog.generic_object_wizard.step1.attribute_name", self.naming_attribute.upper())
        attr_name_label = QLabel(attr_name_text)
        info_layout.addWidget(attr_name_label)

        # Attribute type line
        attr_type_text = self.i18n.get_text("dialog.generic_object_wizard.step1.attribute_type", self.display_name)
        attr_type_label = QLabel(attr_type_text)
        info_layout.addWidget(attr_type_label)

        header_layout.addLayout(info_layout)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Name input
        self.name_input = QLineEdit()
        layout.addWidget(self.name_input)

        # Register field for wizard validation
        self.registerField("naming_value*", self.name_input)

        self.setLayout(layout)

        # Set focus to input
        self.name_input.setFocus()


class GenericObjectWizardPage2(QWizardPage):
    """Second page of the generic object wizard - collect required attributes."""

    def __init__(self, object_class, display_name, required_attributes, parent=None):
        super().__init__(parent)
        self.i18n = I18nManager()
        self.object_class = object_class
        self.display_name = display_name
        self.required_attributes = required_attributes
        self.attribute_inputs = {}

        self.setTitle(self.i18n.get_text("dialog.generic_object_wizard.step2.title", self.display_name))
        self.setSubTitle(self.i18n.get_text("dialog.generic_object_wizard.step2.subtitle", self.display_name))

        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout()
        layout.setSpacing(10)

        for attr_config in self.required_attributes:
            attr_name = attr_config['name']
            display_name = attr_config['display_name']
            attr_type = attr_config['type']
            description = attr_config.get('description', '')

            # Create appropriate input widget based on attribute type
            if attr_type == 'octet_string':
                # For octet string, use a text area for hex input
                input_widget = QTextEdit()
                input_widget.setMaximumHeight(80)
                input_widget.setPlaceholderText("Enter hex values (e.g., 0A1B2C3D)")
            else:
                # Default to line edit for strings
                input_widget = QLineEdit()
                if description:
                    input_widget.setPlaceholderText(description)

            # Store reference for data collection
            self.attribute_inputs[attr_name] = {
                'widget': input_widget,
                'type': attr_type
            }

            # Add to form layout
            layout.addRow(f"{display_name}:", input_widget)

            # Register field for validation if it's required
            if attr_type == 'octet_string':
                self.registerField(f"{attr_name}*", input_widget, "plainText")
            else:
                self.registerField(f"{attr_name}*", input_widget)

        self.setLayout(layout)

    def get_attribute_values(self):
        """Get the attribute values from the input widgets."""
        values = {}
        for attr_name, input_info in self.attribute_inputs.items():
            widget = input_info['widget']
            attr_type = input_info['type']

            if attr_type == 'octet_string':
                # For octet strings, get the plain text and clean it up
                raw_value = widget.toPlainText().strip()
                # Remove spaces and convert to proper format
                clean_value = ''.join(raw_value.split())
                values[attr_name] = clean_value
            else:
                values[attr_name] = widget.text().strip()

        return values


class GenericObjectWizard(QWizard):
    """Two-step wizard for creating complex generic objects with required attributes."""

    def __init__(self, parent=None, container_dn=None, object_class=None, display_name=None, 
                 naming_attribute='cn', required_attributes=None):
        super().__init__(parent)
        self.container_dn = container_dn
        self.object_class = object_class
        self.display_name = display_name or object_class
        self.naming_attribute = naming_attribute
        self.required_attributes = required_attributes or []

        self.setWindowTitle(f"New Object - {self.display_name}")
        self.setModal(True)
        self.setFixedSize(500, 350)

        # Create and add pages
        self.page1 = GenericObjectWizardPage1(object_class, self.display_name, naming_attribute, self)
        self.page2 = GenericObjectWizardPage2(object_class, self.display_name, required_attributes, self)

        self.addPage(self.page1)
        self.addPage(self.page2)

        # Set button text
        self.setButtonText(QWizard.BackButton, "< Back")
        self.setButtonText(QWizard.NextButton, "Next >")
        self.setButtonText(QWizard.FinishButton, "Finish")
        self.setButtonText(QWizard.CancelButton, "Cancel")

    def get_object_data(self):
        """Return the object data collected from the wizard."""
        # Get naming value from page 1
        naming_value = self.field("naming_value")

        # Get attribute values from page 2
        attribute_values = self.page2.get_attribute_values()

        return {
            'object_class': self.object_class,
            'naming_attribute': self.naming_attribute,
            'naming_value': naming_value,
            'container_dn': self.container_dn,
            'attributes': attribute_values
        }