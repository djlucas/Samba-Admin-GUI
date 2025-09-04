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

def get_ldap_conn_with_server(target_server):
    """
    Establishes an authenticated LDAP connection to a specific server using GSSAPI/Kerberos.
    
    Args:
        target_server (str): The specific domain controller to connect to
        
    Returns:
        tuple: (ldap_connection, connected_server) or (None, None) if failed
    """
    global BASE_DN, NON_EXPANDABLE_CONTAINERS
    
    # Check for a valid Kerberos ticket before attempting connection
    logger.info("Checking for a valid Kerberos ticket...")
    result = subprocess.run(['klist', '-s'], capture_output=True, text=True)
    if result.returncode != 0:
        raise NoKerberosTicketError(f"No valid Kerberos ticket found. Please run 'kinit' first.")
    logger.info("Kerberos ticket found.")
    
    # Try different connection methods for the target server
    connection_attempts = [
        (target_server, 'ldaps', 'ldaps', 636),     # LDAPS (SSL)
        (target_server, 'starttls', 'ldap', 389),  # StartTLS
        (target_server, 'none', 'ldap', 389)       # Plain LDAP
    ]
    
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
            elif ssl_method == 'starttls':
                # For StartTLS, enable TLS on the connection
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                conn.start_tls_s()
                # Disable SASL channel binding for GSSAPI compatibility
                conn.set_option(ldap.OPT_X_SASL_NOCANON, 1)
            else:
                # For plain LDAP, still disable SASL channel binding for compatibility
                conn.set_option(ldap.OPT_X_SASL_NOCANON, 1)
            
            # Attempt GSSAPI authentication
            conn.sasl_non_interactive_bind_s('GSSAPI')
            logger.info(f"Successfully authenticated with GSSAPI to {server} using {ssl_method.upper()}")
            
            # Discover and setup BASE_DN if needed
            if BASE_DN is None:
                _discover_base_dn_and_setup(conn, server)
            
            return conn, server
            
        except ldap.SERVER_DOWN:
            logger.error(f"Server {server}:{port} ({ssl_method}) is not reachable")
            conn = None
        except ldap.INVALID_CREDENTIALS:
            logger.error(f"Invalid credentials for server {server}:{port} ({ssl_method})")
            conn = None
        except ldap.INAPPROPRIATE_AUTH:
            logger.error(f"Authentication method not supported by server {server}:{port} ({ssl_method})")
            conn = None
        except ldap.UNWILLING_TO_PERFORM:
            logger.error(f"Server {server}:{port} ({ssl_method}) is unwilling to perform the operation")
            conn = None
        except Exception as e:
            logger.error(f"Unexpected error connecting to {server}:{port} ({ssl_method}): {e}")
            conn = None
    
    # If we get here, all connection attempts failed
    logger.critical(f"Failed to connect to target server: {target_server}")
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

def _is_tree_branch(entry, advanced_view=False, show_objects_as_containers=False):
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
    
    if show_objects_as_containers:
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

def get_expandable_children(samba_conn, dn, advanced_view=False, object_class=None, show_objects_as_containers=False):
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
            elif _is_tree_branch(entry, advanced_view, show_objects_as_containers) and name_attr:
                has_sub_containers = has_expandable_children(samba_conn, child_dn, advanced_view, show_objects_as_containers=show_objects_as_containers)
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


