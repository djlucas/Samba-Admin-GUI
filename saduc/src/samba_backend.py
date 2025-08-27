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
from ldap.controls import SimplePagedResultsControl
import dns.resolver
import subprocess
import os

# Set SASL environment variables globally for GSSAPI over LDAPS compatibility
os.environ['LDAP_SASL_SECPROPS'] = 'minssf=0,maxssf=0'
# Try to disable SASL channel binding at the system level
os.environ['LDAP_SASL_CBT'] = 'none'
# Also set the SASL_SECPROPS for broader compatibility
os.environ['SASL_SECPROPS'] = 'minssf=0,maxssf=0'
import sys
import uuid
from impacket.ldap.ldaptypes import SR_SECURITY_DESCRIPTOR

# A map of attribute syntax OIDs to their i18n keys
SYNTAX_MAP = {
    "2.5.5.1": "attribute_edit_dialog.syntax.dn",
    "2.5.5.2": "attribute_edit_dialog.syntax.oid",
    "2.5.5.3": "attribute_edit_dialog.syntax.css",
    "2.5.5.4": "attribute_edit_dialog.syntax.cis",
    "2.5.5.5": "attribute_edit_dialog.syntax.ia5",
    "2.5.5.6": "attribute_edit_dialog.syntax.numeric",
    "2.5.5.7": "attribute_edit_dialog.syntax.dnwb",
    "2.5.5.8": "attribute_edit_dialog.syntax.bool",
    "2.5.5.9": "attribute_edit_dialog.syntax.int",
    "2.5.5.10": "attribute_edit_dialog.syntax.ocs",
    "2.5.5.11": "attribute_edit_dialog.syntax.utc",
    "2.5.5.12": "attribute_edit_dialog.syntax.us",
    "2.5.5.13": "attribute_edit_dialog.syntax.pa",
    "2.5.5.14": "attribute_edit_dialog.syntax.dns",
    "2.5.5.15": "attribute_edit_dialog.syntax.ntsd",
    "2.5.5.16": "attribute_edit_dialog.syntax.lii",
    "2.5.5.17": "attribute_edit_dialog.syntax.sid",
    "1.2.840.113556.1.4.906": "attribute_edit_dialog.syntax.dnb",
}
''

# --- Custom Exception ---
class NoKerberosTicketError(Exception):
    """Raised when no valid Kerberos ticket is found."""
    pass

# --- Global Configuration ---
logger = logging.getLogger("saduc_app." + __name__)

# BASE_DN will be dynamically determined from RootDSE
BASE_DN = None
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
# These will be dynamically built based on the actual domain DN.
NON_EXPANDABLE_CONTAINERS = set()

# Constants for groupType bits
GROUP_TYPE_SECURITY = 0x80000000
GROUP_TYPE_UNIVERSAL = 0x00000008
GROUP_TYPE_GLOBAL = 0x00000002
GROUP_TYPE_DOMAIN_LOCAL = 0x00000004


def get_base_dn(samba_conn=None):
    """
    Gets the BASE_DN, using cached value or dynamically discovering it.
    
    Args:
        samba_conn: Optional LDAP connection to use for discovery
        
    Returns:
        str: The base DN, or empty string if not found
    """
    global BASE_DN
    
    if BASE_DN is not None:
        return BASE_DN
    
    if samba_conn is not None:
        try:
            root_info = get_forest_root_info(samba_conn)
            if root_info and root_info.get('dn'):
                BASE_DN = root_info['dn']
                return BASE_DN
        except Exception as e:
            logger.warning(f"Failed to get base DN from connection: {e}")
    
    return ""


