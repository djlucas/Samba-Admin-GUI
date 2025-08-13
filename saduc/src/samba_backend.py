#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/samba_backend.py
#
# Description:
# This module handles all interactions with the Samba/LDAP backend. It's
# responsible for establishing connections, querying for Active Directory
# objects, and executing modification commands.
#
# -----------------------------------------------------------------------------

import logging
import ldap
import ldap.sasl
from ldap.controls import SimplePagedResultsControl
import dns.resolver
import subprocess
import sys
import uuid

# --- Custom Exception ---
class NoKerberosTicketError(Exception):
    """Raised when no valid Kerberos ticket is found."""
    pass

# --- Global Configuration ---
logger = logging.getLogger("saduc_app." + __name__)

BASE_DN = 'dc=home,dc=lucasit,dc=com'
# Use a broad filter to get all objects, then filter in Python
DEFAULT_SEARCH_FILTER = "(objectclass=*)"
PAGE_SIZE = 1000  # Default page size for paged results control

# A specific, curated list of classes for objects that can appear as
# expandable branches in the left-hand tree view. This includes standard
# containers as well as various special system containers.
TREE_BRANCH_CLASSES = {
    'organizationalUnit',
    'container',
    'builtinDomain',
    'domainDns',
    'dnsZone',
    'msDS-PasswordSettingsContainer',
    'fileLinkTracking',
    'linkTrackObjectMoveTable',
    'linkTrackVolumeTable',
    'msDFSR-GlobalSettings',
    'msDFSR-ReplicationGroup',
    'msDFSR-Topology',
    'msDFSR-Content',
    'groupPolicyContainer', # Correct class for GPOs
    'nTFRSSettings',        # File Replication Service is a container
    'dfsConfiguration',
    'classStore',
    'domainPolicy'          # For the "Default Domain Policy" object under System
}

# Specific container names that should not be expandable in the tree view.
# This is a performance optimization for containers that *never* have sub-containers.
# Stored in lowercase for robust, case-insensitive comparison.
NON_EXPANDABLE_CONTAINERS = {
    'cn=users,dc=home,dc=lucasit,dc=com',
    'cn=computers,dc=home,dc=lucasit,dc=com',
    'cn=builtin,dc=home,dc=lucasit,dc=com',
    'cn=foreignsecurityprincipals,dc=home,dc=lucasit,dc=com'
}


def get_ldap_conn():
    """
    Establishes an authenticated LDAP connection using GSSAPI/Kerberos.
    Includes a fallback mechanism for multiple servers discovered via DNS SRV records.
    """
    # Check for a valid Kerberos ticket before attempting connection
    logger.info("Checking for a valid Kerberos ticket...")
    result = subprocess.run(['klist', '-s'], capture_output=True, text=True)
    if result.returncode != 0:
        raise NoKerberosTicketError(f"No valid Kerberos ticket found. Please run 'kinit' first.")
    logger.info("Kerberos ticket found.")

    domain = '.'.join(p.split('=', 1)[-1] for p in BASE_DN.split(','))
    srv_record = f'_ldap._tcp.{domain}'

    try:
        answers = dns.resolver.resolve(srv_record, 'SRV')
        # Sort answers by priority and weight to get the preferred servers
        ldap_servers = sorted(answers, key=lambda x: (x.priority, x.weight))
        server_list = [str(r.target).rstrip('.') for r in ldap_servers]
        logger.info(f"Dynamically discovered LDAP servers via DNS: {server_list}")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
        logger.error(f"Failed to resolve DNS SRV record for '{srv_record}': {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected DNS error occurred: {e}")
        return None

    for server in server_list:
        try:
            logger.info(f"Attempting to connect to LDAP server: {server}")
            conn = ldap.initialize(f'ldap://{server}')
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            conn.set_option(ldap.OPT_REFERRALS, 0)

            # Kerberos/GSSAPI bind
            sasl_auth = ldap.sasl.gssapi('')
            conn.sasl_interactive_bind_s("", sasl_auth)
            logger.info(f"Samba backend: Successfully established LDAP connection to {server}.")
            return conn, server
        except ldap.LDAPError as e:
            logger.warning(f"Failed to connect to {server}: {e}")
            continue

    logger.critical("Samba backend: Failed to connect to any LDAP servers.")
    return None, None

