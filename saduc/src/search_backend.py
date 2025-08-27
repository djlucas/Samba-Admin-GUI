#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/search_backend.py
#
# Description:
# Modular search backend providing reusable search functionality for 
# various object types and use cases.
#
# -----------------------------------------------------------------------------

import logging
import ldap
from typing import List, Dict, Any, Optional, Tuple
from samba_backend import get_paged_results, get_base_dn

logger = logging.getLogger("saduc_app.search_backend")

# Object class mappings
OBJECT_CLASS_FILTERS = {
    'users': '(objectClass=user)',
    'groups': '(objectClass=group)', 
    'computers': '(objectClass=computer)',
    'contacts': '(objectClass=contact)',
    'containers': '(|(objectClass=organizationalUnit)(objectClass=container))',
    'printers': '(objectClass=printQueue)',
    'all_objects': '(objectClass=*)'
}

# Common attribute sets for different object types
STANDARD_ATTRIBUTES = {
    'users': ['cn', 'displayName', 'sAMAccountName', 'mail', 'telephoneNumber', 
              'title', 'department', 'company', 'manager', 'objectSid'],
    'groups': ['cn', 'displayName', 'sAMAccountName', 'description', 'groupType',
               'member', 'memberOf', 'objectSid'],
    'computers': ['cn', 'dNSHostName', 'operatingSystem', 'operatingSystemVersion', 
                  'description', 'location', 'managedBy'],
    'contacts': ['cn', 'displayName', 'mail', 'telephoneNumber', 'company', 
                 'department', 'title'],
    'containers': ['cn', 'distinguishedName', 'description', 'managedBy'],
    'minimal': ['cn', 'displayName', 'distinguishedName', 'objectClass']
}

def build_search_filter(object_type: str, name_filter: str = "", 
                       description_filter: str = "", custom_filters: List[str] = None) -> str:
    """
    Build an LDAP search filter combining object class and attribute filters.
    """
    filters = []
    
    # Add object class filter
    if object_type in OBJECT_CLASS_FILTERS:
        filters.append(OBJECT_CLASS_FILTERS[object_type])
    
    # Add name filter
    if name_filter:
        name_filter = name_filter.strip()
        if not name_filter.startswith('*') and not name_filter.endswith('*'):
            name_filter = f"*{name_filter}*"
        filters.append(f"(|(cn={name_filter})(displayName={name_filter})(sAMAccountName={name_filter}))")
    
    # Add description filter
    if description_filter:
        desc_filter = description_filter.strip()
        if not desc_filter.startswith('*') and not desc_filter.endswith('*'):
            desc_filter = f"*{desc_filter}*"
        filters.append(f"(description={desc_filter})")
    
    # Add custom filters
    if custom_filters:
        filters.extend(custom_filters)
    
    # Combine all filters
    if len(filters) == 1:
        return filters[0]
    elif len(filters) > 1:
        return f"(&{''.join(filters)})"
    else:
        return "(objectClass=*)"

def search_users(samba_conn, search_base: str = None, name_filter: str = "", 
                 enabled_only: bool = True) -> List[Dict[str, Any]]:
    """Search for user objects with user-specific options."""
    if not search_base:
        search_base = get_base_dn(samba_conn)
    
    custom_filters = []
    if enabled_only:
        custom_filters.append('(!(userAccountControl:1.2.840.113556.1.4.803:=2))')
    custom_filters.append('(!(objectClass=computer))')
    
    search_filter = build_search_filter('users', name_filter, custom_filters=custom_filters)
    attributes = STANDARD_ATTRIBUTES['users']
    
    try:
        results = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, 
                                  search_filter, attributes)
        return _process_search_results(results)
    except ldap.LDAPError as e:
        logger.error(f"LDAP error during user search: {e}")
        return []

def search_groups(samba_conn, search_base: str = None, name_filter: str = "") -> List[Dict[str, Any]]:
    """Search for group objects."""
    if not search_base:
        search_base = get_base_dn(samba_conn)
    
    search_filter = build_search_filter('groups', name_filter)
    attributes = STANDARD_ATTRIBUTES['groups']
    
    try:
        results = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, 
                                  search_filter, attributes)
        return _process_search_results(results)
    except ldap.LDAPError as e:
        logger.error(f"LDAP error during group search: {e}")
        return []

def search_containers(samba_conn, search_base: str = None, name_filter: str = "") -> List[Dict[str, Any]]:
    """Search for container and OU objects."""
    if not search_base:
        search_base = get_base_dn(samba_conn)
    
    search_filter = build_search_filter('containers', name_filter)
    attributes = STANDARD_ATTRIBUTES['containers']
    
    try:
        results = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, 
                                  search_filter, attributes)
        return _process_search_results(results)
    except ldap.LDAPError as e:
        logger.error(f"LDAP error during container search: {e}")
        return []

def _process_search_results(results) -> List[Dict[str, Any]]:
    """Process raw LDAP search results into standardized format."""
    processed = []
    for dn, attrs in results:
        if dn is None:
            continue
            
        obj = {'dn': dn}
        for attr, values in attrs.items():
            if isinstance(values, list) and values:
                decoded_values = []
                for value in values:
                    if isinstance(value, bytes):
                        try:
                            decoded_values.append(value.decode('utf-8'))
                        except UnicodeDecodeError:
                            decoded_values.append(str(value))
                    else:
                        decoded_values.append(str(value))
                obj[attr] = decoded_values
        
        obj['display_name'] = _get_display_name(obj)
        obj['object_type'] = _get_object_type(obj)
        processed.append(obj)
    
    return processed

def _get_display_name(obj: Dict[str, Any]) -> str:
    """Get the best display name for an object."""
    for attr in ['displayName', 'cn', 'sAMAccountName']:
        if attr in obj and obj[attr]:
            value = obj[attr]
            return value[0] if isinstance(value, list) else value
    return obj.get('dn', 'Unknown')

def _get_object_type(obj: Dict[str, Any]) -> str:
    """Determine the object type from objectClass attribute."""
    object_classes = obj.get('objectClass', [])
    if isinstance(object_classes, str):
        object_classes = [object_classes]
    
    if 'user' in object_classes and 'computer' in object_classes:
        return 'Computer'
    elif 'user' in object_classes:
        return 'User'
    elif 'group' in object_classes:
        return 'Group'
    elif 'contact' in object_classes:
        return 'Contact'
    elif 'organizationalUnit' in object_classes:
        return 'Organizational Unit'
    elif 'container' in object_classes:
        return 'Container'
    else:
        return 'Object'