def get_ldap_conn():
    """
    Establishes an authenticated LDAP connection using GSSAPI/Kerberos.
    Includes a fallback mechanism for multiple servers discovered via DNS SRV records.
    Dynamically determines the domain and BASE_DN.
    """
    global BASE_DN, NON_EXPANDABLE_CONTAINERS
    
    # Check for a valid Kerberos ticket before attempting connection
    logger.info("Checking for a valid Kerberos ticket...")
    result = subprocess.run(['klist', '-s'], capture_output=True, text=True)
    if result.returncode != 0:
        raise NoKerberosTicketError(f"No valid Kerberos ticket found. Please run 'kinit' first.")
    logger.info("Kerberos ticket found.")

    # Get domain from Kerberos ticket if BASE_DN is not set
    if BASE_DN is None:
        result = subprocess.run(['klist'], capture_output=True, text=True)
        if result.returncode == 0:
            # Extract domain from kerberos ticket
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if '@' in line and ('krbtgt' in line.lower() or 'default principal' in line.lower()):
                    # Extract domain from principal
                    if '@' in line:
                        domain_part = line.split('@')[-1].strip()
                        if '.' in domain_part:
                            domain = domain_part.lower()
                            break
            else:
                # Fallback: try to get domain from environment or use a reasonable default
                logger.warning("Could not extract domain from kerberos ticket, will discover from LDAP")
                domain = None
        else:
            domain = None
    else:
        domain = '.'.join(p.split('=', 1)[-1] for p in BASE_DN.split(','))
    
    # If we have a domain, use it for SRV lookup, otherwise try common approaches
    if domain:
        srv_record = f'_ldap._tcp.{domain}'
    else:
        # This will be handled in the connection loop by trying to discover domain
        srv_record = None

    server_list = []
    
    if domain:
        try:
            answers = dns.resolver.resolve(srv_record, 'SRV')
            # Sort answers by priority and weight to get the preferred servers
            ldap_servers = sorted(answers, key=lambda x: (x.priority, x.weight))
            server_list = [str(r.target).rstrip('.') for r in ldap_servers]
            logger.info(f"Dynamically discovered LDAP servers via DNS: {server_list}")
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as e:
            logger.error(f"Failed to resolve DNS SRV record for '{srv_record}': {e}")
        except Exception as e:
            logger.error(f"An unexpected DNS error occurred: {e}")
    
    # If DNS SRV didn't work, try common server names
    if not server_list:
        if domain:
            common_names = ['dc', 'dc1', 'dc01', 'pdc', 'ldap']
            server_list = [f"{name}.{domain}" for name in common_names]
            server_list.append(domain)  # Try domain name directly
        else:
            # Last resort - try localhost
            server_list = ['localhost']
        logger.info(f"Using fallback server list: {server_list}")

    # Modified order: try LDAPS for all servers first, then StartTLS for all servers, then plain LDAP
    connection_attempts = []
    # LDAPS attempts for all servers
    for server in server_list:
        connection_attempts.append((server, 'ldaps', 'ldaps', 636))
    # StartTLS attempts for all servers  
    for server in server_list:
        connection_attempts.append((server, 'starttls', 'ldap', 389))
    # Plain LDAP attempts for all servers
    for server in server_list:
        connection_attempts.append((server, 'none', 'ldap', 389))
    
    for server, ssl_method, protocol, port in connection_attempts:
        try:
            logger.info(f"Attempting to connect to {ssl_method.upper()} server: {server}:{port}")
            conn = ldap.initialize(f'{protocol}://{server}:{port}')
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            conn.set_option(ldap.OPT_REFERRALS, 0)
            
            if ssl_method == 'ldaps':
                # For LDAPS, set SSL options
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                # Disable SASL channel binding for GSSAPI over LDAPS compatibility
                conn.set_option(ldap.OPT_X_SASL_NOCANON, 1)
                # Additional TLS settings for GSSAPI compatibility
                conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                # Set additional SASL security properties - disable SASL encryption since TLS provides it
                os.environ['LDAP_SASL_SECPROPS'] = 'minssf=0,maxssf=0'
                # Try to disable channel binding at multiple levels
                os.environ['LDAP_SASL_CBT'] = 'none'
                os.environ['KRB5_KTNAME'] = ''  # Clear any keytab that might interfere
                # Disable SASL channel binding entirely
                try:
                    conn.set_option(ldap.OPT_X_SASL_CBT, ldap.OPT_X_SASL_CBT_NONE)
                except AttributeError:
                    pass  # Option not available in this python-ldap version
            elif ssl_method == 'starttls':
                # For StartTLS, set TLS options before starting TLS
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                # Start TLS on the connection
                conn.start_tls_s()

            # Kerberos/GSSAPI bind with method-specific handling
            if ssl_method in ['ldaps', 'starttls']:
                # For encrypted connections, disable SASL security layer to avoid conflicts with TLS
                try:
                    # Set SASL security properties to disable encryption (let TLS handle it)
                    conn.set_option(ldap.OPT_X_SASL_SSF_MIN, 0)
                    conn.set_option(ldap.OPT_X_SASL_SSF_MAX, 0)
                    sasl_auth = ldap.sasl.gssapi('')
                    conn.sasl_interactive_bind_s("", sasl_auth)
                except ldap.LDAPError as ssl_sasl_error:
                    # If that fails, try with hostname specification
                    logger.debug(f"First GSSAPI bind failed, trying with hostname: {ssl_sasl_error}")
                    import socket
                    hostname = socket.getfqdn(server)
                    sasl_auth = ldap.sasl.gssapi(f'ldap@{hostname}')
                    conn.set_option(ldap.OPT_X_SASL_SSF_MIN, 0)
                    conn.set_option(ldap.OPT_X_SASL_SSF_MAX, 0)
                    conn.sasl_interactive_bind_s("", sasl_auth)
            else:
                # For plain LDAP, use standard GSSAPI (allows SASL encryption)
                sasl_auth = ldap.sasl.gssapi('')
                conn.sasl_interactive_bind_s("", sasl_auth)
            
            if ssl_method == 'ldaps':
                logger.info(f"Samba backend: Successfully established secure LDAPS connection to {server}:{port}.")
            elif ssl_method == 'starttls':
                logger.info(f"Samba backend: Successfully established secure LDAP+StartTLS connection to {server}:{port}.")
            else:
                # Plain LDAP with GSSAPI actually provides encryption via SASL (typically SSF=256)
                logger.info(f"Samba backend: Successfully established LDAP connection with GSSAPI encryption to {server}:{port}.")
            
            # Connection successful, discover BASE_DN if needed
            if BASE_DN is None:
                try:
                    root_dse = conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ['rootDomainNamingContext'])
                    if root_dse and 'rootDomainNamingContext' in root_dse[0][1]:
                        BASE_DN = root_dse[0][1]['rootDomainNamingContext'][0].decode('utf-8')
                        logger.info(f"Discovered BASE_DN from RootDSE: {BASE_DN}")
                        
                        # Set up NON_EXPANDABLE_CONTAINERS based on discovered BASE_DN
                        NON_EXPANDABLE_CONTAINERS.update({
                            f'cn=users,{BASE_DN}'.lower(),
                            f'cn=computers,{BASE_DN}'.lower(),
                            f'cn=builtin,{BASE_DN}'.lower(),
                            f'cn=foreignsecurityprincipals,{BASE_DN}'.lower()
                        })
                        logger.debug(f"Set NON_EXPANDABLE_CONTAINERS: {NON_EXPANDABLE_CONTAINERS}")
                    else:
                        logger.error("Could not discover BASE_DN from RootDSE")
                        return None, None
                except ldap.LDAPError as e:
                    logger.error(f"Error discovering BASE_DN: {e}")
                    return None, None
            
            return conn, server
            
        except ldap.LDAPError as e:
            if ssl_method == 'ldaps':
                logger.warning(f"LDAPS connection to {server}:{port} failed: {e}.")
            elif ssl_method == 'starttls':
                logger.warning(f"StartTLS connection to {server}:{port} failed: {e}.")
            else:
                logger.warning(f"LDAP connection to {server}:{port} failed: {e}")
            # Continue to next connection attempt
            conn = None
    
    # If we get here, all connection attempts failed
    logger.critical("Samba backend: Failed to connect to any LDAP servers.")
    return None, None

