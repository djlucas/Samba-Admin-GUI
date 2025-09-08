#!/usr/bin/env python3

import base64
import logging
import ldap
from impacket.ldap import ldaptypes

logger = logging.getLogger("saduc_app.acl_utils")

def check_protection_from_deletion(security_descriptor_data):
    """
    Check if an object has protection from accidental deletion enabled using impacket.

    This function looks for DENY ACEs with DELETE and DELETE_TREE permissions
    applied to the "Everyone" group (S-1-1-0) as per AD protection standards.

    Args:
        security_descriptor_data: Raw bytes from nTSecurityDescriptor attribute, or base64 string

    Returns:
        bool: True if protection is enabled, False otherwise
    """
    try:
        if not security_descriptor_data:
            return False

        # Handle both raw bytes and base64 string input
        if isinstance(security_descriptor_data, str):
            # If it's a string, assume it's base64 and decode it
            sd_bytes = base64.b64decode(security_descriptor_data)
        else:
            # If it's already bytes, use it directly
            sd_bytes = security_descriptor_data

        # Use impacket to parse the security descriptor
        # We'll parse it piece by piece to handle the parsing issues
        if len(sd_bytes) < 20:
            return False

        # Manually extract DACL offset from SD header
        dacl_offset = int.from_bytes(sd_bytes[16:20], 'little')

        if dacl_offset == 0 or dacl_offset >= len(sd_bytes):
            return False

        # Extract just the DACL portion and parse it separately
        dacl_data = sd_bytes[dacl_offset:]

        # Manual DACL parsing to avoid impacket issues
        if len(dacl_data) < 8:
            return False

        # Parse DACL header manually
        ace_count = int.from_bytes(dacl_data[4:6], 'little')
        acl_size = int.from_bytes(dacl_data[2:4], 'little')

        logger.debug(f"DACL: {ace_count} ACEs, size {acl_size}")

        if ace_count == 0:
            logger.debug("No ACEs found in DACL")
            return False

        if acl_size > len(dacl_data):
            logger.debug(f"ACL size {acl_size} > available data {len(dacl_data)}, continuing with available data")
            # Continue anyway - use what we have

        # Parse each ACE manually first, then use impacket for individual ACEs
        ace_data = dacl_data[8:]  # Skip ACL header
        ace_offset = 0

        for i in range(min(ace_count, 50)):  # Safety limit
            if ace_offset + 8 > len(ace_data):
                break

            # Parse ACE header manually
            ace_type = ace_data[ace_offset]
            ace_size = int.from_bytes(ace_data[ace_offset + 2:ace_offset + 4], 'little')

            logger.debug(f"ACE {i}: Type={ace_type}, Size={ace_size}")

            if ace_size == 0 or ace_offset + ace_size > len(ace_data):
                logger.debug(f"Breaking ACE parsing: Invalid ACE size or offset")
                break

            # Check if this is an ACCESS_DENIED_ACE (type 1)
            if ace_type == 1:
                logger.debug(f"Found ACCESS_DENIED_ACE at index {i}")
                try:
                    # Extract this ACE's data and parse with impacket
                    single_ace_data = ace_data[ace_offset:ace_offset + ace_size]
                    deny_ace = ldaptypes.ACCESS_DENIED_ACE(single_ace_data)

                    # Handle ACCESS_MASK object properly - convert to int
                    access_mask_obj = deny_ace['Mask']
                    # Extract the access mask value from the impacket object
                    access_mask = 0
                    if hasattr(access_mask_obj, 'value'):
                        access_mask = access_mask_obj.value
                    elif hasattr(access_mask_obj, '__int__'):
                        access_mask = int(access_mask_obj)
                    elif hasattr(access_mask_obj, 'getData'):
                        mask_data = access_mask_obj.getData()
                        access_mask = int.from_bytes(mask_data[:4], 'little')
                    else:
                        # Try to access as bytes from the raw ACE data
                        access_mask = int.from_bytes(single_ace_data[4:8], 'little')

                    # Parse the SID to see what this ACE is about
                    try:
                        sid_data = single_ace_data[8:]  # Skip ACE header + mask
                        sid = ldaptypes.LDAP_SID(sid_data)
                        sid_string = sid.formatCanonical()

                        logger.debug(f"DENY ACE {i}: SID={sid_string}, Mask=0x{access_mask:08x}")

                        # AD Protection detection: Active Directory uses specific permission patterns
                        # for "Protect from accidental deletion"
                        DELETE = 0x00010000      # RIGHT_DELETE 
                        DELETE_TREE = 0x00000040 # RIGHT_DS_DELETE_TREE
                        DELETE_CHILD = 0x00000002 # RIGHT_DS_DELETE_CHILD

                        # Standard protection checks
                        protection_bits = DELETE | DELETE_TREE | DELETE_CHILD

                        # AD often uses the specific mask 0x00140001 for protection
                        # (observed in testing with real AD environments)
                        ad_protection_mask = 0x00140001

                        if (access_mask & protection_bits) or (access_mask == ad_protection_mask):
                            logger.debug(f"Protection-related DENY ACE {i}: SID={sid_string}, mask=0x{access_mask:08x}")

                            # Look for specific delete bits
                            delete_bits = []
                            if access_mask & DELETE:
                                delete_bits.append("DELETE")
                            if access_mask & DELETE_TREE:
                                delete_bits.append("DELETE_TREE") 
                            if access_mask & DELETE_CHILD:
                                delete_bits.append("DELETE_CHILD")

                            logger.debug(f"Delete permissions: {', '.join(delete_bits) if delete_bits else 'specific AD protection mask'}")

                            # Check if this is Everyone (S-1-1-0) or Authenticated Users (S-1-5-11)
                            if sid_string in ["S-1-1-0", "S-1-5-11"]:
                                logger.info(f"Protection from accidental deletion detected: DENY {sid_string}")
                                return True

                    except Exception as sid_e:
                        logger.debug(f"Failed to parse SID in ACE {i}: {sid_e}")

                except Exception as ace_e:
                    logger.debug(f"Failed to parse DENY ACE {i}: {ace_e}")

            ace_offset += ace_size

        return False

    except Exception as e:
        logger.error(f"Error checking protection from deletion: {e}")
        return False