def has_expandable_children(samba_conn, dn, advanced_view=False, object_class=None, show_objects_as_containers=False):
    """
    Checks if a given DN has any children that are themselves structural containers.
    """
    logger.debug(f"Checking for expandable children in DN: {dn}")

    if not advanced_view and dn.lower() in NON_EXPANDABLE_CONTAINERS and not show_objects_as_containers:
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
            if _is_tree_branch(entry, advanced_view, show_objects_as_containers):
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

        logger.info(f"Requesting attributes: {attributes_to_fetch}")
        res = get_paged_results(samba_conn, dn, ldap.SCOPE_ONELEVEL, search_filter, attributes_to_fetch)
        logger.info(f"Got {len(res)} objects from LDAP")

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
                
                # Special handling for user and computer objects that didn't get userAccountControl
                if ('user' in obj_data.get('objectClass', []) or 'computer' in obj_data.get('objectClass', [])) and 'userAccountControl' not in obj_data:
                    try:
                        # Make a specific query for this object's userAccountControl
                        object_filter = '(|(objectClass=user)(objectClass=computer))'
                        obj_res = samba_conn.search_s(child_dn, ldap.SCOPE_BASE, object_filter, ['userAccountControl'])
                        if obj_res and len(obj_res) > 0 and 'userAccountControl' in obj_res[0][1]:
                            uac_values = obj_res[0][1]['userAccountControl']
                            obj_data['userAccountControl'] = uac_values[0].decode('utf-8') if uac_values else '0'
                            obj_type = 'user' if 'user' in obj_data.get('objectClass', []) else 'computer'
                            logger.debug(f"Retrieved userAccountControl={obj_data['userAccountControl']} for {obj_type} {child_dn}")
                    except ldap.LDAPError as e:
                        logger.warning(f"Failed to get userAccountControl for {child_dn}: {e}")
                        obj_data['userAccountControl'] = '0'

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
    """Creates a new user in Samba AD."""
    logger.info(f"Samba backend: Creating user with data: {user_data}")
    
    # Construct user DN
    cn_value = user_data.get('full_name') or user_data.get('user_logon_name')
    if not cn_value:
        logger.error("Cannot create user: missing both full_name and user_logon_name")
        return False, "samba_backend.error.missing_username"
        
    dn = f"CN={cn_value},{user_data['container_dn']}"
    
    # Build userAccountControl value
    uac_value = 0x0200  # NORMAL_ACCOUNT
    
    if user_data.get('account_is_disabled', False):
        uac_value |= 0x0002  # UAC_ACCOUNT_DISABLED
    if user_data.get('password_never_expires', False):
        uac_value |= 0x10000  # UAC_DONT_EXPIRE_PASSWORD
    if user_data.get('user_cannot_change_password', False):
        uac_value |= 0x0040  # UAC_PASSWORD_CANT_CHANGE
    if user_data.get('user_must_change_password', True):
        # When user must change password, set password expired
        uac_value |= 0x800000  # UAC_PASSWORD_EXPIRED

    # Build attributes list
    attrs = []
    attrs.append(('objectClass', [b'top', b'person', b'organizationalPerson', b'user']))
    attrs.append(('cn', [cn_value.encode('utf-8')]))
    attrs.append(('sAMAccountName', [user_data['pre_win2k_logon'].encode('utf-8')]))
    attrs.append(('userAccountControl', [str(uac_value).encode('utf-8')]))
    
    # Note: primaryGroupID will be automatically set to 513 (Domain Users) by AD
    
    # Add optional attributes
    if user_data.get('first_name'):
        attrs.append(('givenName', [user_data['first_name'].encode('utf-8')]))
    if user_data.get('last_name'):
        attrs.append(('sn', [user_data['last_name'].encode('utf-8')]))
    if user_data.get('initials'):
        attrs.append(('initials', [user_data['initials'].encode('utf-8')]))
    if user_data.get('full_name'):
        attrs.append(('displayName', [user_data['full_name'].encode('utf-8')]))
    
    # Set UPN
    if user_data.get('user_logon_name') and user_data.get('upn_domain'):
        # Strip @ prefix if present (UI includes @ in dropdown)
        upn_domain = user_data['upn_domain'].lstrip('@')
        upn = f"{user_data['user_logon_name']}@{upn_domain}"
        attrs.append(('userPrincipalName', [upn.encode('utf-8')]))

    try:
        # Create the user object first
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created user object: {dn}")
        
        # Set password if provided
        password = user_data.get('password')
        if password:
            try:
                # Format password for unicodePwd (UTF-16LE with quotes)
                password_utf16 = f'"{password}"'.encode('utf-16le')
                mod_list = [(ldap.MOD_REPLACE, 'unicodePwd', password_utf16)]
                samba_conn.modify_s(dn, mod_list)
                logger.info(f"Successfully set password for user: {cn_value}")
            except ldap.INSUFFICIENT_ACCESS as e:
                logger.error(f"Insufficient access to set password for {cn_value}: {e}")
                logger.error("Service account may lack 'Reset Password' permissions")
            except ldap.CONSTRAINT_VIOLATION as e:
                logger.error(f"Password constraint violation for {cn_value}: {e}")
                logger.error("Password may not meet complexity requirements")
            except ldap.UNWILLING_TO_PERFORM as e:
                logger.error(f"Server unwilling to perform password change for {cn_value}: {e}")
                logger.error("This often indicates SSL/TLS is required but not active")
            except ldap.LDAPError as e:
                logger.error(f"LDAP error setting password for {cn_value}: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                # Don't fail the entire user creation if password fails
                # The user can be created and password set later
        
        return True, "samba_backend.success.create_user", [cn_value]
        
    except ldap.ALREADY_EXISTS:
        logger.error(f"User '{dn}' already exists.")
        return False, "samba_backend.error.user_exists", [cn_value]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating user '{dn}': {e}")
        return False, "samba_backend.error.create_user", [str(e)]


def create_contact_samba(samba_conn, contact_data):
    """Creates a new contact in Samba AD."""
    logger.info(f"Samba backend: Creating contact with data: {contact_data}")
    
    # Construct contact DN - use display name if available, otherwise first or last name
    cn_value = (contact_data.get('display_name') or 
                contact_data.get('first_name') or 
                contact_data.get('last_name') or
                'New Contact')
    
    if not cn_value.strip():
        logger.error("Cannot create contact: missing name information")
        return False, "samba_backend.error.missing_contact_name"
        
    dn = f"CN={cn_value},{contact_data['container_dn']}"
    
    # Build attributes list for contact
    attrs = []
    attrs.append(('objectClass', [b'top', b'person', b'organizationalPerson', b'contact']))
    attrs.append(('cn', [cn_value.encode('utf-8')]))
    
    # Add optional attributes
    if contact_data.get('first_name'):
        attrs.append(('givenName', [contact_data['first_name'].encode('utf-8')]))
    if contact_data.get('last_name'):
        attrs.append(('sn', [contact_data['last_name'].encode('utf-8')]))
    if contact_data.get('initials'):
        attrs.append(('initials', [contact_data['initials'].encode('utf-8')]))
    if contact_data.get('display_name'):
        attrs.append(('displayName', [contact_data['display_name'].encode('utf-8')]))

    try:
        # Create the contact object
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created contact object: {dn}")
        
        return True, "samba_backend.success.create_contact", [cn_value]
        
    except ldap.ALREADY_EXISTS:
        logger.error(f"Contact '{dn}' already exists.")
        return False, "samba_backend.error.contact_exists", [cn_value]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating contact '{dn}': {e}")
        return False, "samba_backend.error.create_contact", [str(e)]


def create_inetorgperson_samba(samba_conn, user_data):
    """Creates a new inetOrgPerson in Samba AD."""
    logger.info(f"Samba backend: Creating inetOrgPerson with data: {user_data}")
    
    # Construct inetOrgPerson DN
    cn_value = user_data.get('full_name') or user_data.get('user_logon_name')
    if not cn_value:
        logger.error("Cannot create inetOrgPerson: missing both full_name and user_logon_name")
        return False, "samba_backend.error.missing_username"
        
    dn = f"CN={cn_value},{user_data['container_dn']}"
    
    # Build userAccountControl value
    uac_value = 0x0200  # NORMAL_ACCOUNT
    
    if user_data.get('account_is_disabled', False):
        uac_value |= 0x0002  # UAC_ACCOUNT_DISABLED
    if user_data.get('password_never_expires', False):
        uac_value |= 0x10000  # UAC_DONT_EXPIRE_PASSWORD
    if user_data.get('user_cannot_change_password', False):
        uac_value |= 0x0040  # UAC_PASSWORD_CANT_CHANGE
    if user_data.get('user_must_change_password', True):
        # When user must change password, set password expired
        uac_value |= 0x800000  # UAC_PASSWORD_EXPIRED

    # Build attributes list - inetOrgPerson extends organizationalPerson
    attrs = []
    attrs.append(('objectClass', [b'top', b'person', b'organizationalPerson', b'user', b'inetOrgPerson']))
    attrs.append(('cn', [cn_value.encode('utf-8')]))
    attrs.append(('sAMAccountName', [user_data['pre_win2k_logon'].encode('utf-8')]))
    attrs.append(('userAccountControl', [str(uac_value).encode('utf-8')]))
    
    # Note: primaryGroupID will be automatically set to 513 (Domain Users) by AD
    
    # Add optional attributes
    if user_data.get('first_name'):
        attrs.append(('givenName', [user_data['first_name'].encode('utf-8')]))
    if user_data.get('last_name'):
        attrs.append(('sn', [user_data['last_name'].encode('utf-8')]))
    if user_data.get('initials'):
        attrs.append(('initials', [user_data['initials'].encode('utf-8')]))
    if user_data.get('full_name'):
        attrs.append(('displayName', [user_data['full_name'].encode('utf-8')]))
    
    # Set UPN
    if user_data.get('user_logon_name') and user_data.get('upn_domain'):
        # Strip @ prefix if present (UI includes @ in dropdown)
        upn_domain = user_data['upn_domain'].lstrip('@')
        upn = f"{user_data['user_logon_name']}@{upn_domain}"
        attrs.append(('userPrincipalName', [upn.encode('utf-8')]))

    try:
        # Create the inetOrgPerson object first
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created inetOrgPerson object: {dn}")
        
        # Set password if provided
        password = user_data.get('password')
        if password:
            try:
                # Format password for unicodePwd (UTF-16LE with quotes)
                password_utf16 = f'"{password}"'.encode('utf-16le')
                mod_list = [(ldap.MOD_REPLACE, 'unicodePwd', password_utf16)]
                samba_conn.modify_s(dn, mod_list)
                logger.info(f"Successfully set password for inetOrgPerson: {cn_value}")
            except ldap.INSUFFICIENT_ACCESS as e:
                logger.error(f"Insufficient access to set password for {cn_value}: {e}")
                logger.error("Service account may lack 'Reset Password' permissions")
            except ldap.CONSTRAINT_VIOLATION as e:
                logger.error(f"Password constraint violation for {cn_value}: {e}")
                logger.error("Password may not meet complexity requirements")
            except ldap.UNWILLING_TO_PERFORM as e:
                logger.error(f"Server unwilling to perform password change for {cn_value}: {e}")
                logger.error("This often indicates SSL/TLS is required but not active")
            except ldap.LDAPError as e:
                logger.error(f"LDAP error setting password for {cn_value}: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                # Don't fail the entire creation if password fails
                # The user can be created and password set later
        
        return True, "samba_backend.success.create_inetorgperson", [cn_value]
        
    except ldap.ALREADY_EXISTS:
        logger.error(f"inetOrgPerson '{dn}' already exists.")
        return False, "samba_backend.error.inetorgperson_exists", [cn_value]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating inetOrgPerson '{dn}': {e}")
        return False, "samba_backend.error.create_inetorgperson", [str(e)]


def create_computer_samba(samba_conn, computer_data):
    """Creates a new computer account in Samba AD."""
    logger.info(f"Samba backend: Creating computer with data: {computer_data}")
    
    # Construct computer DN
    cn_value = computer_data.get('computer_name')
    if not cn_value:
        logger.error("Cannot create computer: missing computer name")
        return False, "samba_backend.error.missing_computer_name"
        
    dn = f"CN={cn_value},{computer_data['container_dn']}"
    
    # Build userAccountControl value for computer account
    uac_value = 0x1000  # UAC_WORKSTATION_TRUST_ACCOUNT
    
    if computer_data.get('is_pre2k_computer', False):
        # Additional flags for pre-Windows 2000 compatibility if needed
        pass
    
    # Build attributes list for computer
    attrs = []
    attrs.append(('objectClass', [b'top', b'person', b'organizationalPerson', b'user', b'computer']))
    attrs.append(('cn', [cn_value.encode('utf-8')]))
    
    # sAMAccountName should be the pre2k name (with $ suffix)
    sam_account_name = computer_data.get('pre2k_name', cn_value + '$')
    if not sam_account_name.endswith('$'):
        sam_account_name += '$'
    attrs.append(('sAMAccountName', [sam_account_name.encode('utf-8')]))
    
    # Set userAccountControl for computer account
    attrs.append(('userAccountControl', [str(uac_value).encode('utf-8')]))
    
    
    # Set DNS hostname (servicePrincipalName will be set automatically by AD)
    if computer_data.get('computer_name'):
        # Extract domain from BASE_DN for FQDN
        try:
            domain_parts = [p.split('=')[1] for p in computer_data['container_dn'].split(',') if p.lower().startswith('dc=')]
            domain = ".".join(domain_parts)
            fqdn = f"{computer_data['computer_name'].lower()}.{domain}"
            attrs.append(('dNSHostName', [fqdn.encode('utf-8')]))
        except Exception as e:
            logger.debug(f"Could not set dNSHostName: {e}")

    try:
        # Create the computer object
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created computer object: {dn}")
        
        # Add computer to selected group if specified
        if computer_data.get('group_dn'):
            try:
                group_dn = computer_data['group_dn']
                mod_attrs = [(ldap.MOD_ADD, 'member', [dn.encode('utf-8')])]
                samba_conn.modify_s(group_dn, mod_attrs)
                logger.info(f"Added computer {dn} to group {group_dn}")
            except ldap.LDAPError as e:
                logger.warning(f"Failed to add computer to group {group_dn}: {e}")
                # Don't fail the entire operation if group membership fails
        
        return True, "samba_backend.success.create_computer", [cn_value]
        
    except ldap.ALREADY_EXISTS:
        logger.error(f"Computer '{dn}' already exists.")
        return False, "samba_backend.error.computer_exists", [cn_value]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating computer '{dn}': {e}")
        return False, "samba_backend.error.create_computer", [str(e)]


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


def create_ou_samba(samba_conn, ou_data):
    """Creates a new Organizational Unit in Samba AD."""
    logger.info(f"Samba backend: Creating OU with data: {ou_data}")
    
    dn = f"OU={ou_data['name']},{ou_data['container_dn']}"
    
    attrs = []
    attrs.append(('objectClass', [b'top', b'organizationalUnit']))
    attrs.append(('ou', [ou_data['name'].encode('utf-8')]))
    
    # Add protection from accidental deletion if requested
    if ou_data.get('protect_from_deletion', False):
        # In Samba AD, we can use the msDS-HostServiceAccount attribute
        # or implement protection through ACLs. For now, we'll add a description
        # indicating protection status and handle it in deletion logic
        attrs.append(('description', [b'Protected from accidental deletion']))

    try:
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created OU: {dn}")
        return True, "samba_backend.success.create_ou", [ou_data['name']]
    except ldap.ALREADY_EXISTS:
        logger.error(f"OU '{dn}' already exists.")
        return False, "samba_backend.error.ou_exists", [ou_data['name']]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating OU '{dn}': {e}")
        return False, "samba_backend.error.create_ou", [str(e)]


def copy_user_samba(samba_conn, source_user_dn, new_user_data):
    """Creates a new user by copying properties from an existing user."""
    logger.info(f"Samba backend: Copying user from DN '{source_user_dn}' to new user with data: {new_user_data}")
    
    try:
        # First, get the source user's properties
        source_user_props = get_user_properties(samba_conn, source_user_dn)
        if not source_user_props:
            logger.error(f"Could not find source user: {source_user_dn}")
            return False, "samba_backend.error.source_user_not_found", [source_user_dn]
        
        # Attributes to copy from source user (excluding unique/system attributes)
        copyable_attributes = [
            'description', 'department', 'company', 'manager', 'memberOf',
            'physicalDeliveryOfficeName', 'telephoneNumber', 'facsimileTelephoneNumber',
            'mail', 'wWWHomePage', 'streetAddress', 'postOfficeBox', 'l', 'st',
            'postalCode', 'co', 'profilePath', 'scriptPath', 'homeDirectory',
            'homeDrive', 'title', 'employeeID', 'employeeNumber', 'employeeType'
        ]
        
        # Start with the user data from the wizard
        cn_value = new_user_data.get('full_name') or new_user_data.get('user_logon_name')
        if not cn_value:
            logger.error("Cannot create user: missing both full_name and user_logon_name")
            return False, "samba_backend.error.missing_username"
            
        dn = f"CN={cn_value},{new_user_data['container_dn']}"
        
        # Build userAccountControl value (start with NORMAL_ACCOUNT)
        uac_value = 0x0200  # NORMAL_ACCOUNT
        
        # Copy certain UAC flags from source user
        source_uac = int(source_user_props.get('userAccountControl', ['0'])[0])
        
        # Copy these flags if they exist in source
        flags_to_copy = [
            (0x0040, 'user_cannot_change_password'),  # UAC_PASSWORD_CANT_CHANGE
            (0x10000, 'password_never_expires'),       # UAC_DONT_EXPIRE_PASSWORD
            (0x0080, None),                           # UAC_ENCRYPTED_TEXT_PASSWORD_ALLOWED
            (0x40000, None),                          # UAC_SMARTCARD_REQUIRED
            (0x80000, None),                          # UAC_TRUSTED_FOR_DELEGATION
            (0x100000, None),                         # UAC_NOT_DELEGATED
            (0x200000, None),                         # UAC_USE_DES_KEY_ONLY
            (0x400000, None),                         # UAC_DONT_REQUIRE_PREAUTH
            (0x1000000, None)                         # UAC_TRUSTED_TO_AUTHENTICATE_FOR_DELEGATION
        ]
        
        for flag_value, override_key in flags_to_copy:
            if override_key and override_key in new_user_data:
                # Use wizard value if explicitly set
                if new_user_data[override_key]:
                    uac_value |= flag_value
            elif source_uac & flag_value:
                # Copy from source user if not overridden
                uac_value |= flag_value
        
        # Apply wizard overrides for standard flags
        if new_user_data.get('account_is_disabled', False):
            uac_value |= 0x0002  # UAC_ACCOUNT_DISABLED
        if new_user_data.get('user_must_change_password', True):
            uac_value |= 0x800000  # UAC_PASSWORD_EXPIRED

        # Build basic attributes
        attrs = []
        attrs.append(('objectClass', [b'top', b'person', b'organizationalPerson', b'user']))
        attrs.append(('cn', [cn_value.encode('utf-8')]))
        attrs.append(('sAMAccountName', [new_user_data['pre_win2k_logon'].encode('utf-8')]))
        attrs.append(('userAccountControl', [str(uac_value).encode('utf-8')]))
        
        # Add attributes from wizard (these override any copied values)
        if new_user_data.get('first_name'):
            attrs.append(('givenName', [new_user_data['first_name'].encode('utf-8')]))
        if new_user_data.get('last_name'):
            attrs.append(('sn', [new_user_data['last_name'].encode('utf-8')]))
        if new_user_data.get('initials'):
            attrs.append(('initials', [new_user_data['initials'].encode('utf-8')]))
        if new_user_data.get('full_name'):
            attrs.append(('displayName', [new_user_data['full_name'].encode('utf-8')]))
        
        # Set UPN
        if new_user_data.get('user_logon_name') and new_user_data.get('upn_domain'):
            # Strip @ prefix if present (UI includes @ in dropdown)
            upn_domain = new_user_data['upn_domain'].lstrip('@')
            upn = f"{new_user_data['user_logon_name']}@{upn_domain}"
            attrs.append(('userPrincipalName', [upn.encode('utf-8')]))
        
        # Copy applicable attributes from source user
        for attr_name in copyable_attributes:
            if attr_name in source_user_props and source_user_props[attr_name]:
                # Skip memberOf for now - group membership should be handled separately
                if attr_name == 'memberOf':
                    continue
                
                # Convert to bytes and add to attributes
                attr_values = []
                for value in source_user_props[attr_name]:
                    if isinstance(value, str):
                        attr_values.append(value.encode('utf-8'))
                    elif isinstance(value, bytes):
                        attr_values.append(value)
                
                if attr_values:
                    attrs.append((attr_name, attr_values))

        try:
            # Create the user object
            samba_conn.add_s(dn, attrs)
            logger.info(f"Successfully created user object: {dn}")
            
            # Set password if provided
            password = new_user_data.get('password')
            if password:
                try:
                    # Format password for unicodePwd (UTF-16LE with quotes)
                    password_utf16 = f'"{password}"'.encode('utf-16le')
                    mod_list = [(ldap.MOD_REPLACE, 'unicodePwd', password_utf16)]
                    samba_conn.modify_s(dn, mod_list)
                    logger.info(f"Successfully set password for copied user: {cn_value}")
                except ldap.INSUFFICIENT_ACCESS as e:
                    logger.error(f"Insufficient access to set password for {cn_value}: {e}")
                    logger.error("Service account may lack 'Reset Password' permissions")
                except ldap.CONSTRAINT_VIOLATION as e:
                    logger.error(f"Password constraint violation for {cn_value}: {e}")
                    logger.error("Password may not meet complexity requirements")
                except ldap.UNWILLING_TO_PERFORM as e:
                    logger.error(f"Server unwilling to perform password change for {cn_value}: {e}")
                    logger.error("This often indicates SSL/TLS is required but not active")
                except ldap.LDAPError as e:
                    logger.error(f"LDAP error setting password for {cn_value}: {e}")
                    logger.error(f"Error type: {type(e).__name__}")
            
            # Copy group memberships from source user
            source_member_of = source_user_props.get('memberOf', [])
            if source_member_of:
                logger.info(f"Copying group memberships from source user: {len(source_member_of)} groups")
                groups_copied = 0
                groups_failed = 0
                
                for group_dn in source_member_of:
                    try:
                        # Use the existing group membership function
                        add_user_to_group_samba(samba_conn, dn, group_dn)
                        groups_copied += 1
                        logger.debug(f"Added copied user to group: {group_dn}")
                    except Exception as e:
                        groups_failed += 1
                        logger.warning(f"Failed to add copied user to group {group_dn}: {e}")
                
                logger.info(f"Group membership copy complete: {groups_copied} succeeded, {groups_failed} failed")
            
            return True, "samba_backend.success.copy_user", [cn_value]
            
        except ldap.ALREADY_EXISTS:
            logger.error(f"User '{dn}' already exists.")
            return False, "samba_backend.error.user_exists", [cn_value]
        except ldap.LDAPError as e:
            logger.error(f"LDAP error creating user '{dn}': {e}")
            return False, "samba_backend.error.create_user", [str(e)]
            
    except Exception as e:
        logger.error(f"Error copying user {source_user_dn}: {e}")
        return False, "samba_backend.error.copy_user", [str(e)]


# Legacy function - now uses generic implementation
def delete_user_samba(samba_conn, user_dn):
    """Deletes a user from Samba AD."""
    return delete_object_samba(samba_conn, user_dn, 'user')


def _get_object_name(attrs):
    """Helper function to extract a readable name from LDAP attributes."""
    # Try common name attributes in order of preference
    for attr_name in ['cn', 'ou', 'name', 'displayName']:
        if attr_name in attrs and attrs[attr_name]:
            value = attrs[attr_name][0]
            if isinstance(value, bytes):
                return value.decode('utf-8')
            return str(value)
    return "Unknown"

def _scan_descendants_for_protection(samba_conn, base_dn):
    """Recursively scan all descendants of a DN for protected or critical objects.
    
    Returns:
        tuple: (protected_objects, critical_objects) where each is a list of (name, type) tuples
    """
    from acl_utils import check_protection_from_deletion
    
    protected_descendants = []
    critical_descendants = []
    
    try:
        # Search all descendants (SCOPE_SUBTREE) except the base object itself
        descendants = samba_conn.search_s(
            base_dn, 
            ldap.SCOPE_SUBTREE, 
            '(objectClass=*)', 
            ['cn', 'ou', 'name', 'objectClass', 'nTSecurityDescriptor']
        )
        
        # Skip the first result (base DN itself)
        for child_dn, child_attrs in descendants[1:]:
            if not child_attrs:  # Skip if no attributes
                continue
                
            child_name = _get_object_name(child_attrs)
            child_classes = [cls.decode('utf-8') if isinstance(cls, bytes) else cls 
                           for cls in child_attrs.get('objectClass', [])]
            
            # Check if child is a critical system object
            if 'organizationalUnit' in child_classes:
                ou_name_child = child_attrs.get('ou', [child_attrs.get('name', [b'Unknown'])[0]])[0]
                if isinstance(ou_name_child, bytes):
                    ou_name_child = ou_name_child.decode('utf-8')
                if ou_name_child in ['Domain Controllers', 'System', 'Builtin', 'Users', 'Computers']:
                    critical_descendants.append((child_name, 'Critical System OU'))
                    continue  # Don't check protection for critical objects
            
            # Check if child is protected from deletion
            if 'nTSecurityDescriptor' in child_attrs:
                sd_data = child_attrs['nTSecurityDescriptor'][0]
                if check_protection_from_deletion(sd_data):
                    object_type = 'OU' if 'organizationalUnit' in child_classes else \
                                 'User' if 'user' in child_classes else \
                                 'Computer' if 'computer' in child_classes else \
                                 'Contact' if 'contact' in child_classes else \
                                 'Object'
                    # Include the relative path for better identification
                    relative_path = child_dn.replace(f",{base_dn}", "").replace(base_dn, "")
                    display_name = f"{child_name} ({relative_path})" if relative_path else child_name
                    protected_descendants.append((display_name, object_type))
        
        logger.debug(f"Deep scan found {len(protected_descendants)} protected and {len(critical_descendants)} critical descendants")
        
    except Exception as e:
        logger.error(f"Error scanning descendants for protection: {e}")
        
    return protected_descendants, critical_descendants

def delete_ou_samba(samba_conn, ou_dn, recursive=False):
    """Deletes an OU from Samba AD with protection checking and optional recursive deletion."""
    from acl_utils import check_protection_from_deletion
    
    logger.info(f"Samba backend: Deleting OU with DN: {ou_dn}")
    
    try:
        # First, get the OU to check if it exists and get its name
        res = samba_conn.search_s(ou_dn, ldap.SCOPE_BASE, '(objectClass=organizationalUnit)', ['ou', 'name', 'nTSecurityDescriptor'])
        if not res:
            logger.error(f"OU not found: {ou_dn}")
            return False, "samba_backend.error.ou_not_found", [ou_dn]
        
        obj_attrs = res[0][1]
        ou_name = obj_attrs.get('ou', [obj_attrs.get('name', [b'Unknown'])[0]])[0].decode('utf-8')
        
        # Check for system/critical OUs that should never be deleted
        critical_ou_names = ['Domain Controllers', 'System', 'Builtin', 'Users', 'Computers']
        if ou_name in critical_ou_names:
            logger.warning(f"Attempted to delete critical system OU: {ou_name}")
            return False, "samba_backend.error.critical_ou_cannot_delete", [ou_name]
        
        # Check for protection from accidental deletion
        if 'nTSecurityDescriptor' in obj_attrs:
            sd_data = obj_attrs['nTSecurityDescriptor'][0]
            if check_protection_from_deletion(sd_data):
                logger.warning(f"OU '{ou_name}' is protected from accidental deletion")
                return False, "samba_backend.error.ou_protected_from_deletion", [ou_name]
        
        # Check if OU has child objects and analyze protection status
        try:
            # For recursive delete, we need to scan ALL descendants for protection FIRST
            if recursive:
                logger.info(f"Recursive delete requested - performing deep scan for protected objects in {ou_name}")
                protected_descendants, critical_descendants = _scan_descendants_for_protection(samba_conn, ou_dn)
                
                if critical_descendants:
                    child_list = ', '.join([f"{name} ({type_})" for name, type_ in critical_descendants])
                    logger.warning(f"OU '{ou_name}' contains critical system objects in descendants: {child_list}")
                    return False, "samba_backend.error.ou_has_critical_children", [ou_name, child_list]
                
                if protected_descendants:
                    child_list = ', '.join([f"{name} ({type_})" for name, type_ in protected_descendants])
                    logger.warning(f"OU '{ou_name}' contains protected objects in descendants: {child_list}")
                    return False, "samba_backend.error.ou_has_protected_children", [ou_name, child_list]
                
                # If we get here with recursive=True, no protected/critical objects found in entire tree
                logger.info(f"Deep scan complete - no protected objects found, proceeding with recursive delete of {ou_name}")
            
            # Check immediate children (for both recursive and non-recursive)
            child_res = samba_conn.search_s(ou_dn, ldap.SCOPE_ONELEVEL, '(objectClass=*)', ['cn', 'ou', 'name', 'objectClass', 'nTSecurityDescriptor'])
            if child_res:
                child_count = len(child_res)
                
                # For non-recursive deletes, analyze immediate children for protection
                if not recursive:
                    protected_children = []
                    critical_children = []
                    
                    # Analyze each immediate child object
                    for child_dn, child_attrs in child_res:
                        child_name = _get_object_name(child_attrs)
                        child_classes = [cls.decode('utf-8') if isinstance(cls, bytes) else cls 
                                       for cls in child_attrs.get('objectClass', [])]
                        
                        # Check if child is a critical system object
                        if 'organizationalUnit' in child_classes:
                            ou_name_child = child_attrs.get('ou', [child_attrs.get('name', [b'Unknown'])[0]])[0]
                            if isinstance(ou_name_child, bytes):
                                ou_name_child = ou_name_child.decode('utf-8')
                            if ou_name_child in ['Domain Controllers', 'System', 'Builtin', 'Users', 'Computers']:
                                critical_children.append((child_name, 'Critical System OU'))
                                continue
                        
                        # Check if child is protected from deletion
                        if 'nTSecurityDescriptor' in child_attrs:
                            sd_data = child_attrs['nTSecurityDescriptor'][0]
                            if check_protection_from_deletion(sd_data):
                                object_type = 'OU' if 'organizationalUnit' in child_classes else \
                                             'User' if 'user' in child_classes else \
                                             'Computer' if 'computer' in child_classes else \
                                             'Contact' if 'contact' in child_classes else \
                                             'Object'
                                protected_children.append((child_name, object_type))
                    
                    # Report findings for immediate children (non-recursive case)
                    if critical_children:
                        child_list = ', '.join([f"{name} ({type_})" for name, type_ in critical_children])
                        logger.warning(f"OU '{ou_name}' contains critical system objects: {child_list}")
                        return False, "samba_backend.error.ou_has_critical_children", [ou_name, child_list]
                    
                    if protected_children:
                        child_list = ', '.join([f"{name} ({type_})" for name, type_ in protected_children])
                        logger.warning(f"OU '{ou_name}' contains protected objects: {child_list}")
                        return False, "samba_backend.error.ou_has_protected_children", [ou_name, child_list]
                
                # If we get here, OU has children but none are protected
                if not recursive:
                    logger.warning(f"OU '{ou_name}' has {child_count} child objects (none protected)")
                    return False, "samba_backend.error.ou_has_children", [ou_name, str(child_count)]
                else:
                    # Recursive delete requested - delete all child objects first
                    logger.info(f"Recursive delete: removing {child_count} child objects from OU '{ou_name}'")
                    deleted_count = 0
                    failed_deletions = []
                    
                    # Delete children in reverse order (deepest first for nested OUs)
                    for child_dn, child_attrs in reversed(child_res):
                        child_name = _get_object_name(child_attrs)
                        child_classes = [cls.decode('utf-8') if isinstance(cls, bytes) else cls 
                                       for cls in child_attrs.get('objectClass', [])]
                        
                        try:
                            # Determine object type and delete accordingly
                            if 'organizationalUnit' in child_classes:
                                success, _, _ = delete_ou_samba(samba_conn, child_dn, recursive=True)
                            else:
                                # For other objects, use generic delete
                                object_type = 'user' if 'user' in child_classes else \
                                             'computer' if 'computer' in child_classes else \
                                             'contact' if 'contact' in child_classes else \
                                             'object'
                                success, _, _ = delete_object_samba(samba_conn, child_dn, object_type)
                            
                            if success:
                                deleted_count += 1
                                logger.debug(f"Successfully deleted child object: {child_name}")
                            else:
                                failed_deletions.append(child_name)
                                logger.error(f"Failed to delete child object: {child_name}")
                                
                        except Exception as e:
                            failed_deletions.append(child_name)
                            logger.error(f"Exception deleting child object '{child_name}': {e}")
                    
                    # Report results
                    if failed_deletions:
                        failed_list = ', '.join(failed_deletions)
                        logger.error(f"Failed to delete {len(failed_deletions)} child objects: {failed_list}")
                        return False, "samba_backend.error.ou_recursive_delete_failed", [ou_name, failed_list]
                    
                    logger.info(f"Successfully deleted all {deleted_count} child objects from OU '{ou_name}'")
                
        except ldap.LDAPError as e:
            logger.warning(f"Could not check child objects for OU '{ou_name}': {e}")
            # If we can't check children, proceed cautiously but warn user
            pass
        
        # All checks passed, delete the OU
        return delete_object_samba(samba_conn, ou_dn, 'organizationalUnit')
        
    except ldap.LDAPError as e:
        logger.error(f"LDAP error while deleting OU '{ou_dn}': {e}")
        return False, "samba_backend.error.ldap_error", [str(e)]


def delete_object_samba(samba_conn, object_dn, object_type="object"):
    """Generic function to delete any AD object (user, computer, contact, printer, OU)."""
    from acl_utils import check_protection_from_deletion
    
    logger.info(f"Samba backend: Deleting {object_type} with DN: {object_dn}")
    
    # Object type configurations
    object_configs = {
        'user': {'filter': '(objectClass=user)', 'name_attrs': ['cn', 'sAMAccountName']},
        'computer': {'filter': '(objectClass=computer)', 'name_attrs': ['cn', 'sAMAccountName']},
        'contact': {'filter': '(objectClass=contact)', 'name_attrs': ['cn', 'displayName']},
        'group': {'filter': '(objectClass=group)', 'name_attrs': ['cn', 'sAMAccountName']},
        'printer': {'filter': '(objectClass=printQueue)', 'name_attrs': ['cn', 'printerName']},
        'organizationalUnit': {'filter': '(objectClass=organizationalUnit)', 'name_attrs': ['ou', 'name']},
        'object': {'filter': '(objectClass=*)', 'name_attrs': ['cn', 'name', 'ou']}
    }
    
    config = object_configs.get(object_type, object_configs['object'])
    
    try:
        # Get object name and security descriptor for protection checking
        search_attrs = config['name_attrs'] + ['nTSecurityDescriptor', 'objectClass']
        res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, config['filter'], search_attrs)
        if not res:
            logger.error(f"{object_type.title()} not found: {object_dn}")
            return False, f"samba_backend.error.{object_type}_not_found", [object_dn]
        
        obj_attrs = res[0][1]
        obj_name = "Unknown"
        for attr in config['name_attrs']:
            if attr in obj_attrs:
                obj_name = obj_attrs[attr][0].decode('utf-8')
                break
        
        # Check for special computer object protections
        if object_type == 'computer':
            # Check if this is a Domain Controller
            object_classes = obj_attrs.get('objectClass', [])
            if b'computer' in object_classes:
                # Get the computer name to check for DC naming patterns
                computer_name = obj_name.rstrip('$')  # Remove trailing $ from computer accounts
                
                # Check if it's likely a Domain Controller (common naming patterns)
                dc_indicators = ['DC', 'DOMAINCONTROLLER', 'PDC', 'BDC']
                if any(indicator in computer_name.upper() for indicator in dc_indicators):
                    logger.warning(f"Attempted to delete what appears to be a Domain Controller: {computer_name}")
                    return False, "samba_backend.error.critical_computer_cannot_delete", [computer_name]
        
        # Check for protection from accidental deletion (for all object types)
        if 'nTSecurityDescriptor' in obj_attrs:
            sd_data = obj_attrs['nTSecurityDescriptor'][0]
            if check_protection_from_deletion(sd_data):
                logger.warning(f"{object_type.title()} '{obj_name}' is protected from accidental deletion")
                return False, f"samba_backend.error.{object_type}_protected_from_deletion", [obj_name]
        
        # Delete the object
        samba_conn.delete_s(object_dn)
        logger.info(f"Successfully deleted {object_type}: {object_dn}")
        return True, f"samba_backend.success.delete_{object_type}", [obj_name]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"{object_type.title()} '{object_dn}' does not exist.")
        return False, f"samba_backend.error.{object_type}_not_found", [object_dn]
    except ldap.NOT_ALLOWED_ON_NONLEAF:
        logger.error(f"Cannot delete {object_type} '{object_dn}': object has child objects.")
        return False, "samba_backend.error.object_has_children", [obj_name if 'obj_name' in locals() else object_dn]
    except ldap.INSUFFICIENT_ACCESS:
        logger.error(f"Insufficient access to delete {object_type} '{object_dn}'.")
        return False, "samba_backend.error.insufficient_access", [obj_name if 'obj_name' in locals() else object_dn]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error deleting {object_type} '{object_dn}': {e}")
        return False, f"samba_backend.error.delete_{object_type}", [str(e)]
    except Exception as e:
        logger.error(f"Unexpected error deleting {object_type} {object_dn}: {e}")
        return False, f"samba_backend.error.delete_{object_type}", [str(e)]