def _discover_base_dn_and_setup(conn, server):
    """Helper function to discover BASE_DN and setup containers after successful connection."""
    global BASE_DN, NON_EXPANDABLE_CONTAINERS
    
    # Now discover the BASE_DN from RootDSE if not already set
    if BASE_DN is None:
            if BASE_DN is None:
                try:
                    root_dse = conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ['rootDomainNamingContext'])
                    if root_dse and 'rootDomainNamingContext' in root_dse[0][1]:
                        BASE_DN = root_dse[0][1]['rootDomainNamingContext'][0].decode('utf-8')
                        logger.info(f"Discovered BASE_DN from RootDSE: {BASE_DN}")
                        
                        # Set up NON_EXPANDABLE_CONTAINERS based on discovered BASE_DN
                        NON_EXPANDABLE_CONTAINERS.update({
                            f'cn=users,{BASE_DN}'.lower(),
                            f'cn=computers,{BASE_DN}'.lower(),
                            f'cn=builtin,{BASE_DN}'.lower(),
                            f'cn=foreignsecurityprincipals,{BASE_DN}'.lower()
                        })
                        logger.debug(f"Set NON_EXPANDABLE_CONTAINERS: {NON_EXPANDABLE_CONTAINERS}")
                    else:
                        logger.error("Could not discover BASE_DN from RootDSE")
                        return None, None
                except ldap.LDAPError as e:
                    logger.error(f"Error discovering BASE_DN: {e}")
                    return None, None
            
            return conn, server

    logger.critical("Samba backend: Failed to connect to any LDAP servers.")
    return None, None

def get_paged_results(samba_conn, dn, scope, search_filter, attributes):
    """
    Performs a paged LDAP search to handle server-side result limits.
    """
    page_ctrl = SimplePagedResultsControl(True, size=PAGE_SIZE, cookie='')
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
            # Re-raise the exception so the caller can handle it
            raise e

    return all_results

def _is_tree_branch(entry, advanced_view=False, objects_as_containers=False):
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
    if len(object_classes.intersection(TREE_BRANCH_CLASSES)) > 0:
        return True
    
    if objects_as_containers:
        if len(object_classes.intersection({'user', 'group', 'contact', 'computer'})) > 0:
            return True

    return False

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

def get_expandable_children(samba_conn, dn, advanced_view=False, object_class=None, objects_as_containers=False):
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

            if object_class and any(c in object_class for c in ['user', 'group', 'contact', 'computer']):
                if name_attr:
                    children.append({
                        'name': name_attr[0].decode('utf-8'),
                        'dn': child_dn,
                        'objectClass': [oc.decode('utf-8') for oc in entry.get('objectClass', [])],
                        'has_sub_containers': False
                    })
            # Use our stricter check to see if this object belongs in the tree
            elif _is_tree_branch(entry, advanced_view, objects_as_containers) and name_attr:
                has_sub_containers = has_expandable_children(samba_conn, child_dn, advanced_view, objects_as_containers=objects_as_containers)
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


def has_expandable_children(samba_conn, dn, advanced_view=False, object_class=None, objects_as_containers=False):
    """
    Checks if a given DN has any children that are themselves structural containers.
    """
    logger.debug(f"Checking for expandable children in DN: {dn}")

    if not advanced_view and dn.lower() in NON_EXPANDABLE_CONTAINERS and not objects_as_containers:
        return False

    try:
        attributes = ['cn', 'ou', 'dc', 'objectClass', 'showInAdvancedViewOnly']
        res = samba_conn.search_s(dn, ldap.SCOPE_ONELEVEL, DEFAULT_SEARCH_FILTER, attributes)

        if not res:
            return False

        if object_class and any(c in object_class for c in ['user', 'group', 'contact', 'computer']):
            return len(res) > 0

        for child_dn, entry in res:
            # Use the same strict check here
            if _is_tree_branch(entry, advanced_view, objects_as_containers):
                return True # Found at least one valid branch child
        return False
    except ldap.NO_SUCH_OBJECT:
        return False
    except ldap.LDAPError as e:
        logger.error(f"LDAP error checking for expandable children in '{dn}': {e}")
        return False


