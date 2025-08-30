"""
Icon utilities for SADUC

Provides consistent icon loading with fallback handling.
"""

import os
import logging
from PyQt5.QtGui import QIcon

logger = logging.getLogger("saduc_app.icon_utils")

def get_saduc_icon():
    """Get the main SADUC application icon."""
    return _load_icon('directory.png', 'Main SADUC icon')

def get_search_icon():
    """Get the search/saved queries icon."""
    return _load_icon('directory-search.png', 'SADUC search icon')

def _load_icon(filename, description):
    """Load an icon with fallback handling."""
    icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', filename)
    
    if os.path.exists(icon_path):
        try:
            icon = QIcon(icon_path)
            if not icon.isNull():
                logger.info(f"Successfully loaded {description}: {icon_path}")
                return icon
            else:
                logger.warning(f"Icon loaded but is null: {icon_path}")
        except Exception as e:
            logger.warning(f"Failed to load {description} from {icon_path}: {e}")
    else:
        logger.warning(f"{description} not found at {icon_path}")
    
    # Return empty icon as fallback
    logger.debug(f"Using fallback (empty) icon for {description}")
    return QIcon()

def set_window_icon(window, use_search_icon=False):
    """Set window icon with proper fallback handling."""
    try:
        if use_search_icon:
            icon = get_search_icon()
        else:
            icon = get_saduc_icon()
        
        if not icon.isNull():
            window.setWindowIcon(icon)
            return True
    except Exception as e:
        logger.error(f"Failed to set window icon: {e}")
    
    return False