def get_paged_results(samba_conn, dn, scope, search_filter, attributes):
    """
    Performs a paged LDAP search to handle server-side result limits.
    """
    page_ctrl = SimplePagedResultsControl(3, size=PAGE_SIZE, cookie='')
    search_ctrls = [page_ctrl]
    all_results = []

    while True:
        try:
            msgid = samba_conn.search_ext(dn, scope, search_filter, attributes, serverctrls=search_ctrls)
            rtype, rdata, rmsgid, serverctrls = samba_conn.result3(msgid)
            all_results.extend(rdata)

            pctrls = [c for c in serverctrls if c.controlType == SimplePagedResultsControl.controlType]
            if not pctrls or not pctrls[0].cookie:
                break

            page_ctrl.cookie = pctrls[0].cookie

        except ldap.LDAPError as e:
            logger.error(f"Paged search error: {e}")
            return all_results

    return all_results

def _is_tree_branch(entry, advanced_view=False):
    """
    Helper to check if an LDAP object is a structural container for the tree view.
    """
    if not isinstance(entry, dict) or not entry.get('objectClass'):
        return False

    if not advanced_view:
        show_in_adv_view = entry.get('showInAdvancedViewOnly')
        if show_in_adv_view and show_in_adv_view[0].decode('utf-8').lower() == 'true':
            return False

    object_classes = {oc.decode('utf-8') for oc in entry['objectClass']}
    
    # An object is a branch if its class is in our specific list.
    return len(object_classes.intersection(TREE_BRANCH_CLASSES)) > 0

def get_forest_root_info(samba_conn):
    """
    Retrieves the forest root domain by querying the RootDSE.
    """
    logger.info("Querying RootDSE to find the forest root domain.")
    try:
        # A search with an empty base DN targets the RootDSE
        res = samba_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ['rootDomainNamingContext'])
        if res and res[0][1].get('rootDomainNamingContext'):
            attrs_dict = res[0][1]
            root_dn = attrs_dict['rootDomainNamingContext'][0].decode('utf-8')
            domain_name = ".".join(p.split('=')[1] for p in root_dn.split(',') if p.lower().startswith('dc='))
            logger.info(f"Found forest root DN: {root_dn} (Name: {domain_name})")
            return {'name': domain_name, 'dn': root_dn}
        
        logger.warning("RootDSE query successful but 'rootDomainNamingContext' attribute not found.")
        return None
    except ldap.LDAPError as e:
        logger.error(f"LDAP error querying RootDSE: {e}")
        return None

def get_expandable_children(samba_conn, dn, advanced_view=False):
    """
    Retrieves children of a given DN that should appear as branches in the tree view.
    """
    logger.debug(f"Fetching expandable children for DN: {dn}")
    try:
        # Request RDN attributes. We specifically AVOID displayName for the tree view.
        attributes = ['cn', 'ou', 'dc', 'distinguishedName', 'objectClass', 'showInAdvancedViewOnly']
        res = get_paged_results(samba_conn, dn, ldap.SCOPE_ONELEVEL, DEFAULT_SEARCH_FILTER, attributes)

        children = []
        for child_dn, entry in res:
            if not isinstance(entry, dict):
                logger.debug(f"Skipping non-dict entry for DN='{child_dn}': {entry}")
                continue
            
            # Use the correct RDN attribute for the name ('ou', 'dc', or 'cn')
            name_attr = entry.get('ou') or entry.get('dc') or entry.get('cn')

            # Use our stricter check to see if this object belongs in the tree
            if _is_tree_branch(entry, advanced_view) and name_attr:
                has_sub_containers = has_expandable_children(samba_conn, child_dn, advanced_view)
                children.append({
                    'name': name_attr[0].decode('utf-8'),
                    'dn': child_dn,
                    'objectClass': [oc.decode('utf-8') for oc in entry.get('objectClass', [])],
                    'has_sub_containers': has_sub_containers
                })
        return children
    except ldap.NO_SUCH_OBJECT:
        logger.warning(f"DN '{dn}' does not exist.")
        return []
    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching expandable children for '{dn}': {e}")
        return []