def get_all_objects_in_dn(samba_conn, dn, attributes=None):
    """
    Retrieves all objects within a given DN, for display in the right pane.
    """
    logger.debug(f"Fetching all objects in DN: {dn}")
    try:
        search_filter = "(objectclass=*)"

        # Define a base set of attributes that are always needed
        required_attrs = {
            'cn', 'ou', 'dc', 'displayName', 'distinguishedName',
            'objectClass', 'showInAdvancedViewOnly'
        }

        if attributes:
            # Combine provided attributes with the required ones
            attributes_to_fetch = list(required_attrs.union(set(attributes)))
        else:
            # Use a default set if none are provided
            attributes_to_fetch = list(required_attrs.union({
                'description', 'sAMAccountName', 'userAccountControl'
            }))

        res = get_paged_results(samba_conn, dn, ldap.SCOPE_ONELEVEL, search_filter, attributes_to_fetch)

        objects = []
        for child_dn, entry in res:
            if isinstance(entry, dict):
                obj_data = {
                    'dn': child_dn,
                    'objectClass': [oc.decode('utf-8') for oc in entry.get('objectClass', [])]
                }

                # Process all fetched attributes
                for attr, value in entry.items():
                    try:
                        # Decode if possible, otherwise keep raw (for binary data)
                        obj_data[attr] = [v.decode('utf-8') for v in value]
                    except (UnicodeDecodeError, AttributeError):
                        obj_data[attr] = value

                # Handle single-value attributes for easier access
                for key, val in obj_data.items():
                    if isinstance(val, list) and len(val) == 1:
                        obj_data[key] = val[0]

                # Special handling for showInAdvancedViewOnly to be a boolean
                if 'showInAdvancedViewOnly' in obj_data:
                    obj_data['showInAdvancedViewOnly'] = obj_data['showInAdvancedViewOnly'].lower() == 'true'

                # Prioritize displayName for the list view 'name' field
                obj_data['name'] = obj_data.get('displayName', obj_data.get('ou', obj_data.get('dc', obj_data.get('cn', ''))))

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


def create_group_samba(samba_conn, group_data):
    """Creates a new group in Samba AD."""
    logger.info(f"Samba backend: Creating group with data: {group_data}")
    
    dn = f"CN={group_data['name']},{group_data['container_dn']}"
    
    group_type_val = 0
    if group_data['type'] == 'security':
        group_type_val |= GROUP_TYPE_SECURITY
    
    if group_data['scope'] == 'local':
        group_type_val |= GROUP_TYPE_DOMAIN_LOCAL
    elif group_data['scope'] == 'global':
        group_type_val |= GROUP_TYPE_GLOBAL
    elif group_data['scope'] == 'universal':
        group_type_val |= GROUP_TYPE_UNIVERSAL

    attrs = []
    attrs.append(('objectClass', [b'top', b'group']))
    attrs.append(('cn', [group_data['name'].encode('utf-8')]))
    attrs.append(('sAMAccountName', [group_data['name'].encode('utf-8')]))
    attrs.append(('groupType', [str(group_type_val).encode('utf-8')]))

    try:
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created group: {dn}")
        return True, "samba_backend.success.create_group", [group_data['name']]
    except ldap.ALREADY_EXISTS:
        logger.error(f"Group '{dn}' already exists.")
        return False, "samba_backend.error.group_exists", [group_data['name']]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating group '{dn}': {e}")
        return False, "samba_backend.error.create_group", [str(e)]


def copy_user_samba(samba_conn, source_username, new_user_data):
    """Placeholder for Samba user creation logic."""
    logger.info(f"Samba backend: Copying user '{source_username}' to new user with data: {new_user_data}")
    # ... placeholder for backend logic ...
    return True, "samba_backend.success.copy_user"

def get_schema_attributes(samba_conn, object_classes):
    """
    Retrieves the full schema definition for a given set of object classes.
    """
    schema_attributes = {}
    try:
        root_dse = samba_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ["schemaNamingContext"])
        schema_dn = root_dse[0][1]["schemaNamingContext"][0].decode('utf-8')
        
        classes_to_process = list(object_classes)
        processed_classes = set()
        must_contain_attrs = set()
        may_contain_attrs = set()

        while classes_to_process:
            oc = classes_to_process.pop(0)
            if oc in processed_classes:
                continue
            processed_classes.add(oc)

            try:
                attributes_to_fetch = ["mustContain", "mayContain", "systemMustContain", "systemMayContain", "subClassOf"]
                class_schema_result = samba_conn.search_s(schema_dn, ldap.SCOPE_ONELEVEL, f"(&(objectClass=classSchema)(lDAPDisplayName={oc}))", attributes_to_fetch)
                
                if class_schema_result:
                    class_attrs = class_schema_result[0][1]
                    must_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('mustContain', [])])
                    must_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('systemMustContain', [])])
                    may_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('mayContain', [])])
                    may_contain_attrs.update([attr.decode('utf-8') for attr in class_attrs.get('systemMayContain', [])])
                    parent_classes = [parent.decode('utf-8') for parent in class_attrs.get('subClassOf', [])]
                    classes_to_process.extend(parent_classes)
            except ldap.NO_SUCH_OBJECT:
                logger.warning(f"Could not find schema for objectClass '{oc}'.")
        
        class_schema_attrs = must_contain_attrs | may_contain_attrs

        all_attr_schemas_raw = get_paged_results(
            samba_conn,
            schema_dn,
            ldap.SCOPE_ONELEVEL,
            "(objectClass=attributeSchema)",
            ["lDAPDisplayName", "attributeSyntax", "isSingleValued", "systemFlags"]
        )

        all_attr_schemas = {
            attr_data['lDAPDisplayName'][0].decode('utf-8'): attr_data
            for _, attr_data in all_attr_schemas_raw if 'lDAPDisplayName' in attr_data
        }

        for attr_name in class_schema_attrs:
            attr_schema = all_attr_schemas.get(attr_name)
            if attr_schema:
                syntax_oid = attr_schema.get('attributeSyntax', [b''])[0].decode('utf-8')
                system_flags_raw = attr_schema.get('systemFlags', [b'0'])
                system_flags = int(system_flags_raw[0].decode('utf-8')) if system_flags_raw else 0
                
                schema_attributes[attr_name] = {
                    "attributeSyntax": SYNTAX_MAP.get(syntax_oid, syntax_oid),
                    "is_single_valued": attr_schema.get('isSingleValued', [b'FALSE'])[0].decode('utf-8').upper() == 'TRUE',
                    "is_read_only": (system_flags & 0x8) != 0,
                    "is_mandatory": attr_name in must_contain_attrs,
                    "is_constructed": (system_flags & 0x1) != 0,
                    "is_backlink": (system_flags & 0x2) != 0,
                    "is_system_only": (system_flags & 0x10) != 0,
                }
    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching schema attributes: {e}")
    return schema_attributes