# Legacy function - now uses generic implementation
def disable_user_samba(samba_conn, user_dn):
    """Disables a user account in Samba AD."""
    return enable_disable_account_samba(samba_conn, user_dn, enable=False, object_type='user')


# Legacy function - now uses generic implementation  
def enable_user_samba(samba_conn, user_dn):
    """Enables a user account in Samba AD."""
    return enable_disable_account_samba(samba_conn, user_dn, enable=True, object_type='user')


def enable_disable_account_samba(samba_conn, object_dn, enable=True, object_type="user"):
    """Generic function to enable/disable user or computer accounts."""
    action = "Enabling" if enable else "Disabling"
    logger.info(f"Samba backend: {action} {object_type} with DN: {object_dn}")
    
    # Both users and computers use userAccountControl
    object_filter = '(|(objectClass=user)(objectClass=computer))'
    
    try:
        # Get current object attributes
        res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, object_filter, ['cn', 'userAccountControl', 'objectClass'])
        if not res:
            logger.error(f"{object_type.title()} not found: {object_dn}")
            return False, f"samba_backend.error.{object_type}_not_found", [object_dn]
        
        obj_attrs = res[0][1]
        cn_value = obj_attrs.get('cn', [b'Unknown'])[0].decode('utf-8')
        current_uac = int(obj_attrs.get('userAccountControl', [b'0'])[0].decode('utf-8'))
        
        # Determine actual object type from objectClass
        obj_classes = [oc.decode('utf-8').lower() for oc in obj_attrs.get('objectClass', [])]
        if 'computer' in obj_classes:
            actual_type = 'computer'
        else:
            actual_type = 'user'
        
        # Modify UAC flag
        if enable:
            new_uac = current_uac & ~0x0002  # Remove UAC_ACCOUNT_DISABLED
            success_key = f"samba_backend.success.enable_{actual_type}"
            error_key = f"samba_backend.error.enable_{actual_type}"
        else:
            new_uac = current_uac | 0x0002   # Set UAC_ACCOUNT_DISABLED
            success_key = f"samba_backend.success.disable_{actual_type}"
            error_key = f"samba_backend.error.disable_{actual_type}"
        
        # Update userAccountControl
        mod_list = [(ldap.MOD_REPLACE, 'userAccountControl', [str(new_uac).encode('utf-8')])]
        samba_conn.modify_s(object_dn, mod_list)
        
        action_past = "enabled" if enable else "disabled"
        logger.info(f"Successfully {action_past} {actual_type}: {object_dn}")
        return True, success_key, [cn_value]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"{object_type.title()} '{object_dn}' does not exist.")
        return False, f"samba_backend.error.{object_type}_not_found", [object_dn]
    except ldap.INSUFFICIENT_ACCESS:
        logger.error(f"Insufficient access to {action.lower()} {object_type} '{object_dn}'.")
        return False, "samba_backend.error.insufficient_access", [cn_value if 'cn_value' in locals() else object_dn]
    except ldap.LDAPError as e:
        action_key = "enable" if enable else "disable"
        logger.error(f"LDAP error {action.lower()} {object_type} '{object_dn}': {e}")
        return False, f"samba_backend.error.{action_key}_{object_type}", [str(e)]
    except Exception as e:
        action_key = "enable" if enable else "disable"
        logger.error(f"Unexpected error {action.lower()} {object_type} {object_dn}: {e}")
        return False, f"samba_backend.error.{action_key}_{object_type}", [str(e)]