def has_expandable_children(samba_conn, dn, advanced_view=False):
    """
    Checks if a given DN has any children that are themselves structural containers.
    """
    logger.debug(f"Checking for expandable children in DN: {dn}")

    if not advanced_view and dn.lower() in NON_EXPANDABLE_CONTAINERS:
        return False

    try:
        attributes = ['cn', 'ou', 'dc', 'objectClass', 'showInAdvancedViewOnly']
        res = samba_conn.search_s(dn, ldap.SCOPE_ONELEVEL, DEFAULT_SEARCH_FILTER, attributes)

        if not res:
            return False

        for child_dn, entry in res:
            # Use the same strict check here
            if _is_tree_branch(entry, advanced_view):
                return True # Found at least one valid branch child
        return False
    except ldap.NO_SUCH_OBJECT:
        return False
    except ldap.LDAPError as e:
        logger.error(f"LDAP error checking for expandable children in '{dn}': {e}")
        return False


def get_all_objects_in_dn(samba_conn, dn):
    """
    Retrieves all objects within a given DN, for display in the right pane.
    """
    logger.debug(f"Fetching all objects in DN: {dn}")
    try:
        search_filter = "(objectclass=*)"
        attributes = ['cn', 'ou', 'dc', 'displayName', 'description', 'distinguishedName', 'objectClass', 'sAMAccountName', 'userAccountControl']

        res = get_paged_results(samba_conn, dn, ldap.SCOPE_ONELEVEL, search_filter, attributes)

        objects = []
        for child_dn, entry in res:
            if isinstance(entry, dict):
                # Prioritize displayName for the list view
                name_attr = entry.get('displayName') or entry.get('ou') or entry.get('dc') or entry.get('cn')
                if name_attr:
                    obj_data = {
                        'name': name_attr[0].decode('utf-8'),
                        'dn': child_dn,
                        'objectClass': [oc.decode('utf-8') for oc in entry.get('objectClass', [])]
                    }
                    # Add description if it exists
                    if 'description' in entry:
                        obj_data['description'] = entry['description'][0].decode('utf-8')
                    if 'userAccountControl' in entry:
                        obj_data['userAccountControl'] = entry['userAccountControl'][0].decode('utf-8')
                    objects.append(obj_data)

        return objects
    except ldap.NO_SUCH_OBJECT:
        logger.warning(f"DN '{dn}' does not exist.")
        return []
    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching objects in '{dn}': {e}")
        return []


def create_user_samba(samba_conn, user_data):
    """Placeholder for Samba user creation logic."""
    logger.info(f"Samba backend: Creating user with data: {user_data}")
    # ... placeholder for backend logic ...
    return True, "samba_backend.success.create_user"


def copy_user_samba(samba_conn, source_username, new_user_data):
    """Placeholder for Samba user creation logic."""
    logger.info(f"Samba backend: Copying user '{source_username}' to new user with data: {new_user_data}")
    # ... placeholder for backend logic ...
    return True, "samba_backend.success.copy_user"

def get_user_properties(samba_conn, user_dn):
    """Retrieves all properties for a given user."""
    logger.debug(f"Fetching properties for user DN: {user_dn}")
    try:
        attributes = [
            'givenName', 'sn', 'displayName', 'description', 'sAMAccountName',
            'userAccountControl', 'memberOf', 'primaryGroupID', 'userPrincipalName',
            'initials', 'physicalDeliveryOfficeName', 'telephoneNumber', 'mail',
            'wWWHomePage', 'streetAddress', 'postOfficeBox', 'l', 'st',
            'postalCode', 'co', 'accountExpires', 'profilePath', 'scriptPath',
            'homeDirectory', 'homeDrive', 'homePhone', 'pager', 'mobile',
            'facsimileTelephoneNumber', 'ipPhone', 'info', 'title', 'department',
            'company', 'manager'
        ]
        res = samba_conn.search_s(user_dn, ldap.SCOPE_BASE, '(objectClass=user)', attributes)

        if not res:
            return None

        entry = res[0][1]
        properties = {}
        for key, value in entry.items():
            properties[key] = [v.decode('utf-8') for v in value]

        return properties

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching user properties for DN '{user_dn}': {e}")
        return None

def get_computer_properties(samba_conn, computer_dn):
    """Retrieves all properties for a given computer."""
    logger.debug(f"Fetching properties for computer DN: {computer_dn}")
    try:
        attributes = [
            'cn', 'dNSHostName', 'description', 'operatingSystem',
            'operatingSystemVersion', 'operatingSystemServicePack', 'memberOf',
            'primaryGroupID', 'userAccountControl', 'location', 'managedBy',
            'msDS-AllowedToDelegateTo', 'sAMAccountName', 'serverReferenceBL'
        ]
        res = samba_conn.search_s(computer_dn, ldap.SCOPE_BASE, '(objectClass=computer)', attributes)

        if not res:
            return None

        entry = res[0][1]
        properties = {}
        for key, value in entry.items():
            properties[key] = [v.decode('utf-8') for v in value]

        return properties

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching computer properties for DN '{computer_dn}': {e}")
        return None