def get_all_user_attributes_with_schema_info(samba_conn, user_dn):
    """
    Retrieves all attributes for a user, including empty ones from the schema.
    """
    logger.debug(f"Fetching all attributes with schema info for user DN: {user_dn}")
    try:
        res = samba_conn.search_s(user_dn, ldap.SCOPE_BASE, '(objectClass=user)', ['*', '+'])
        if not res:
            return None, None

        user_attributes = res[0][1]
        object_classes = [oc.decode('utf-8') for oc in user_attributes.get('objectClass', [])]
        
        schema_info = get_schema_attributes(samba_conn, object_classes)
        
        # Decode user attributes
        decoded_user_attributes = {}
        for key, value in user_attributes.items():
            try:
                decoded_user_attributes[key] = [v.decode('utf-8') for v in value]
            except (UnicodeDecodeError, AttributeError):
                decoded_user_attributes[key] = value # Keep raw for binary data

        return decoded_user_attributes, schema_info

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching user attributes with schema for DN '{user_dn}': {e}")
        return None, None

def get_all_computer_attributes_with_schema_info(samba_conn, computer_dn):
    """
    Retrieves all attributes for a computer, including empty ones from the schema.
    """
    logger.debug(f"Fetching all attributes with schema info for computer DN: {computer_dn}")
    try:
        res = samba_conn.search_s(computer_dn, ldap.SCOPE_BASE, '(objectClass=computer)', ['*', '+'])
        if not res:
            return None, None

        computer_attributes = res[0][1]
        object_classes = [oc.decode('utf-8') for oc in computer_attributes.get('objectClass', [])]
        
        schema_info = get_schema_attributes(samba_conn, object_classes)
        
        # Decode computer attributes
        decoded_computer_attributes = {}
        for key, value in computer_attributes.items():
            try:
                decoded_computer_attributes[key] = [v.decode('utf-8') for v in value]
            except (UnicodeDecodeError, AttributeError):
                decoded_computer_attributes[key] = value # Keep raw for binary data

        return decoded_computer_attributes, schema_info

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching computer attributes with schema for DN '{computer_dn}': {e}")
        return None, None

def get_all_printer_attributes_with_schema_info(samba_conn, printer_dn):
    """
    Retrieves all attributes for a printer, including empty ones from the schema.
    """
    logger.debug(f"Fetching all attributes with schema info for printer DN: {printer_dn}")
    try:
        res = samba_conn.search_s(printer_dn, ldap.SCOPE_BASE, '(objectClass=printQueue)', ['*', '+'])
        if not res:
            return None, None

        printer_attributes = res[0][1]
        object_classes = [oc.decode('utf-8') for oc in printer_attributes.get('objectClass', [])]

        schema_info = get_schema_attributes(samba_conn, object_classes)

        # Decode printer attributes
        decoded_printer_attributes = {}
        for key, value in printer_attributes.items():
            try:
                decoded_printer_attributes[key] = [v.decode('utf-8') for v in value]
            except (UnicodeDecodeError, AttributeError):
                decoded_printer_attributes[key] = value # Keep raw for binary data

        return decoded_printer_attributes, schema_info

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching printer attributes with schema for DN '{printer_dn}': {e}")
        return None, None

def get_all_container_attributes_with_schema_info(samba_conn, container_dn):
    """
    Retrieves all attributes for a container/ou, including empty ones from the schema.
    """
    logger.debug(f"Fetching all attributes with schema info for container DN: {container_dn}")
    try:
        search_filter = '''(|(objectClass=container)(objectClass=organizationalUnit))'''
        res = samba_conn.search_s(container_dn, ldap.SCOPE_BASE, search_filter, ['*', '+'])
        if not res:
            return None, None

        container_attributes = res[0][1]
        object_classes = [oc.decode('utf-8') for oc in container_attributes.get('objectClass', [])]
        
        schema_info = get_schema_attributes(samba_conn, object_classes)
        
        # Decode container attributes
        decoded_container_attributes = {}
        for key, value in container_attributes.items():
            try:
                decoded_container_attributes[key] = [v.decode('utf-8') for v in value]
            except (UnicodeDecodeError, AttributeError):
                decoded_container_attributes[key] = value # Keep raw for binary data

        return decoded_container_attributes, schema_info

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching container attributes with schema for DN '{container_dn}': {e}")
        return None, None