# Convenience wrapper functions for different object types
def delete_computer_samba(samba_conn, computer_dn):
    """Deletes a computer from Samba AD."""
    return delete_object_samba(samba_conn, computer_dn, 'computer')

def delete_contact_samba(samba_conn, contact_dn):
    """Deletes a contact from Samba AD."""
    return delete_object_samba(samba_conn, contact_dn, 'contact')

def delete_printer_samba(samba_conn, printer_dn):
    """Deletes a printer from Samba AD."""
    return delete_object_samba(samba_conn, printer_dn, 'printer')


def reset_computer_account_samba(samba_conn, computer_dn):
    """
    Reset a computer account in Samba AD.
    This breaks the trust relationship and requires the computer to rejoin the domain.
    """
    logger.info(f"Samba backend: Resetting computer account: {computer_dn}")
    
    try:
        # Get current computer attributes
        res = samba_conn.search_s(computer_dn, ldap.SCOPE_BASE, '(objectClass=computer)', 
                                ['cn', 'sAMAccountName', 'userAccountControl'])
        if not res:
            logger.error(f"Computer not found: {computer_dn}")
            return False, "samba_backend.error.computer_not_found", [computer_dn]
        
        computer_attrs = res[0][1]
        computer_name = computer_attrs['cn'][0].decode('utf-8')
        sam_account = computer_attrs['sAMAccountName'][0].decode('utf-8')
        current_uac = int(computer_attrs['userAccountControl'][0].decode('utf-8'))
        
        # Reset the computer account by modifying userAccountControl
        # First, set UF_PASSWD_NOTREQD flag (0x20) to allow password reset
        reset_uac = current_uac | 0x20  # Add UF_PASSWD_NOTREQD flag
        
        # Step 1: Set password not required flag
        mod_attrs = [(ldap.MOD_REPLACE, 'userAccountControl', str(reset_uac).encode('utf-8'))]
        samba_conn.modify_s(computer_dn, mod_attrs)
        
        # Step 2: Remove the flag to complete the reset
        final_uac = reset_uac & ~0x20  # Remove UF_PASSWD_NOTREQD flag
        mod_attrs = [(ldap.MOD_REPLACE, 'userAccountControl', str(final_uac).encode('utf-8'))]
        samba_conn.modify_s(computer_dn, mod_attrs)
        
        logger.info(f"Successfully reset computer account: {computer_name}")
        return True, "samba_backend.success.reset_computer", [computer_name]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Computer '{computer_dn}' does not exist.")
        return False, "samba_backend.error.computer_not_found", [computer_dn]
    except ldap.INSUFFICIENT_ACCESS:
        logger.error(f"Insufficient access to reset computer '{computer_dn}'.")
        return False, "samba_backend.error.insufficient_access", [computer_dn]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error resetting computer '{computer_dn}': {e}")
        return False, "samba_backend.error.reset_computer", [str(e)]
    except Exception as e:
        logger.error(f"Unexpected error resetting computer {computer_dn}: {e}")
        return False, "samba_backend.error.reset_computer", [str(e)]