def set_protection_from_deletion(samba_conn, object_dn, protect=True):
    """
    Set or remove protection from accidental deletion on an AD object using real ACL manipulation.

    This function adds or removes DENY ACEs with the specific permission pattern that
    Active Directory uses for "Protect from accidental deletion" (mask 0x00140001 on Everyone).

    Args:
        samba_conn: LDAP connection
        object_dn: Distinguished name of the object
        protect: True to enable protection, False to disable

    Returns:
        bool: True if operation succeeded, False otherwise
    """
    logger.info(f"set_protection_from_deletion: {'Enabling' if protect else 'Disabling'} protection for {object_dn}")

    try:
        # Get the current security descriptor
        res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['nTSecurityDescriptor'])
        if not res or 'nTSecurityDescriptor' not in res[0][1]:
            logger.error(f"Could not retrieve security descriptor for {object_dn}")
            return False

        sd_data = res[0][1]['nTSecurityDescriptor'][0]
        logger.debug(f"Retrieved security descriptor: {len(sd_data)} bytes")

        if protect:
            # Add protection ACE
            result = _add_protection_ace(sd_data)
        else:
            # Remove protection ACE  
            result = _remove_protection_ace(sd_data)

        if result is None:
            logger.warning("No changes needed - protection status already correct")
            return True

        if result is False:
            logger.error("Failed to modify security descriptor")
            return False

        # Write the modified security descriptor back to LDAP
        mod_attrs = [(ldap.MOD_REPLACE, 'nTSecurityDescriptor', [result])]
        samba_conn.modify_s(object_dn, mod_attrs)

        action = "enabled" if protect else "disabled"
        logger.info(f"Successfully {action} protection from accidental deletion for {object_dn}")
        return True

    except ldap.LDAPError as e:
        logger.error(f"LDAP error setting protection for {object_dn}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error setting protection from deletion for {object_dn}: {e}")
        return False