def get_group_properties(samba_conn, group_dn, attributes=None):
    """Retrieves properties for a given group."""
    logger.debug(f"Fetching properties for group DN: {group_dn}")
    if attributes is None:
        attributes = [
            'cn', 'description', 'groupType', 'member', 'memberOf', 'primaryGroupToken', 'displayName'
        ]
    try:
        res = samba_conn.search_s(group_dn, ldap.SCOPE_BASE, '(objectClass=group)', attributes)

        if not res:
            return None

        entry = res[0][1]
        properties = {}
        for key, value in entry.items():
            properties[key] = [v.decode('utf-8') for v in value]

        return properties

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching group properties for DN '{group_dn}': {e}")
        return None

def get_group_by_rid(samba_conn, rid):
    """Finds a group by its primaryGroupToken (RID)."""
    logger.debug(f"Searching for group with RID: {rid}")
    
    root_info = get_forest_root_info(samba_conn)
    search_base = root_info['dn'] if root_info else BASE_DN

    # Convert RID to string if it's not already
    rid_str = str(rid)
    
    search_filter = f"(&(objectClass=group)(primaryGroupToken={rid_str}))"
    logger.debug(f"Using search filter: {search_filter}")
    logger.debug(f"Searching in base DN: {search_base}")
    
    try:
        # Use paged results for better reliability
        res = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, search_filter, ['cn', 'displayName'])
        
        logger.debug(f"Search returned {len(res)} results")
        
        for dn, attrs_data in res:
            # Handle referrals, which can appear as (None, ['ldap://...'])
            if dn is None:
                logger.debug(f"Ignoring referral result while searching for group with RID {rid}: {attrs_data}")
                continue

            logger.debug(f"Processing result: DN='{dn}', attrs={attrs_data}")

            # Handle different response formats from ldap library
            attrs = attrs_data
            if isinstance(attrs_data, list):
                try:
                    attrs = dict(attrs_data)
                except (TypeError, ValueError):
                    logger.error(f"Could not convert attribute list to dict for DN '{dn}'. List was: {attrs_data}")
                    continue

            cn_values = attrs.get('cn')
            if not cn_values:
                logger.warning(f"Group with RID {rid} found at DN '{dn}' but has no 'cn' attribute.")
                continue
                
            cn = cn_values[0].decode('utf-8') if isinstance(cn_values[0], bytes) else cn_values[0]
            
            # Handle displayName
            displayName_values = attrs.get('displayName')
            if displayName_values:
                displayName = displayName_values[0].decode('utf-8') if isinstance(displayName_values[0], bytes) else displayName_values[0]
            else:
                displayName = cn
            
            logger.info(f"Found group with RID {rid}: DN='{dn}', cn='{cn}', displayName='{displayName}'")
            return {
                'dn': dn,
                'cn': cn,
                'displayName': displayName
            }
        
        # If we get here, no group was found
        logger.warning(f"No group found with RID {rid}")
        
        # Try alternative search - some systems use 'rid' instead of 'primaryGroupToken'
        alt_filter = f"(&(objectClass=group)(rid={rid_str}))"
        logger.debug(f"Trying alternative search with filter: {alt_filter}")
        
        alt_res = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, alt_filter, ['cn', 'displayName'])
        logger.debug(f"Alternative search returned {len(alt_res)} results")
        
        if alt_res:
            for dn, attrs_data in alt_res:
                if dn is None:
                    continue
                    
                attrs = attrs_data
                if isinstance(attrs_data, list):
                    try:
                        attrs = dict(attrs_data)
                    except (TypeError, ValueError):
                        continue

                cn_values = attrs.get('cn')
                if cn_values:
                    cn = cn_values[0].decode('utf-8') if isinstance(cn_values[0], bytes) else cn_values[0]
                    
                    displayName_values = attrs.get('displayName')
                    if displayName_values:
                        displayName = displayName_values[0].decode('utf-8') if isinstance(displayName_values[0], bytes) else displayName_values[0]
                    else:
                        displayName = cn
                    
                    logger.info(f"Found group with RID {rid} using alternative search: DN='{dn}', cn='{cn}', displayName='{displayName}'")
                    return {
                        'dn': dn,
                        'cn': cn,
                        'displayName': displayName
                    }
        
        # If still no results, try searching for well-known groups
        if rid_str in ['513', '515', '516', '517', '518', '519', '520', '521', '522']:
            well_known_groups = {
                '513': 'Domain Users',
                '515': 'Domain Computers', 
                '516': 'Domain Controllers',
                '517': 'Cert Publishers',
                '518': 'Schema Admins',
                '519': 'Enterprise Admins',
                '520': 'Group Policy Creator Owners',
                '521': 'Read-only Domain Controllers',
                '522': 'Cloneable Domain Controllers'
            }
            
            group_name = well_known_groups.get(rid_str)
            if group_name:
                logger.info(f"Trying to find well-known group '{group_name}' for RID {rid}")
                name_filter = f"(&(objectClass=group)(cn={group_name}))"
                name_res = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, name_filter, ['cn', 'displayName', 'primaryGroupToken'])
                
                for dn, attrs_data in name_res:
                    if dn is None:
                        continue
                    
                    attrs = attrs_data if isinstance(attrs_data, dict) else dict(attrs_data)
                    cn_values = attrs.get('cn')
                    
                    if cn_values:
                        cn = cn_values[0].decode('utf-8') if isinstance(cn_values[0], bytes) else cn_values[0]
                        displayName_values = attrs.get('displayName')
                        displayName = displayName_values[0].decode('utf-8') if displayName_values and isinstance(displayName_values[0], bytes) else cn
                        
                        logger.info(f"Found well-known group: DN='{dn}', cn='{cn}', displayName='{displayName}'")
                        return {
                            'dn': dn,
                            'cn': cn,
                            'displayName': displayName
                        }
        
        return None
        
    except ldap.LDAPError as e:
        logger.error(f"LDAP error searching for group with RID {rid}: {e}")
        return None