def disable_computer_samba(samba_conn, computer_dn):
    """Disables a computer account in Samba AD."""
    return enable_disable_account_samba(samba_conn, computer_dn, enable=False, object_type='computer')

def enable_computer_samba(samba_conn, computer_dn):
    """Enables a computer account in Samba AD."""
    return enable_disable_account_samba(samba_conn, computer_dn, enable=True, object_type='computer')


def reset_password_samba(samba_conn, user_dn, new_password, must_change_password=True):
    """Resets a user's password in Samba AD."""
    logger.info(f"Samba backend: Resetting password for user with DN: {user_dn}")
    
    try:
        # Get user's common name for success message
        res = samba_conn.search_s(user_dn, ldap.SCOPE_BASE, '(objectClass=user)', ['cn', 'userAccountControl'])
        if not res:
            return False, "samba_backend.error.user_not_found", [user_dn]
        
        user_attrs = res[0][1]
        cn_value = user_attrs.get('cn', [b'Unknown'])[0].decode('utf-8')
        
        # Set new password
        password_utf16 = f'"{new_password}"'.encode('utf-16le')
        modifications = [(ldap.MOD_REPLACE, 'unicodePwd', password_utf16)]
        
        if must_change_password:
            # Clear pwdLastSet to force password change
            modifications.append((ldap.MOD_REPLACE, 'pwdLastSet', [b'0']))
            
            # Update userAccountControl: clear DONT_EXPIRE_PASSWORD flag
            current_uac = int(user_attrs.get('userAccountControl', [b'0'])[0].decode('utf-8'))
            new_uac = current_uac & ~0x10000  # Clear UAC_DONT_EXPIRE_PASSWORD
            
            modifications.append((ldap.MOD_REPLACE, 'userAccountControl', [str(new_uac).encode('utf-8')]))
        
        samba_conn.modify_s(user_dn, modifications)
        return True, "samba_backend.success.reset_password", [cn_value]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"User '{user_dn}' does not exist.")
        return False, "samba_backend.error.user_not_found", [user_dn]
    except ldap.INSUFFICIENT_ACCESS:
        logger.error(f"Insufficient access to reset password for user '{user_dn}'.")
        return False, "samba_backend.error.insufficient_access", [cn_value if 'cn_value' in locals() else user_dn]
    except ldap.CONSTRAINT_VIOLATION as e:
        logger.error(f"Password constraint violation for {cn_value}: {e}")
        error_info = str(e).lower()
        if 'complexity criteria' in error_info or 'complexity requirements' in error_info:
            logger.error("Password does not meet domain complexity requirements")
            return False, "samba_backend.error.password_complexity", []
        elif 'password history' in error_info or 'recently used' in error_info:
            logger.error("Password was recently used and cannot be reused")
            return False, "samba_backend.error.password_history", []
        elif 'minimum age' in error_info or 'too soon' in error_info:
            logger.error("Password was changed too recently")
            return False, "samba_backend.error.password_age", []
        else:
            logger.error("Password constraint violation - general policy issue")
            return False, "samba_backend.error.password_constraint", [str(e)]
    except ldap.UNWILLING_TO_PERFORM as e:
        logger.error(f"Server unwilling to perform password reset for {user_dn}: {e}")
        logger.error("This often indicates SSL/TLS is required but not active")
        return False, "samba_backend.error.password_ssl_required", [str(e)]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error resetting password for user '{user_dn}': {e}")
        return False, "samba_backend.error.reset_password", [str(e)]
    except Exception as e:
        logger.error(f"Unexpected error resetting password for user {user_dn}: {e}")
        return False, "samba_backend.error.reset_password", [str(e)]


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


