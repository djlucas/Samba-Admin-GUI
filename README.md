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
- **cryptography** - Required for X.509 certificate parsing in the Published Certificates tab
- **dnspython** - DNS toolkit for Python
- **impacket** - Pure Python implementation of network protocols for LDAP security descriptors
- **MIT/Heimdal krb5 utilities** – Backend integration (`kinit`, `klist`, etc.)
- **Samba utilities** - samba-tool configured for domain (needed for funtional level and FSMO operations only)

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
  - Advanced Security tab functionality (partially implemented)
  - Advanced menu features:
    - Change Domain functionality (may not be implemented due to Kerberos limitation)
    - Export/Import capabilities (Export List, Import Query Definition)
    - Domain management (Delegate Control, Raise Domain functional level)
    - Advanced filtering

**SDNS (Samba DNS Manager)** - *~45% Complete*
- ✅ **Complete Windows DNS Manager tree structure** - Proper DNS/Server/Forward Zones/Reverse Zones/Conditional Forwarders hierarchy
- ✅ **Zone discovery and display** - Automatic discovery and categorization of Forward/Reverse DNS zones from AD
- ✅ **DNS record parsing and display** - Full DNS record type support (A, AAAA, CNAME, SRV, TXT, MX, NS, SOA, PTR)
- ✅ **Hierarchical DNS containers** - Smart folder structure generation from DNS record names (_sites, _tcp, etc.)
- ✅ **Multi-partition DNS zone support** - Handles zones spanning multiple DNS partitions with proper record aggregation
- ✅ **IPv4 reverse lookup enhancement** - Full IP address reconstruction and display in reverse zones
- ✅ **IPv6 reverse lookup support** - Complete IPv6 address reconstruction from nibble-based PTR records
- ✅ **Intelligent IP address sorting** - Proper numerical sorting for IP addresses (80 before 103) in all DNS views
- ✅ **Authentication integration** - Same Kerberos/LDAP authentication system as SADUC
- ❌ DNS record editing and creation not implemented
- ❌ Zone creation and management incomplete  
- ❌ DNS replication management missing

### Module Status Summary

| Module   | Completion | Status     | Notes                                  |
|----------|------------|------------|----------------------------------------|
| saduc    | ~98%       | 🚧 Active Development | Core functionality complete, advanced menu features and integrations remaining |
| sdns     | ~45%       | 🚧 Active Development | Zone display and IP address handling complete, record editing functionality needed |
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
21. ✅ **SDNS Tree Structure Overhaul** - Complete rewrite of DNS tree view to match Windows DNS Manager with proper DNS/Server/Forward Zones/Reverse Zones hierarchy
22. ✅ **DNS Zone Discovery Enhancement** - Automatic discovery and categorization of Forward/Reverse DNS zones from Active Directory with proper metadata
23. ✅ **DNS Record Parsing Implementation** - Full support for all major DNS record types (A, AAAA, CNAME, SRV, TXT, MX, NS, SOA, PTR) with proper data extraction
24. ✅ **Hierarchical DNS Container System** - Smart folder structure generation from DNS record names for organized record management (_sites, _tcp, service containers)
25. ✅ **DNS Hierarchy Bug Fixes** - Fixed critical DNS hierarchy overwriting issues where container structures were being lost during record processing
26. ✅ **Multi-partition DNS Zone Support** - Enhanced zone loading to handle DNS zones spanning multiple Active Directory partitions with proper record aggregation
27. ✅ **IPv4 Reverse Lookup Enhancement** - Complete IP address reconstruction for reverse DNS zones showing full addresses (192.168.1.80) instead of just octets
28. ✅ **IPv6 Reverse Lookup Support** - Full IPv6 address reconstruction from nibble-based PTR records with proper hierarchy handling
29. ✅ **Intelligent IP Address Sorting** - Implemented custom sorting for IP addresses ensuring proper numerical order (80 before 103) across all DNS record views

### Next Development Priorities

**🚨 CRITICAL (Alpha Release Blockers):**
- **Comprehensive Testing Suite** - Unit and integration tests for core functionality (21,000+ lines with zero tests)
- **Security Review** - Code audit for enterprise deployment readiness
- **Documentation** - Installation, configuration, and user guides

**🔴 HIGH PRIORITY (Beta Features):**
- **SADUC Complete Advanced Security Tab** - Principal management interface implementation
- **SADUC Advanced Menu Features** - Export/Import, Domain management (undetermined)
- **SDNS IPv6 Address Sorting** - Extend numerical sorting to IPv6 addresses with proper segment padding
- **SDNS RootDNSZone removal** - For now, this is in the tree view until zone properties dialog is created
- **SDNS Record Management** - DNS record editing, creation, and deletion functionality
- **SDNS Zone Management** - Zone creation, deletion, and property management

**🟡 MEDIUM PRIORITY (Enhancement):**
- **SADUC Enhanced Search Features** - finish advanced search filters
- **Performance Optimization** - Large directory handling improvements

**🟢 LOW PRIORITY (Future Releases):**
- **SADUC Samba-Specific Extensions** - ex: sambaSamAccount objectType extension for inetOrgPerson
- **SADSS Module Development** - Sites and Services functionality
- **SGPOE Module Development** - Group Policy Object editing
- **UI/UX Polish** - Additional interface improvements and user preferences

## 🤝 Contributing

This project welcomes contributions! Please see our contributing guidelines for development setup and coding standards.

## 📄 License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0) - see the LICENSE file for details.

**Note:** This project uses PyQt5, which requires GPL v3 licensing for open source applications. All derivative works must also be licensed under GPL v3 or a compatible license.
