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

> ⚠️ This project is under active development. Installation instructions will be added once the first module (SADUC) reaches alpha.

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

You can test the current development version by running:

```bash
cd saduc/src
python main.py
```

## 🧪 Development Status

### Current Implementation Status (~85% Complete)

**SADUC (Samba Active Directory Users & Computers)** - *~98% Complete*

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
  - **Complete move and rename operations** with drag-and-drop support and context menu actions
  - Context menus with dynamic enable/disable options based on object state

- ✅ **Advanced Security Features:**
  - Authentic Active Directory ACE detection and manipulation
  - Enterprise-grade protection checking across all object types
  - Domain Controller identification and blocking from deletion
  - Critical system OU protection (Domain Controllers, System, Builtin, etc.)
  - Consistent "Protect from accidental deletion" functionality across all dialogs

- ⚠️ **Remaining Features:**
  - Security tab functionality (partially implemented)

**SDNS (Samba DNS Manager)** - *~15% Complete*
- ✅ Basic GUI structure exists
- ❌ DNS record management not implemented
- ❌ Zone management incomplete
- ❌ Replication management missing

### Module Status Summary

| Module   | Completion | Status     | Notes                                  |
|----------|------------|------------|----------------------------------------|
| saduc    | ~98%       | 🚧 Active Development | Core functionality complete, only Security tab enhancement remaining |
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

### Next Development Priorities

**MEDIUM PRIORITY (Enhancement):**  
1. **Security Tab Enhancement** - Complete the partially implemented security permissions interface  

**LOW PRIORITY:**  
2. **Search Dialog Parameter Setting** - Enhanced search functionality configuration  
3. **Samba-Specific Tasks** - Add Samba extensions (e.g., sambaSamAccount objectType to inetOrgPerson)  
4. **Comprehensive Testing Suite** - Implement automated test coverage for core functionality  

**QUALITY OF LIFE:**  
5. **Additional UI Polish** - Minor interface improvements and user experience enhancements  
  