def create_printer_samba(samba_conn, printer_data):
    """Creates a new printer object in Samba AD."""
    logger.info(f"Samba backend: Creating printer with data: {printer_data}")
    
    # Validate required fields
    if not printer_data.get('network_path'):
        logger.error("Network path is required for printer creation")
        return False, "samba_backend.error.printer_path_required", []
    
    network_path = printer_data['network_path'].strip()
    if not network_path:
        logger.error("Network path cannot be empty")
        return False, "samba_backend.error.printer_path_required", []
    
    # Extract printer name from network path (\\server\share -> share)
    printer_name = network_path.split('\\')[-1] if '\\' in network_path else network_path
    if not printer_name:
        logger.error("Could not determine printer name from network path")
        return False, "samba_backend.error.printer_name_required", []
    
    dn = f"CN={printer_name},{printer_data['container_dn']}"
    
    # Create printer object attributes
    attrs = []
    attrs.append(('objectClass', [b'top', b'printQueue']))
    attrs.append(('cn', [printer_name.encode('utf-8')]))
    attrs.append(('printShareName', [printer_name.encode('utf-8')]))
    attrs.append(('uNCName', [network_path.encode('utf-8')]))
    attrs.append(('serverName', [network_path.encode('utf-8')]))
    
    try:
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created printer: {dn}")
        return True, "samba_backend.success.create_printer", [printer_name]
    except ldap.ALREADY_EXISTS:
        logger.error(f"Printer '{dn}' already exists.")
        return False, "samba_backend.error.printer_exists", [printer_name]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating printer '{dn}': {e}")
        return False, "samba_backend.error.create_printer", [str(e)]


def create_shared_folder_samba(samba_conn, shared_folder_data):
    """Creates a new shared folder object in Samba AD."""
    logger.info(f"Samba backend: Creating shared folder with data: {shared_folder_data}")
    
    # Validate required fields
    if not shared_folder_data.get('name'):
        logger.error("Name is required for shared folder creation")
        return False, "samba_backend.error.shared_folder_name_required", []
    
    if not shared_folder_data.get('network_path'):
        logger.error("Network path is required for shared folder creation")
        return False, "samba_backend.error.shared_folder_path_required", []
    
    name = shared_folder_data['name'].strip()
    network_path = shared_folder_data['network_path'].strip()
    
    if not name:
        logger.error("Name cannot be empty")
        return False, "samba_backend.error.shared_folder_name_required", []
    
    if not network_path:
        logger.error("Network path cannot be empty")
        return False, "samba_backend.error.shared_folder_path_required", []
    
    dn = f"CN={name},{shared_folder_data['container_dn']}"
    
    # Create shared folder object attributes
    attrs = []
    attrs.append(('objectClass', [b'top', b'volume']))
    attrs.append(('cn', [name.encode('utf-8')]))
    attrs.append(('uNCName', [network_path.encode('utf-8')]))
    
    try:
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created shared folder: {dn}")
        return True, "samba_backend.success.create_shared_folder", [name]
    except ldap.ALREADY_EXISTS:
        logger.error(f"Shared folder '{dn}' already exists.")
        return False, "samba_backend.error.shared_folder_exists", [name]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating shared folder '{dn}': {e}")
        return False, "samba_backend.error.create_shared_folder", [str(e)]


def get_schema_structural_classes(samba_conn):
    """Get all structural object classes from the schema that can be created."""
    logger.info("Querying schema for structural object classes")
    
    # Hardcoded configuration for object types with known required attributes beyond the naming attribute.
    # These use the generic multi-part dialog (wizard) instead of the simple single-field dialog.
    # New extensions with known required attributes can be defined here as bug reports come in.
    # These objects do not show up unless the specific schema extension is present in the directory.
    COMPLEX_OBJECT_TYPES = {
        'msDS-KeyCredential': {
            'display_name': 'msDS-KeyCredential',
            'naming_attribute': 'cn',
            'required_attributes': [
                {
                    'name': 'msDS-KeyId', 
                    'display_name': 'Key ID',
                    'type': 'octet_string',
                    'description': 'Unique identifier for the key credential'
                }
            ]
        }
        # Add more complex object types here as needed:
        # 'SomeOtherClass': {
        #     'display_name': 'Some Other Class',
        #     'naming_attribute': 'cn',
        #     'required_attributes': [
        #         {'name': 'someRequiredAttr', 'display_name': 'Some Required Attribute', 'type': 'string'}
        #     ]
        # }
    }
    
    try:
        # Get the schema naming context
        res = samba_conn.search_s('', ldap.SCOPE_BASE, '(objectClass=*)', ['schemaNamingContext'])
        if not res or 'schemaNamingContext' not in res[0][1]:
            logger.error("Could not determine schema naming context")
            return []
        
        schema_dn = res[0][1]['schemaNamingContext'][0].decode('utf-8')
        logger.info(f"Schema DN: {schema_dn}")
        
        # Query for structural object classes that are not hidden
        filter_expr = '(&(objectClass=classSchema)(objectClassCategory=1)(!(systemFlags:1.2.840.113556.1.4.803:=1)))'
        attrs = ['cn', 'displayName', 'defaultHidingValue', 'rDNAttID']
        
        res = samba_conn.search_s(schema_dn, ldap.SCOPE_ONELEVEL, filter_expr, attrs)
        
        structural_classes = []
        for dn, attrs in res:
            if not attrs:
                continue
                
            class_name = attrs.get('cn', [b''])[0].decode('utf-8')
            if not class_name:
                continue
            
            # Skip system classes that have dedicated dialogs
            if class_name.lower() in ['user', 'computer', 'group', 'organizationalunit', 'container', 
                                     'contact', 'printqueue', 'volume', 'person', 'organizationalperson', 
                                     'inetorgperson']:
                continue
            
            # Check if the class is hidden (defaultHidingValue = TRUE means hidden)
            default_hiding = attrs.get('defaultHidingValue', [b'FALSE'])[0].decode('utf-8').upper()
            if default_hiding == 'TRUE':
                continue
            
            # Get display name or format from class name
            display_name = attrs.get('displayName', [b''])[0].decode('utf-8')
            if not display_name:
                display_name = class_name
            
            # Get naming attribute (assume cn for simplicity)
            naming_attribute = 'cn'
            
            # Check if this is a complex object type with additional required attributes
            class_info = {
                'class_name': class_name,
                'display_name': display_name,
                'naming_attribute': naming_attribute,
                'is_complex': False
            }
            
            if class_name in COMPLEX_OBJECT_TYPES:
                complex_config = COMPLEX_OBJECT_TYPES[class_name]
                class_info.update({
                    'is_complex': True,
                    'display_name': complex_config.get('display_name', display_name),
                    'naming_attribute': complex_config.get('naming_attribute', naming_attribute),
                    'required_attributes': complex_config['required_attributes']
                })
            
            structural_classes.append(class_info)
        
        # Sort by display name
        structural_classes.sort(key=lambda x: x['display_name'])
        
        logger.info(f"Found {len(structural_classes)} structural classes")
        return structural_classes
        
    except ldap.LDAPError as e:
        logger.error(f"LDAP error querying schema: {e}")
        return []
    except Exception as e:
        logger.error(f"Error querying schema: {e}")
        return []


def create_generic_object_samba(samba_conn, object_data):
    """Creates a generic object in Samba AD based on provided class and naming value."""
    logger.info(f"Samba backend: Creating generic object with data: {object_data}")
    
    class_name = object_data.get('object_class')
    naming_attr = object_data.get('naming_attribute', 'cn')
    naming_value = object_data.get('naming_value')
    container_dn = object_data.get('container_dn')
    additional_attrs = object_data.get('attributes', {})
    
    if not class_name or not naming_value or not container_dn:
        logger.error("Missing required fields for generic object creation")
        return False, "samba_backend.error.generic_object_missing_fields", []
    
    naming_value = naming_value.strip()
    if not naming_value:
        logger.error("Naming value cannot be empty")
        return False, "samba_backend.error.generic_object_name_required", []
    
    # Construct DN
    dn = f"{naming_attr}={naming_value},{container_dn}"
    
    # Build attribute list
    attrs = []
    attrs.append(('objectClass', [b'top', class_name.encode('utf-8')]))
    attrs.append((naming_attr, [naming_value.encode('utf-8')]))
    
    # Add additional attributes from wizard
    for attr_name, attr_value in additional_attrs.items():
        if attr_value and attr_name != naming_attr:
            # Convert the value appropriately
            if isinstance(attr_value, str):
                attr_value = attr_value.strip()
                if attr_value:
                    # For octet strings (hex values), convert to binary
                    if attr_name == 'msDS-KeyId' and len(attr_value) % 2 == 0:
                        try:
                            # Convert hex string to bytes
                            binary_value = bytes.fromhex(attr_value)
                            attrs.append((attr_name, [binary_value]))
                        except ValueError:
                            logger.error(f"Invalid hex value for {attr_name}: {attr_value}")
                            return False, "samba_backend.error.create_generic_object", [f"Invalid hex value for {attr_name}"]
                    else:
                        # Regular string attribute
                        attrs.append((attr_name, [attr_value.encode('utf-8')]))
    
    try:
        samba_conn.add_s(dn, attrs)
        logger.info(f"Successfully created generic object: {dn}")
        return True, "samba_backend.success.create_generic_object", [naming_value, class_name]
    except ldap.ALREADY_EXISTS:
        logger.error(f"Object '{dn}' already exists.")
        return False, "samba_backend.error.generic_object_exists", [naming_value]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error creating generic object '{dn}': {e}")
        return False, "samba_backend.error.create_generic_object", [str(e)]


def add_user_to_group_samba(samba_conn, user_dn, group_dn):
    """Adds a user to a group in Samba AD."""
    logger.info(f"Samba backend: Adding user {user_dn} to group {group_dn}")
    
    try:
        # Add the user DN to the group's member attribute
        modifications = [(ldap.MOD_ADD, 'member', [user_dn.encode('utf-8')])]
        samba_conn.modify_s(group_dn, modifications)
        logger.info(f"Successfully added user {user_dn} to group {group_dn}")
        return True, "samba_backend.success.add_user_to_group", [user_dn, group_dn]
    except ldap.TYPE_OR_VALUE_EXISTS:
        logger.warning(f"User {user_dn} is already a member of group {group_dn}")
        return False, "samba_backend.error.user_already_in_group", [user_dn, group_dn]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error adding user {user_dn} to group {group_dn}: {e}")
        return False, "samba_backend.error.add_user_to_group", [str(e)]