def get_all_group_attributes_with_schema_info(samba_conn, group_dn):
    """
    Retrieves all attributes for a group, including empty ones from the schema.
    """
    logger.debug(f"Fetching all attributes with schema info for group DN: {group_dn}")
    try:
        res = samba_conn.search_s(group_dn, ldap.SCOPE_BASE, '(objectClass=group)', ['*', '+'])
        if not res:
            return None, None

        group_attributes = res[0][1]
        object_classes = [oc.decode('utf-8') for oc in group_attributes.get('objectClass', [])]
        
        schema_info = get_schema_attributes(samba_conn, object_classes)
        
        # Decode group attributes
        decoded_group_attributes = {}
        for key, value in group_attributes.items():
            try:
                decoded_group_attributes[key] = [v.decode('utf-8') for v in value]
            except (UnicodeDecodeError, AttributeError):
                decoded_group_attributes[key] = value # Keep raw for binary data

        return decoded_group_attributes, schema_info

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching group attributes with schema for DN '{group_dn}': {e}")
        return None, None

def get_all_contact_attributes_with_schema_info(samba_conn, contact_dn):
    """
    Retrieves all attributes for a contact, including empty ones from the schema.
    """
    logger.debug(f"Fetching all attributes with schema info for contact DN: {contact_dn}")
    try:
        res = samba_conn.search_s(contact_dn, ldap.SCOPE_BASE, '(objectClass=contact)', ['*', '+'])
        if not res:
            return None, None

        contact_attributes = res[0][1]
        object_classes = [oc.decode('utf-8') for oc in contact_attributes.get('objectClass', [])]

        schema_info = get_schema_attributes(samba_conn, object_classes)

        # Decode contact attributes
        decoded_contact_attributes = {}
        for key, value in contact_attributes.items():
            try:
                decoded_contact_attributes[key] = [v.decode('utf-8') for v in value]
            except (UnicodeDecodeError, AttributeError):
                decoded_contact_attributes[key] = value # Keep raw for binary data

        return decoded_contact_attributes, schema_info

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching contact attributes with schema for DN '{contact_dn}': {e}")
        return None, None

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

def get_container_properties(samba_conn, container_dn, attributes=None):
    """Retrieves properties for a given container, OU, or built-in domain."""
    logger.debug(f"Fetching properties for container DN: {container_dn}")
    if attributes is None:
        attributes = [
            'cn', 'ou', 'description', 'objectClass', 'street', 'l', 'st',
            'postalCode', 'co', 'managedBy'
        ]

    search_filter = '(|(objectClass=container)(objectClass=organizationalUnit)(objectClass=builtinDomain)(objectClass=domainDNS))'

    try:
        res = samba_conn.search_s(container_dn, ldap.SCOPE_BASE, search_filter, attributes)

        if not res:
            logger.warning(f"No container object found at DN: {container_dn}")
            return None

        entry = res[0][1]
        properties = {}
        for key, value in entry.items():
            properties[key] = [v.decode('utf-8') for v in value]

        return properties

    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching container properties for DN '{container_dn}': {e}")
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

def get_netbios_name(samba_conn):
    """Retrieves the NETBIOS name of the domain using the correct query."""
    logger.info("Querying for NETBIOS domain name.")
    try:
        # Get the configuration naming context from RootDSE
        root_dse = samba_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ['configurationNamingContext', 'rootDomainNamingContext'])
        if not root_dse or 'configurationNamingContext' not in root_dse[0][1]:
            logger.error("Could not find 'configurationNamingContext' in RootDSE.")
            return "SAMBA" # Fallback

        config_dn = root_dse[0][1]['configurationNamingContext'][0].decode('utf-8')
        
        # Get the DNS root name
        root_dn = root_dse[0][1]['rootDomainNamingContext'][0].decode('utf-8')
        domain_dns_name = ".".join(p.split('=')[1] for p in root_dn.split(',') if p.lower().startswith('dc='))

        search_filter = f"(&(objectCategory=crossRef)(dnsRoot={domain_dns_name})(netBIOSName=*))"
        logger.debug(f"Searching for NETBIOS name with filter: {search_filter} in base {config_dn}")

        res = samba_conn.search_s(config_dn, ldap.SCOPE_SUBTREE, search_filter, ['nETBIOSName'])

        if res and 'nETBIOSName' in res[0][1]:
            netbios_name = res[0][1]['nETBIOSName'][0].decode('utf-8')
            logger.info(f"Found NETBIOS name: {netbios_name}")
            return netbios_name
        else:
            logger.warning(f"Could not find NETBIOS name with crossRef query. Falling back to domain object.")
            # Fallback to original method if the crossRef query fails
            res = samba_conn.search_s(root_dn, ldap.SCOPE_BASE, "(objectClass=domain)", ['nETBIOSName'])
            if res and 'nETBIOSName' in res[0][1]:
                netbios_name = res[0][1]['nETBIOSName'][0].decode('utf-8')
                logger.info(f"Found NETBIOS name on domain object: {netbios_name}")
                return netbios_name

    except ldap.LDAPError as e:
        logger.error(f"LDAP error querying for NETBIOS name: {e}")
    
    logger.error("NETBIOS name not found, returning fallback.")
    return "SAMBA" # Fallback


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
        if object_type == "Organizational Units":
            name_filter = f"(ou=*{name}*)"
        else:
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
                name_attr = entry.get('displayName') or entry.get('ou') or entry.get('cn')
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

