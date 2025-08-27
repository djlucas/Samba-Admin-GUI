# src/i18n_manager.py

import os
import logging

class I18nManager:
    """
    Manages loading and retrieving internationalized strings from text files.
    """
    def __init__(self, lang_code='en_US', base_path='i18n'):
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.lang_code = lang_code
        self.base_path = base_path
        self._strings = {}
        self.load_strings()

    def load_strings(self):
        """
        Loads strings from the specified language file.
        """
        file_path = os.path.join(os.path.dirname(__file__), self.base_path, f"{self.lang_code}.txt")
        self.logger.info(f"Attempting to load language file from: {file_path}")
        
        if not os.path.exists(file_path):
            self.logger.error(f"Language file not found: {file_path}")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                try:
                    key, value = line.split('=', 1)
                    self._strings[key.strip()] = value.strip()
                except ValueError:
                    self.logger.warning(f"Invalid string format in {self.lang_code}.txt: '{line}'")

        self.logger.info(f"Loaded {len(self._strings)} strings for '{self.lang_code}'.")

    def get_string(self, key, default=None):
        """
        Retrieves a string by its key.
        Returns the default value if the key is not found.
        """
        return self._strings.get(key, default if default is not None else f"[{key}]")

    def get_text(self, key, *args, default=None):
        """
        Retrieves and formats a string with given arguments.
        """
        text = self.get_string(key, default)
        if args:
            try:
                return text.format(*args)
            except IndexError:
                self.logger.error(f"Formatting error for key '{key}'. Arguments provided: {args}")
                return text
        return text

