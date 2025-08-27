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
  - Attribute editing and schema-aware validatio

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

| Module   | Status     | Notes                                  |
|----------|------------|----------------------------------------|
| saduc    | 🚧 In Progress | Core UI and basic read-only acces to most of ADUC        |
| sdns     | 🚧 In Progress | Very rough draft in place with partial read funtionality |
| ssas     | 🕒 Planned     | Pending topology mapping logic                           |
| sgpoe    | 🕒 Planned     | Requires policy template scaffolding                     |

