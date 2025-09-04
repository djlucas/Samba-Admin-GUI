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


class MainWindow(QWidget):
    def __init__(self, ldap_conn, logger, zones):
        super().__init__()
        self.ldap_conn = ldap_conn
        self.logger = logger
        self.zones = zones
        self.setWindowTitle("SDNS - Samba DNS Management")
        self.resize(800, 500)

        # Zone tree
        self.zone_tree = QTreeWidget()
        self.zone_tree.setHeaderHidden(True)
        self.zone_tree.itemClicked.connect(self.handle_zone_click)

        zone_layout = QVBoxLayout()
        zone_layout.addWidget(QLabel("DNS Zones"))
        zone_layout.addWidget(self.zone_tree)

        # Record list (now a QTreeWidget with columns)
        self.record_list = QTreeWidget()
        self.record_list.setHeaderLabels(["", "Name", "Type", "Data", "Timestamp"])
        self.record_list.setRootIsDecorated(False)
        self.record_list.setIconSize(QSize(16, 16))
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

    def load_zones(self):
        """Load DNS zones in proper Windows DNS Manager tree structure."""
        self.zone_tree.clear()
        uri = self.ldap_conn.get_option(ldap.OPT_URI)
        server_fqdn = uri.split("://")[-1].split(":")[0]

        def icon(name):
            path = os.path.join("src", "res", "icons", name)
            if not os.path.exists(path):
                self.logger.warning(f"Missing icon: {path}")
                return QIcon()
            return QIcon(path)

        # Root DNS node
        root = QTreeWidgetItem(["DNS"])
        root.setIcon(0, icon("dns.png"))
        root.setData(0, Qt.UserRole, {"type": "dns_root"})

        # Server node (connected server)
        server_node = QTreeWidgetItem([server_fqdn])
        server_node.setIcon(0, icon("server.png"))  
        server_node.setData(0, Qt.UserRole, {"type": "server", "fqdn": server_fqdn})

        # Forward Lookup Zones container
        forward_node = QTreeWidgetItem(["Forward Lookup Zones"])
        forward_node.setIcon(0, icon("folder.png"))
        forward_node.setData(0, Qt.UserRole, {"type": "forward_container"})
        
        # Reverse Lookup Zones container  
        reverse_node = QTreeWidgetItem(["Reverse Lookup Zones"])
        reverse_node.setIcon(0, icon("folder.png"))
        reverse_node.setData(0, Qt.UserRole, {"type": "reverse_container"})
        
        # Conditional Forwarders container
        forwarders_node = QTreeWidgetItem(["Conditional Forwarders"])
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
        self.zone_tree.expandAll()
        self.logger.info("Loaded DNS zones into tree view")

    def _populate_forward_zones(self, forward_node, icon):
        """Populate Forward Lookup Zones with actual DNS zones"""
        forward_zones = [zone for zone in self.zones if zone.get("type") == "Forward"]
        
        for zone in forward_zones:
            zone_item = QTreeWidgetItem([zone["name"]])
            zone_item.setIcon(0, icon("zone.png"))
            zone_item.setData(0, Qt.UserRole, {
                "type": "zone",
                "dn": zone["dn"],
                "name": zone["name"],
                "zone_type": "Forward"
            })
            forward_node.addChild(zone_item)
            
            # Build hierarchical structure for this zone
            self.build_zone_hierarchy(zone_item, zone, icon)
    
    def _populate_reverse_zones(self, reverse_node, icon):
        """Populate Reverse Lookup Zones with actual DNS zones"""
        reverse_zones = [zone for zone in self.zones if zone.get("type") == "Reverse"]
        
        for zone in reverse_zones:
            zone_item = QTreeWidgetItem([zone["name"]])
            zone_item.setIcon(0, icon("zone.png"))
            zone_item.setData(0, Qt.UserRole, {
                "type": "zone", 
                "dn": zone["dn"],
                "name": zone["name"],
                "zone_type": "Reverse"
            })
            reverse_node.addChild(zone_item)
            
            # Build hierarchical structure for this zone
            self.build_zone_hierarchy(zone_item, zone, icon)

    def build_zone_hierarchy(self, zone_item, zone, icon_func):
        """Build hierarchical container structure from DNS record names"""
        try:
            # Get all DNS records in the zone
            result = self.ldap_conn.search_s(
                zone["dn"],
                ldap.SCOPE_ONELEVEL,
                "(objectClass=dnsNode)",
                ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
            )
            
            # Build hierarchy tree from DNS names
            hierarchy = defaultdict(dict)
            records = {}
            
            for dn, attrs in result:
                name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                dns_blobs = attrs.get("dnsRecord", [])
                
                if name == "@":  # Zone root
                    continue
                
                # Store record data
                records[name] = {
                    'dn': dn,
                    'name': name,
                    'attrs': attrs,
                    'dns_blobs': dns_blobs
                }
                
                # Build hierarchy from DNS name parts
                if "." in name:
                    parts = name.split(".")
                    current = hierarchy
                    for part in reversed(parts):  # Build from right to left
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                else:
                    hierarchy[name] = {}
            
            # Create tree items from hierarchy
            self.create_hierarchy_items(zone_item, hierarchy, records, icon_func, "")
                    
        except Exception as e:
            self.logger.warning(f"Could not build hierarchy for zone {zone['name']}: {e}")

    def create_hierarchy_items(self, parent_item, hierarchy, records, icon_func, prefix):
        """Recursively create tree items from hierarchy"""
        for name, children in hierarchy.items():
            full_name = f"{name}.{prefix}" if prefix else name
            
            # Check if this is a leaf node (actual DNS record) or container
            is_leaf = len(children) == 0 and full_name in records
            is_service_container = name.startswith("_") and len(children) > 0
            
            if is_leaf:
                # This is an actual DNS record, don't add to tree
                continue
            elif is_service_container or len(children) > 0:
                # This is a container
                container_item = QTreeWidgetItem([name])
                container_item.setData(0, Qt.UserRole, {
                    "type": "container", 
                    "name": name,
                    "full_name": full_name,
                    "zone_dn": parent_item.data(0, Qt.UserRole).get("dn") if parent_item.data(0, Qt.UserRole) else None
                })
                container_item.setIcon(0, icon_func("folder.png"))
                parent_item.addChild(container_item)
                
                # Recursively add children
                self.create_hierarchy_items(container_item, children, records, icon_func, full_name)

    def handle_zone_click(self, item, column):
        item_data = item.data(0, Qt.UserRole)
        if not item_data:
            return

        if item_data.get("type") == "container":
            # Show records that start with this container's full name
            self.load_container_records(item_data)
        elif "dn" in item_data:
            # This is a zone, show its records
            self.load_zone_records(item_data["dn"])

    def load_zone_records(self, zone_dn):
        """Load DNS records for a zone"""
        try:
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

                if not dns_blobs:
                    continue  # Skip items without DNS records

                # Parse record type and data
                record_type, data = self.parse_dns_record(dns_blobs[0])

                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                item = QTreeWidgetItem(["", name, record_type, data, timestamp])
                item.setIcon(0, icon("unknown.png"))
                item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})
                self.record_list.addTopLevelItem(item)

            self.logger.info(f"Loaded {self.record_list.topLevelItemCount()} DNS records")

        except Exception as e:
            self.logger.error(f"Failed to load zone records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load records:\n{e}")

    def load_container_records(self, container_data):
        """Load DNS records that belong to a container"""
        try:
            # Find the zone for this container
            zone_dn = container_data.get("zone_dn")
            container_prefix = container_data.get("full_name", "")
            
            if not zone_dn:
                # Walk up the tree to find the zone
                current_item = self.zone_tree.currentItem()
                while current_item:
                    current_data = current_item.data(0, Qt.UserRole)
                    if current_data and "dn" in current_data and not current_data.get("type"):
                        zone_dn = current_data["dn"]
                        break
                    current_item = current_item.parent()
            
            if not zone_dn:
                return
                
            result = self.ldap_conn.search_s(
                zone_dn,
                ldap.SCOPE_ONELEVEL,
                "(objectClass=dnsNode)",
                ["name", "dnsRecord", "whenCreated", "modifyTimestamp"]
            )
            self.record_list.clear()

            for dn, attrs in result:
                name = attrs.get("name", [b""])[0].decode("utf-8") if "name" in attrs else ""
                dns_blobs = attrs.get("dnsRecord", [])

                if not dns_blobs:
                    continue
                
                # Check if this record belongs to the container
                if container_prefix and not name.endswith(f".{container_prefix}") and name != container_prefix:
                    continue

                record_type, data = self.parse_dns_record(dns_blobs[0])

                raw_ts = attrs.get("modifyTimestamp", attrs.get("whenCreated", [b""]))[0].decode("utf-8")
                timestamp = self.format_timestamp(raw_ts)

                item = QTreeWidgetItem(["", name, record_type, data, timestamp])
                item.setIcon(0, icon("unknown.png"))
                item.setData(0, Qt.UserRole, {"dn": dn, "name": name, "zone_dn": zone_dn})
                self.record_list.addTopLevelItem(item)

            self.logger.info(f"Loaded {self.record_list.topLevelItemCount()} records from container")

        except Exception as e:
            self.logger.error(f"Failed to load container records: {e}")
            QMessageBox.critical(self, "Error", f"Could not load container records:\n{e}")

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
            data_length, record_type, version, rank, flags, serial = struct.unpack('<H H B B H L', blob[:12])
            ttl = struct.unpack('<L', blob[12:16])[0]
            reserved, ts = struct.unpack('<L L', blob[16:24])
            record_data = blob[24:]
            data = blob if isinstance(blob, bytes) else blob.encode("latin1")

            if len(data) < 14:
                return "(container)", "(no record)"

            record_type = struct.unpack("<H", data[2:4])[0]
            payload = data[12:]

            if record_type == 1:  # A
                ip = socket.inet_ntoa(record_data)
                return "A", ip

            elif record_type == 28:  # AAAA
                ip = socket.inet_ntop(socket.AF_INET6, record_data)
                return "AAAA", ip

            elif record_type == 5:  # CNAME
                length = payload[0]
                cname = payload[1:1 + length].decode("utf-8", errors="ignore")
                return "CNAME", cname

            elif record_type == 33:  # SRV
                if len(payload) >= 7:
                    priority, weight, port = struct.unpack("<HHH", payload[:6])
                    length = payload[6]
                    target = payload[7:7 + length].decode("utf-8", errors="ignore")
                    return "SRV", f"{priority} {weight} {port} {target}"
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
                length = payload[0]
                ns = payload[1:1 + length].decode("utf-8", errors="ignore")
                return "NS", ns

            elif record_type == 6:  # SOA
                mlen = payload[0]
                mname = payload[1:1 + mlen].decode("utf-8", errors="ignore")
                rlen = payload[1 + mlen]
                rname = payload[2 + mlen:2 + mlen + rlen].decode("utf-8", errors="ignore")
                soa_fields = payload[2 + mlen + rlen:2 + mlen + rlen + 20]
                if len(soa_fields) == 20:
                    serial, refresh, retry, expire, minimum = struct.unpack("<IIIII", soa_fields)
                    return "SOA", f"{mname} {rname} {serial} {refresh} {retry} {expire} {minimum}"
                return "SOA", "(invalid length)"

            elif record_type == 12:  # PTR
                length = payload[0]
                ptr = payload[1:1 + length].decode("utf-8", errors="ignore")
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

    def format_timestamp(self, raw):
        from datetime import datetime
        try:
            return datetime.strptime(raw, "%Y%m%d%H%M%SZ").strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return raw

def icon(name):
    return QIcon(os.path.join("src", "res", "icons", name))