def remove_user_from_group_samba(samba_conn, user_dn, group_dn):
    """Removes a user from a group in Samba AD."""
    logger.info(f"Samba backend: Removing user {user_dn} from group {group_dn}")
    
    try:
        # Remove the user DN from the group's member attribute
        modifications = [(ldap.MOD_DELETE, 'member', [user_dn.encode('utf-8')])]
        samba_conn.modify_s(group_dn, modifications)
        logger.info(f"Successfully removed user {user_dn} from group {group_dn}")
        return True, "samba_backend.success.remove_user_from_group", [user_dn, group_dn]
    except ldap.NO_SUCH_ATTRIBUTE:
        logger.warning(f"User {user_dn} is not a member of group {group_dn}")
        return False, "samba_backend.error.user_not_in_group", [user_dn, group_dn]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error removing user {user_dn} from group {group_dn}: {e}")
        return False, "samba_backend.error.remove_user_from_group", [str(e)]


def get_user_groups_samba(samba_conn, user_dn):
    """Gets all groups that a user is a member of."""
    logger.info(f"Samba backend: Getting groups for user {user_dn}")
    
    try:
        # Search for all groups where this user is a member
        base_dn = BASE_DN
        filter_expr = f'(&(objectClass=group)(member={user_dn}))'
        attrs = ['cn', 'distinguishedName', 'groupType', 'description']
        
        res = samba_conn.search_s(base_dn, ldap.SCOPE_SUBTREE, filter_expr, attrs)
        
        groups = []
        for dn, attrs in res:
            if attrs:
                group_info = {
                    'dn': dn,
                    'cn': attrs.get('cn', [b''])[0].decode('utf-8'),
                    'description': attrs.get('description', [b''])[0].decode('utf-8'),
                    'groupType': attrs.get('groupType', [b''])[0].decode('utf-8')
                }
                groups.append(group_info)
        
        logger.info(f"Found {len(groups)} groups for user {user_dn}")
        return True, groups
        
    except ldap.LDAPError as e:
        logger.error(f"LDAP error getting groups for user {user_dn}: {e}")
        return False, []


def get_group_members_samba(samba_conn, group_dn):
    """Gets all members of a group."""
    logger.info(f"Samba backend: Getting members for group {group_dn}")
    
    try:
        # Get the group's member attribute
        attrs = ['member']
        res = samba_conn.search_s(group_dn, ldap.SCOPE_BASE, '(objectClass=*)', attrs)
        
        if not res or not res[0][1]:
            logger.info(f"Group {group_dn} has no members")
            return True, []
        
        member_dns = res[0][1].get('member', [])
        members = []
        
        # Get details for each member
        for member_dn_bytes in member_dns:
            member_dn = member_dn_bytes.decode('utf-8')
            try:
                # Get member details
                member_attrs = ['cn', 'sAMAccountName', 'objectClass', 'description']
                member_res = samba_conn.search_s(member_dn, ldap.SCOPE_BASE, '(objectClass=*)', member_attrs)
                
                if member_res and member_res[0][1]:
                    attrs = member_res[0][1]
                    object_classes = [cls.decode('utf-8') for cls in attrs.get('objectClass', [])]
                    
                    member_info = {
                        'dn': member_dn,
                        'cn': attrs.get('cn', [b''])[0].decode('utf-8'),
                        'sAMAccountName': attrs.get('sAMAccountName', [b''])[0].decode('utf-8'),
                        'description': attrs.get('description', [b''])[0].decode('utf-8'),
                        'objectClass': object_classes,
                        'type': 'User' if 'user' in object_classes else 'Group' if 'group' in object_classes else 'Computer' if 'computer' in object_classes else 'Other'
                    }
                    members.append(member_info)
                    
            except ldap.LDAPError as e:
                logger.warning(f"Could not get details for member {member_dn}: {e}")
                # Add with minimal info
                members.append({
                    'dn': member_dn,
                    'cn': member_dn.split(',')[0].split('=')[1] if '=' in member_dn else member_dn,
                    'sAMAccountName': '',
                    'description': '',
                    'objectClass': [],
                    'type': 'Unknown'
                })
        
        logger.info(f"Found {len(members)} members for group {group_dn}")
        return True, members
        
    except ldap.LDAPError as e:
        logger.error(f"LDAP error getting members for group {group_dn}: {e}")
        return False, []


def move_object_samba(samba_conn, object_dn, new_parent_dn):
    """Moves an AD object to a new parent container."""
    logger.info(f"Samba backend: Moving object {object_dn} to {new_parent_dn}")
    
    try:
        # Parse the current DN to get the RDN (relative DN)
        import ldap.dn
        dn_components = ldap.dn.explode_dn(object_dn)
        if not dn_components:
            logger.error(f"Invalid DN format: {object_dn}")
            return False, "samba_backend.error.invalid_dn", [object_dn]
        
        rdn = dn_components[0]  # First component is the RDN (e.g., "CN=John")
        
        # Perform the move using modrdn
        # modrdn(dn, newrdn, delold=1, newsuperior=new_parent)
        samba_conn.rename_s(object_dn, rdn, newsuperior=new_parent_dn)
        
        new_dn = f"{rdn},{new_parent_dn}"
        logger.info(f"Successfully moved object to: {new_dn}")
        return True, "samba_backend.success.move_object", [object_dn, new_parent_dn]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Object not found: {object_dn}")
        return False, "samba_backend.error.object_not_found", [object_dn]
    except ldap.UNWILLING_TO_PERFORM as e:
        logger.error(f"Server unwilling to perform move operation: {e}")
        return False, "samba_backend.error.move_unwilling", [str(e)]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error moving object {object_dn}: {e}")
        return False, "samba_backend.error.move_object", [str(e)]


def rename_object_samba(samba_conn, object_dn, new_name):
    """Renames an AD object by changing its RDN."""
    logger.info(f"Samba backend: Renaming object {object_dn} to {new_name}")
    
    try:
        # Parse the current DN to determine the attribute type
        import ldap.dn
        dn_components = ldap.dn.explode_dn(object_dn)
        if not dn_components:
            logger.error(f"Invalid DN format: {object_dn}")
            return False, "samba_backend.error.invalid_dn", [object_dn]
        
        current_rdn = dn_components[0]  # e.g., "CN=OldName"
        parent_dn = ','.join(dn_components[1:])  # Everything after the first component
        
        # Extract the attribute type from current RDN (CN, OU, etc.)
        if '=' not in current_rdn:
            logger.error(f"Invalid RDN format: {current_rdn}")
            return False, "samba_backend.error.invalid_rdn", [current_rdn]
        
        attr_type = current_rdn.split('=')[0]  # e.g., "CN" from "CN=OldName"
        new_rdn = f"{attr_type}={new_name}"  # e.g., "CN=NewName"
        
        # Perform the rename using modrdn
        # rename_s(dn, newrdn, delold=1) - delold=1 means delete the old RDN attribute
        samba_conn.rename_s(object_dn, new_rdn, delold=1)
        
        new_dn = f"{new_rdn},{parent_dn}"
        logger.info(f"Successfully renamed object to: {new_dn}")
        return True, "samba_backend.success.rename_object", [object_dn, new_name]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Object not found: {object_dn}")
        return False, "samba_backend.error.object_not_found", [object_dn]
    except ldap.ALREADY_EXISTS:
        logger.error(f"Object with name '{new_name}' already exists in the same container")
        return False, "samba_backend.error.name_exists", [new_name]
    except ldap.UNWILLING_TO_PERFORM as e:
        logger.error(f"Server unwilling to perform rename operation: {e}")
        return False, "samba_backend.error.rename_unwilling", [str(e)]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error renaming object {object_dn}: {e}")
        return False, "samba_backend.error.rename_object", [str(e)]


