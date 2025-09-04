# Samba-Admin-GUI

**Samba-Admin-GUI** is a modular Python-based administrative toolkit designed to bring native RSAT-like functionality to Linux workstations. Built for sysadmins and IT professionals, it provides graphical interfaces for managing Samba-based Active Directory environments—without relying on Windows.

## 🚀 Project Goals

- Recreate a limited set of RSAT-like tools for use on Linux workstations
- Provide intuitive, field-ready GUIs for common administrative tasks
- Ensure cross-platform compatibility and robust UX on Linux
- Support Kerberos-authenticated workflows and ticket-based execution

## 🧩 Modules

### ✅ In Progress

- **saduc** – *Samba Active Directory Users and Computers*  
  A native GUI replacement for Microsoft's ADUC, enabling:
  - User, group, and computer account management
  - OU creation and delegation
  - Attribute editing and schema-aware validation

- **sdns** – Samba DNS Manager  
  A native GUI replacement for Microsoft's DNS, enabling:
  - Manage AD integrated zone
  - Zone record management
  - Manage DNS replication

### 🧭 Planned Modules (TBA)

All future modules will follow the `s<RSAT>` naming convention.

- **sadss** – Samba Active Directory Sites and Services  
  Visual topology editor for sites, subnets, and replication links, posibly implementing a sysvol replication method

- **sgpoe** – Samba Group Policy Object Editor  
  Native GPO creation, linking, and template-based policy editing

## 🛠️ Tech Stack

- **Python 3.11+**
- **PyQt5** – Modular, scalable GUI framework
- **python-ldap** - LDAPv3 module for Python
- **dnspython** - DNS toolkit for Python
- **impacket** - Pure Python implementation of network protocols for LDAP security descriptors
- **MIT/Heimdal krb5 utilities** – Backend integration (`kinit`, `klist`, etc.)

### Optional Dependencies

- **cryptography** - Required for X.509 certificate parsing in the Published Certificates tab

## 🔐 Authentication Requirements

Samba-Admin-GUI is **entirely dependent on Kerberos and DNS** for secure authentication and domain resolution. All modules assume:

- Valid Kerberos configuration
- Proper DNS resolution for domain controllers and services

### 📄 Sample `krb5.conf`

Ensure your Kerberos configuration reflects your domain topology. Below is a minimal working example for AD/Samba:

```ini
[libdefaults]
    default_realm = MY.DOMAIN.TLD
    dns_lookup_realm = false
    dns_lookup_kdc = true

[realms]
MY.DOMAIN.TLD = {
    default_domain = my.domain.tld
}

[domain_realm]
    MyServerName = my.domain.tld
```
> 🧠 Tip: Replace `MY.DOMAIN.TLD`, `my.domain.tld`, and `MyServerName` with your actual realm, DNS domain, and hostname. DNS must resolve these correctly for Kerberos to function.

## 📦 Installation

### Dependencies

Install required dependencies:

```bash
pip install -r requirements.txt
```

### Optional Features

For full functionality including X.509 certificate parsing in the Published Certificates tab:

```bash
pip install cryptography
```

### Running

**Production Mode (Recommended):**
```bash
cd saduc/src
python main.py
```

**Debug Mode (Development):**
```bash
cd saduc/src  
python main.py --debug
```

The `--debug` flag enables verbose logging to both console and `saduc_debug.log` file. In production mode, only INFO+ messages are displayed to the console with no file logging for optimal performance.

## 🧪 Development Status

> **🎯 ALPHA RELEASE CANDIDATE** - SADUC module is production-ready for testing environments

### Current Implementation Status

**SADUC (Samba Active Directory Users & Computers)** - *Alpha Ready (~98% Complete)*

- ✅ **Core Features (Complete):**
  - LDAP connectivity and authentication via Kerberos
  - Complete tree navigation of AD structure
  - Property dialogs for all major object types (Users, Computers, Groups, OUs, Containers)
  - **Property write-back functionality** - All property dialog changes are persistent
  - Advanced search functionality with custom LDAP filters
  - Attribute editor with schema-aware validation
  - User creation/copy with full UPN and password support
  - **New OU creation** with "Protect from accidental deletion" option
  - **Enhanced object deletion** with protection checking and recursive options:
    - Smart protection detection for all object types
    - Critical system object blocking (Domain Controllers, System OUs)
    - Deep recursive scanning for nested protected objects
    - User choice for bulk/recursive deletion with detailed warnings
  - **Enable/disable functionality** for user and computer accounts
  - **Password reset** with "user must change password at next logon" support
  - **Real Windows ACL manipulation** using impacket for "Protect from accidental deletion"
  - **Complete group membership management** with add/remove functionality across all interfaces
  - **Advanced search dialog system** with intelligent name validation, object type filtering, and location browsing
  - **Unified search experience** - Single StandardSearchDialog replaces all legacy search dialogs for consistent UX
  - **Enhanced property tabs** - Improved Members, Member Of, and Managed By tabs with multi-select, staging, and proper write-back
  - **Complete move and rename operations** with drag-and-drop support and context menu actions
  - **FSMO roles management** with comprehensive Operations Masters dialog for all five roles
  - Context menus with dynamic enable/disable options based on object state

