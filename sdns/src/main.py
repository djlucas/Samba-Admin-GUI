#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SDNS (Samba DNS Management)
#
# src/main.py
#
# Description:
# This is the main entry point for the sdns tool
#
# -----------------------------------------------------------------------------

import sys
import logging
import subprocess
from subprocess import CalledProcessError
import os

# Set SASL environment variables globally for GSSAPI over LDAPS compatibility
os.environ['LDAP_SASL_SECPROPS'] = 'minssf=0,maxssf=0'
# Try to disable SASL channel binding at the system level
os.environ['LDAP_SASL_CBT'] = 'none'
# Also set the SASL_SECPROPS for broader compatibility
os.environ['SASL_SECPROPS'] = 'minssf=0,maxssf=0'

from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QDialog, QVBoxLayout, QFormLayout, 
    QLineEdit, QDialogButtonBox, QLabel, QHBoxLayout
)
from PyQt5.QtCore import Qt
from gui import MainWindow
import ldap
import ldap.sasl

def setup_logging():
    logFile = "sdns_debug.log"
    logger = logging.getLogger("sdns_app")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        consoleHandler = logging.StreamHandler(sys.stdout)
        consoleHandler.setLevel(logging.INFO)
        consoleFormatter = logging.Formatter('%(levelname)s: %(message)s')
        consoleHandler.setFormatter(consoleFormatter)
        logger.addHandler(consoleHandler)

        fileHandler = logging.FileHandler(logFile)
        fileHandler.setLevel(logging.DEBUG)
        fileFormatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fileHandler.setFormatter(fileFormatter)
        logger.addHandler(fileHandler)

    logger.info(f"Logging initialized. Output to console (INFO+) and '{logFile}' (DEBUG+).")
    return logger

def get_current_domain():
    try:
        with open("/etc/krb5.conf") as f:
            for line in f:
                if "default_realm" in line:
                    return line.split("=")[1].strip().lower()
    except Exception:
        return None

def domain_to_dn(domain):
    return ",".join([f"DC={part}" for part in domain.split(".")])

def get_zone_bases(domain):
    domain_dn = domain_to_dn(domain)
    return [
        ("Domain", f"CN=MicrosoftDNS,DC=DomainDnsZones,{domain_dn}"),
        ("Forest", f"CN=MicrosoftDNS,DC=ForestDnsZones,{domain_dn}")
    ]

def discover_domain_controllers(domain, logger):
    try:
        import dns.resolver
        query = f"_ldap._tcp.{domain}"
        answers = dns.resolver.resolve(query, "SRV")
        dc_hosts = [str(r.target).rstrip('.') for r in answers]
        logger.info(f"Discovered DCs: {dc_hosts}")
        return dc_hosts
    except Exception as e:
        logger.warning(f"Failed to discover DCs via DNS: {e}")
        return []

class NoKerberosTicketError(Exception):
    pass