def _add_protection_ace(sd_bytes):
    """
    Add a protection DENY ACE to the security descriptor.
    Returns modified SD bytes, None if already protected, or False on error.
    """
    try:
        # Check if already protected
        if check_protection_from_deletion(sd_bytes):
            logger.debug("Object is already protected - no changes needed")
            return None

        # Parse the security descriptor structure manually
        if len(sd_bytes) < 20:
            logger.error("Security descriptor too short")
            return False

        # Get DACL offset
        dacl_offset = int.from_bytes(sd_bytes[16:20], 'little')
        if dacl_offset == 0 or dacl_offset >= len(sd_bytes):
            logger.error("Invalid or missing DACL")
            return False

        # Parse DACL header
        dacl_data = sd_bytes[dacl_offset:]
        if len(dacl_data) < 8:
            logger.error("DACL too short")
            return False

        acl_revision = dacl_data[0]
        acl_size = int.from_bytes(dacl_data[2:4], 'little')
        ace_count = int.from_bytes(dacl_data[4:6], 'little')

        # Create the protection DENY ACE for Everyone (S-1-1-0) with mask 0x00140001
        protection_ace = _create_protection_deny_ace()
        if not protection_ace:
            logger.error("Failed to create protection ACE")
            return False

        # Insert the protection ACE at the beginning of the DACL (before existing ACEs)
        new_dacl_data = dacl_data[:8] + protection_ace + dacl_data[8:]

        # Update DACL header
        new_acl_size = len(new_dacl_data)
        new_ace_count = ace_count + 1

        # Update size and count in the new DACL
        new_dacl_data = bytes([acl_revision]) + dacl_data[1:2] + \
                       new_acl_size.to_bytes(2, 'little') + \
                       new_ace_count.to_bytes(2, 'little') + \
                       dacl_data[6:8] + new_dacl_data[8:]

        # Reconstruct the full security descriptor with the new DACL
        new_sd_bytes = sd_bytes[:dacl_offset] + new_dacl_data

        logger.debug(f"Added protection ACE: SD size {len(sd_bytes)} -> {len(new_sd_bytes)}")
        return new_sd_bytes

    except Exception as e:
        logger.error(f"Error adding protection ACE: {e}")
        return False


def _remove_protection_ace(sd_bytes):
    """
    Remove protection DENY ACE from the security descriptor.
    Returns modified SD bytes, None if not protected, or False on error.
    """
    try:
        # Check if currently protected
        if not check_protection_from_deletion(sd_bytes):
            logger.debug("Object is not protected - no changes needed")
            return None

        # Parse the security descriptor structure manually
        if len(sd_bytes) < 20:
            logger.error("Security descriptor too short")
            return False

        # Get DACL offset
        dacl_offset = int.from_bytes(sd_bytes[16:20], 'little')
        if dacl_offset == 0 or dacl_offset >= len(sd_bytes):
            logger.error("Invalid or missing DACL")
            return False

        # Parse DACL header
        dacl_data = sd_bytes[dacl_offset:]
        if len(dacl_data) < 8:
            logger.error("DACL too short")
            return False

        acl_revision = dacl_data[0]
        acl_size = int.from_bytes(dacl_data[2:4], 'little')
        ace_count = int.from_bytes(dacl_data[4:6], 'little')

        logger.debug(f"Removing protection ACE: {ace_count} ACEs, DACL size {acl_size}")

        if ace_count == 0:
            logger.debug("No ACEs to process")
            return None

        # Parse each ACE and rebuild DACL without protection ACEs
        ace_data = dacl_data[8:]  # Skip ACL header
        ace_offset = 0
        new_aces = []
        protection_ace_found = False

        for i in range(min(ace_count, 50)):  # Safety limit
            if ace_offset + 8 > len(ace_data):
                break

            # Parse ACE header
            ace_type = ace_data[ace_offset]
            ace_size = int.from_bytes(ace_data[ace_offset + 2:ace_offset + 4], 'little')

            if ace_size == 0 or ace_offset + ace_size > len(ace_data):
                logger.debug(f"Breaking ACE parsing: Invalid ACE size or offset")
                break

            # Extract this ACE's data
            single_ace_data = ace_data[ace_offset:ace_offset + ace_size]

            # Check if this is a protection DENY ACE (type 1)
            is_protection_ace = False
            if ace_type == 1:  # ACCESS_DENIED_ACE
                try:
                    # Parse the access mask and SID to identify protection ACEs
                    access_mask = int.from_bytes(single_ace_data[4:8], 'little')

                    # Parse SID from ACE data (starts at offset 8)
                    sid_data = single_ace_data[8:]
                    if len(sid_data) >= 12:  # Minimum SID size
                        sid = ldaptypes.LDAP_SID(sid_data)
                        sid_string = sid.formatCanonical()

                        # AD Protection patterns we need to remove
                        DELETE = 0x00010000      # RIGHT_DELETE 
                        DELETE_TREE = 0x00000040 # RIGHT_DS_DELETE_TREE
                        DELETE_CHILD = 0x00000002 # RIGHT_DS_DELETE_CHILD
                        protection_bits = DELETE | DELETE_TREE | DELETE_CHILD
                        ad_protection_mask = 0x00140001

                        # Check if this is a protection ACE on Everyone or Authenticated Users
                        if sid_string in ["S-1-1-0", "S-1-5-11"]:
                            if (access_mask & protection_bits) or (access_mask == ad_protection_mask):
                                logger.info(f"Found protection ACE to remove: SID={sid_string}, mask=0x{access_mask:08x}")
                                is_protection_ace = True
                                protection_ace_found = True

                except Exception as sid_e:
                    logger.debug(f"Failed to parse ACE {i} for protection check: {sid_e}")

            # Keep non-protection ACEs
            if not is_protection_ace:
                new_aces.append(single_ace_data)

            ace_offset += ace_size

        if not protection_ace_found:
            logger.debug("No protection ACE found to remove")
            return None

        # Rebuild DACL with remaining ACEs
        new_ace_count = len(new_aces)
        new_aces_data = b''.join(new_aces)
        new_dacl_size = 8 + len(new_aces_data)  # ACL header + ACEs

        # Build new DACL
        new_dacl_data = bytes([acl_revision]) + dacl_data[1:2] + \
                       new_dacl_size.to_bytes(2, 'little') + \
                       new_ace_count.to_bytes(2, 'little') + \
                       dacl_data[6:8] + new_aces_data

        # Reconstruct the full security descriptor with the new DACL
        new_sd_bytes = sd_bytes[:dacl_offset] + new_dacl_data

        logger.debug(f"Removed protection ACE: SD size {len(sd_bytes)} -> {len(new_sd_bytes)}, ACEs {ace_count} -> {new_ace_count}")
        return new_sd_bytes

    except Exception as e:
        logger.error(f"Error removing protection ACE: {e}")
        return False


