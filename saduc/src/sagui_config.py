"""
SAGUI Configuration Manager

Manages configuration directories, saved searches, and persistent settings
for all SAGUI tools (saduc, sdns, sadss, sgpoe).
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class SAGUIConfig:
    """Configuration manager for SAGUI tools"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config_dir = Path.home() / '.sagui'
        self.searches_dir = self.config_dir / 'searches'
        self.connections_dir = self.config_dir / 'connections'
        self.preferences_dir = self.config_dir / 'preferences'
        self.cache_dir = self.config_dir / 'cache'

        self._ensure_directories()

    def _ensure_directories(self):
        """Create SAGUI configuration directories if they don't exist"""
        directories = [
            self.config_dir,
            self.searches_dir,
            self.connections_dir,
            self.preferences_dir,
            self.cache_dir
        ]

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Ensured directory exists: {directory}")
            except Exception as e:
                self.logger.error(f"Failed to create directory {directory}: {e}")
                raise

    def save_search(self, name: str, search_data: Dict[str, Any]) -> bool:
        """
        Save a search query to JSON file

        Args:
            name: Display name for the search
            search_data: Dictionary containing search parameters

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Add metadata
            search_data.update({
                'name': name,
                'created': datetime.now().isoformat(),
                'lastUsed': datetime.now().isoformat()
            })

            # Sanitize filename
            filename = self._sanitize_filename(name) + '.json'
            filepath = self.searches_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(search_data, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Saved search '{name}' to {filepath}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save search '{name}': {e}")
            return False

    def load_search(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load a saved search by name

        Args:
            name: Display name of the search

        Returns:
            Dict containing search data or None if not found
        """
        try:
            filename = self._sanitize_filename(name) + '.json'
            filepath = self.searches_dir / filename

            if not filepath.exists():
                self.logger.warning(f"Search file not found: {filepath}")
                return None

            with open(filepath, 'r', encoding='utf-8') as f:
                search_data = json.load(f)

            # Update last used timestamp
            search_data['lastUsed'] = datetime.now().isoformat()
            self.save_search(name, search_data)

            self.logger.debug(f"Loaded search '{name}'")
            return search_data

        except Exception as e:
            self.logger.error(f"Failed to load search '{name}': {e}")
            return None

    def list_saved_searches(self) -> List[Dict[str, Any]]:
        """
        Get list of all saved searches with metadata

        Returns:
            List of dictionaries containing search metadata
        """
        searches = []

        try:
            for filepath in self.searches_dir.glob('*.json'):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        search_data = json.load(f)

                    # Extract metadata for list display
                    metadata = {
                        'name': search_data.get('name', filepath.stem),
                        'description': search_data.get('description', ''),
                        'created': search_data.get('created', ''),
                        'lastUsed': search_data.get('lastUsed', ''),
                        'filename': filepath.name
                    }
                    searches.append(metadata)

                except Exception as e:
                    self.logger.warning(f"Failed to read search file {filepath}: {e}")
                    continue

            # Sort by last used, then by name
            searches.sort(key=lambda x: (x.get('lastUsed', ''), x.get('name', '')), reverse=True)

        except Exception as e:
            self.logger.error(f"Failed to list saved searches: {e}")

        return searches

    def list_saved_search_folders(self, relative_path: str = "") -> List[str]:
        """
        Get list of subdirectories in the saved searches folder

        Args:
            relative_path: Relative path from searches_dir root

        Returns:
            List of directory names
        """
        folders = []

        try:
            search_path = self.searches_dir
            if relative_path:
                search_path = search_path / relative_path

            if search_path.exists() and search_path.is_dir():
                for item in search_path.iterdir():
                    if item.is_dir():
                        folders.append(item.name)

            folders.sort()
            return folders

        except Exception as e:
            self.logger.error(f"Failed to list search folders in {search_path}: {e}")
            return []

    def delete_search(self, name: str) -> bool:
        """
        Delete a saved search

        Args:
            name: Display name of the search to delete

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            filename = self._sanitize_filename(name) + '.json'
            filepath = self.searches_dir / filename

            if filepath.exists():
                filepath.unlink()
                self.logger.info(f"Deleted search '{name}'")
                return True
            else:
                self.logger.warning(f"Search '{name}' not found for deletion")
                return False

        except Exception as e:
            self.logger.error(f"Failed to delete search '{name}': {e}")
            return False

    def save_preferences(self, tool_name: str, preferences: Dict[str, Any]) -> bool:
        """
        Save tool preferences

        Args:
            tool_name: Name of the tool (saduc, sdns, etc.)
            preferences: Dictionary of preferences

        Returns:
            bool: True if saved successfully
        """
        try:
            filepath = self.preferences_dir / f'{tool_name}.json'

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(preferences, f, indent=2, ensure_ascii=False)

            self.logger.debug(f"Saved preferences for {tool_name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save preferences for {tool_name}: {e}")
            return False

    def load_preferences(self, tool_name: str) -> Dict[str, Any]:
        """
        Load tool preferences

        Args:
            tool_name: Name of the tool (saduc, sdns, etc.)

        Returns:
            Dictionary of preferences (empty dict if not found)
        """
        try:
            filepath = self.preferences_dir / f'{tool_name}.json'

            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)

        except Exception as e:
            self.logger.error(f"Failed to load preferences for {tool_name}: {e}")

        return {}

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a display name for use as filename

        Args:
            name: Original name

        Returns:
            Sanitized filename (without extension)
        """
        # Replace invalid characters with underscores
        invalid_chars = '<>:"/\\|?*'
        sanitized = name

        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')

        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip('. ')

        # Limit length
        if len(sanitized) > 100:
            sanitized = sanitized[:100]

        return sanitized


