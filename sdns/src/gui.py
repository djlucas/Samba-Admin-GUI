#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SDNS (Samba DNS Management)
#
# src/gui.py
#
# Description:
# Main GUI window for SDNS, showing DNS zones and records
# -----------------------------------------------------------------------------

from PyQt5.QtWidgets import (
    QWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QHBoxLayout, QLabel, QMessageBox
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QSize
from edit_dialog import EditDialog
import os
import ldap
import struct
import socket
from datetime import datetime
from collections import defaultdict


class SortableTreeWidgetItem(QTreeWidgetItem):
    """Custom SortableTreeWidgetItem that provides custom sorting for IP addresses"""

    def __lt__(self, other):
        """Custom comparison for sorting"""
        column = self.treeWidget().sortColumn()

        # Get sort data from UserRole if available
        self_data = self.data(column, Qt.UserRole)
        other_data = other.data(column, Qt.UserRole)

        # If both have UserRole data, compare that
        if self_data is not None and other_data is not None:
            return str(self_data) < str(other_data)

        # If only one has UserRole data, it comes first
        if self_data is not None:
            return True
        if other_data is not None:
            return False

        # Fall back to text comparison
        return self.text(column).lower() < other.text(column).lower()

class SortableTreeWidget(QTreeWidget):
    """Custom QTreeWidget that uses UserRole data for sorting IP addresses"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable sorting
        self.setSortingEnabled(True)


class MainWindow(QWidget):
    def __init__(self, ldap_conn, logger, zones):
        super().__init__()
        self.ldap_conn = ldap_conn
        self.logger = logger
        self.zones = zones
        self._site_names_cache = None  # Cache for AD site names
        self.zone_records_cache = {}   # Cache for parsed DNS records by zone
        self.setWindowTitle("SDNS - Samba DNS Management")
        self.resize(800, 500)

        # Zone tree
        self.zone_tree = QTreeWidget()
        self.zone_tree.setHeaderHidden(True)
        self.zone_tree.itemClicked.connect(self.handle_zone_click)

        zone_layout = QVBoxLayout()
        zone_layout.addWidget(QLabel("DNS Zones"))
        zone_layout.addWidget(self.zone_tree)

        # Record list (now a SortableTreeWidget with columns for IP address sorting)
        self.record_list = SortableTreeWidget()
        self.record_list.setHeaderLabels(["", "Name", "Type", "Data", "Timestamp"])
        self.record_list.setRootIsDecorated(False)
        self.record_list.setIconSize(QSize(16, 16))
        self.record_list.setSortingEnabled(True)
        self.record_list.sortByColumn(1, Qt.AscendingOrder)  # Sort by Name column (index 1) by default
        # Set column widths - Icon, Name, Type, Data, Timestamp
        self.record_list.setColumnWidth(0, 30)   # Icon column - just enough for 16px icon
        self.record_list.setColumnWidth(1, 200)  # Name column
        self.record_list.setColumnWidth(2, 60)   # Type column  
        self.record_list.setColumnWidth(3, 300)  # Data column - widest for long DNS names
        self.record_list.setColumnWidth(4, 150)  # Timestamp column
        self.record_list.itemDoubleClicked.connect(self.launch_edit_dialog)

        record_layout = QVBoxLayout()
        record_layout.addWidget(QLabel("DNS Records"))
        record_layout.addWidget(self.record_list)

        # Main layout
        main_layout = QHBoxLayout()
        main_layout.addLayout(zone_layout, stretch=1)
        main_layout.addLayout(record_layout, stretch=2)
        self.setLayout(main_layout)

        self.load_zones()

    def _get_base_dn(self):
        """Extract the base DN from LDAP connection"""
        try:
            # Get the root DSE to find the default naming context
            result = self.ldap_conn.search_s("", ldap.SCOPE_BASE, "(objectClass=*)", ["defaultNamingContext"])
            if result and result[0][1] and "defaultNamingContext" in result[0][1]:
                return result[0][1]["defaultNamingContext"][0].decode("utf-8")
        except Exception as e:
            self.logger.warning(f"Could not get base DN: {e}")

        # Fallback - try to derive from URI or assume common pattern
        return "DC=home,DC=lucasit,DC=com"

    def _get_ad_site_names(self):
        """Query Active Directory for all site names (cached)"""
        if self._site_names_cache is not None:
            return self._site_names_cache

        try:
            base_dn = self._get_base_dn()
            sites_dn = f"CN=Sites,CN=Configuration,{base_dn}"

            result = self.ldap_conn.search_s(
                sites_dn,
                ldap.SCOPE_SUBTREE,
                "(objectClass=site)",
                ["cn"]
            )

            site_names = []
            for dn, attrs in result:
                cn = attrs.get("cn", [b""])[0].decode("utf-8") if "cn" in attrs else ""
                if cn:
                    site_names.append(cn)
                    self.logger.debug(f"Found AD site: {cn}")

            # Cache the results
            self._site_names_cache = site_names if site_names else ["Default-First-Site-Name"]
            return self._site_names_cache

        except Exception as e:
            self.logger.warning(f"Could not query AD sites: {e}")
            # Cache the fallback too
            self._site_names_cache = ["Default-First-Site-Name"]
            return self._site_names_cache

    def _get_icon(self, name):
        """Get icon for a given filename"""
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, "res", "icons", name)
        if not os.path.exists(path):
            self.logger.warning(f"Missing icon: {path}")
            return QIcon()
        return QIcon(path)

    def _should_create_hierarchy(self, name, zone=None):
        """Determine if a DNS name should create hierarchical folders"""
        # Service records (start with underscore) always create hierarchy
        if name.startswith("_"):
            return True

        # Check for actual AD site names and site-related patterns
        site_names = self._get_ad_site_names()
        for site_name in site_names:
            if site_name in name:
                return True

        # Also check for _sites pattern (generic site indicator)
        if "_sites" in name or name.endswith("_sites"):
            return True

        # Special case: DomainDnsZones and ForestDnsZones by themselves should create hierarchy
        # if there are other records with the same base name
        well_known_containers = ["DomainDnsZones", "ForestDnsZones"]
        if name in well_known_containers:
            return True

        # Create hierarchy for any dotted name containing well-known containers
        if "." in name:
            parts = name.split(".")
            for part in parts:
                if (part.startswith("_") or 
                    part in site_names or 
                    part == "_sites" or
                    part in well_known_containers):
                    return True

        # Don't create hierarchy for other dotted names
        return False


    def load_zones(self):
        """Load DNS zones in proper Windows DNS Manager tree structure."""
        self.zone_tree.clear()
        uri = self.ldap_conn.get_option(ldap.OPT_URI)
        server_fqdn = uri.split("://")[-1].split(":")[0]

        def icon(name):
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(script_dir, "res", "icons", name)
            if not os.path.exists(path):
                self.logger.warning(f"Missing icon: {path}")
                return QIcon()
            return QIcon(path)

        # Root DNS node
        root = SortableTreeWidgetItem(["DNS"])
        root.setIcon(0, icon("dns.png"))
        root.setData(0, Qt.UserRole, {"type": "dns_root"})

        # Server node (connected server)
        server_node = SortableTreeWidgetItem([server_fqdn])
        server_node.setIcon(0, icon("server.png"))  
        server_node.setData(0, Qt.UserRole, {"type": "server", "fqdn": server_fqdn})

        # Forward Lookup Zones container
        forward_node = SortableTreeWidgetItem(["Forward Lookup Zones"])
        forward_node.setIcon(0, icon("folder.png"))
        forward_node.setData(0, Qt.UserRole, {"type": "forward_container"})

        # Reverse Lookup Zones container  
        reverse_node = SortableTreeWidgetItem(["Reverse Lookup Zones"])
        reverse_node.setIcon(0, icon("folder.png"))
        reverse_node.setData(0, Qt.UserRole, {"type": "reverse_container"})

        # Conditional Forwarders container
        forwarders_node = SortableTreeWidgetItem(["Conditional Forwarders"])
        forwarders_node.setIcon(0, icon("folder.png"))
        forwarders_node.setData(0, Qt.UserRole, {"type": "forwarders_container"})

        # Populate Forward Lookup Zones
        self._populate_forward_zones(forward_node, icon)

        # Populate Reverse Lookup Zones  
        self._populate_reverse_zones(reverse_node, icon)

        # Build tree hierarchy
        server_node.addChild(forward_node)
        server_node.addChild(reverse_node)
        server_node.addChild(forwarders_node)
        root.addChild(server_node)

        self.zone_tree.addTopLevelItem(root)
        
        # Expand only specific nodes
        root.setExpanded(True)  # DNS root
        server_node.setExpanded(True)  # Server node
        forward_node.setExpanded(True)  # Forward Lookup Zones
        reverse_node.setExpanded(True)  # Reverse Lookup Zones
        # forwarders_node stays collapsed
        
        self.logger.info("Loaded DNS zones into tree view")

    def _populate_forward_zones(self, forward_node, icon):
        """Populate Forward Lookup Zones with actual DNS zones"""
        forward_zones = [zone for zone in self.zones if zone.get("type") == "Forward" and zone["name"] != "RootDNSServers"]

        for zone in forward_zones:
            zone_item = SortableTreeWidgetItem([zone["name"]])
            zone_item.setIcon(0, icon("zone.png"))
            # Handle both new and legacy zone structure
            zone_data = {
                "type": "zone",
                "name": zone["name"],
                "zone_type": "Forward"
            }
            if "dns" in zone:
                zone_data["dns"] = zone["dns"]  # New structure
            else:
                zone_data["dn"] = zone["dn"]    # Legacy structure

            zone_item.setData(0, Qt.UserRole, zone_data)
            forward_node.addChild(zone_item)

            # Build hierarchical structure for this zone
            self.build_zone_hierarchy(zone_item, zone, self._get_icon)

    def _populate_reverse_zones(self, reverse_node, icon):
        """Populate Reverse Lookup Zones with actual DNS zones"""
        reverse_zones = [zone for zone in self.zones if zone.get("type") == "Reverse"]

        for zone in reverse_zones:
            zone_item = SortableTreeWidgetItem([zone["name"]])
            zone_item.setIcon(0, icon("zone.png"))
            # Handle both new and legacy zone structure
            zone_data = {
                "type": "zone",
                "name": zone["name"],
                "zone_type": "Reverse"
            }
            if "dns" in zone:
                zone_data["dns"] = zone["dns"]  # New structure
            else:
                zone_data["dn"] = zone["dn"]    # Legacy structure

            zone_item.setData(0, Qt.UserRole, zone_data)
            reverse_node.addChild(zone_item)

            # Build hierarchical structure for reverse zones
            self.build_zone_hierarchy(zone_item, zone, self._get_icon)

    def build_zone_hierarchy(self, zone_item, zone, icon_func):
        """Build hierarchical container structure from DNS record names and cache parsed records"""
        try:
            zone_name = zone["name"]

            # Check if this zone is already cached
            if zone_name in self.zone_records_cache:
                self.logger.debug(f"Using cached records for zone {zone_name}")
                cached_zone = self.zone_records_cache[zone_name]
                all_records = cached_zone["raw_records"]
                # Skip to hierarchy building since records are cached
            else:
                # Collect all records from all zone partitions
                all_records = {}

                if "dns" in zone:
                    # New structure: zone has multiple DNs
                    for zone_info in zone["dns"]:
                        try:
                            result = self.ldap_conn.search_s(
                                zone_info["dn"],
                                ldap.SCOPE_ONELEVEL,
                                "(objectClass=dnsNode)",
                                ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                            )
                            for dn, attrs in result:
                                name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                                record_data = {
                                    'dn': dn,
                                    'name': name,
                                    'attrs': attrs,
                                    'dns_blobs': attrs.get("dnsRecord", []),
                                    'source': zone_info["source"]
                                }
                                all_records[name] = record_data

                        except Exception as e:
                            self.logger.warning(f"Failed to load records from {zone_info['dn']}: {e}")
                else:
                    # Legacy structure: zone has single DN
                    result = self.ldap_conn.search_s(
                        zone["dn"],
                        ldap.SCOPE_ONELEVEL,
                        "(objectClass=dnsNode)",
                        ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                    )
                    for dn, attrs in result:
                        name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                        record_data = {
                            'dn': dn,
                            'name': name,
                            'attrs': attrs,
                            'dns_blobs': attrs.get("dnsRecord", []),
                            'source': "System"
                        }
                        all_records[name] = record_data

                # Parse and cache all records for this zone
                self._build_zone_cache(zone_name, zone, all_records)

            # Check if this is an IPv6 or IPv4 reverse zone
            is_ipv6_reverse = zone["name"].endswith(".ip6.arpa")
            is_ipv4_reverse = zone["name"].endswith(".in-addr.arpa")

            # Build hierarchy tree from all records
            hierarchy = defaultdict(dict)

            for name, record_data in all_records.items():

                if is_ipv6_reverse and len(name) > 0 and name != "@":
                    # IPv6 reverse zone logic
                    last_hex = name[-1]
                    if last_hex not in hierarchy:
                        hierarchy[last_hex] = {}
                elif "." in name and self._should_create_hierarchy(name, zone):
                    # Build hierarchy for dotted names
                    self.logger.debug(f"Building hierarchy for dotted name: {name}")
                    parts = name.split(".")
                    self.logger.debug(f"  Parts: {parts}")
                    current = hierarchy
                    for i, part in enumerate(reversed(parts)):
                        self.logger.debug(f"  Step {i+1}: Processing part '{part}'")
                        if part not in current:
                            self.logger.debug(f"    '{part}' not found, creating new dict")
                            current[part] = {}
                        else:
                            self.logger.debug(f"    '{part}' already exists with keys: {list(current[part].keys()) if isinstance(current[part], dict) else 'not dict'}")
                            if not isinstance(current[part], dict):
                                self.logger.debug(f"    Converting '{part}' to dict (was {type(current[part])})")
                                current[part] = {}
                        # Move to the next level - DON'T reassign if it already exists
                        current = current[part]
                else:
                    # Skip creating hierarchy for @ records in IPv6 reverse zones
                    if is_ipv6_reverse and name == "@":
                        continue

                    # Only create empty hierarchy if the name doesn't already exist
                    # This prevents overwriting existing hierarchical structures
                    if name not in hierarchy:
                        hierarchy[name] = {}

            # Create tree items from hierarchy
            self.create_hierarchy_items(zone_item, hierarchy, all_records, icon_func, "", is_ipv6_reverse)

        except Exception as e:
            self.logger.warning(f"Could not build hierarchy for zone {zone['name']}: {e}")

    def _build_zone_cache(self, zone_name, zone, all_records):
        """Parse and cache all DNS records for a zone"""
        try:
            from datetime import datetime

            parsed_records = {}
            is_ipv4_reverse = zone_name.endswith(".in-addr.arpa")
            is_ipv6_reverse = zone_name.endswith(".ip6.arpa")

            for name, record_data in all_records.items():
                dns_blobs = record_data['dns_blobs']
                attrs = record_data['attrs']
                dn = record_data['dn']

                if not dns_blobs:
                    continue

                # Parse timestamp
                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                # Determine display name based on zone type
                if name == "@":
                    display_name = "(same as parent)"
                elif is_ipv4_reverse and name != "@":
                    display_name = self._reconstruct_ipv4_from_octets(name, zone_name)
                else:
                    display_name = name

                # Parse all DNS records for this name
                parsed_dns_records = []
                for blob in dns_blobs:
                    try:
                        record_type, data = self.parse_dns_record(blob)
                        parsed_dns_records.append({
                            "type": record_type,
                            "data": data,
                            "raw_blob": blob
                        })
                    except Exception as e:
                        self.logger.warning(f"Failed to parse DNS record for {name}: {e}")
                        continue

                # Store in cache
                parsed_records[name] = {
                    "dn": dn,
                    "display_name": display_name,
                    "parsed_records": parsed_dns_records,
                    "timestamp": timestamp,
                    "raw_attrs": attrs,
                    "source": record_data.get("source", "System")
                }

            # Store the complete zone cache
            self.zone_records_cache[zone_name] = {
                "raw_records": all_records,  # Keep for hierarchy building
                "parsed_records": parsed_records,  # Parsed for quick display
                "zone_info": zone,
                "is_ipv4_reverse": is_ipv4_reverse,
                "is_ipv6_reverse": is_ipv6_reverse,
                "last_updated": datetime.now()
            }

            self.logger.info(f"Cached {len(parsed_records)} parsed records for zone {zone_name}")

        except Exception as e:
            self.logger.error(f"Failed to build cache for zone {zone_name}: {e}")

    def create_hierarchy_items(self, parent_item, hierarchy, records, icon_func, prefix, is_ipv6_reverse=False):
        """Recursively create tree items from hierarchy"""
        # Sort the hierarchy items for consistent order (especially for IPv6 hex digits)
        for name, children in sorted(hierarchy.items()):
            full_name = f"{name}.{prefix}" if prefix else name


            # For IPv6 reverse zones, create hex digit folders that contain records directly
            if is_ipv6_reverse:
                # Create folder for this hex digit
                container_item = SortableTreeWidgetItem([name])
                # Get zone info from parent (handle both old and new zone structures)
                parent_data = parent_item.data(0, Qt.UserRole)
                zone_dn = None
                zone_data = None
                if parent_data:
                    if "dns" in parent_data:
                        # New structure - store the zone data for later use
                        zone_data = parent_data
                    elif "dn" in parent_data:
                        # Legacy structure
                        zone_dn = parent_data["dn"]

                container_item.setData(0, Qt.UserRole, {
                    "type": "ipv6_container",
                    "name": name,
                    "full_name": name,  # Just the hex digit
                    "zone_dn": zone_dn,
                    "zone_data": zone_data  # Store zone data for new structure
                })
                container_item.setIcon(0, icon_func("folder.png"))
                parent_item.addChild(container_item)
                # Don't recurse further for IPv6 - records will be shown when folder is clicked
                continue

            # Regular processing for non-IPv6 zones
            # Only create containers for nodes that have children
            # Leaf nodes (actual records) should not create empty folders
            if len(children) > 0:
                # This is a container
                container_item = SortableTreeWidgetItem([name])
                # Get zone_dn from parent - walk up to find the zone
                zone_dn = None
                parent_data = parent_item.data(0, Qt.UserRole)
                if parent_data:
                    zone_dn = parent_data.get("zone_dn") or parent_data.get("dn")

                container_item.setData(0, Qt.UserRole, {
                    "type": "container", 
                    "name": name,
                    "full_name": full_name,
                    "zone_dn": zone_dn
                })
                container_item.setIcon(0, icon_func("folder.png"))
                parent_item.addChild(container_item)

                # Recursively add children
                self.create_hierarchy_items(container_item, children, records, icon_func, full_name)

    def handle_zone_click(self, item, column):
        item_data = item.data(0, Qt.UserRole)
        if not item_data:
            self.logger.debug("No item data found")
            return

        item_type = item_data.get("type")
        self.logger.debug(f"Clicked item type: {item_type}, data: {item_data}")

        if item_type == "container":
            # Show records that start with this container's full name
            self.logger.debug(f"Loading container: {item_data.get('full_name')}")
            self.load_container_records(item_data)
        elif item_type == "ipv6_container":
            # Show IPv6 PTR records that start with this hex digit
            self.load_ipv6_container_records(item_data)
        elif item_type == "zone" or "dn" in item_data:
            # This is a zone, show its records
            if "dns" in item_data:
                # New structure: zone has multiple DNs, load all records from all partitions
                self.load_zone_records_multi(item_data)
            else:
                # Legacy structure: zone has single DN
                self.load_zone_records(item_data["dn"])

    def load_zone_records_multi(self, zone_data):
        """Load DNS records for a zone with multiple DNS partitions (new structure) - using cache"""
        try:
            zone_name = zone_data.get("name", "")

            # Use cached records if available
            if zone_name in self.zone_records_cache:
                self.logger.debug(f"Loading zone records from cache for {zone_name}")
                self._display_cached_zone_records(zone_name)
            else:
                # Fallback to original method if not cached (shouldn't happen after hierarchy building)
                self.logger.warning(f"Zone {zone_name} not found in cache, loading from LDAP")
                self._load_zone_records_from_ldap_multi(zone_data)

        except Exception as e:
            self.logger.error(f"Failed to load zone records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load zone records:\n{e}")

    def _load_zone_records_from_ldap_multi(self, zone_data):
        """Fallback method to load from LDAP when cache is unavailable"""
        # Collect all records from all zone partitions (similar to build_zone_hierarchy)
        all_records = {}

        for zone_info in zone_data["dns"]:
            try:
                result = self.ldap_conn.search_s(
                    zone_info["dn"],
                    ldap.SCOPE_ONELEVEL,
                    "(objectClass=dnsNode)",
                    ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                )
                for dn, attrs in result:
                    name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                    if name not in all_records:  # Avoid duplicates
                        all_records[name] = {
                            'dn': dn,
                            'name': name,
                            'attrs': attrs,
                            'dns_blobs': attrs.get("dnsRecord", []),
                            'source': zone_info["source"]
                        }

            except Exception as e:
                self.logger.warning(f"Failed to load records from {zone_info['dn']}: {e}")

        # Now process all records for display (using the same logic as load_zone_records)
        self.process_zone_records_for_display(all_records, zone_data)

    def _display_cached_zone_records(self, zone_name):
        """Display zone records from cache"""
        try:
            cached_zone = self.zone_records_cache[zone_name]
            parsed_records = cached_zone["parsed_records"]
            is_ipv6_reverse = cached_zone["is_ipv6_reverse"]

            self.record_list.clear()

            for name, record_info in parsed_records.items():
                # For IPv6 reverse zones, only show @ records at zone level
                if is_ipv6_reverse and name != "@":
                    continue  # Skip PTR records - they belong in subfolders

                # For forward zones, skip names that should create hierarchy AND single names that have containers
                if not is_ipv6_reverse and name != "@":
                    if "." in name and self._should_create_hierarchy(name):
                        continue  # Skip names that belong in hierarchical containers
                    else:
                        # Check if this single name has a corresponding container in the current zone
                        zone_item = self.zone_tree.currentItem()
                        if zone_item:
                            should_skip = False
                            for i in range(zone_item.childCount()):
                                child = zone_item.child(i)
                                child_data = child.data(0, Qt.UserRole)
                                if (child_data and 
                                    child_data.get("type") == "container" and 
                                    child_data.get("name") == name):
                                    should_skip = True
                                    break
                            if should_skip:
                                continue

                # Display all parsed records for this name
                display_name = record_info["display_name"]
                timestamp = record_info["timestamp"]
                dn = record_info["dn"]

                # Extract zone_dn from record DN for compatibility
                zone_dn = dn.split(",", 1)[1] if "," in dn else ""

                for parsed_record in record_info["parsed_records"]:
                    record_type = parsed_record["type"]
                    data = parsed_record["data"]

                    item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                    item.setIcon(0, self._get_icon("unknown.png"))
                    item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})

                    # Set sortable data for both Name column (1) and Data column (3)
                    self._set_sortable_text(item, 1, display_name)
                    self._set_sortable_text(item, 3, data)

                    self.record_list.addTopLevelItem(item)

            self.logger.info(f"Displayed {self.record_list.topLevelItemCount()} DNS records from cache")

        except Exception as e:
            self.logger.error(f"Failed to display cached zone records: {e}")

    def process_zone_records_for_display(self, all_records, zone_data):
        """Process zone records for display in the record list"""
        try:
            zone_name = zone_data.get("name", "")
            is_ipv6_reverse = zone_name.endswith(".ip6.arpa")
            is_ipv4_reverse = zone_name.endswith(".in-addr.arpa")

            self.record_list.clear()

            for name, record_data in all_records.items():
                attrs = record_data['attrs']
                dn = record_data['dn'] 
                dns_blobs = record_data['dns_blobs']

                if not dns_blobs:
                    continue  # Skip items without DNS records

                # For IPv6 reverse zones, only show @ records at zone level
                if is_ipv6_reverse and name != "@":
                    continue  # Skip PTR records - they belong in subfolders

                # For forward zones, skip names that should create hierarchy AND single names that have containers
                if not is_ipv6_reverse and name != "@":
                    if "." in name and self._should_create_hierarchy(name, zone_data):
                        self.logger.debug(f"Skipping hierarchical record '{name}' - belongs in container")
                        continue  # Skip names that belong in hierarchical containers
                    else:
                        # Check if this single name has a corresponding container in the current zone
                        zone_item = self.zone_tree.currentItem()
                        should_skip = False
                        if zone_item:
                            for i in range(zone_item.childCount()):
                                child = zone_item.child(i)
                                child_data = child.data(0, Qt.UserRole)
                                if (child_data and 
                                    child_data.get("type") == "container" and 
                                    child_data.get("name") == name):
                                    # This record belongs in the container, skip it at root level
                                    should_skip = True
                                    break
                        if should_skip:
                            self.logger.debug(f"Skipping single name record '{name}' - has container")
                            continue

                # Process record for display
                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                # Set display name based on zone type
                if name == "@":
                    display_name = "(same as parent)"
                elif is_ipv4_reverse and name != "@":
                    # For IPv4 reverse zones, reconstruct the full IP address
                    ip_address = self._reconstruct_ipv4_from_octets(name, zone_name)
                    display_name = ip_address
                else:
                    display_name = name
                zone_dn = dn.split(",", 1)[1] if "," in dn else ""  # Get zone DN from record DN

                for blob in dns_blobs:
                    record_type, data = self.parse_dns_record(blob)

                    item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                    item.setIcon(0, self._get_icon("unknown.png"))
                    item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})

                    # Set sortable data for both Name column (1) and Data column (3)
                    self._set_sortable_text(item, 1, display_name)
                    self._set_sortable_text(item, 3, data)

                    self.record_list.addTopLevelItem(item)

            self.logger.info(f"Loaded {self.record_list.topLevelItemCount()} DNS records")

        except Exception as e:
            self.logger.error(f"Failed to process zone records for display: {e}")

    def load_zone_records(self, zone_dn):
        """Load DNS records for a zone - using cache"""
        try:
            # Get zone information to check if it's IPv6 reverse
            zone_item = self.zone_tree.currentItem()
            zone_data = zone_item.data(0, Qt.UserRole) if zone_item else {}
            zone_name = zone_data.get("name", "")

            # Use cached records if available
            if zone_name in self.zone_records_cache:
                self.logger.debug(f"Loading zone records from cache for {zone_name}")
                self._display_cached_zone_records(zone_name)
                return

            # Fallback to LDAP loading if not cached
            self.logger.warning(f"Zone {zone_name} not found in cache, loading from LDAP")
            is_ipv6_reverse = zone_name.endswith(".ip6.arpa")

            result = self.ldap_conn.search_s(
                zone_dn,
                ldap.SCOPE_ONELEVEL,
                "(objectClass=dnsNode)",
                ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
            )
            self.record_list.clear()

            for dn, attrs in result:
                name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else "(unknown)"
                dns_blobs = attrs.get("dnsRecord", [])
                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")

                if not dns_blobs:
                    continue  # Skip items without DNS records

                # For IPv6 reverse zones, only show @ records at zone level
                # PTR records should only appear in their hex digit folders
                if is_ipv6_reverse and name != "@":
                    continue  # Skip PTR records - they belong in subfolders

                # For forward zones, skip names that should create hierarchy AND single names that have containers
                if not is_ipv6_reverse and name != "@":
                    if "." in name and self._should_create_hierarchy(name):
                        self.logger.debug(f"Skipping hierarchical record '{name}' - belongs in container")
                        continue  # Skip names that belong in hierarchical containers
                    else:
                        # Check if this single name has a corresponding container in the current zone
                        # Look for child containers of the current zone item
                        zone_item = self.zone_tree.currentItem()
                        should_skip = False
                        if zone_item:
                            for i in range(zone_item.childCount()):
                                child = zone_item.child(i)
                                child_data = child.data(0, Qt.UserRole)
                                if (child_data and 
                                    child_data.get("type") == "container" and 
                                    child_data.get("name") == name):
                                    # This record belongs in the container, skip it at root level
                                    should_skip = True
                                    break
                        if should_skip:
                            self.logger.debug(f"Skipping single name record '{name}' - has container")
                            continue

                # For @ records, parse all DNS record blobs (may have multiple SOA, NS, etc.)
                if name == "@" and len(dns_blobs) > 1:
                    # Multiple records in @ entry - add each one separately
                    for blob in dns_blobs:
                        record_type, data = self.parse_dns_record(blob)
                        raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                        timestamp = self.format_timestamp(raw_ts)
                        display_name = "(same as parent)"
                        item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                        item.setIcon(0, self._get_icon("unknown.png"))
                        item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})

                        # Set sortable data for both Name column (1) and Data column (3)
                        self._set_sortable_text(item, 1, display_name)
                        self._set_sortable_text(item, 3, data)

                        self.record_list.addTopLevelItem(item)
                    continue

                # Process all DNS blobs for this record (handles round robin entries)
                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                # Set display name based on zone type
                if name == "@":
                    display_name = "(same as parent)"
                elif is_ipv4_reverse and name != "@":
                    # For IPv4 reverse zones, reconstruct the full IP address
                    ip_address = self._reconstruct_ipv4_from_octets(name, zone_name)
                    display_name = ip_address
                else:
                    display_name = name

                for blob in dns_blobs:
                    record_type, data = self.parse_dns_record(blob)

                    item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                    item.setIcon(0, self._get_icon("unknown.png"))
                    item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})

                    # Set sortable data for both Name column (1) and Data column (3)
                    self._set_sortable_text(item, 1, display_name)
                    self._set_sortable_text(item, 3, data)

                    self.record_list.addTopLevelItem(item)

            self.logger.info(f"Loaded {self.record_list.topLevelItemCount()} DNS records")

        except Exception as e:
            self.logger.error(f"Failed to load zone records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load records:\n{e}")

    def load_container_records(self, container_data):
        """Load DNS records that belong to a container - using cache"""
        try:
            container_prefix = container_data.get("full_name", "")
            self.logger.debug(f"Loading container records for: '{container_prefix}'")

            # Find the zone name by walking up the tree
            zone_name = None
            current_item = self.zone_tree.currentItem()
            while current_item:
                current_data = current_item.data(0, Qt.UserRole)
                if current_data and current_data.get("type") == "zone":
                    zone_name = current_data.get("name")
                    break
                current_item = current_item.parent()

            if not zone_name:
                self.logger.error("Could not find zone name for container")
                return

            # Use cached records if available
            if zone_name in self.zone_records_cache:
                self.logger.debug(f"Loading container records from cache for {zone_name}")
                self._display_cached_container_records(zone_name, container_prefix)
                return

            # Fallback to LDAP loading if not cached (original method)
            self.logger.warning(f"Zone {zone_name} not found in cache, loading container from LDAP")
            self._load_container_records_from_ldap(container_data)

        except Exception as e:
            self.logger.error(f"Failed to load container records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load container records:\n{e}")

    def _display_cached_container_records(self, zone_name, container_prefix):
        """Display container records from cache"""
        try:
            cached_zone = self.zone_records_cache[zone_name]
            parsed_records = cached_zone["parsed_records"]

            self.record_list.clear()

            for name, record_info in parsed_records.items():
                # Check if this record belongs to this container level
                if container_prefix:
                    if name == container_prefix:
                        # This is the container itself - show as "@" record
                        display_name = "(same as parent)"
                    elif name.endswith(f".{container_prefix}"):
                        # This record belongs to this container - extract the prefix
                        remaining = name[:-len(f".{container_prefix}")]
                        if "." in remaining:
                            continue  # Skip - belongs to deeper container
                        display_name = remaining
                    else:
                        continue  # No match, skip this record
                else:
                    # No container prefix, show name as-is
                    display_name = name

                # Display all parsed records for this name
                timestamp = record_info["timestamp"]
                dn = record_info["dn"]

                # Extract zone_dn from record DN for compatibility
                zone_dn = dn.split(",", 1)[1] if "," in dn else ""

                for parsed_record in record_info["parsed_records"]:
                    record_type = parsed_record["type"]
                    data = parsed_record["data"]

                    item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                    item.setIcon(0, self._get_icon("unknown.png"))
                    item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})

                    # Set sortable data for both Name column (1) and Data column (3)
                    self._set_sortable_text(item, 1, display_name)
                    self._set_sortable_text(item, 3, data)

                    self.record_list.addTopLevelItem(item)

            self.logger.info(f"Displayed {self.record_list.topLevelItemCount()} container records from cache")

        except Exception as e:
            self.logger.error(f"Failed to display cached container records: {e}")

    def _load_container_records_from_ldap(self, container_data):
        """Fallback method to load container records from LDAP when cache unavailable"""
        try:
            # Find the zone for this container
            zone_dn = container_data.get("zone_dn")
            container_prefix = container_data.get("full_name", "")

            # Find the zone data (either from zone_dn or by walking up the tree)
            zone_data = None
            if not zone_dn:
                # Walk up the tree to find the zone
                current_item = self.zone_tree.currentItem()
                while current_item:
                    current_data = current_item.data(0, Qt.UserRole)
                    if current_data and current_data.get("type") == "zone":
                        zone_data = current_data
                        break
                    elif current_data and "dn" in current_data and not current_data.get("type"):
                        # Legacy structure
                        zone_dn = current_data["dn"]
                        break
                    current_item = current_item.parent()

            # Load records from zone (either multi-partition or single)
            all_records = {}
            if zone_data and "dns" in zone_data:
                # New structure: zone has multiple DNs
                for zone_info in zone_data["dns"]:
                    try:
                        result = self.ldap_conn.search_s(
                            zone_info["dn"],
                            ldap.SCOPE_ONELEVEL,
                            "(objectClass=dnsNode)",
                            ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                        )
                        for dn, attrs in result:
                            name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                            if name not in all_records:  # Avoid duplicates
                                all_records[name] = {
                                    'dn': dn,
                                    'name': name,
                                    'attrs': attrs,
                                    'dns_blobs': attrs.get("dnsRecord", []),
                                    'source': zone_info["source"]
                                }
                    except Exception as e:
                        self.logger.warning(f"Failed to load records from {zone_info['dn']}: {e}")
            elif zone_dn:
                # Legacy structure: single zone DN
                try:
                    result = self.ldap_conn.search_s(
                        zone_dn,
                        ldap.SCOPE_ONELEVEL,
                        "(objectClass=dnsNode)",
                        ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                    )
                    for dn, attrs in result:
                        name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                        all_records[name] = {
                            'dn': dn,
                            'name': name,
                            'attrs': attrs,
                            'dns_blobs': attrs.get("dnsRecord", []),
                            'source': "System"
                        }
                except Exception as e:
                    self.logger.warning(f"Failed to load records from {zone_dn}: {e}")
            else:
                self.logger.warning("Could not find zone data for container")
                return

            self.record_list.clear()

            for name, record_data in all_records.items():
                attrs = record_data['attrs']
                dn = record_data['dn']
                dns_blobs = record_data['dns_blobs']

                if not dns_blobs:
                    continue

                # Check if this record belongs to this container level
                if container_prefix:
                    self.logger.debug(f"  Checking record '{name}' against container '{container_prefix}'")
                    if name == container_prefix:
                        # This is the container itself - show as "@" record
                        display_name = "(same as parent)"
                        self.logger.debug(f"    → Match: container itself, display as '{display_name}'")
                    elif name.endswith(f".{container_prefix}"):
                        # Check if this is DIRECTLY under this container (exactly one more dot level)
                        remaining = name[:-len(f".{container_prefix}")]
                        self.logger.debug(f"    → Suffix match, remaining: '{remaining}'")
                        if "." in remaining:
                            # This record has more dot levels, belongs to a deeper container
                            self.logger.debug(f"    → Skip: belongs to deeper container")
                            continue
                        # This record belongs directly in this container - show only final part
                        display_name = name.split(".")[0] if "." in name else name
                        self.logger.debug(f"    → Match: direct child, display as '{display_name}'")
                    else:
                        # Doesn't match this container at all
                        self.logger.debug(f"    → No match, skipping")
                        continue
                else:
                    # No container prefix, show name as-is
                    display_name = name

                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                # Process all DNS blobs for this record (handles round robin entries)
                for blob in dns_blobs:
                    record_type, data = self.parse_dns_record(blob)

                    item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                    item.setIcon(0, self._get_icon("unknown.png"))
                    # Extract zone_dn from record DN for compatibility
                    record_zone_dn = dn.split(",", 1)[1] if "," in dn else (zone_dn or "")
                    item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": record_zone_dn})

                    # Set sortable data for both Name column (1) and Data column (3)
                    self._set_sortable_text(item, 1, display_name)
                    self._set_sortable_text(item, 3, data)

                    self.record_list.addTopLevelItem(item)

            self.logger.info(f"Loaded {self.record_list.topLevelItemCount()} records from container")

        except Exception as e:
            self.logger.error(f"Failed to load container records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load container records:\n{e}")

    def load_ipv6_container_records(self, container_data):
        """Load IPv6 PTR records that start with a specific hex digit - using cache"""
        try:
            hex_digit = container_data.get("name", "")
            if not hex_digit:
                return

            # Find the zone name by walking up the tree
            zone_name = None
            current_item = self.zone_tree.currentItem()
            while current_item:
                current_data = current_item.data(0, Qt.UserRole)
                if current_data and current_data.get("type") == "zone":
                    zone_name = current_data.get("name")
                    break
                current_item = current_item.parent()

            if not zone_name:
                self.logger.error("Could not find zone name for IPv6 container")
                return

            # Use cached records if available
            if zone_name in self.zone_records_cache:
                self.logger.debug(f"Loading IPv6 container records from cache for {zone_name}")
                self._display_cached_ipv6_container_records(zone_name, hex_digit)
                return

            # Fallback to LDAP loading if not cached
            self.logger.warning(f"Zone {zone_name} not found in cache, loading IPv6 container from LDAP")
            self._load_ipv6_container_records_from_ldap(container_data)

        except Exception as e:
            self.logger.error(f"Failed to load IPv6 container records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load IPv6 container records:\n{e}")

    def _display_cached_ipv6_container_records(self, zone_name, hex_digit):
        """Display IPv6 container records from cache"""
        try:
            cached_zone = self.zone_records_cache[zone_name]
            parsed_records = cached_zone["parsed_records"]
            zone_info = cached_zone["zone_info"]

            self.record_list.clear()

            for name, record_info in parsed_records.items():
                # Only show records that end with this hex digit (and aren't "@")
                if name == "@" or not name.endswith(hex_digit):
                    continue

                # For IPv6 PTR records, reconstruct the IPv6 address for the Name column
                # Get zone_dn for the reconstruction function
                zone_dn = None
                if "dns" in zone_info and zone_info["dns"]:
                    zone_dn = zone_info["dns"][0]["dn"]
                elif "dn" in zone_info:
                    zone_dn = zone_info["dn"]

                if zone_dn:
                    ipv6_addr = self._reconstruct_ipv6_from_nibbles(name, hex_digit, zone_dn)
                else:
                    ipv6_addr = name  # Fallback if no zone DN

                # Display all parsed records for this name
                timestamp = record_info["timestamp"]
                dn = record_info["dn"]

                # Extract zone_dn from record DN for compatibility  
                record_zone_dn = dn.split(",", 1)[1] if "," in dn else (zone_dn or "")

                for parsed_record in record_info["parsed_records"]:
                    record_type = parsed_record["type"]
                    data = parsed_record["data"]

                    item = SortableTreeWidgetItem(["", ipv6_addr, record_type, data, timestamp])
                    item.setIcon(0, self._get_icon("unknown.png"))
                    item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": record_zone_dn})

                    # Set sortable data for both Name column (1) and Data column (3)
                    self._set_sortable_text(item, 1, ipv6_addr)
                    self._set_sortable_text(item, 3, data)

                    self.record_list.addTopLevelItem(item)

            self.logger.info(f"Displayed {self.record_list.topLevelItemCount()} IPv6 container records from cache")

        except Exception as e:
            self.logger.error(f"Failed to display cached IPv6 container records: {e}")

    def _load_ipv6_container_records_from_ldap(self, container_data):
        """Fallback method to load IPv6 container records from LDAP when cache unavailable"""
        try:
            # Get zone information (handle both old and new structures)
            zone_dn = container_data.get("zone_dn")
            zone_data = container_data.get("zone_data")
            hex_digit = container_data.get("name", "")

            # Load records from zone (either multi-partition or single)
            all_records = {}
            if zone_data and "dns" in zone_data:
                # New structure: zone has multiple DNs
                for zone_info in zone_data["dns"]:
                    try:
                        result = self.ldap_conn.search_s(
                            zone_info["dn"],
                            ldap.SCOPE_ONELEVEL,
                            "(objectClass=dnsNode)",
                            ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                        )
                        for dn, attrs in result:
                            name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                            if name not in all_records:  # Avoid duplicates
                                all_records[name] = {
                                    'dn': dn,
                                    'name': name,
                                    'attrs': attrs,
                                    'dns_blobs': attrs.get("dnsRecord", []),
                                    'source': zone_info["source"]
                                }
                    except Exception as e:
                        self.logger.warning(f"Failed to load IPv6 records from {zone_info['dn']}: {e}")
            elif zone_dn:
                # Legacy structure: single zone DN
                try:
                    result = self.ldap_conn.search_s(
                        zone_dn,
                        ldap.SCOPE_ONELEVEL,
                        "(objectClass=dnsNode)",
                        ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
                    )
                    for dn, attrs in result:
                        name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                        all_records[name] = {
                            'dn': dn,
                            'name': name,
                            'attrs': attrs,
                            'dns_blobs': attrs.get("dnsRecord", []),
                            'source': "System"
                        }
                except Exception as e:
                    self.logger.warning(f"Failed to load IPv6 records from {zone_dn}: {e}")
            else:
                self.logger.warning("Could not find zone data for IPv6 container")
                return

            self.record_list.clear()

            for name, record_data in all_records.items():
                attrs = record_data['attrs']
                dn = record_data['dn']
                dns_blobs = record_data['dns_blobs']

                if not dns_blobs:
                    continue

                # Only show records that end with this hex digit (and aren't "@")
                if name == "@" or not name.endswith(hex_digit):
                    continue

                record_type, data = self.parse_dns_record(dns_blobs[0])

                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                # For IPv6 PTR records, reconstruct the IPv6 address for the Name column
                # Include the hex folder digit in the reconstruction  
                # Get zone_dn for the reconstruction function
                reconstruction_zone_dn = zone_dn or (zone_data["dns"][0]["dn"] if zone_data and zone_data.get("dns") else "")
                ipv6_addr = self._reconstruct_ipv6_from_nibbles(name, hex_digit, reconstruction_zone_dn)

                item = SortableTreeWidgetItem(["", ipv6_addr, record_type, data, timestamp])
                item.setIcon(0, self._get_icon("unknown.png"))
                # Extract zone_dn from record DN for compatibility
                record_zone_dn = dn.split(",", 1)[1] if "," in dn else reconstruction_zone_dn
                item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": record_zone_dn})

                # Set sortable data for both Name column (1) and Data column (3)
                self._set_sortable_text(item, 1, ipv6_addr)
                self._set_sortable_text(item, 3, data)

                self.record_list.addTopLevelItem(item)

            self.logger.info(f"Loaded {self.record_list.topLevelItemCount()} IPv6 records from container {hex_digit}")

        except Exception as e:
            self.logger.error(f"Failed to load IPv6 container records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load IPv6 container records:\n{e}")

    def launch_edit_dialog(self, item, column):
        record = item.data(0, Qt.UserRole)
        if not record:
            return

        zone_dn = record.get("zone_dn")
        if not zone_dn:
            return

        dialog = EditDialog(zone_dn, record["name"], self.ldap_conn, self.logger, self)
        dialog.exec_()

    def parse_dns_record(self, blob):
        import struct, socket
        try:
            data_length, record_type, version, rank, flags, header_serial = struct.unpack('<H H B B H L', blob[:12])
            ttl = struct.unpack('<L', blob[12:16])[0]
            reserved, ts = struct.unpack('<L L', blob[16:24])
            payload = blob[24:]

            # For SOA records, get the actual SOA serial from offset 8
            soa_serial = None
            if record_type == 6 and len(blob) > 8:
                soa_serial = struct.unpack('<I', blob[8:12])[0]

            if record_type == 1:  # A
                ip = socket.inet_ntoa(payload)
                return "A", ip

            elif record_type == 28:  # AAAA
                ip = socket.inet_ntop(socket.AF_INET6, payload)
                return "AAAA", ip

            elif record_type == 5:  # CNAME
                # Parse the CNAME DNS name - scan for valid DNS name in payload
                cname = ""
                for i in range(len(payload) - 1):
                    if 1 <= payload[i] <= 63:  # Valid DNS label length
                        length = payload[i]
                        if i + 1 + length < len(payload):
                            try:
                                label = payload[i+1:i+1+length].decode('ascii', errors='ignore')
                                if label.replace('-', '').replace('_', '').isalnum():  # Looks like a DNS label
                                    cname, _ = self._parse_dns_name(payload, i)
                                    break
                            except:
                                continue
                return "CNAME", cname

            elif record_type == 33:  # SRV
                if len(payload) >= 6:
                    priority, weight, port = struct.unpack(">HHH", payload[:6])  # Big-endian for SRV
                    # Parse the target DNS name - scan for valid DNS name starting after priority/weight/port
                    target = ""
                    for i in range(6, len(payload) - 1):
                        if 1 <= payload[i] <= 63:  # Valid DNS label length
                            length = payload[i]
                            if i + 1 + length < len(payload):
                                try:
                                    label = payload[i+1:i+1+length].decode('ascii', errors='ignore')
                                    if label.replace('-', '').replace('_', '').isalnum():  # Looks like a DNS label
                                        target, _ = self._parse_dns_name(payload, i)
                                        break
                                except:
                                    continue
                    return "SRV", f"[{priority}][{weight}][{port}] {target}"
                return "SRV", "(invalid length)"

            elif record_type == 16:  # TXT
                txt_parts = []
                i = 0
                while i < len(payload):
                    length = payload[i]
                    i += 1
                    txt = payload[i:i + length].decode("utf-8", errors="ignore")
                    txt_parts.append(txt)
                    i += length
                return "TXT", " ".join(txt_parts) if txt_parts else "(empty)"

            elif record_type == 15:  # MX
                if len(payload) >= 3:
                    preference = struct.unpack("<H", payload[:2])[0]
                    length = payload[2]
                    exchange = payload[3:3 + length].decode("utf-8", errors="ignore")
                    return "MX", f"{preference} {exchange}"
                return "MX", "(invalid length)"

            elif record_type == 2:  # NS
                # Find the start of DNS name by looking for valid length bytes
                for i in range(len(payload) - 5):
                    if 1 <= payload[i] <= 63:  # Valid DNS label length
                        length = payload[i]
                        if i + 1 + length < len(payload):
                            try:
                                label = payload[i+1:i+1+length].decode('ascii', errors='ignore')
                                if label.isalpha():  # Looks like a DNS name
                                    ns_name = self._parse_dns_name(payload, i)[0]
                                    return "NS", ns_name
                            except:
                                continue
                return "NS", "(cannot parse DNS name)"

            elif record_type == 6:  # SOA
                # SOA serial is in the header at offset 8
                # MNAME typically starts around offset 22, RNAME around offset 50
                if soa_serial is not None:
                    try:
                        # Try known working offsets first
                        mname = ""
                        rname = ""

                        # Try to find MNAME starting around offset 22
                        for mname_start in range(20, min(30, len(payload))):
                            if mname_start < len(payload) and 1 <= payload[mname_start] <= 63:
                                try:
                                    test_mname, mname_end = self._parse_dns_name(payload, mname_start)
                                    if test_mname and '.' in test_mname:  # Valid MNAME with dots
                                        mname = test_mname

                                        # Now look for RNAME starting after MNAME + some header bytes
                                        for rname_start in range(mname_end, min(mname_end + 10, len(payload))):
                                            if rname_start < len(payload) and 1 <= payload[rname_start] <= 63:
                                                try:
                                                    test_rname, _ = self._parse_dns_name(payload, rname_start)
                                                    if test_rname and '.' in test_rname:  # Valid RNAME with dots
                                                        rname = test_rname
                                                        break
                                                except:
                                                    continue
                                        break
                                except:
                                    continue

                        return "SOA", f"[{soa_serial}], {mname}., {rname}."
                    except Exception as e:
                        return "SOA", f"(parse error: {e})"
                return "SOA", "(cannot find DNS names)"

            elif record_type == 12:  # PTR
                # Parse the PTR DNS name - scan for valid DNS name in payload
                ptr = ""
                for i in range(len(payload) - 1):
                    if 1 <= payload[i] <= 63:  # Valid DNS label length
                        length = payload[i]
                        if i + 1 + length < len(payload):
                            try:
                                label = payload[i+1:i+1+length].decode('ascii', errors='ignore')
                                if label.replace('-', '').replace('_', '').isalnum():  # Looks like a DNS label
                                    ptr, _ = self._parse_dns_name(payload, i)
                                    break
                            except:
                                continue
                return "PTR", ptr

            elif record_type == 34:  # A6
                prefix_len = payload[0]
                if len(payload) >= 17:
                    ip = socket.inet_ntop(socket.AF_INET6, payload[1:17])
                    return "A6", f"{ip} (prefixLen={prefix_len})"
                return "A6", "(invalid length)"

            else:
                hex_dump = " ".join(f"{b:02x}" for b in payload)
                return f"TYPE{record_type}", f"(unparsed) {hex_dump}"

        except Exception as e:
            return "(error)", str(e)

    def _parse_dns_name(self, data, offset):
        """Parse a DNS name from binary data starting at offset. Returns (name, new_offset)"""
        name_parts = []
        jumped = False
        saved_offset = 0
        start_offset = offset

        while offset < len(data):
            if offset >= len(data):
                break

            length = data[offset]

            if length == 0:  # End of name
                offset += 1
                break
            elif (length & 0xC0) == 0xC0:  # Compression pointer (bits 11)
                if not jumped:
                    saved_offset = offset + 2  # Save position after pointer
                if offset + 1 >= len(data):
                    break
                # Extract 14-bit pointer
                pointer = ((length & 0x3F) << 8) | data[offset + 1]
                offset = pointer
                jumped = True
                if pointer >= len(data) or pointer == start_offset:  # Avoid infinite loops
                    break
                continue
            elif 1 <= length <= 63:  # Regular label (valid DNS label length)
                offset += 1
                if offset + length > len(data):
                    break
                try:
                    label_bytes = data[offset:offset + length]
                    # Decode as ASCII/UTF-8 for DNS names
                    label = label_bytes.decode('ascii', errors='ignore')
                    if label.strip():  # Only add non-empty labels
                        name_parts.append(label)
                except Exception:
                    pass
                offset += length
            else:
                # Invalid length, stop parsing
                break

        if jumped and saved_offset > 0:
            offset = saved_offset

        return ".".join(name_parts), offset

    def _reconstruct_ipv6_from_nibbles(self, nibble_name, hex_digit, zone_dn):
        """Reconstruct IPv6 address from reversed nibble DNS name with zone prefix and hex digit"""
        try:
            # Extract zone name from DN to get the prefix
            zone_prefix_nibbles = ""
            if zone_dn:
                # Extract zone name from DN like "DC=4.0.8.0.0.4.f.1.0.4.c.6.0.0.6.2.ip6.arpa,..."
                import re
                match = re.search(r'DC=([^,]+\.ip6\.arpa)', zone_dn)
                if match:
                    zone_name = match.group(1)
                    # Remove .ip6.arpa and extract nibbles
                    zone_nibbles = zone_name.replace(".ip6.arpa", "").replace(".", "")
                    # Reverse to get original order (zone is also in reverse)
                    zone_prefix_nibbles = zone_nibbles[::-1]

            # Remove dots from record name and reverse the nibbles
            record_nibbles = nibble_name.replace(".", "")
            record_nibbles = record_nibbles[::-1]

            # Combine: zone_prefix + record_nibbles (hex_digit is just for folder organization)
            full_nibbles = zone_prefix_nibbles + record_nibbles

            # Pad to 32 nibbles (128 bits) if needed
            full_nibbles = full_nibbles.ljust(32, "0")

            # Group into 4-nibble chunks and join with colons
            groups = []
            for i in range(0, min(32, len(full_nibbles)), 4):
                group = full_nibbles[i:i+4]
                groups.append(group)

            # Join with colons and compress zeros
            ipv6_addr = ":".join(groups)

            # Basic IPv6 compression (remove leading zeros in each group)
            parts = ipv6_addr.split(":")
            compressed_parts = []
            for part in parts:
                compressed_parts.append(part.lstrip("0") or "0")

            return ":".join(compressed_parts)

        except Exception:
            return nibble_name  # Return original if reconstruction fails

    def _reconstruct_ipv4_from_octets(self, octet_name, zone_name):
        """Reconstruct IPv4 address from reversed octet DNS name"""
        try:
            # IPv4 reverse zones are like "1.168.192.in-addr.arpa"
            # Records are like "10" for IP 192.168.1.10

            # Extract the IP prefix from zone name
            if ".in-addr.arpa" not in zone_name:
                return octet_name  # Not an IPv4 reverse zone

            # Get the reversed octets from zone name (e.g., "1.168.192" from "1.168.192.in-addr.arpa")
            zone_octets = zone_name.replace(".in-addr.arpa", "").split(".")

            # Reverse the zone octets to get original order
            zone_octets.reverse()

            # The record name is the final octet(s)
            record_octets = octet_name.split(".") if "." in octet_name else [octet_name]

            # Combine zone octets + record octets to form full IP
            full_ip_octets = zone_octets + record_octets

            # Validate and return IP address
            ip_address = ".".join(full_ip_octets)

            # Basic validation - should have 4 octets
            if len(full_ip_octets) == 4 and all(octet.isdigit() and 0 <= int(octet) <= 255 for octet in full_ip_octets):
                return ip_address
            else:
                return octet_name  # Return original if not a valid IP

        except Exception:
            return octet_name  # Return original if reconstruction fails

    def _ip_to_sortable_int(self, ip_or_text):
        """Convert IP address to sortable integer, return large number if not an IP"""
        try:
            # Check if this looks like an IPv4 address
            parts = str(ip_or_text).split(".")
            if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
                # Convert IPv4 to integer: 192.168.1.10 -> 3232235786
                return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])

            # Try to extract IP from more complex strings like "192.168.1.10 some.domain.com"
            import re
            ip_match = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', str(ip_or_text))
            if ip_match:
                ip = ip_match.group(1)
                parts = ip.split(".")
                if all(0 <= int(part) <= 255 for part in parts):
                    return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])

            # Not an IP address, return a large number so it sorts after IPs
            return 0xFFFFFFFF + hash(str(ip_or_text)) % 1000000

        except (ValueError, AttributeError):
            # Not an IP address, return a large number so it sorts after IPs  
            return 0xFFFFFFFF + hash(str(ip_or_text)) % 1000000

    def _make_ip_text_sortable(self, text):
        """Convert IP addresses in text to zero-padded format for natural string sorting"""
        try:
            import re

            def pad_ipv4(match):
                ip = match.group(0)
                parts = ip.split(".")
                if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
                    # Pad each octet to 3 digits: 192.168.1.10 -> 192.168.001.010
                    return ".".join(f"{int(part):03d}" for part in parts)
                return ip

            def pad_ipv6(match):
                ip = match.group(0)
                try:
                    # Handle IPv6 addresses
                    # First, expand :: to full form
                    if '::' in ip:
                        # Split on ::
                        left, right = ip.split('::', 1)
                        left_parts = left.split(':') if left else []
                        right_parts = right.split(':') if right else []

                        # Remove empty parts
                        left_parts = [p for p in left_parts if p]
                        right_parts = [p for p in right_parts if p]

                        # Calculate missing segments (IPv6 has 8 segments total)
                        missing_segments = 8 - len(left_parts) - len(right_parts)

                        # Reconstruct full address
                        full_parts = left_parts + ['0000'] * missing_segments + right_parts
                    else:
                        # Already full form
                        full_parts = ip.split(':')

                    # Pad each segment to 4 hex digits
                    padded_parts = []
                    for part in full_parts:
                        # Validate hex and pad
                        if all(c in '0123456789abcdefABCDEF' for c in part):
                            padded_parts.append(f"{int(part, 16):04x}")
                        else:
                            return ip  # Invalid hex, return original

                    return ':'.join(padded_parts)

                except (ValueError, IndexError):
                    return ip  # Invalid IPv6, return original

            # Process text - first IPv4, then IPv6
            result = str(text)

            # Replace IPv4 addresses with zero-padded versions
            result = re.sub(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', pad_ipv4, result)

            # Replace IPv6 addresses (more complex pattern to avoid matching IPv4)
            # Match IPv6: groups of hex digits separated by colons, may contain ::
            ipv6_pattern = r'\b(?:[0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}\b|\b[0-9a-fA-F]{1,4}::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b|\b::(?:[0-9a-fA-F]{1,4}:){0,7}[0-9a-fA-F]{1,4}\b|\b[0-9a-fA-F]{1,4}::\b|\b::\b'
            result = re.sub(ipv6_pattern, pad_ipv6, result)

            return result

        except:
            return str(text)

    def _set_sortable_text(self, item, column, display_text):
        """Set both display text and sortable data for proper IP address sorting"""
        item.setText(column, display_text)
        sortable_text = self._make_ip_text_sortable(display_text)
        item.setData(column, Qt.UserRole, sortable_text)

    def _place_record_in_hierarchy(self, zone_item, name, dns_blob, dn, zone_dn, raw_ts):
        """Dynamically create folder hierarchy for dotted DNS record names and place records in correct containers"""
        try:
            # Parse the DNS record to get type and data
            record_type, data = self.parse_dns_record(dns_blob)
            timestamp = self.format_timestamp(raw_ts)

            # Split the name by dots (e.g., "_gc._tcp.Default-First-Site-Name._sites")
            parts = name.split(".")

            if len(parts) <= 1:
                # No dots, place directly in zone
                display_name = name
                item = SortableTreeWidgetItem(["", display_name, record_type, data, timestamp])
                item.setIcon(0, self._get_icon("unknown.png"))
                item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})

                # Set sortable data for both Name column (1) and Data column (3)
                self._set_sortable_text(item, 1, display_name)
                self._set_sortable_text(item, 3, data)

                # Add to record list since we're in zone view
                self.record_list.addTopLevelItem(item)
                return

            # Process parts from right to left to create hierarchy
            # e.g., for "_gc._tcp.Default-First-Site-Name._sites" we get:
            # parts = ["_gc", "_tcp", "Default-First-Site-Name", "_sites"]
            # We need to create: _sites -> Default-First-Site-Name -> _tcp (and place _gc in _tcp)

            current_item = zone_item
            current_path = ""

            # Process all but the last part to create folder hierarchy
            for i in range(len(parts) - 1, 0, -1):  # Process from rightmost to second part
                folder_name = parts[i]
                current_path = folder_name if not current_path else f"{folder_name}.{current_path}"

                # Look for existing folder at current level
                existing_folder = None
                for j in range(current_item.childCount()):
                    child = current_item.child(j)
                    child_data = child.data(0, Qt.UserRole)
                    if (child_data and 
                        child_data.get("type") == "container" and 
                        child_data.get("name") == folder_name):
                        existing_folder = child
                        break

                # Create folder if it doesn't exist
                if not existing_folder:
                    container_item = SortableTreeWidgetItem([folder_name])
                    container_item.setData(0, Qt.UserRole, {
                        "type": "container",
                        "name": folder_name,
                        "full_name": current_path,
                        "zone_dn": zone_dn
                    })
                    container_item.setIcon(0, self._get_icon("folder.png"))
                    current_item.addChild(container_item)
                    existing_folder = container_item

                current_item = existing_folder

            # The first part (leftmost) is the actual record name to display
            display_name = parts[0]

            # Note: The record isn't actually added to any tree here since this method
            # is called from load_zone_records which manages the record display.
            # The hierarchy creation is the main purpose of this method.

        except Exception as e:
            self.logger.error(f"Failed to place record {name} in hierarchy: {e}")

    def format_timestamp(self, raw):
        from datetime import datetime, timezone
        try:
            # Parse UTC timestamp and convert to local timezone
            utc_dt = datetime.strptime(raw, "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)
            local_dt = utc_dt.astimezone()  # Convert to local timezone
            return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            return raw

def icon(name):
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return QIcon(os.path.join(script_dir, "res", "icons", name))