def _create_protection_deny_ace():
    """Create a DENY ACE for Everyone (S-1-1-0) with the protection mask 0x00140001."""
    try:
        # ACE structure:
        # - AceType (1 byte): 1 = ACCESS_DENIED_ACE
        # - AceFlags (1 byte): 0 = no special flags
        # - AceSize (2 bytes): total ACE size in little-endian
        # - AccessMask (4 bytes): 0x00140001 in little-endian  
        # - SID: Everyone (S-1-1-0) = 01 01 00 00 00 00 00 01 00 00 00 00

        ace_type = bytes([1])  # ACCESS_DENIED_ACE
        ace_flags = bytes([0])  # No flags
        access_mask = (0x00140001).to_bytes(4, 'little')  # Protection mask

        # Everyone SID (S-1-1-0): revision=1, subauth_count=1, authority=1, subauth=0
        everyone_sid = bytes([
            1,    # Revision
            1,    # SubAuthorityCount  
            0, 0, 0, 0, 0, 1,  # IdentifierAuthority (6 bytes) = SECURITY_WORLD_SID_AUTHORITY
            0, 0, 0, 0         # SubAuthority[0] = 0 (4 bytes little-endian)
        ])

        # Calculate total ACE size
        ace_size = (1 + 1 + 2 + 4 + len(everyone_sid)).to_bytes(2, 'little')  # 20 bytes total

        # Assemble the ACE
        ace = ace_type + ace_flags + ace_size + access_mask + everyone_sid

        logger.debug(f"Created protection DENY ACE: {len(ace)} bytes")
        return ace

    except Exception as e:
        logger.error(f"Error creating protection ACE: {e}")
        return None


def add_principal_to_acl(samba_conn, object_dn, principal_dn, permissions_mask=0x001F01FF):
    """
    Add a principal (user/group) to the ACL with specified permissions.

    Args:
        samba_conn: LDAP connection
        object_dn: Distinguished name of the object to modify
        principal_dn: Distinguished name of the principal to add
        permissions_mask: Permission mask (default: Full Control)

    Returns:
        bool: True if operation succeeded, False otherwise
    """
    logger.info(f"Adding principal {principal_dn} to ACL of {object_dn}")

    try:
        # Get the principal's SID
        principal_sid = _get_object_sid(samba_conn, principal_dn)
        if not principal_sid:
            logger.error(f"Could not get SID for principal {principal_dn}")
            return False

        # Get the current security descriptor
        res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['nTSecurityDescriptor'])
        if not res or 'nTSecurityDescriptor' not in res[0][1]:
            logger.error(f"Could not retrieve security descriptor for {object_dn}")
            return False

        sd_data = res[0][1]['nTSecurityDescriptor'][0]

        # Add the ACE
        modified_sd = _add_allow_ace(sd_data, principal_sid, permissions_mask)
        if not modified_sd:
            return False

        # Write back the modified security descriptor
        mod_list = [(ldap.MOD_REPLACE, 'nTSecurityDescriptor', [modified_sd])]
        samba_conn.modify_s(object_dn, mod_list)

        logger.info(f"Successfully added principal {principal_dn} to ACL")
        return True

    except Exception as e:
        logger.error(f"Error adding principal to ACL: {e}")
        return False