- ✅ **Advanced Security Features:**
  - Authentic Active Directory ACE detection and manipulation
  - Enterprise-grade protection checking across all object types
  - Domain Controller identification and blocking from deletion
  - Critical system OU protection (Domain Controllers, System, Builtin, etc.)
  - Consistent "Protect from accidental deletion" functionality across all dialogs

- ⚠️ **Remaining Features:**
  - Security tab functionality (partially implemented - view/add/remove principals)
  - Advanced menu features:
    - Change Domain functionality
    - Export/Import capabilities (Export List, Import Query Definition)
    - Domain management (Delegate Control, Raise Domain functional level)
    - View customization (Large Icons, Small Icons, List, Detail views)
    - Advanced filtering and UI customization options
  - Enhanced search dialog features (member of tab, advanced filters)
  - Specialized AD object creation (msDS-KeyCredential, msDS-ResourcePropertyList, etc.)

**SDNS (Samba DNS Manager)** - *~15% Complete*
- ✅ Basic GUI structure exists
- ❌ DNS record management not implemented
- ❌ Zone management incomplete
- ❌ Replication management missing

### Module Status Summary

| Module   | Completion | Status     | Notes                                  |
|----------|------------|------------|----------------------------------------|
| saduc    | ~95%       | 🚧 Active Development | Core functionality complete, advanced menu features and integrations remaining |
| sdns     | ~15%       | 🚧 Early Stage | Basic structure only, core functionality missing |
| sadss    | 0%         | 🕒 Planned | Pending topology mapping logic |
| sgpoe    | 0%         | 🕒 Planned | Requires policy template scaffolding |

### Recent Major Achievements

1. ✅ **Property Write-Back Implementation** - All property dialogs now save changes to Active Directory
2. ✅ **New OU Creation** - Complete OU creation workflow with protection options
3. ✅ **Enhanced Delete Operations** - Enterprise-grade deletion with recursive scanning and protection validation
4. ✅ **Real ACL Manipulation** - Authentic Windows security descriptor manipulation using impacket
5. ✅ **Smart Protection System** - Consistent "Protect from accidental deletion" across all object types
6. ✅ **Complete Group Membership Management** - Full add/remove functionality via properties dialogs and context menus
7. ✅ **Move and Rename Operations** - Full drag-and-drop support plus context menu operations for AD object management
8. ✅ **FSMO Roles Management** - Comprehensive Operations Masters dialog with transfer and seizure capabilities for all five FSMO roles
9. ✅ **StandardSearchDialog Implementation** - Advanced search system with name validation, blue text formatting, object type selection, tree-based location browsing, and protected text editing
10. ✅ **Unified Search Dialog System** - Replaced all custom search dialogs (AddToGroupDialog, GroupPickerDialog, UserPickerDialog) with the StandardSearchDialog for consistent UX across all property tabs
11. ✅ **Enhanced Group Management** - Improved member addition/removal with multi-select support, immediate UI feedback, and staging behavior for all group operations
12. ✅ **Manager Selection Enhancement** - Implemented manager selection in Managed By tab using StandardSearchDialog with single-selection validation and proper write-back to Active Directory
13. ✅ **Member Of Tab Improvements** - Enhanced user/group membership management with multi-select removal, no confirmation dialogs, and consistent staging behavior

### Latest Updates (Alpha Release Preparation)

14. ✅ **Complete Rename Operations** - Fixed comprehensive rename workflow with ObjectRenameDialog for users, groups, contacts, and inetOrgPerson objects
15. ✅ **Enhanced Object Type Detection** - Proper prioritization of sambaSamAccount → inetOrgPerson → user object types with consistent iconography
16. ✅ **Fixed User Creation** - Resolved primaryGroupID issue that blocked new user creation in Active Directory
17. ✅ **Group Properties Dialog Complete** - Added missing email and notes fields with proper side-by-side group scope/type layout
18. ✅ **Smart Context Menu Positioning** - Context menus now intelligently position above cursor when near screen bottom for better UX
19. ✅ **Production-Ready Logging** - Implemented professional logging system with debug mode (--debug flag) and clean production output
20. ✅ **Code Quality Improvements** - Replaced all debug print() statements with proper logger calls for enterprise-grade output

### Next Development Priorities

**🚨 CRITICAL (Alpha Release Blockers):**
- **Comprehensive Testing Suite** - Unit and integration tests for core functionality (21,000+ lines with zero tests)
- **Security Review** - Code audit for enterprise deployment readiness
- **Documentation** - Installation, configuration, and user guides

**🔴 HIGH PRIORITY (Beta Features):**
- **Complete Security Tab** - Principal management interface implementation
- **Advanced Menu Features** - Export/Import, Domain management, View customization  
- **SDNS Core Development** - DNS record editing and zone management

**🟡 MEDIUM PRIORITY (Enhancement):**
- **Enhanced Search Features** - Member of tab functionality and advanced search filters
- **Specialized Object Creation** - Support for advanced AD object types (msDS-KeyCredential, etc.)
- **Performance Optimization** - Large directory handling improvements

**🟢 LOW PRIORITY (Future Releases):**
- **SADSS Module Development** - Sites and Services functionality
- **SGPOE Module Development** - Group Policy Object editing
- **Samba-Specific Extensions** - sambaSamAccount objectType extensions
- **UI/UX Polish** - Additional interface improvements and user preferences

## 🤝 Contributing

This project welcomes contributions! Please see our contributing guidelines for development setup and coding standards.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