def get_upn_suffixes(samba_conn):
    """
    Retrieves the UPN suffixes for the forest.
    """
    logger.info("Querying for UPN suffixes.")
    try:
        # First, find the configuration naming context from the RootDSE
        root_dse = samba_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ['configurationNamingContext'])
        if not root_dse or 'configurationNamingContext' not in root_dse[0][1]:
            logger.warning("Could not find 'configurationNamingContext' in RootDSE.")
            return []

        config_dn = root_dse[0][1]['configurationNamingContext'][0].decode('utf-8')
        partitions_dn = f"CN=Partitions,{config_dn}"

        # Now query the partitions container for the upnSuffixes attribute
        res = samba_conn.search_s(partitions_dn, ldap.SCOPE_BASE, "(objectClass=*)", ['upnSuffixes'])

        if res and 'upnSuffixes' in res[0][1]:
            suffixes = [s.decode('utf-8') for s in res[0][1]['upnSuffixes']]
            logger.info(f"Found UPN Suffixes: {suffixes}")
            return suffixes

        logger.info("No additional UPN suffixes found.")
        return []
    except ldap.LDAPError as e:
        logger.error(f"LDAP error querying for UPN suffixes: {e}")
        return []

def update_object_attributes(samba_conn, dn, modifications):
    """
    Updates attributes for a given LDAP object.
    modifications: A list of tuples, e.g., [(ldap.MOD_REPLACE, 'attributeName', b'newValue')]
    """
    logger.info(f"Attempting to modify DN: {dn} with changes: {modifications}")
    try:
        samba_conn.modify_s(dn, modifications)
        logger.info(f"Successfully modified DN: {dn}")
        return True, "Object updated successfully."
    except ldap.LDAPError as e:
        logger.error(f"LDAP error modifying DN '{dn}': {e}")
        return False, str(e)

def get_ntds_settings(samba_conn, ntds_dn):
    """Retrieves properties for the NTDS Settings object."""
    logger.debug(f"Fetching properties for NTDS Settings DN: {ntds_dn}")
    try:
        attributes = [
            'description', 'options', 'msDS-AdditionalDnsHostName', 'queryPolicyObject', 'objectGUID'
        ]
        res = samba_conn.search_s(ntds_dn, ldap.SCOPE_BASE, '(objectClass=nTDSDSA)', attributes)

        if not res:
            return None

        entry = res[0][1]
        properties = {}
        for key, value in entry.items():
            if key == 'objectGUID':
                properties[key] = value # Keep it as raw bytes
            else:
                properties[key] = [v.decode('utf-8') for v in value]

        return properties

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching NTDS settings for DN '{ntds_dn}': {e}")
        return None