def rename_object_with_attributes_samba(samba_conn, object_dn, rename_data, object_type):
    """
    Renames an AD object by updating multiple attributes based on object type.
    This is a comprehensive rename that updates all relevant naming attributes.
    """
    logger.info(f"Samba backend: Comprehensive rename of {object_type} object {object_dn}")
    logger.debug(f"Rename data: {rename_data}")
    
    try:
        import ldap.modlist
        
        # Get current object attributes to determine what needs to be changed
        try:
            res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['*'])
            if not res:
                return False, "samba_backend.error.object_not_found", [object_dn]
            current_attrs = res[0][1]
        except ldap.LDAPError as e:
            logger.error(f"Error fetching current object attributes: {e}")
            return False, "samba_backend.error.fetch_current", [str(e)]
        
        # Build the modification list based on object type and provided data
        mod_list = []
        
        # Handle different object types and their specific attributes
        if object_type in ['user', 'inetOrgPerson']:
            # User/inetOrgPerson rename attributes
            attribute_mappings = {
                'cn': 'cn',
                'displayName': 'displayName',
                'givenName': 'givenName',
                'sn': 'sn',
                'sAMAccountName': 'sAMAccountName',
                'userPrincipalName': 'userPrincipalName'
            }
        elif object_type == 'group':
            # Group rename attributes
            attribute_mappings = {
                'cn': 'cn',
                'sAMAccountName': 'sAMAccountName',
                'displayName': 'displayName',
                'description': 'description'
            }
        elif object_type == 'contact':
            # Contact rename attributes
            attribute_mappings = {
                'displayName': 'displayName',
                'givenName': 'givenName',
                'sn': 'sn',
                'cn': 'cn'
            }
        else:
            # Generic object - just update cn and displayName if provided
            attribute_mappings = {
                'cn': 'cn',
                'displayName': 'displayName'
            }
        
        # Check if we need to rename the RDN (CN attribute change)
        rdn_changed = False
        new_cn = None
        
        # Process attribute changes
        for form_field, ldap_attr in attribute_mappings.items():
            if form_field in rename_data and rename_data[form_field].strip():
                new_value = rename_data[form_field].strip()
                current_value = current_attrs.get(ldap_attr)
                
                # Convert current value to string for comparison
                if current_value:
                    if isinstance(current_value, list):
                        current_value_str = current_value[0].decode('utf-8') if isinstance(current_value[0], bytes) else str(current_value[0])
                    else:
                        current_value_str = current_value.decode('utf-8') if isinstance(current_value, bytes) else str(current_value)
                else:
                    current_value_str = ""
                
                # Only modify if the value has actually changed
                if new_value != current_value_str:
                    if ldap_attr == 'cn':
                        new_cn = new_value
                        rdn_changed = True
                    else:
                        # For non-CN attributes, add to modification list
                        if current_value:
                            mod_list.append((ldap.MOD_REPLACE, ldap_attr, [new_value.encode('utf-8')]))
                        else:
                            mod_list.append((ldap.MOD_ADD, ldap_attr, [new_value.encode('utf-8')]))
        
        # Apply attribute modifications first (before RDN change)
        if mod_list:
            logger.debug(f"Applying attribute modifications: {mod_list}")
            samba_conn.modify_s(object_dn, mod_list)
            logger.info(f"Successfully updated attributes for {object_dn}")
        
        # Handle RDN change (CN attribute) if needed
        new_dn = object_dn  # Default to current DN
        if rdn_changed and new_cn:
            logger.debug(f"Performing RDN change from {object_dn} to CN={new_cn}")
            
            # Parse the current DN to build new RDN
            import ldap.dn
            dn_components = ldap.dn.explode_dn(object_dn)
            if not dn_components:
                return False, "samba_backend.error.invalid_dn", [object_dn]
            
            parent_dn = ','.join(dn_components[1:])  # Everything after the first component
            new_rdn = f"CN={new_cn}"
            new_dn = f"{new_rdn},{parent_dn}"
            
            # Perform the RDN change
            samba_conn.rename_s(object_dn, new_rdn, delold=1)
            logger.info(f"Successfully renamed RDN to: {new_dn}")
        
        logger.info(f"Comprehensive rename completed successfully. New DN: {new_dn}")
        return True, "samba_backend.success.rename_object_comprehensive", [object_dn, new_dn]
        
    except ldap.NO_SUCH_OBJECT:
        logger.error(f"Object not found: {object_dn}")
        return False, "samba_backend.error.object_not_found", [object_dn]
    except ldap.ALREADY_EXISTS:
        logger.error(f"Object with new name already exists")
        return False, "samba_backend.error.name_exists", [new_cn or "unknown"]
    except ldap.UNWILLING_TO_PERFORM as e:
        logger.error(f"Server unwilling to perform rename operation: {e}")
        return False, "samba_backend.error.rename_unwilling", [str(e)]
    except ldap.LDAPError as e:
        logger.error(f"LDAP error in comprehensive rename of {object_dn}: {e}")
        return False, "samba_backend.error.rename_object", [str(e)]
    except Exception as e:
        logger.error(f"Unexpected error in comprehensive rename of {object_dn}: {e}")
        return False, "samba_backend.error.rename_unexpected", [str(e)]


def get_fsmo_role_holders(samba_conn):
    """Get information about all FSMO role holders using samba-tool."""
    logger.info("Retrieving FSMO role holders using samba-tool")
    
    try:
        import subprocess
        import json
        
        # Use samba-tool to get FSMO roles - much more reliable than LDAP parsing
        cmd = ['samba-tool', 'fsmo', 'show', '--json']
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            logger.error(f"samba-tool fsmo show failed: {error_msg}")
            return False, f"Failed to retrieve FSMO roles: {error_msg}"
        
        # Parse JSON output
        try:
            fsmo_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse samba-tool fsmo JSON output: {e}")
            # Fall back to parsing text output
            return _parse_fsmo_text_output(result.stdout)
        
        # Convert to our expected format
        fsmo_roles = {}
        
        # Map samba-tool role names to display names
        role_mapping = {
            'SchemaMasterRole': ('Schema Master', 'Forest', 'Controls schema modifications for the entire forest'),
            'DomainNamingMasterRole': ('Domain Naming Master', 'Forest', 'Controls addition and removal of domains in the forest'),
            'PDCEmulatorMasterRole': ('PDC Emulator', 'Domain', 'Handles password changes, account lockouts, and time synchronization'),
            'RidAllocationMasterRole': ('RID Master', 'Domain', 'Allocates RID pools to domain controllers for creating security principals'),
            'InfrastructureMasterRole': ('Infrastructure Master', 'Domain', 'Updates cross-domain group and user references')
        }
        
        for role_key, role_info in fsmo_data.items():
            if role_key in role_mapping:
                display_name, scope, description = role_mapping[role_key]
                holder = role_info.get('holder', 'Unknown')
                
                fsmo_roles[display_name] = {
                    'holder': holder,
                    'server_name': holder,  # samba-tool should give us the server name directly
                    'scope': scope,
                    'description': description
                }
        
        return True, fsmo_roles
        
    except subprocess.TimeoutExpired:
        logger.error("samba-tool fsmo show command timed out")
        return False, "FSMO query timed out"
    except FileNotFoundError:
        logger.error("samba-tool command not found")
        return False, "samba-tool command not found - ensure Samba is properly installed"
    except Exception as e:
        logger.error(f"Error retrieving FSMO role holders: {e}")
        return False, f"Error retrieving FSMO roles: {str(e)}"


def _parse_fsmo_text_output(output):
    """Parse text output from samba-tool fsmo show when JSON isn't available."""
    logger.info("Parsing samba-tool fsmo text output")
    
    try:
        fsmo_roles = {}
        lines = output.strip().split('\n')
        
        # Parse text output format
        for line in lines:
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    role_part = parts[0].strip()
                    holder_part = parts[1].strip()
                    
                    # Map role names
                    if 'SchemaMasterRole' in role_part or 'Schema Master' in role_part:
                        fsmo_roles['Schema Master'] = {
                            'holder': holder_part,
                            'server_name': holder_part,
                            'scope': 'Forest',
                            'description': 'Controls schema modifications for the entire forest'
                        }
                    elif 'DomainNamingMasterRole' in role_part or 'Domain Naming Master' in role_part:
                        fsmo_roles['Domain Naming Master'] = {
                            'holder': holder_part,
                            'server_name': holder_part,
                            'scope': 'Forest',
                            'description': 'Controls addition and removal of domains in the forest'
                        }
                    elif 'PDCEmulatorMasterRole' in role_part or 'PDC Emulator' in role_part:
                        fsmo_roles['PDC Emulator'] = {
                            'holder': holder_part,
                            'server_name': holder_part,
                            'scope': 'Domain',
                            'description': 'Handles password changes, account lockouts, and time synchronization'
                        }
                    elif 'RidAllocationMasterRole' in role_part or 'RID Master' in role_part:
                        fsmo_roles['RID Master'] = {
                            'holder': holder_part,
                            'server_name': holder_part,
                            'scope': 'Domain',
                            'description': 'Allocates RID pools to domain controllers for creating security principals'
                        }
                    elif 'InfrastructureMasterRole' in role_part or 'Infrastructure Master' in role_part:
                        fsmo_roles['Infrastructure Master'] = {
                            'holder': holder_part,
                            'server_name': holder_part,
                            'scope': 'Domain',
                            'description': 'Updates cross-domain group and user references'
                        }
        
        return True, fsmo_roles
        
    except Exception as e:
        logger.error(f"Error parsing FSMO text output: {e}")
        return False, f"Error parsing FSMO roles: {str(e)}"


def transfer_fsmo_role(role_name, target_server):
    """Transfer a FSMO role to another domain controller using samba-tool."""
    logger.info(f"Transferring FSMO role {role_name} to {target_server}")
    
    try:
        import subprocess
        
        # Map display names to samba-tool role names
        role_mapping = {
            'Schema Master': 'schema',
            'Domain Naming Master': 'naming', 
            'PDC Emulator': 'pdc',
            'RID Master': 'rid',
            'Infrastructure Master': 'infrastructure'
        }
        
        samba_role = role_mapping.get(role_name)
        if not samba_role:
            return False, f"Unknown role: {role_name}"
        
        # Use samba-tool to transfer the role
        cmd = ['samba-tool', 'fsmo', 'transfer', samba_role, '--role-owner=' + target_server]
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            logger.error(f"samba-tool fsmo transfer failed: {error_msg}")
            return False, f"Failed to transfer role: {error_msg}"
        
        logger.info(f"Successfully transferred {role_name} to {target_server}")
        return True, f"Successfully transferred {role_name} to {target_server}"
        
    except subprocess.TimeoutExpired:
        logger.error("samba-tool fsmo transfer command timed out")
        return False, "Role transfer timed out"
    except FileNotFoundError:
        logger.error("samba-tool command not found")
        return False, "samba-tool command not found - ensure Samba is properly installed"
    except Exception as e:
        logger.error(f"Error transferring FSMO role: {e}")
        return False, f"Error transferring role: {str(e)}"


def seize_fsmo_role(role_name, target_server):
    """Seize a FSMO role (emergency takeover) using samba-tool."""
    logger.warning(f"Seizing FSMO role {role_name} to {target_server} - this is an emergency operation")
    
    try:
        import subprocess
        
        # Map display names to samba-tool role names
        role_mapping = {
            'Schema Master': 'schema',
            'Domain Naming Master': 'naming',
            'PDC Emulator': 'pdc', 
            'RID Master': 'rid',
            'Infrastructure Master': 'infrastructure'
        }
        
        samba_role = role_mapping.get(role_name)
        if not samba_role:
            return False, f"Unknown role: {role_name}"
        
        # Use samba-tool to seize the role
        cmd = ['samba-tool', 'fsmo', 'seize', samba_role, '--role-owner=' + target_server]
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            logger.error(f"samba-tool fsmo seize failed: {error_msg}")
            return False, f"Failed to seize role: {error_msg}"
        
        logger.warning(f"Successfully seized {role_name} to {target_server}")
        return True, f"Successfully seized {role_name} to {target_server}"
        
    except subprocess.TimeoutExpired:
        logger.error("samba-tool fsmo seize command timed out")
        return False, "Role seizure timed out"
    except FileNotFoundError:
        logger.error("samba-tool command not found")
        return False, "samba-tool command not found - ensure Samba is properly installed"  
    except Exception as e:
        logger.error(f"Error seizing FSMO role: {e}")
        return False, f"Error seizing role: {str(e)}"