def remove_principal_from_acl(samba_conn, object_dn, principal_dn):
    """
    Remove a principal (user/group) from the ACL by DN.

    Args:
        samba_conn: LDAP connection
        object_dn: Distinguished name of the object to modify
        principal_dn: Distinguished name of the principal to remove

    Returns:
        bool: True if operation succeeded, False otherwise
    """
    logger.info(f"Removing principal {principal_dn} from ACL of {object_dn}")

    try:
        # Get the principal's SID
        principal_sid = _get_object_sid(samba_conn, principal_dn)
        if not principal_sid:
            logger.error(f"Could not get SID for principal {principal_dn}")
            return False

        return remove_principal_from_acl_by_sid(samba_conn, object_dn, principal_sid)

    except Exception as e:
        logger.error(f"Error removing principal from ACL: {e}")
        return False


def remove_principal_from_acl_by_sid(samba_conn, object_dn, principal_sid):
    """
    Remove a principal (user/group) from the ACL by SID.

    Args:
        samba_conn: LDAP connection
        object_dn: Distinguished name of the object to modify
        principal_sid: SID bytes of the principal to remove

    Returns:
        bool: True if operation succeeded, False otherwise
    """
    logger.info(f"Removing principal SID from ACL of {object_dn}")

    try:
        # Get the current security descriptor
        res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['nTSecurityDescriptor'])
        if not res or 'nTSecurityDescriptor' not in res[0][1]:
            logger.error(f"Could not retrieve security descriptor for {object_dn}")
            return False

        sd_data = res[0][1]['nTSecurityDescriptor'][0]

        # Remove ACEs for this principal
        modified_sd = _remove_principal_aces(sd_data, principal_sid)
        if not modified_sd:
            return False

        # Write back the modified security descriptor
        mod_list = [(ldap.MOD_REPLACE, 'nTSecurityDescriptor', [modified_sd])]
        samba_conn.modify_s(object_dn, mod_list)

        logger.info(f"Successfully removed principal SID from ACL")
        return True

    except Exception as e:
        logger.error(f"Error removing principal from ACL by SID: {e}")
        return False


def _get_object_sid(samba_conn, object_dn):
    """Get the objectSid for a given DN."""
    try:
        res = samba_conn.search_s(object_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['objectSid'])
        if res and 'objectSid' in res[0][1]:
            return res[0][1]['objectSid'][0]
        return None
    except Exception as e:
        logger.error(f"Error getting SID for {object_dn}: {e}")
        return None


def get_dn_from_sid(samba_conn, sid_bytes):
    """Get the DN for a given SID."""
    try:
        # Search for object with this SID
        from samba_backend import BASE_DN
        if not BASE_DN:
            logger.error("BASE_DN not available for SID lookup")
            return None

        # Create LDAP filter for binary SID search
        # Convert SID bytes to escaped format for LDAP filter
        sid_hex = ''.join(f'\\{b:02x}' for b in sid_bytes)
        filter_str = f'(objectSid={sid_hex})'

        res = samba_conn.search_s(
            BASE_DN, 
            ldap.SCOPE_SUBTREE, 
            filter_str,
            ['distinguishedName']
        )

        if res and 'distinguishedName' in res[0][1]:
            return res[0][1]['distinguishedName'][0].decode('utf-8')
        return None

    except Exception as e:
        logger.error(f"Error getting DN for SID: {e}")
        return None