def get_nt_security_descriptor(samba_conn, dn):
    """Retrieves and parses the nTSecurityDescriptor for a given object."""
    logger.debug(f"Fetching nTSecurityDescriptor for DN: {dn}")
    try:
        # To avoid errors when the user doesn't have permission to read the SACL,
        # we need to use a special control to request only the Owner, Group, and DACL.
        # The OID for this control is 1.2.840.113556.1.4.801
        # The value is a BER-encoded integer with the flags.
        # 1 = OWNER_SECURITY_INFORMATION
        # 2 = GROUP_SECURITY_INFORMATION
        # 4 = DACL_SECURITY_INFORMATION
        # 7 = 1 | 2 | 4
        # For now, we will try to fetch everything and handle the error if it occurs.
        res = samba_conn.search_s(dn, ldap.SCOPE_BASE, '(objectClass=*)', ['nTSecurityDescriptor'])

        if not res or 'nTSecurityDescriptor' not in res[0][1]:
            logger.warning(f"nTSecurityDescriptor not found for DN: {dn}")
            return None

        sd_data = res[0][1]['nTSecurityDescriptor'][0]
        sd = SR_SECURITY_DESCRIPTOR()
        sd.fromString(sd_data)
        return sd

    except ldap.INSUFFICIENT_ACCESS as e:
        logger.error(f"LDAP error fetching nTSecurityDescriptor for DN '{dn}': {e}. This is likely due to missing permissions to read the SACL.")
        return None
    except ldap.LDAPError as e:
        logger.error(f"LDAP error fetching nTSecurityDescriptor for DN '{dn}': {e}")
        return None

WELL_KNOWN_SIDS = {
    "S-1-1-0": "Everyone",
    "S-1-3-0": "Creator Owner",
    "S-1-5-10": "NT Authority\\SELF",
    "S-1-5-18": "LOCAL SYSTEM",
    "S-1-5-32-544": "Administrators",
    "S-1-5-32-545": "Users",
    "S-1-5-32-546": "Guests",
    "S-1-5-32-547": "Power Users",
    "S-1-5-32-554": "Pre-Windows 2000 Compatible Access",
    "S-1-5-32-555": "Remote Desktop Users",
    "S-1-5-32-556": "Network Configuration Operators",
    "S-1-5-6": "Service",
    "S-1-5-7": "Anonymous Logon",
    "S-1-5-9": "Enterprise Domain Controllers",
    "S-1-5-11": "Authenticated Users",
    "S-1-5-12": "Restricted Code",
    "S-1-5-13": "Terminal Server Users",
    "S-1-5-14": "Remote Interactive Logon",
    "S-1-5-15": "This Organization",
    "S-1-5-17": "IUSR",
    "S-1-5-19": "NT Authority",
    "S-1-5-20": "Network Service",
}

def resolve_sid(samba_conn, sid):
    """Resolves a SID to a user or group name."""
    logger.debug(f"Resolving SID: {sid}")
    if sid in WELL_KNOWN_SIDS:
        return WELL_KNOWN_SIDS[sid]
    try:
        search_filter = f"(objectSid={sid})"
        # Use forest root info if BASE_DN is not available
        search_base = BASE_DN
        if search_base is None:
            root_info = get_forest_root_info(samba_conn)
            search_base = root_info['dn'] if root_info else ""
        res = samba_conn.search_s(search_base, ldap.SCOPE_SUBTREE, search_filter, ['sAMAccountName', 'cn'])
        logger.debug(f"LDAP search result for SID {sid}: {res}")
        if res:
            if 'sAMAccountName' in res[0][1]:
                return res[0][1]['sAMAccountName'][0].decode('utf-8')
            elif 'cn' in res[0][1]:
                return res[0][1]['cn'][0].decode('utf-8')
        return sid
    except ldap.LDAPError as e:
        logger.error(f"LDAP error resolving SID '{sid}': {e}")
        return sid


def get_rodc_password_replication_status(samba_conn, object_dn):
    """Gets the password replication status for a given object on all RODCs."""
    rodc_list = []
    try:
        # Find all RODCs
        rodc_filter = "(&(objectCategory=computer)(userAccountControl:1.2.840.113556.1.4.803:=8388608))"
        rodc_attrs = ['cn', 'msDS-RevealOnDemandGroup', 'msDS-NeverRevealGroup', 'msDS-RevealedList']
        
        # Get base DN dynamically
        search_base = get_base_dn(samba_conn)
        if not search_base:
            return rodc_list
            
        rodcs = get_paged_results(samba_conn, search_base, ldap.SCOPE_SUBTREE, rodc_filter, rodc_attrs)
        for rodc_dn, rodc_attrs_data in rodcs:
            if rodc_dn is None:
                continue
            rodc_attrs_dict = rodc_attrs_data
            if isinstance(rodc_attrs_data, list):
                try:
                    rodc_attrs_dict = dict(rodc_attrs_data)
                except (TypeError, ValueError):
                    logger.warning(f"Could not convert attribute list to dict for RODC DN '{rodc_dn}'.")
                    continue
            
            # Decode the revealed list for comparison
            revealed_list_raw = rodc_attrs_dict.get('msDS-RevealedList', [])
            revealed_list = [dn.decode('utf-8') for dn in revealed_list_raw]
            # Check if the user is in the revealed list
            if object_dn in revealed_list:
                rodc_name = rodc_attrs_dict.get('cn', [b'Unknown'])[0].decode('utf-8')
                rodc_list.append({'name': rodc_name, 'site': 'Default-First-Site-Name'}) # Site is placeholder
    except ldap.LDAPError as e:
        logger.error(f"LDAP error getting RODC password replication status: {e}")
    return rodc_list