class UsernamePasswordDialog(QDialog):
    """
    A simple dialog to get username and password from the user.
    Enhanced version matching saduc's authentication dialog.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Authenticate to Active Directory")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Get the domain and format it as a Kerberos realm (uppercase)
        self.realm = self._get_kerberos_realm()
        
        formLayout = QFormLayout()
        
        self.usernameInput = QLineEdit()
        self.passwordInput = QLineEdit()
        self.passwordInput.setEchoMode(QLineEdit.Password)

        # Use an QHBoxLayout to combine the username input and the realm label
        usernameLayout = QHBoxLayout()
        usernameLayout.addWidget(self.usernameInput, 1)
        
        realmLabel = QLabel(self.realm)
        realmLabel.setStyleSheet("font-weight: bold;")
        usernameLayout.addWidget(realmLabel)

        formLayout.addRow("User Name", usernameLayout)
        formLayout.addRow("Password", self.passwordInput)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(formLayout)
        mainLayout.addWidget(self.buttonBox)
        
        self.setLayout(mainLayout)
        
        # Center the dialog on screen or parent
        self._center_dialog()

    def _get_kerberos_realm(self):
        """Get the Kerberos realm from krb5.conf."""
        try:
            # Read the realm from krb5.conf
            with open('/etc/krb5.conf', 'r') as f:
                content = f.read()
            
            # Look for default_realm in [libdefaults] section
            lines = content.split('\n')
            in_libdefaults = False
            
            for line in lines:
                line = line.strip()
                if line == '[libdefaults]':
                    in_libdefaults = True
                elif line.startswith('[') and line != '[libdefaults]':
                    in_libdefaults = False
                elif in_libdefaults and line.startswith('default_realm'):
                    # Extract the realm value
                    realm = line.split('=', 1)[1].strip()
                    return f"@{realm}"
            
            # If not found, try environment variable
            import os
            domain = os.environ.get('USERDNSDOMAIN', '')
            if domain:
                return f"@{domain.upper()}"
            
        except Exception:
            pass
        
        # Fallback
        return "@DOMAIN.TLD"

    def _center_dialog(self):
        """Center the dialog on the screen or parent widget."""
        # Make sure the dialog has been sized properly first
        self.adjustSize()
        
        if self.parent():
            # Center on parent widget
            parent_rect = self.parent().geometry()
            dialog_size = self.size()
            x = parent_rect.x() + (parent_rect.width() - dialog_size.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - dialog_size.height()) // 2
            self.move(x, y)
        else:
            # Center on screen
            from PyQt5.QtWidgets import QApplication
            screen = QApplication.desktop().screenGeometry()
            dialog_size = self.size()
            x = (screen.width() - dialog_size.width()) // 2
            y = (screen.height() - dialog_size.height()) // 2
            self.move(x, y)

    def get_credentials(self):
        username = self.usernameInput.text()
        return username, self.passwordInput.text()

def get_ldap_conn(dc_list, logger):
    # Build connection attempts: LDAPS -> StartTLS -> Plain LDAP for all servers
    connection_attempts = []
    # LDAPS attempts for all servers
    for server in dc_list:
        connection_attempts.append((server, 'ldaps', 'ldaps', 636))
    # StartTLS attempts for all servers  
    for server in dc_list:
        connection_attempts.append((server, 'starttls', 'ldap', 389))
    # Plain LDAP attempts for all servers
    for server in dc_list:
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
                # Clear any keytab that might interfere
                os.environ['KRB5_KTNAME'] = ''
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
                # Disable SASL channel binding for GSSAPI compatibility
                conn.set_option(ldap.OPT_X_SASL_NOCANON, 1)
            else:
                # For plain LDAP, still disable SASL channel binding for compatibility
                conn.set_option(ldap.OPT_X_SASL_NOCANON, 1)
            
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
                logger.info(f"Successfully established secure LDAPS connection to {server}:{port}.")
            elif ssl_method == 'starttls':
                logger.info(f"Successfully established secure LDAP+StartTLS connection to {server}:{port}.")
            else:
                # Plain LDAP with GSSAPI actually provides encryption via SASL (typically SSF=256)
                logger.info(f"Successfully established LDAP connection with GSSAPI encryption to {server}:{port}.")
            return conn
            
        except ldap.LOCAL_ERROR as e:
            raise NoKerberosTicketError("No Kerberos ticket found") from e
        except ldap.LDAPError as e:
            logger.warning(f"{ssl_method.upper()} connection to {server}:{port} failed: {e}")
            continue
    
    raise ldap.LDAPError("All LDAP connection attempts failed.")

def get_authenticated_connection(logger, app):
    """
    Handles the authentication flow with Kerberos, including manual
    username/password entry and retries.
    """
    domain = get_current_domain()
    if not domain:
        QMessageBox.critical(None, "Domain Error", "Could not determine current domain.")
        sys.exit(1)

    dc_list = discover_domain_controllers(domain, logger)
    if not dc_list:
        QMessageBox.critical(None, "Discovery Error", f"No domain controllers found for {domain}.")
        sys.exit(1)

    ldap_conn = None
    while ldap_conn is None:
        try:
            ldap_conn = get_ldap_conn(dc_list, logger)
        except NoKerberosTicketError:
            logger.warning("No Kerberos ticket found. Presenting manual authentication dialog.")

            auth_dialog = UsernamePasswordDialog()
            if auth_dialog.exec_() == auth_dialog.Accepted:
                username, password = auth_dialog.get_credentials()

                if not username or not password:
                    QMessageBox.critical(None, "Authentication Failed", "Username and password cannot be empty.")
                    # Loop will continue to re-prompt
                    continue

                # Construct the Kerberos principal from the username and domain
                realm = domain.upper()
                principal = f"{username}@{realm}"

                try:
                    logger.info(f"Attempting kinit for principal: {principal}")
                    result = subprocess.run(
                        ['kinit', principal],
                        input=password.encode('utf-8'),
                        capture_output=True,
                        check=True
                    )
                    logger.info("kinit successful. A ticket has been obtained.")
                    # On successful kinit, the loop will run again and this time
                    # get_ldap_conn() should succeed, breaking the loop.

                except CalledProcessError as e:
                    error_output = e.stderr.decode('utf-8').strip()
                    logger.error(f"kinit failed. Error: {error_output}")
                    QMessageBox.critical(None, "Authentication Failed", f"kinit failed. Please check your username and password.\n\nDetails: {error_output}")
                    # Loop will continue to re-prompt

                except FileNotFoundError:
                    logger.error("kinit command not found")
                    QMessageBox.critical(None, "System Error", "The 'kinit' command was not found. Please ensure Kerberos client tools are installed.")
                    sys.exit(1)

                except Exception as e:
                    logger.error(f"An unexpected error occurred during kinit: {e}")
                    QMessageBox.critical(None, "Application Error", "An unexpected error occurred during authentication. Check the debug log for details.")
                    sys.exit(1)
            else:
                QMessageBox.information(None, "Authentication Canceled", "Authentication was canceled. Exiting application.")
                sys.exit(0)
        except Exception as e:
            logger.error(f"LDAP connection failed: {e}")
            QMessageBox.critical(None, "Connection Error", f"LDAP connection failed:\n{e}")
            sys.exit(1)

    return ldap_conn, domain

def discover_dns_zones(conn, logger, zone_bases):
    zones = []
    for label, base_dn in zone_bases:
        try:
            result = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, "(objectClass=dnsZone)", ["dc"])
            for dn, attrs in result:
                name = attrs.get("dc", [b"(unnamed)"])[0].decode()
                zone_type = "Reverse" if name.endswith(".arpa") else "Forward"
                zones.append({
                    "dn": dn,
                    "name": name,
                    "source": label,
                    "type": zone_type
                })
            logger.info(f"Found {len(result)} zones under {label}")
        except ldap.NO_SUCH_OBJECT:
            logger.warning(f"No zones found under {label}")
        except ldap.LDAPError as e:
            logger.error(f"LDAP error during zone discovery in {label}: {e}")
    return zones

def main():
    """
    Main function to initialize and run the SDNS application.
    """
    logger = setup_logging()
    logger.info("Starting SDNS application...")

    app = QApplication(sys.argv)

    try:
        ldap_conn, domain = get_authenticated_connection(logger, app)
    except Exception as e:
        logger.error(f"Application failed to start. Error: {e}")
        QMessageBox.critical(None, "Application Error", "The application failed to start due to an unexpected error. Check the debug log for details.")
        sys.exit(1)

    if not ldap_conn:
        # This case should ideally not be reached with the new function
        QMessageBox.critical(None, "Application Error", "Failed to establish a connection to Samba. Exiting.")
        sys.exit(1)

    zone_bases = get_zone_bases(domain)
    zones = discover_dns_zones(ldap_conn, logger, zone_bases)

    window = MainWindow(ldap_conn, logger, zones)
    window.show()

    logger.info("SDNS GUI launched.")
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

