"""
Unraid GraphQL API Client

This script demonstrates how to connect to the Unraid GraphQL API,
authenticate with an API key, and perform various queries.
"""

import requests
import json
import argparse
from typing import Dict, Any, Optional, List
import urllib3
import re
import warnings

# Disable SSL warnings for self-signed certificates if needed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Suppress urllib3 OpenSSL warnings
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='.*NotOpenSSLWarning.*')

class UnraidGraphQLClient:
    """Client for interacting with the Unraid GraphQL API."""
    
    def __init__(self, server_ip: str, api_key: str, port: int = 80):
        """
        Initialize the Unraid GraphQL client.
        
        Args:
            server_ip: IP address of the Unraid server
            api_key: API key for authentication
            port: Port number (default: 80)
        """
        self.server_ip = server_ip
        self.api_key = api_key
        self.port = port
        self.base_url = f"http://{server_ip}:{port}"
        self.endpoint = f"{self.base_url}/graphql"
        self.redirect_url = None
        
        # Initial set of headers
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "Accept": "application/json"
        }
        
        # Discover the redirect URL if any
        self._discover_redirect_url()
    
    def _discover_redirect_url(self):
        """Discover and store the redirect URL if the server uses one."""
        try:
            response = requests.get(self.endpoint, allow_redirects=False)
            
            if response.status_code == 302 and 'Location' in response.headers:
                self.redirect_url = response.headers['Location']
                print(f"Discovered redirect URL: {self.redirect_url}")
                
                # Update our endpoint to use the redirect URL
                self.endpoint = self.redirect_url
                
                # If the redirect is to a domain name, extract it for the Origin header
                domain_match = re.search(r'https?://([^/]+)', self.redirect_url)
                if domain_match:
                    domain = domain_match.group(1)
                    self.headers["Host"] = domain
                    self.headers["Origin"] = f"https://{domain}"
                    self.headers["Referer"] = f"https://{domain}/dashboard"
        
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not discover redirect URL: {e}")
    
    def execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the Unraid API.
        
        Args:
            query: The GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            The JSON response from the API
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        try:
            # Create a session that will persist across requests
            session = requests.Session()
            
            # Always follow redirects
            session.max_redirects = 5
            
            # Add all headers to the session
            for key, value in self.headers.items():
                session.headers[key] = value
            
            # Make the GraphQL request
            response = session.post(
                self.endpoint,
                json=payload,
                verify=False,  # Skip SSL verification for self-signed certificates
                timeout=15
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error making the request: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return {"error": str(e)}
    
    def get_server_info(self) -> Dict[str, Any]:
        """Get detailed server information including CPU, memory, and system details."""
        query = """
        query {
            info {
                os {
                    platform
                    distro
                    release
                    kernel
                    arch
                    hostname
                    uptime
                }
                cpu {
                    id
                    manufacturer
                    brand
                    vendor
                    family
                    model
                    stepping
                    revision
                    voltage
                    speed
                    speedmin
                    speedmax
                    cores
                    threads
                    processors
                    socket
                    cache
                    flags
                }
                memory {
                    id
                    layout {
                        size
                        bank
                        type
                        clockSpeed
                        manufacturer
                    }
                }
                baseboard {
                    manufacturer
                    model
                    version
                    serial
                }
                system {
                    manufacturer
                    model
                    version
                    serial
                }
                versions {
                    id
                    core {
                        unraid
                        api
                        kernel
                    }
                    packages {
                        openssl
                        node
                        npm
                        pm2
                        git
                        nginx
                        php
                        docker
                    }
                }
            }
        }
        """
        return self.execute_query(query)

    def get_memory_utilization(self) -> Dict[str, Any]:
        """Get memory layout and calculate total memory information."""
        query = """
        query {
            info {
                memory {
                    layout {
                        size
                        bank
                        type
                        clockSpeed
                        manufacturer
                    }
                }
            }
        }
        """
        result = self.execute_query(query)

        # Calculate total memory from layout
        if 'data' in result and 'info' in result['data'] and 'memory' in result['data']['info']:
            layout = result['data']['info']['memory'].get('layout', [])
            total_memory = sum(module.get('size', 0) for module in layout)

            return {
                'total': total_memory,
                'layout': layout,
                'modules_count': len(layout)
            }

        return result

    def get_cpu_utilization(self) -> Dict[str, Any]:
        """Get CPU information and specifications."""
        query = """
        query {
            info {
                cpu {
                    manufacturer
                    brand
                    cores
                    threads
                    speed
                    speedmax
                    speedmin
                    socket
                    cache
                }
            }
        }
        """
        result = self.execute_query(query)

        # Extract CPU info for easier access
        if 'data' in result and 'info' in result['data'] and 'cpu' in result['data']['info']:
            cpu_info = result['data']['info']['cpu']
            return {
                'manufacturer': cpu_info.get('manufacturer'),
                'brand': cpu_info.get('brand'),
                'cores': cpu_info.get('cores'),
                'threads': cpu_info.get('threads'),
                'speed': cpu_info.get('speed'),
                'speedmax': cpu_info.get('speedmax'),
                'speedmin': cpu_info.get('speedmin'),
                'socket': cpu_info.get('socket'),
                'cache': cpu_info.get('cache', {})
            }

        return result

    def get_array_status(self) -> Dict[str, Any]:
        """Get detailed array status including all disk types."""
        query = """
        query {
            array {
                state
                capacity {
                    kilobytes {
                        free
                        used
                        total
                    }
                    disks {
                        free
                        used
                        total
                    }
                }
                boot {
                    id
                    name
                    device
                    size
                    temp
                    rotational
                    fsSize
                    fsFree
                    fsUsed
                    type
                }
                parities {
                    id
                    name
                    device
                    size
                    temp
                    status
                    rotational
                    isSpinning
                    type
                }
                disks {
                    id
                    name
                    device
                    size
                    status
                    type
                    temp
                    rotational
                    isSpinning
                    fsSize
                    fsFree
                    fsUsed
                    numReads
                    numWrites
                    numErrors
                }
                caches {
                    id
                    name
                    device
                    size
                    temp
                    status
                    rotational
                    isSpinning
                    fsSize
                    fsFree
                    fsUsed
                    type
                }
            }
        }
        """
        return self.execute_query(query)
    
    def get_docker_containers(self) -> Dict[str, Any]:
        """Get detailed information about Docker containers."""
        query = """
        query {
            docker {
                containers {
                    id
                    names
                    image
                    state
                    status
                    autoStart
                    ports {
                        ip
                        privatePort
                        publicPort
                        type
                    }
                }
            }
        }
        """
        return self.execute_query(query)
        
    def start_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Start a Docker container.

        Args:
            container_id: The ID of the container to start
        """
        mutation = """
        mutation {
            docker {
                start(id: "%s") {
                    id
                    state
                    status
                }
            }
        }
        """ % container_id
        return self.execute_query(mutation)

    def stop_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Stop a Docker container.

        Args:
            container_id: The ID of the container to stop
        """
        mutation = """
        mutation {
            docker {
                stop(id: "%s") {
                    id
                    state
                    status
                }
            }
        }
        """ % container_id
        return self.execute_query(mutation)

    def restart_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Restart a Docker container.

        Args:
            container_id: The ID of the container to restart

        Note:
            This performs a stop followed by start operation.
        """
        # Stop the container first
        stop_result = self.stop_docker_container(container_id)
        if "errors" in stop_result:
            return stop_result

        # Then start it
        return self.start_docker_container(container_id)
    
    def get_disks_info(self) -> Dict[str, Any]:
        """Get detailed information about all disks."""
        query = """
        query {
            disks {
                id
                device
                name
                type
                size
                vendor
                firmwareRevision
                serialNum
                interfaceType
                smartStatus
                temperature
                partitions {
                    name
                    fsType
                    size
                }
                isSpinning
            }
        }
        """
        return self.execute_query(query)

    def get_disk_sleep_status(self, include_array_disks: bool = True, include_unassigned_disks: bool = True) -> Dict[str, Any]:
        """
        Get disk sleep status for all disks.

        Args:
            include_array_disks: Include disks that are part of the array (data, parity, cache)
            include_unassigned_disks: Include unassigned/standalone disks

        Returns:
            Dictionary with spinning and sleeping disk information

        Note:
            Querying disk information may wake up sleeping disks. Use with caution
            if you want to preserve disk sleep states.
        """
        result = {
            'spinning': [],
            'sleeping': [],
            'unknown': [],
            'summary': {
                'total_disks': 0,
                'spinning_count': 0,
                'sleeping_count': 0,
                'unknown_count': 0
            }
        }

        # Get array disks if requested
        if include_array_disks:
            array_result = self.get_array_status()
            if 'data' in array_result and 'array' in array_result['data']:
                array = array_result['data']['array']

                # Process all disk types in the array
                for disk_type in ['disks', 'parities', 'caches']:
                    if disk_type in array:
                        for disk in array[disk_type]:
                            disk_info = {
                                'name': disk.get('name', 'Unknown'),
                                'device': disk.get('device', 'Unknown'),
                                'type': disk_type.rstrip('s').upper(),  # 'disks' -> 'DISK', etc.
                                'temperature': disk.get('temp'),
                                'size': disk.get('size'),
                                'location': 'array'
                            }

                            is_spinning = disk.get('isSpinning')
                            if is_spinning is True:
                                result['spinning'].append(disk_info)
                                result['summary']['spinning_count'] += 1
                            elif is_spinning is False:
                                result['sleeping'].append(disk_info)
                                result['summary']['sleeping_count'] += 1
                            else:
                                result['unknown'].append(disk_info)
                                result['summary']['unknown_count'] += 1

                            result['summary']['total_disks'] += 1

        # Get unassigned disks if requested
        if include_unassigned_disks:
            disks_result = self.get_disks_info()
            if 'data' in disks_result and 'disks' in disks_result['data']:
                for disk in disks_result['data']['disks']:
                    # Skip disks that are already counted in array
                    device = disk.get('device', '').replace('/dev/', '')
                    if include_array_disks:
                        # Check if this disk is already in our results
                        already_counted = any(
                            d['device'] == device
                            for disk_list in [result['spinning'], result['sleeping'], result['unknown']]
                            for d in disk_list
                        )
                        if already_counted:
                            continue

                    disk_info = {
                        'name': disk.get('name', 'Unknown'),
                        'device': device,
                        'type': disk.get('type', 'UNKNOWN'),
                        'temperature': disk.get('temperature'),
                        'size': disk.get('size'),
                        'location': 'unassigned'
                    }

                    is_spinning = disk.get('isSpinning')
                    if is_spinning is True:
                        result['spinning'].append(disk_info)
                        result['summary']['spinning_count'] += 1
                    elif is_spinning is False:
                        result['sleeping'].append(disk_info)
                        result['summary']['sleeping_count'] += 1
                    else:
                        result['unknown'].append(disk_info)
                        result['summary']['unknown_count'] += 1

                    result['summary']['total_disks'] += 1

        return result

    def get_network_info(self) -> Dict[str, Any]:
        """Get network interface information."""
        query = """
        query {
            network {
                iface
                ifaceName
                ipv4
                ipv6
                mac
                operstate
                type
                duplex
                speed
                accessUrls {
                    type
                    name
                    ipv4
                    ipv6
                }
            }
        }
        """
        return self.execute_query(query)
        
    def get_detailed_network_info(self) -> Dict[str, Any]:
        """Get detailed network interface information including all devices."""
        query = """
        query {
            info {
                devices {
                    network {
                        id
                        iface
                        ifaceName
                        ipv4
                        ipv6
                        mac
                        internal
                        operstate
                        type
                        duplex
                        mtu
                        speed
                        carrierChanges
                    }
                }
            }
        }
        """
        return self.execute_query(query)
    
    def get_shares(self) -> Dict[str, Any]:
        """Get information about network shares."""
        query = """
        query {
            shares {
                name
                comment
                free
                size
                used
            }
        }
        """
        return self.execute_query(query)
    
    def get_vms(self) -> Dict[str, Any]:
        """Get information about virtual machines."""
        query = """
        query {
            vms {
                domain {
                    uuid
                    name
                    state
                }
            }
        }
        """
        return self.execute_query(query)
    
    def start_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Start a virtual machine.

        Args:
            vm_uuid: The UUID of the VM to start
        """
        mutation = """
        mutation {
            vm {
                start(id: "%s") {
                    uuid
                    name
                    state
                }
            }
        }
        """ % vm_uuid
        return self.execute_query(mutation)

    def stop_vm(self, vm_uuid: str, force: bool = False) -> Dict[str, Any]:
        """
        Stop a virtual machine.

        Args:
            vm_uuid: The UUID of the VM to stop
            force: Force power off if True, otherwise graceful shutdown
        """
        if force:
            mutation = """
            mutation {
                vm {
                    forceStop(id: "%s") {
                        uuid
                        name
                        state
                    }
                }
            }
            """ % vm_uuid
        else:
            mutation = """
            mutation {
                vm {
                    stop(id: "%s") {
                        uuid
                        name
                        state
                    }
                }
            }
            """ % vm_uuid
        return self.execute_query(mutation)

    def pause_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Pause a virtual machine.

        Args:
            vm_uuid: The UUID of the VM to pause
        """
        mutation = """
        mutation {
            vm {
                pause(id: "%s") {
                    uuid
                    name
                    state
                }
            }
        }
        """ % vm_uuid
        return self.execute_query(mutation)

    def resume_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Resume a paused virtual machine.

        Args:
            vm_uuid: The UUID of the VM to resume
        """
        mutation = """
        mutation {
            vm {
                resume(id: "%s") {
                    uuid
                    name
                    state
                }
            }
        }
        """ % vm_uuid
        return self.execute_query(mutation)

    def reboot_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Reboot a virtual machine.

        Args:
            vm_uuid: The UUID of the VM to reboot
        """
        mutation = """
        mutation {
            vm {
                reboot(id: "%s") {
                    uuid
                    name
                    state
                }
            }
        }
        """ % vm_uuid
        return self.execute_query(mutation)

    def reset_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Reset a virtual machine.

        Args:
            vm_uuid: The UUID of the VM to reset
        """
        mutation = """
        mutation {
            vm {
                reset(id: "%s") {
                    uuid
                    name
                    state
                }
            }
        }
        """ % vm_uuid
        return self.execute_query(mutation)
        
    def get_parity_history(self) -> Dict[str, Any]:
        """Get parity check history."""
        query = """
        query {
            parityHistory {
                date
                duration
                speed
                status
                errors
            }
        }
        """
        return self.execute_query(query)
        
    def get_vars(self) -> Dict[str, Any]:
        """Get system variables and settings."""
        query = """
        query {
            vars {
                version
                name
                timeZone
                security
                workgroup
                domain
                sysModel
                useSsl
                port
                portssl
                startArray
                spindownDelay
                shareCount
                shareSmbCount
                shareNfsCount
                shareAfpCount
            }
        }
        """
        return self.execute_query(query)
    
    def run_custom_query(self, query_string: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run a custom GraphQL query."""
        return self.execute_query(query_string, variables)
        
    # System control methods
    
    def reboot_system(self) -> Dict[str, Any]:
        """
        Reboot the Unraid system.

        Note: System reboot/shutdown operations are not currently available
        through the Unraid GraphQL API. These operations may need to be
        performed through the web interface or SSH.
        """
        return {"error": "System reboot operations are not currently supported by the Unraid GraphQL API"}

    def shutdown_system(self) -> Dict[str, Any]:
        """
        Shutdown the Unraid system.

        Note: System reboot/shutdown operations are not currently available
        through the Unraid GraphQL API. These operations may need to be
        performed through the web interface or SSH.
        """
        return {"error": "System shutdown operations are not currently supported by the Unraid GraphQL API"}
    
    # Array control methods
    
    def start_array(self) -> Dict[str, Any]:
        """Start the Unraid array."""
        mutation = """
        mutation {
            array {
                setState(input: { desiredState: START }) {
                    state
                }
            }
        }
        """
        return self.execute_query(mutation)

    def stop_array(self) -> Dict[str, Any]:
        """Stop the Unraid array."""
        mutation = """
        mutation {
            array {
                setState(input: { desiredState: STOP }) {
                    state
                }
            }
        }
        """
        return self.execute_query(mutation)
    
    # Parity control methods
    
    def start_parity_check(self, correct: bool = False) -> Dict[str, Any]:
        """Start a parity check. Set correct=True to correct errors."""
        mutation = """
        mutation {
            parityCheck {
                start(correct: %s) {
                    status
                    progress
                }
            }
        }
        """ % ("true" if correct else "false")
        return self.execute_query(mutation)

    def pause_parity_check(self) -> Dict[str, Any]:
        """Pause a running parity check."""
        mutation = """
        mutation {
            parityCheck {
                pause {
                    status
                    progress
                }
            }
        }
        """
        return self.execute_query(mutation)

    def resume_parity_check(self) -> Dict[str, Any]:
        """Resume a paused parity check."""
        mutation = """
        mutation {
            parityCheck {
                resume {
                    status
                    progress
                }
            }
        }
        """
        return self.execute_query(mutation)

    def cancel_parity_check(self) -> Dict[str, Any]:
        """Cancel a running parity check."""
        mutation = """
        mutation {
            parityCheck {
                cancel {
                    status
                    progress
                }
            }
        }
        """
        return self.execute_query(mutation)
    
    # User management methods
    
    def add_user(self, name: str, password: str, description: str = "") -> Dict[str, Any]:
        """Add a new user to the system."""
        mutation = """
        mutation {
            addUser(input: {
                name: "%s",
                password: "%s",
                description: "%s"
            }) {
                id
                name
                description
                roles
            }
        }
        """ % (name, password, description)
        return self.execute_query(mutation)
    
    def delete_user(self, name: str) -> Dict[str, Any]:
        """Delete a user from the system."""
        mutation = """
        mutation {
            deleteUser(input: {
                name: "%s"
            }) {
                id
                name
            }
        }
        """ % name
        return self.execute_query(mutation)
    
    def get_users(self) -> Dict[str, Any]:
        """Get information about the current user."""
        query = """
        query {
            me {
                id
                name
                description
                roles
                permissions {
                    resource
                    actions
                }
            }
        }
        """
        return self.execute_query(query)
    
    # API key management
    
    def create_api_key(self, name: str, description: str = "", roles: List[str] = None) -> Dict[str, Any]:
        """Create a new API key."""
        roles_str = ""
        if roles:
            roles_str = ", roles: [%s]" % ", ".join(roles)
            
        mutation = """
        mutation {
            createApiKey(input: {
                name: "%s",
                description: "%s"%s
            }) {
                id
                key
                name
                description
                roles
                createdAt
            }
        }
        """ % (name, description, roles_str)
        return self.execute_query(mutation)
    
    def get_api_keys(self) -> Dict[str, Any]:
        """Get all API keys."""
        query = """
        query {
            apiKeys {
                id
                name
                description
                roles
                createdAt
                permissions {
                    resource
                    actions
                }
            }
        }
        """
        return self.execute_query(query)
    
    # Notification management
    
    def create_notification(self, title: str, subject: str, description: str, 
                           importance: str = "INFO", link: str = None) -> Dict[str, Any]:
        """
        Create a new notification.
        
        Args:
            title: The notification title
            subject: The notification subject
            description: The notification description
            importance: Importance level (INFO, WARNING, ALERT)
            link: Optional link
        """
        link_str = ""
        if link:
            link_str = ', link: "%s"' % link
            
        mutation = """
        mutation {
            createNotification(input: {
                title: "%s",
                subject: "%s",
                description: "%s",
                importance: %s%s
            }) {
                id
                title
                subject
                description
                importance
                timestamp
                formattedTimestamp
            }
        }
        """ % (title, subject, description, importance, link_str)
        return self.execute_query(mutation)
    
    def get_notifications(self, notification_type: str = "UNREAD", 
                         importance: str = None, limit: int = 100) -> Dict[str, Any]:
        """
        Get notifications.
        
        Args:
            notification_type: Type of notifications to retrieve (UNREAD or ARCHIVE)
            importance: Optional filter by importance (INFO, WARNING, ALERT)
            limit: Maximum number of notifications to return
        """
        importance_str = ""
        if importance:
            importance_str = ", importance: %s" % importance
            
        query = """
        query {
            notifications {
                list(filter: {
                    type: %s%s,
                    offset: 0,
                    limit: %d
                }) {
                    id
                    title
                    subject
                    description
                    importance
                    link
                    type
                    timestamp
                    formattedTimestamp
                }
                overview {
                    unread {
                        info
                        warning
                        alert
                        total
                    }
                    archive {
                        info
                        warning
                        alert
                        total
                    }
                }
            }
        }
        """ % (notification_type, importance_str, limit)
        return self.execute_query(query)
    
    def archive_notification(self, notification_id: str) -> Dict[str, Any]:
        """Archive a notification."""
        mutation = """
        mutation {
            archiveNotification(id: "%s") {
                id
                title
                type
            }
        }
        """ % notification_id
        return self.execute_query(mutation)
    
    def archive_all_notifications(self, importance: str = None) -> Dict[str, Any]:
        """
        Archive all notifications.
        
        Args:
            importance: Optional filter by importance (INFO, WARNING, ALERT)
        """
        importance_str = ""
        if importance:
            importance_str = "(importance: %s)" % importance
            
        mutation = """
        mutation {
            archiveAll%s {
                unread {
                    total
                }
                archive {
                    total
                }
            }
        }
        """ % importance_str
        return self.execute_query(mutation)

    # UPS Monitoring

    def get_ups_devices(self) -> Dict[str, Any]:
        """
        Get information about all UPS devices.

        Returns:
            Dictionary containing UPS device information including status, battery, and power data
        """
        query = """
        query {
            upsDevices {
                id
                name
                model
                status
                battery {
                    chargeLevel
                    estimatedRuntime
                    health
                }
                power {
                    inputVoltage
                    outputVoltage
                    loadPercentage
                }
            }
        }
        """
        return self.execute_query(query)

    def get_ups_device_by_id(self, device_id: str) -> Dict[str, Any]:
        """
        Get information about a specific UPS device.

        Args:
            device_id: The ID of the UPS device

        Returns:
            Dictionary containing UPS device information
        """
        query = """
        query {
            upsDeviceById(id: "%s") {
                id
                name
                model
                status
                battery {
                    chargeLevel
                    estimatedRuntime
                    health
                }
                power {
                    inputVoltage
                    outputVoltage
                    loadPercentage
                }
            }
        }
        """ % device_id
        return self.execute_query(query)

    def get_ups_configuration(self) -> Dict[str, Any]:
        """
        Get UPS configuration settings.

        Returns:
            Dictionary containing UPS configuration
        """
        query = """
        query {
            upsConfiguration {
                service
                upsCable
                customUpsCable
                upsType
                device
                overrideUpsCapacity
                batteryLevel
                minutes
                timeout
                killUps
                nisIp
                netServer
                upsName
                modelName
            }
        }
        """
        return self.execute_query(query)

    def get_ups_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of UPS status for monitoring purposes.

        Returns:
            Dictionary with simplified UPS status information suitable for Home Assistant
        """
        result = self.get_ups_devices()

        if 'data' in result and 'upsDevices' in result['data']:
            devices = result['data']['upsDevices']

            if not devices:
                return {
                    'connected': False,
                    'device_count': 0,
                    'message': 'No UPS devices found'
                }

            # For simplicity, return info for the first device
            # In most home setups, there's typically only one UPS
            device = devices[0]
            battery = device.get('battery', {})
            power = device.get('power', {})

            return {
                'connected': True,
                'device_count': len(devices),
                'device_id': device.get('id'),
                'device_name': device.get('name'),
                'model': device.get('model'),
                'status': device.get('status'),
                'battery_level': battery.get('chargeLevel'),
                'estimated_runtime': battery.get('estimatedRuntime'),
                'battery_health': battery.get('health'),
                'input_voltage': power.get('inputVoltage'),
                'output_voltage': power.get('outputVoltage'),
                'load_percentage': power.get('loadPercentage'),
                'on_battery': device.get('status') not in ['ONLINE', 'CHARGING'],
                'battery_low': battery.get('chargeLevel', 100) < 20 if battery.get('chargeLevel') is not None else False
            }

        return {
            'connected': False,
            'device_count': 0,
            'error': 'Failed to retrieve UPS information'
        }

    # ===== VERIFIED SYSTEM MONITORING METHODS =====

    def get_system_uptime(self) -> Dict[str, Any]:
        """
        Get system uptime information.

        Returns:
            Dictionary containing uptime and system information
        """
        query = """
        {
            info {
                os {
                    uptime
                    hostname
                    platform
                    distro
                    release
                    kernel
                    arch
                }
            }
        }
        """

        try:
            result = self.execute_query(query)
            if 'data' in result and 'info' in result['data']:
                os_info = result['data']['info']['os']
                return {
                    'uptime': os_info.get('uptime'),
                    'hostname': os_info.get('hostname'),
                    'platform': os_info.get('platform'),
                    'distro': os_info.get('distro'),
                    'release': os_info.get('release'),
                    'kernel': os_info.get('kernel'),
                    'architecture': os_info.get('arch')
                }
            return result
        except Exception as e:
            print(f"Error getting system uptime: {e}")
            return {'error': str(e)}

    def get_array_usage_summary(self) -> Dict[str, Any]:
        """
        Get overall array usage statistics.

        Returns:
            Dictionary with array usage summary including total, used, and free space
        """
        query = """
        {
            array {
                state
                disks {
                    name
                    device
                    size
                    fsUsed
                    fsFree
                    fsType
                }
                parities {
                    name
                    device
                    size
                }
                caches {
                    name
                    device
                    size
                    fsUsed
                    fsFree
                    fsType
                }
            }
        }
        """

        try:
            result = self.execute_query(query)
            if 'data' in result and 'array' in result['data']:
                array_data = result['data']['array']

                # Calculate totals for data disks
                total_size = 0
                total_used = 0
                total_free = 0

                for disk in array_data.get('disks', []):
                    if disk.get('size'):
                        total_size += disk['size']
                    if disk.get('fsUsed'):
                        total_used += disk['fsUsed']
                    if disk.get('fsFree'):
                        total_free += disk['fsFree']

                # Add cache usage
                cache_size = 0
                cache_used = 0
                cache_free = 0

                for cache in array_data.get('caches', []):
                    if cache.get('size'):
                        cache_size += cache['size']
                    if cache.get('fsUsed'):
                        cache_used += cache['fsUsed']
                    if cache.get('fsFree'):
                        cache_free += cache['fsFree']

                # Calculate percentages
                data_percent_used = (total_used / total_size * 100) if total_size > 0 else 0
                cache_percent_used = (cache_used / cache_size * 100) if cache_size > 0 else 0

                return {
                    'array_state': array_data.get('state'),
                    'data_array': {
                        'total_size': total_size,
                        'used_space': total_used,
                        'free_space': total_free,
                        'percent_used': round(data_percent_used, 2),
                        'disk_count': len(array_data.get('disks', []))
                    },
                    'cache': {
                        'total_size': cache_size,
                        'used_space': cache_used,
                        'free_space': cache_free,
                        'percent_used': round(cache_percent_used, 2),
                        'cache_count': len(array_data.get('caches', []))
                    },
                    'parity_count': len(array_data.get('parities', []))
                }
            return result
        except Exception as e:
            print(f"Error getting array usage summary: {e}")
            return {'error': str(e)}

    def get_disk_health_status(self) -> Dict[str, Any]:
        """
        Get disk health status including temperature and error information.

        Returns:
            Dictionary with disk health information for array disks
        """
        query = """
        {
            array {
                disks {
                    name
                    device
                    size
                    temp
                    status
                    numErrors
                    numReads
                    numWrites
                    rotational
                }
                parities {
                    name
                    device
                    size
                    temp
                    status
                    numErrors
                    numReads
                    numWrites
                    rotational
                }
                caches {
                    name
                    device
                    size
                    temp
                    status
                    numErrors
                    numReads
                    numWrites
                    rotational
                }
            }
        }
        """

        try:
            result = self.execute_query(query)
            if 'data' in result and 'array' in result['data']:
                array_data = result['data']['array']

                all_disks = []

                # Process data disks
                for disk in array_data.get('disks', []):
                    all_disks.append({
                        'name': disk.get('name'),
                        'device': disk.get('device'),
                        'type': 'data',
                        'size': disk.get('size'),
                        'temperature': disk.get('temp'),
                        'status': disk.get('status'),
                        'errors': disk.get('numErrors', 0),
                        'reads': disk.get('numReads', 0),
                        'writes': disk.get('numWrites', 0),
                        'rotational': disk.get('rotational', True),
                        'health_ok': disk.get('status') == 'DISK_OK' and disk.get('numErrors', 0) == 0
                    })

                # Process parity disks
                for disk in array_data.get('parities', []):
                    all_disks.append({
                        'name': disk.get('name'),
                        'device': disk.get('device'),
                        'type': 'parity',
                        'size': disk.get('size'),
                        'temperature': disk.get('temp'),
                        'status': disk.get('status'),
                        'errors': disk.get('numErrors', 0),
                        'reads': disk.get('numReads', 0),
                        'writes': disk.get('numWrites', 0),
                        'rotational': disk.get('rotational', True),
                        'health_ok': disk.get('status') == 'DISK_OK' and disk.get('numErrors', 0) == 0
                    })

                # Process cache disks
                for disk in array_data.get('caches', []):
                    all_disks.append({
                        'name': disk.get('name'),
                        'device': disk.get('device'),
                        'type': 'cache',
                        'size': disk.get('size'),
                        'temperature': disk.get('temp'),
                        'status': disk.get('status'),
                        'errors': disk.get('numErrors', 0),
                        'reads': disk.get('numReads', 0),
                        'writes': disk.get('numWrites', 0),
                        'rotational': disk.get('rotational', True),
                        'health_ok': disk.get('status') == 'DISK_OK' and disk.get('numErrors', 0) == 0
                    })

                # Calculate summary
                healthy_disks = [d for d in all_disks if d['health_ok']]
                disks_with_errors = [d for d in all_disks if d['errors'] > 0]
                disks_with_temp = [d for d in all_disks if d['temperature'] is not None]

                avg_temp = sum(d['temperature'] for d in disks_with_temp) / len(disks_with_temp) if disks_with_temp else None
                max_temp = max(d['temperature'] for d in disks_with_temp) if disks_with_temp else None

                return {
                    'summary': {
                        'total_disks': len(all_disks),
                        'healthy_disks': len(healthy_disks),
                        'disks_with_errors': len(disks_with_errors),
                        'average_temperature': round(avg_temp, 1) if avg_temp else None,
                        'max_temperature': max_temp,
                        'overall_health': 'GOOD' if len(healthy_disks) == len(all_disks) else 'WARNING'
                    },
                    'disks': all_disks,
                    'errors': disks_with_errors
                }
            return result
        except Exception as e:
            print(f"Error getting disk health status: {e}")
            return {'error': str(e)}

    def get_parity_check_status(self) -> Dict[str, Any]:
        """
        Get parity check status and history.

        Returns:
            Dictionary with current and historical parity check information
        """
        query = """
        {
            parityHistory {
                date
                duration
                speed
                status
                errors
                progress
                correcting
                paused
                running
            }
        }
        """

        try:
            result = self.execute_query(query)
            if 'data' in result and 'parityHistory' in result['data']:
                history = result['data']['parityHistory']

                if not history:
                    return {
                        'current_check': None,
                        'last_check': None,
                        'history_count': 0,
                        'recent_history': []
                    }

                # Find current running check
                current_check = None
                for check in history:
                    if check.get('running'):
                        current_check = check
                        break

                # Get most recent completed check
                completed_checks = [c for c in history if c.get('status') == 'COMPLETED']
                last_check = completed_checks[0] if completed_checks else None

                # Get recent history (last 10 checks)
                recent_history = history[:10]

                return {
                    'current_check': current_check,
                    'last_check': last_check,
                    'history_count': len(history),
                    'recent_history': recent_history,
                    'summary': {
                        'is_running': current_check is not None,
                        'is_paused': current_check.get('paused', False) if current_check else False,
                        'progress': current_check.get('progress') if current_check else None,
                        'last_status': last_check.get('status') if last_check else None,
                        'last_errors': last_check.get('errors') if last_check else None,
                        'last_duration': last_check.get('duration') if last_check else None
                    }
                }
            return result
        except Exception as e:
            print(f"Error getting parity check status: {e}")
            return {'error': str(e)}

    # ===== VERIFIED CONTROL OPERATIONS =====

    def start_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Start a Docker container.

        Args:
            container_id: The ID of the container to start

        Returns:
            Dictionary with operation result
        """
        mutation = """
        mutation {
            docker {
                start(id: "%s") {
                    id
                    names
                    state
                    status
                }
            }
        }
        """ % container_id

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error starting Docker container: {e}")
            return {'error': str(e)}

    def stop_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Stop a Docker container.

        Args:
            container_id: The ID of the container to stop

        Returns:
            Dictionary with operation result
        """
        mutation = """
        mutation {
            docker {
                stop(id: "%s") {
                    id
                    names
                    state
                    status
                }
            }
        }
        """ % container_id

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error stopping Docker container: {e}")
            return {'error': str(e)}

    def start_vm(self, vm_id: str) -> Dict[str, Any]:
        """
        Start a virtual machine.

        Args:
            vm_id: The ID of the VM to start

        Returns:
            Dictionary with operation result
        """
        mutation = """
        mutation {
            vm {
                start(id: "%s") {
                    id
                    name
                    state
                }
            }
        }
        """ % vm_id

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error starting VM: {e}")
            return {'error': str(e)}

    def stop_vm(self, vm_id: str, force: bool = False) -> Dict[str, Any]:
        """
        Stop a virtual machine.

        Args:
            vm_id: The ID of the VM to stop
            force: Whether to force stop the VM

        Returns:
            Dictionary with operation result
        """
        operation = "forceStop" if force else "stop"
        mutation = """
        mutation {
            vm {
                %s(id: "%s") {
                    id
                    name
                    state
                }
            }
        }
        """ % (operation, vm_id)

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error stopping VM: {e}")
            return {'error': str(e)}

    def pause_vm(self, vm_id: str) -> Dict[str, Any]:
        """
        Pause a virtual machine.

        Args:
            vm_id: The ID of the VM to pause

        Returns:
            Dictionary with operation result
        """
        mutation = """
        mutation {
            vm {
                pause(id: "%s") {
                    id
                    name
                    state
                }
            }
        }
        """ % vm_id

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error pausing VM: {e}")
            return {'error': str(e)}

    def resume_vm(self, vm_id: str) -> Dict[str, Any]:
        """
        Resume a virtual machine.

        Args:
            vm_id: The ID of the VM to resume

        Returns:
            Dictionary with operation result
        """
        mutation = """
        mutation {
            vm {
                resume(id: "%s") {
                    id
                    name
                    state
                }
            }
        }
        """ % vm_id

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error resuming VM: {e}")
            return {'error': str(e)}

    def reboot_vm(self, vm_id: str) -> Dict[str, Any]:
        """
        Reboot a virtual machine.

        Args:
            vm_id: The ID of the VM to reboot

        Returns:
            Dictionary with operation result
        """
        mutation = """
        mutation {
            vm {
                reboot(id: "%s") {
                    id
                    name
                    state
                }
            }
        }
        """ % vm_id

        try:
            return self.execute_query(mutation)
        except Exception as e:
            print(f"Error rebooting VM: {e}")
            return {'error': str(e)}

    # Remote access configuration
    
    def setup_remote_access(self, access_type: str, forward_type: str = None, 
                           port: int = None) -> Dict[str, Any]:
        """
        Configure remote access to the server.
        
        Args:
            access_type: Access type (DYNAMIC, ALWAYS, DISABLED)
            forward_type: Forward type (UPNP, STATIC)
            port: Port number
        """
        forward_type_str = ""
        port_str = ""
        
        if forward_type:
            forward_type_str = ', forwardType: %s' % forward_type
        
        if port:
            port_str = ', port: %d' % port
            
        mutation = """
        mutation {
            setupRemoteAccess(input: {
                accessType: %s%s%s
            })
        }
        """ % (access_type, forward_type_str, port_str)
        return self.execute_query(mutation)
    
    def pretty_print_response(self, data: Dict[str, Any]) -> None:
        """Print the API response in a readable format."""
        print(json.dumps(data, indent=2))

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Unraid GraphQL API Client")
    parser.add_argument("--ip", default="192.168.20.21", help="Unraid server IP address (default: 192.168.20.21)")
    parser.add_argument("--key", default="d19cc212ffe54c88397398237f87791e75e8161e9d78c41509910ceb8f07e688", 
                        help="API key")
    parser.add_argument("--port", type=int, default=80, help="Port (default: 80)")
    parser.add_argument("--query", 
                        choices=["info", "array", "docker", "disks", "network", "shares", "vms", 
                                "parity", "vars", "users", "apikeys", "notifications", "all"], 
                        default="info", help="Query type to execute")
    parser.add_argument("--direct", action="store_true", 
                        help="Use direct IP connection without checking for redirects")
    parser.add_argument("--custom", type=str, help="Run a custom GraphQL query from a string")
    
    # System control arguments
    control_group = parser.add_argument_group("System Control")
    control_group.add_argument("--reboot", action="store_true", help="Reboot the Unraid system")
    control_group.add_argument("--shutdown", action="store_true", help="Shutdown the Unraid system")
    
    # Array control arguments
    array_group = parser.add_argument_group("Array Control")
    array_group.add_argument("--start-array", action="store_true", help="Start the Unraid array")
    array_group.add_argument("--stop-array", action="store_true", help="Stop the Unraid array")
    
    # Parity control arguments
    parity_group = parser.add_argument_group("Parity Control")
    parity_group.add_argument("--start-parity", action="store_true", help="Start a parity check")
    parity_group.add_argument("--correct-parity", action="store_true", 
                             help="Start a parity check with correction")
    parity_group.add_argument("--pause-parity", action="store_true", help="Pause a running parity check")
    parity_group.add_argument("--resume-parity", action="store_true", help="Resume a paused parity check")
    parity_group.add_argument("--cancel-parity", action="store_true", help="Cancel a running parity check")
    
    # User management arguments
    user_group = parser.add_argument_group("User Management")
    user_group.add_argument("--add-user", action="store_true", help="Add a new user")
    user_group.add_argument("--username", type=str, help="Username for user operations")
    user_group.add_argument("--password", type=str, help="Password for user operations")
    user_group.add_argument("--description", type=str, help="Description for user or API key")
    user_group.add_argument("--delete-user", action="store_true", help="Delete a user")
    
    # API key management
    apikey_group = parser.add_argument_group("API Key Management")
    apikey_group.add_argument("--create-apikey", action="store_true", help="Create a new API key")
    apikey_group.add_argument("--apikey-name", type=str, help="Name for the API key")
    apikey_group.add_argument("--apikey-roles", type=str, help="Comma-separated list of roles (admin,guest,connect)")
    
    # Notification management
    notification_group = parser.add_argument_group("Notification Management")
    notification_group.add_argument("--create-notification", action="store_true", help="Create a notification")
    notification_group.add_argument("--title", type=str, help="Title for notification")
    notification_group.add_argument("--subject", type=str, help="Subject for notification")
    notification_group.add_argument("--message", type=str, help="Message content for notification")
    notification_group.add_argument("--importance", choices=["INFO", "WARNING", "ALERT"], 
                                  default="INFO", help="Importance level of notification")
    notification_group.add_argument("--link", type=str, help="Link for notification")
    notification_group.add_argument("--archive-notification", type=str, help="ID of notification to archive")
    notification_group.add_argument("--archive-all", action="store_true", help="Archive all notifications")
    
    # Remote access configuration
    remote_group = parser.add_argument_group("Remote Access")
    remote_group.add_argument("--setup-remote", action="store_true", help="Configure remote access")
    remote_group.add_argument("--access-type", choices=["DYNAMIC", "ALWAYS", "DISABLED"], 
                             help="Remote access type")
    remote_group.add_argument("--forward-type", choices=["UPNP", "STATIC"], 
                             help="Port forwarding type")
    remote_group.add_argument("--remote-port", type=int, help="Port for remote access")
    
    # Docker container control
    docker_group = parser.add_argument_group("Docker Container Control")
    docker_group.add_argument("--start-container", type=str, help="ID of Docker container to start")
    docker_group.add_argument("--stop-container", type=str, help="ID of Docker container to stop")
    docker_group.add_argument("--restart-container", type=str, 
                            help="ID of Docker container to restart")
    
    # VM control
    vm_group = parser.add_argument_group("Virtual Machine Control")
    vm_group.add_argument("--start-vm", type=str, help="UUID of VM to start")
    vm_group.add_argument("--stop-vm", type=str, help="UUID of VM to stop")
    vm_group.add_argument("--force-stop-vm", action="store_true", 
                         help="Force power off VM instead of graceful shutdown")
    vm_group.add_argument("--pause-vm", type=str, help="UUID of VM to pause")
    vm_group.add_argument("--resume-vm", type=str, help="UUID of VM to resume")
    
    args = parser.parse_args()
    
    # Create the client
    client = UnraidGraphQLClient(args.ip, args.key, args.port)
    
    # If direct mode is enabled, force using the direct IP
    if args.direct:
        client.endpoint = f"http://{args.ip}:{args.port}/graphql"
        client.redirect_url = None
    
    try:
        # Handle control operations first
        if args.reboot:
            print("\n=== REBOOTING SYSTEM ===")
            response = client.reboot_system()
            client.pretty_print_response(response)
            return
            
        if args.shutdown:
            print("\n=== SHUTTING DOWN SYSTEM ===")
            response = client.shutdown_system()
            client.pretty_print_response(response)
            return
            
        if args.start_array:
            print("\n=== STARTING ARRAY ===")
            response = client.start_array()
            client.pretty_print_response(response)
            return
            
        if args.stop_array:
            print("\n=== STOPPING ARRAY ===")
            response = client.stop_array()
            client.pretty_print_response(response)
            return
            
        if args.start_parity:
            print("\n=== STARTING PARITY CHECK ===")
            response = client.start_parity_check(False)
            client.pretty_print_response(response)
            return
            
        if args.correct_parity:
            print("\n=== STARTING PARITY CHECK WITH CORRECTION ===")
            response = client.start_parity_check(True)
            client.pretty_print_response(response)
            return
            
        if args.pause_parity:
            print("\n=== PAUSING PARITY CHECK ===")
            response = client.pause_parity_check()
            client.pretty_print_response(response)
            return
            
        if args.resume_parity:
            print("\n=== RESUMING PARITY CHECK ===")
            response = client.resume_parity_check()
            client.pretty_print_response(response)
            return
            
        if args.cancel_parity:
            print("\n=== CANCELLING PARITY CHECK ===")
            response = client.cancel_parity_check()
            client.pretty_print_response(response)
            return
            
        # User management
        if args.add_user:
            if not args.username or not args.password:
                print("Error: Username and password are required for adding a user")
                return
                
            print(f"\n=== ADDING USER: {args.username} ===")
            response = client.add_user(args.username, args.password, args.description or "")
            client.pretty_print_response(response)
            return
            
        if args.delete_user:
            if not args.username:
                print("Error: Username is required for deleting a user")
                return
                
            print(f"\n=== DELETING USER: {args.username} ===")
            response = client.delete_user(args.username)
            client.pretty_print_response(response)
            return
            
        # API key management
        if args.create_apikey:
            if not args.apikey_name:
                print("Error: API key name is required")
                return
                
            roles = None
            if args.apikey_roles:
                roles = [role.strip() for role in args.apikey_roles.split(",")]
                
            print(f"\n=== CREATING API KEY: {args.apikey_name} ===")
            response = client.create_api_key(args.apikey_name, args.description or "", roles)
            client.pretty_print_response(response)
            return
            
        # Notification management
        if args.create_notification:
            if not args.title or not args.subject or not args.message:
                print("Error: Title, subject, and message are required for creating a notification")
                return
                
            print(f"\n=== CREATING NOTIFICATION: {args.title} ===")
            response = client.create_notification(args.title, args.subject, args.message, 
                                              args.importance, args.link)
            client.pretty_print_response(response)
            return
            
        if args.archive_notification:
            print(f"\n=== ARCHIVING NOTIFICATION: {args.archive_notification} ===")
            response = client.archive_notification(args.archive_notification)
            client.pretty_print_response(response)
            return
            
        if args.archive_all:
            print("\n=== ARCHIVING ALL NOTIFICATIONS ===")
            response = client.archive_all_notifications(args.importance if args.importance != "INFO" else None)
            client.pretty_print_response(response)
            return
            
        # Remote access configuration
        if args.setup_remote:
            if not args.access_type:
                print("Error: Access type is required for setting up remote access")
                return
                
            print(f"\n=== SETTING UP REMOTE ACCESS: {args.access_type} ===")
            response = client.setup_remote_access(args.access_type, args.forward_type, args.remote_port)
            client.pretty_print_response(response)
            return
            
        # Docker container control
        if args.start_container:
            print(f"\n=== STARTING DOCKER CONTAINER: {args.start_container} ===")
            response = client.start_docker_container(args.start_container)
            client.pretty_print_response(response)
            return
            
        if args.stop_container:
            print(f"\n=== STOPPING DOCKER CONTAINER: {args.stop_container} ===")
            response = client.stop_docker_container(args.stop_container)
            client.pretty_print_response(response)
            return
            
        if args.restart_container:
            print(f"\n=== RESTARTING DOCKER CONTAINER: {args.restart_container} ===")
            response = client.restart_docker_container(args.restart_container)
            client.pretty_print_response(response)
            return
            
        # VM control
        if args.start_vm:
            print(f"\n=== STARTING VM: {args.start_vm} ===")
            response = client.start_vm(args.start_vm)
            client.pretty_print_response(response)
            return
            
        if args.stop_vm:
            print(f"\n=== STOPPING VM: {args.stop_vm} ===")
            response = client.stop_vm(args.stop_vm, args.force_stop_vm)
            client.pretty_print_response(response)
            return
            
        if args.pause_vm:
            print(f"\n=== PAUSING VM: {args.pause_vm} ===")
            response = client.pause_vm(args.pause_vm)
            client.pretty_print_response(response)
            return
            
        if args.resume_vm:
            print(f"\n=== RESUMING VM: {args.resume_vm} ===")
            response = client.resume_vm(args.resume_vm)
            client.pretty_print_response(response)
            return
        
        # Handle custom query if provided
        if args.custom:
            print("\n=== CUSTOM QUERY RESULT ===")
            response = client.run_custom_query(args.custom)
            client.pretty_print_response(response)
            return
            
        # Execute the requested queries
        if args.query == "info" or args.query == "all":
            print("\n=== SERVER INFORMATION ===")
            response = client.get_server_info()
            client.pretty_print_response(response)
            
        if args.query == "array" or args.query == "all":
            print("\n=== ARRAY STATUS ===")
            response = client.get_array_status()
            client.pretty_print_response(response)
            
        if args.query == "docker" or args.query == "all":
            print("\n=== DOCKER CONTAINERS ===")
            response = client.get_docker_containers()
            client.pretty_print_response(response)
            
        if args.query == "disks" or args.query == "all":
            print("\n=== DISK INFORMATION ===")
            response = client.get_disks_info()
            client.pretty_print_response(response)
            
        if args.query == "network" or args.query == "all":
            print("\n=== NETWORK INFORMATION ===")
            response = client.get_network_info()
            client.pretty_print_response(response)
            
            print("\n=== DETAILED NETWORK INTERFACES ===")
            detailed_response = client.get_detailed_network_info()
            client.pretty_print_response(detailed_response)
            
        if args.query == "shares" or args.query == "all":
            print("\n=== SHARES INFORMATION ===")
            response = client.get_shares()
            client.pretty_print_response(response)
            
        if args.query == "vms" or args.query == "all":
            print("\n=== VIRTUAL MACHINES ===")
            response = client.get_vms()
            client.pretty_print_response(response)
        
        if args.query == "parity" or args.query == "all":
            print("\n=== PARITY HISTORY ===")
            response = client.get_parity_history()
            client.pretty_print_response(response)
            
        if args.query == "vars" or args.query == "all":
            print("\n=== SYSTEM VARIABLES ===")
            response = client.get_vars()
            client.pretty_print_response(response)
            
        if args.query == "users" or args.query == "all":
            print("\n=== CURRENT USER ===")
            response = client.get_users()
            client.pretty_print_response(response)
            
        if args.query == "apikeys" or args.query == "all":
            print("\n=== API KEYS ===")
            response = client.get_api_keys()
            client.pretty_print_response(response)
            
        if args.query == "notifications" or args.query == "all":
            print("\n=== NOTIFICATIONS ===")
            response = client.get_notifications()
            client.pretty_print_response(response)
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to the API: {e}")
    except json.JSONDecodeError:
        print("Error decoding the API response")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()