def _add_allow_ace(sd_bytes, principal_sid, permissions_mask):
    """Add an ALLOW ACE for the specified principal to the DACL."""
    try:
        if len(sd_bytes) < 20:
            return None

        # Get DACL offset
        dacl_offset = int.from_bytes(sd_bytes[16:20], 'little')
        if dacl_offset == 0 or dacl_offset >= len(sd_bytes):
            return None

        # Extract DACL
        dacl_data = sd_bytes[dacl_offset:]
        if len(dacl_data) < 8:
            return None

        # Create new ALLOW ACE
        new_ace = _create_allow_ace(principal_sid, permissions_mask)
        if not new_ace:
            return None

        # Insert new ACE at beginning of DACL (after header)
        dacl_header = dacl_data[:8]
        existing_aces = dacl_data[8:]

        # Update ACE count and size in DACL header
        ace_count = int.from_bytes(dacl_header[4:6], 'little') + 1
        dacl_size = int.from_bytes(dacl_header[2:4], 'little') + len(new_ace)

        new_dacl_header = (
            dacl_header[:2] +  # Revision and padding
            dacl_size.to_bytes(2, 'little') +  # New size
            ace_count.to_bytes(2, 'little') +  # New count  
            dacl_header[6:8]   # Reserved bytes
        )

        new_dacl = new_dacl_header + new_ace + existing_aces

        # Reconstruct security descriptor
        new_sd = (
            sd_bytes[:dacl_offset] +  # SD header
            new_dacl +                # Modified DACL
            sd_bytes[dacl_offset + len(dacl_data):]  # Rest (SACL, Owner, Group)
        )

        return new_sd

    except Exception as e:
        logger.error(f"Error adding ALLOW ACE: {e}")
        return None


def _remove_principal_aces(sd_bytes, principal_sid):
    """Remove all ACEs for the specified principal from the DACL."""
    try:
        if len(sd_bytes) < 20:
            return None

        # Get DACL offset  
        dacl_offset = int.from_bytes(sd_bytes[16:20], 'little')
        if dacl_offset == 0 or dacl_offset >= len(sd_bytes):
            return None

        # Extract DACL
        dacl_data = sd_bytes[dacl_offset:]
        if len(dacl_data) < 8:
            return None

        # Parse and filter ACEs
        dacl_header = dacl_data[:8]
        ace_count = int.from_bytes(dacl_header[4:6], 'little')

        new_aces = []
        offset = 8
        removed_count = 0

        for i in range(ace_count):
            if offset + 8 > len(dacl_data):
                break

            ace_size = int.from_bytes(dacl_data[offset + 2:offset + 4], 'little')
            if offset + ace_size > len(dacl_data):
                break

            ace_data = dacl_data[offset:offset + ace_size]

            # Extract SID from ACE (starts at offset 8 in ACE)
            if len(ace_data) > 8:
                ace_sid = ace_data[8:]

                # Compare SIDs - if they don't match, keep the ACE
                if ace_sid != principal_sid:
                    new_aces.append(ace_data)
                else:
                    removed_count += 1

            offset += ace_size

        if removed_count == 0:
            logger.info("No ACEs found for the specified principal")
            return sd_bytes  # No changes needed

        # Rebuild DACL
        new_ace_data = b''.join(new_aces)
        new_dacl_size = 8 + len(new_ace_data)
        new_ace_count = ace_count - removed_count

        new_dacl_header = (
            dacl_header[:2] +  # Revision and padding
            new_dacl_size.to_bytes(2, 'little') +  # New size
            new_ace_count.to_bytes(2, 'little') +  # New count
            dacl_header[6:8]   # Reserved bytes
        )

        new_dacl = new_dacl_header + new_ace_data

        # Reconstruct security descriptor
        new_sd = (
            sd_bytes[:dacl_offset] +  # SD header
            new_dacl +                # Modified DACL
            sd_bytes[dacl_offset + len(dacl_data):]  # Rest
        )

        logger.info(f"Removed {removed_count} ACE(s) for principal")
        return new_sd

    except Exception as e:
        logger.error(f"Error removing principal ACEs: {e}")
        return None


def _create_allow_ace(principal_sid, permissions_mask):
    """Create an ALLOW ACE for the specified principal."""
    try:
        # ACE structure for ACCESS_ALLOWED_ACE:
        # - AceType (1 byte): 0 = ACCESS_ALLOWED_ACE
        # - AceFlags (1 byte): 0 = no inheritance flags
        # - AceSize (2 bytes): total ACE size
        # - AccessMask (4 bytes): permissions
        # - SID: principal SID

        ace_type = bytes([0])  # ACCESS_ALLOWED_ACE
        ace_flags = bytes([0])  # No flags
        access_mask = permissions_mask.to_bytes(4, 'little')

        # Calculate total ACE size
        ace_size = (1 + 1 + 2 + 4 + len(principal_sid)).to_bytes(2, 'little')

        # Assemble the ACE
        ace = ace_type + ace_flags + ace_size + access_mask + principal_sid

        logger.debug(f"Created ALLOW ACE: {len(ace)} bytes, mask=0x{permissions_mask:08x}")
        return ace

    except Exception as e:
        logger.error(f"Error creating ALLOW ACE: {e}")
        return None