def get_user_certificates(samba_conn, user_dn):
    """Gets the published certificates for a given user."""
    certs = []
    try:
        res = samba_conn.search_s(user_dn, ldap.SCOPE_BASE, '(objectClass=user)', ['userCertificate'])
        if res and 'userCertificate' in res[0][1]:
            certs = res[0][1]['userCertificate']
    except ldap.LDAPError as e:
        logger.error(f"LDAP error getting user certificates: {e}")
    return certs


def get_laps_info(samba_conn, computer_dn):
    """Gets LAPS information for a computer object."""
    laps_info = {
        'password': '',
        'password_expiration': None,
        'admin_account': ''  # Empty by default, only set if LAPS is configured
    }
    
    # LAPS attributes to retrieve
    laps_attrs = [
        'ms-Mcs-AdmPwd',                    # Legacy LAPS password
        'ms-Mcs-AdmPwdExpirationTime',      # Legacy LAPS expiration
        'msLAPS-Password',                  # Windows LAPS password
        'msLAPS-PasswordExpirationTime',    # Windows LAPS expiration
        'msLAPS-EncryptedPassword',         # Windows LAPS encrypted password
        'samAccountName'                    # For admin account name derivation
    ]
    
    try:
        res = samba_conn.search_s(computer_dn, ldap.SCOPE_BASE, '(objectClass=computer)', laps_attrs)
        if res:
            attrs = res[0][1]
            
            # Check for Windows LAPS first (newer)
            if 'msLAPS-Password' in attrs:
                password_data = attrs['msLAPS-Password'][0]
                if isinstance(password_data, bytes):
                    # Windows LAPS stores JSON data
                    try:
                        import json
                        password_json = json.loads(password_data.decode('utf-8'))
                        laps_info['password'] = password_json.get('p', '')
                        # Extract admin account name if available
                        laps_info['admin_account'] = password_json.get('n', '')
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        laps_info['password'] = password_data.decode('utf-8', errors='ignore')
                        
            # Check for legacy LAPS
            elif 'ms-Mcs-AdmPwd' in attrs:
                password_bytes = attrs['ms-Mcs-AdmPwd'][0]
                if isinstance(password_bytes, bytes):
                    laps_info['password'] = password_bytes.decode('utf-8', errors='ignore')
                else:
                    laps_info['password'] = str(password_bytes)
            
            # Get expiration time (try Windows LAPS first, then legacy)
            if 'msLAPS-PasswordExpirationTime' in attrs:
                exp_time = attrs['msLAPS-PasswordExpirationTime'][0]
                laps_info['password_expiration'] = _parse_windows_filetime(exp_time)
            elif 'ms-Mcs-AdmPwdExpirationTime' in attrs:
                exp_time = attrs['ms-Mcs-AdmPwdExpirationTime'][0]
                laps_info['password_expiration'] = _parse_windows_filetime(exp_time)
            
            # Only set admin account name if LAPS is actually configured (has password or expiration)
            if (laps_info['password'] or laps_info['password_expiration']) and not laps_info['admin_account']:
                laps_info['admin_account'] = 'Administrator'
                
    except ldap.LDAPError as e:
        logger.error(f"LDAP error getting LAPS info: {e}")
    
    return laps_info


def _parse_windows_filetime(filetime_value):
    """Convert Windows FILETIME to datetime."""
    try:
        if isinstance(filetime_value, bytes):
            filetime_int = int(filetime_value.decode('utf-8'))
        else:
            filetime_int = int(filetime_value)
        
        # Windows FILETIME is 100-nanosecond intervals since January 1, 1601
        # Convert to Unix timestamp
        unix_timestamp = (filetime_int - 116444736000000000) / 10000000
        
        from datetime import datetime
        return datetime.fromtimestamp(unix_timestamp)
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing FILETIME: {e}")
        return None


def set_laps_expiration(samba_conn, computer_dn, expiration_datetime):
    """Set LAPS password expiration time."""
    try:
        # Convert datetime to Windows FILETIME
        from datetime import datetime
        import time
        
        # Convert to Unix timestamp then to Windows FILETIME
        unix_timestamp = time.mktime(expiration_datetime.timetuple())
        filetime = int((unix_timestamp * 10000000) + 116444736000000000)
        
        # Try to update Windows LAPS first, then legacy
        modifications = [
            (ldap.MOD_REPLACE, 'msLAPS-PasswordExpirationTime', [str(filetime).encode('utf-8')]),
            (ldap.MOD_REPLACE, 'ms-Mcs-AdmPwdExpirationTime', [str(filetime).encode('utf-8')])
        ]
        
        for mod in modifications:
            try:
                samba_conn.modify_s(computer_dn, [mod])
                logger.info(f"Successfully updated LAPS expiration for {computer_dn}")
                return True
            except ldap.LDAPError:
                continue  # Try next attribute
                
        logger.error(f"Failed to update LAPS expiration for {computer_dn}")
        return False
        
    except Exception as e:
        logger.error(f"Error setting LAPS expiration: {e}")
        return False

