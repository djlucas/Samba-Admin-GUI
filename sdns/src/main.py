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
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kerberos Login")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        formLayout = QFormLayout()
        
        self.usernameInput = QLineEdit()
        self.passwordInput = QLineEdit()
        self.passwordInput.setEchoMode(QLineEdit.Password)

        formLayout.addRow("Username:", self.usernameInput)
        formLayout.addRow("Password:", self.passwordInput)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(formLayout)
        mainLayout.addWidget(self.buttonBox)
        
        self.setLayout(mainLayout)

    def get_credentials(self):
        username = self.usernameInput.text()
        return username, self.passwordInput.text()

def get_ldap_conn(dc_list, logger):
    for dc in dc_list:
        for scheme in ["ldaps", "ldap"]:
            uri = f"{scheme}://{dc}"
            try:
                conn = ldap.initialize(uri)
                conn.set_option(ldap.OPT_REFERRALS, 0)
                conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
                conn.sasl_interactive_bind_s("", ldap.sasl.gssapi())
                logger.info(f"Connected to LDAP via {scheme.upper()}: {uri}")
                return conn
            except ldap.LOCAL_ERROR as e:
                raise NoKerberosTicketError("No Kerberos ticket found") from e
            except ldap.LDAPError as e:
                logger.warning(f"{scheme.upper()} connection to {dc} failed: {e}")
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
                    subprocess.run(
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

