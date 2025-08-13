# src/main.py
import sys
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox
from gui import SADUCMainWindow
from samba_backend import get_ldap_conn, NoKerberosTicketError, BASE_DN
from user_dialogs import UsernamePasswordDialog
import subprocess
from subprocess import CalledProcessError

# --- Global Logger Configuration ---
def setup_logging():
    """
    Configures the global logging settings for the application.
    Output will go to both console and a debug file.
    """
    logFile = "saduc_debug.log"

    logger = logging.getLogger("saduc_app")
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

def get_authenticated_connection(appLogger, app):
    """
    Handles the authentication flow with Kerberos, including manual
    username/password entry and retries.
    """
    samba_conn = None
    connected_server = None
    while samba_conn is None:
        try:
            samba_conn, connected_server = get_ldap_conn()
        except NoKerberosTicketError:
            appLogger.warning(f"No Kerberos ticket found. Presenting manual authentication dialog.")
            
            auth_dialog = UsernamePasswordDialog()
            if auth_dialog.exec_() == auth_dialog.Accepted:
                username, password = auth_dialog.get_credentials()
                
                if not username or not password:
                    QMessageBox.critical(None, "Authentication Failed", "Username and password cannot be empty.")
                    # Loop will continue to re-prompt
                    continue
                
                # Construct the Kerberos principal from the username and domain
                domain_parts = BASE_DN.split(',')
                realm = ".".join([p.split('=')[1] for p in domain_parts]).upper()
                principal = f"{username}@{realm}"
                
                try:
                    appLogger.info(f"Attempting kinit for principal: {principal}")
                    subprocess.run(
                        ['kinit', principal],
                        input=password.encode('utf-8'),
                        capture_output=True,
                        check=True
                    )
                    appLogger.info("kinit successful. A ticket has been obtained.")
                    # On successful kinit, the loop will run again and this time
                    # get_ldap_conn() should succeed, breaking the loop.
                    
                except CalledProcessError as e:
                    error_output = e.stderr.decode('utf-8').strip()
                    appLogger.error(f"kinit failed. Error: {error_output}")
                    QMessageBox.critical(None, "Authentication Failed", f"kinit failed. Please check your username and password.\n\nDetails: {error_output}")
                    # Loop will continue to re-prompt
                    
                except Exception as e:
                    appLogger.error(f"An unexpected error occurred during kinit: {e}")
                    QMessageBox.critical(None, "Application Error", "An unexpected error occurred during authentication. Check the debug log for details.")
                    sys.exit(1)
            else:
                QMessageBox.information(None, "Authentication Canceled", "Authentication was canceled. Exiting application.")
                sys.exit(0)
    
    return samba_conn, connected_server

def main():
    """
    Main function to initialize and run the SADUC application.
    """
    appLogger = setup_logging()
    appLogger.info("Starting SADUC application...")

    app = QApplication(sys.argv)
    
    try:
        samba_conn, connected_server = get_authenticated_connection(appLogger, app)
    except Exception as e:
        appLogger.error(f"Application failed to start. Error: {e}")
        QMessageBox.critical(None, "Application Error", "The application failed to start due to an unexpected error. Check the debug log for details.")
        sys.exit(1)

    if not samba_conn:
        # This case should ideally not be reached with the new function
        QMessageBox.critical(None, "Application Error", "Failed to establish a connection to Samba. Exiting.")
        sys.exit(1)
        
    window = SADUCMainWindow(samba_conn, connected_server)
    window.show()

    appLogger.info("Application event loop started.")
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