# Global instance
config_manager = SAGUIConfig()


def create_default_searches():
    """Create some useful default saved searches"""
    default_searches = [
        {
            'name': 'Disabled Users',
            'description': 'Find all disabled user accounts',
            'objectClass': 'user',
            'filter': '(&(objectCategory=person)(userAccountControl:1.2.840.113556.1.4.803:=2))',
            'searchBase': 'auto',
            'scope': 'subtree',
            'attributes': ['cn', 'sAMAccountName', 'userAccountControl', 'whenCreated', 'objectClass']
        },
        {
            'name': 'Computers Not Logged On Recently',
            'description': 'Computer accounts that have not logged on in the last 30 days',
            'objectClass': 'computer',
            'filter': '(&(objectCategory=computer)(lastLogonTimeStamp<=131234567890))',
            'searchBase': 'auto',
            'scope': 'subtree',
            'attributes': ['cn', 'dNSHostName', 'operatingSystem', 'lastLogonTimeStamp', 'objectClass']
        },
        {
            'name': 'Empty Groups',
            'description': 'Security groups with no members',
            'objectClass': 'group',
            'filter': '(&(objectCategory=group)(!(member=*)))',
            'searchBase': 'auto',
            'scope': 'subtree',
            'attributes': ['cn', 'groupType', 'whenCreated', 'description', 'objectClass']
        },
        {
            'name': 'Users with Never Expiring Passwords',
            'description': 'User accounts with passwords set to never expire',
            'objectClass': 'user',
            'filter': '(&(objectCategory=person)(userAccountControl:1.2.840.113556.1.4.803:=65536))',
            'searchBase': 'auto',
            'scope': 'subtree',  
            'attributes': ['cn', 'sAMAccountName', 'pwdLastSet', 'userAccountControl', 'objectClass']
        }
    ]

    for search_data in default_searches:
        name = search_data['name']
        if not config_manager.load_search(name):  # Only create if doesn't exist
            config_manager.save_search(name, search_data)
            config_manager.logger.info(f"Created default search: {name}")


if __name__ == '__main__':
    # Test the configuration system
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    logger.info("Testing SAGUI Configuration Manager...")

    # Test directory creation
    logger.info(f"Config directory: {config_manager.config_dir}")

    # Create default searches
    create_default_searches()

    # List saved searches
    searches = config_manager.list_saved_searches()
    logger.info(f"Found {len(searches)} saved searches:")
    for search in searches:
        logger.info(f"  - {search['name']}: {search['description']}")