def format_ldap_guid(guid_bytes_list):
    """Formats raw LDAP GUID bytes from a list into a standard UUID string."""
    if not guid_bytes_list:
        return ""
    return str(uuid.UUID(bytes_le=guid_bytes_list[0]))

def get_query_policies(samba_conn):
    """Retrieves all available query policies."""
    logger.info("Querying for LDAP query policies.")
    try:
        # First, find the configuration naming context from the RootDSE
        root_dse = samba_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ['configurationNamingContext'])
        if not root_dse or 'configurationNamingContext' not in root_dse[0][1]:
            logger.warning("Could not find 'configurationNamingContext' in RootDSE.")
            return ["Default Query Policy"]

        config_dn = root_dse[0][1]['configurationNamingContext'][0].decode('utf-8')
        search_base = f"CN=Query-Policies,CN=Directory Service,CN=Windows NT,CN=Services,{config_dn}"

        res = get_paged_results(samba_conn, search_base, ldap.SCOPE_ONELEVEL, '(objectClass=queryPolicy)', ['cn'])

        policies = []
        for dn, entry in res:
            if 'cn' in entry:
                policies.append(entry['cn'][0].decode('utf-8'))

        if "Default Query Policy" not in policies:
            policies.insert(0, "Default Query Policy")

        logger.info(f"Found query policies: {policies}")
        return policies

    except ldap.LDAPError as e:
        logger.error(f"LDAP error querying for query policies: {e}")
        return ["Default Query Policy"]

def get_replication_connections(samba_conn, ntds_dn):
    """Retrieves replication connections for a DC. Mocked for now."""
    logger.info(f"Fetching replication connections for {ntds_dn} (mocked).")
    # This is a placeholder. A real implementation would search for
    # nTDSConnection objects under this DN and also look at the
    # 'repsFrom' and 'repsTo' attributes.
    return [], [] # from, to

def find_objects(samba_conn, search_base, object_type, name, description):
    """
    Finds objects in the directory based on criteria.
    """
    logger.info(f"Finding objects in {search_base} of type {object_type} with name: {name} and description: {description}")

    # --- Build Object Class Filter ---
    object_class_filter = ""
    if object_type == "Users, Contacts, and Groups":
        object_class_filter = "(|(objectClass=user)(objectClass=contact)(objectClass=group))"
    elif object_type == "Computers":
        object_class_filter = "(objectClass=computer)"
    elif object_type == "Organizational Units":
        object_class_filter = "(objectClass=organizationalUnit)"
    else:
        return [] # Return empty for unsupported types for now

    # --- Build Attribute Filter ---
    attribute_filter = ""
    name_filter = ""
    if name:
        name_filter = f"(|(cn=*{name}*)(name=*{name}*))"

    description_filter = ""
    if description:
        description_filter = f"(description=*{description}*)"

    if name_filter and description_filter:
        attribute_filter = f"(&{name_filter}{description_filter})"
    elif name_filter:
        attribute_filter = name_filter
    elif description_filter:
        attribute_filter = description_filter
    else:
        attribute_filter = ""

    # --- Combine Filters ---
    if attribute_filter:
        search_filter = f"(&{object_class_filter}{attribute_filter})"
    else:
        search_filter = object_class_filter

    logger.debug(f"Constructed LDAP search filter: {search_filter}")

    # --- Perform Search ---
    try:
        attributes = ['cn', 'ou', 'dc', 'displayName', 'description', 'distinguishedName', 'objectClass']
        res = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, search_filter, attributes)

        objects = []
        for child_dn, entry in res:
            if isinstance(entry, dict):
                name_attr = entry.get('displayName') or entry.get('cn')
                if name_attr:
                    obj_data = {
                        'name': name_attr[0].decode('utf-8'),
                        'dn': child_dn,
                        'objectClass': [oc.decode('utf-8') for oc in entry.get('objectClass', [])]
                    }
                    if 'description' in entry:
                        obj_data['description'] = entry['description'][0].decode('utf-8')
                    objects.append(obj_data)
        return objects
    except ldap.LDAPError as e:
        logger.error(f"LDAP error during find operation: {e}")
        return []
