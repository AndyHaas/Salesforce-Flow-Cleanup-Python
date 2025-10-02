#!/usr/bin/env python3
"""
Salesforce Flow Version Cleanup Script

This script helps clean up old Flow versions in Salesforce using the Tooling API.
It includes browser-based OAuth authentication and safety features for production instances.

Requirements:
- Python 3.7+
- requests library
- webbrowser library (built-in)
- json library (built-in)
- urllib.parse library (built-in)
"""

import requests
import webbrowser
import json
import urllib.parse
import sys
import base64
import hashlib
import secrets
import threading
import socket
import time
import os
import re
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Dict, Optional

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/callback'):
            # Parse the query parameters
            query_params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            
            if 'code' in query_params:
                self.server.auth_code = query_params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'''
                <html>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
                ''')
            elif 'error' in query_params:
                error = query_params['error'][0]
                error_desc = query_params.get('error_description', ['Unknown error'])[0]
                self.server.auth_error = f"{error}: {error_desc}"
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f'''
                <html>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {error}</p>
                    <p>Description: {error_desc}</p>
                </body>
                </html>
                '''.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

class SalesforceFlowCleanup:
    def __init__(self):
        self.instance_url = None
        self.access_token = None
        self.api_version = "v60.0"
        self.log_file = None
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def setup_logging(self):
        """Setup logging to file with masked sensitive information"""
        log_filename = f"flow_cleanup_{self.session_id}.log"
        self.log_file = log_filename
        
        # Create initial log entry
        with open(log_filename, 'w') as f:
            f.write(f"=== Salesforce Flow Cleanup Log ===\n")
            f.write(f"Session ID: {self.session_id}\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Instance: {self.instance_url}\n")
            f.write("=" * 50 + "\n\n")
        
        print(f"📝 Logging to: {log_filename}")
    
    def log_message(self, message: str, mask_sensitive: bool = True):
        """Log message to file, optionally masking sensitive information"""
        if not self.log_file:
            return
            
        # Mask sensitive information
        if mask_sensitive:
            message = self.mask_sensitive_data(message)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
    
    def mask_sensitive_data(self, text: str) -> str:
        """Mask sensitive information in log messages"""
        # Mask client IDs (Consumer Keys)
        text = re.sub(r'client_id["\']?\s*[:=]\s*["\']?([A-Za-z0-9]{15,})', 
                     r'client_id="***MASKED***"', text)
        
        # Mask client secrets
        text = re.sub(r'client_secret["\']?\s*[:=]\s*["\']?([A-Za-z0-9]{15,})', 
                     r'client_secret="***MASKED***"', text)
        
        # Mask access tokens
        text = re.sub(r'access_token["\']?\s*[:=]\s*["\']?([A-Za-z0-9]{50,})', 
                     r'access_token="***MASKED***"', text)
        
        # Mask authorization codes
        text = re.sub(r'code["\']?\s*[:=]\s*["\']?([A-Za-z0-9]{20,})', 
                     r'code="***MASKED***"', text)
        
        return text
    
    def save_deletion_list(self, flows_to_delete: List[Dict]) -> str:
        """Save the list of flows to be deleted to a file"""
        if not flows_to_delete:
            return None
        
        filename = f"flows_to_delete_{self.session_id}.json"
        
        # Prepare data for saving (remove sensitive info)
        save_data = {
            "session_id": self.session_id,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "instance_url": self.instance_url,
            "total_flows": len(flows_to_delete),
            "flows": []
        }
        
        for flow in flows_to_delete:
            flow_data = {
                "id": flow['Id'],
                "name": flow['Definition']['DeveloperName'],
                "label": flow['Definition']['MasterLabel'],
                "version": flow['VersionNumber'],
                "status": flow['Status'],
                "definition_id": flow['DefinitionId']
            }
            save_data["flows"].append(flow_data)
        
        with open(filename, 'w') as f:
            json.dump(save_data, f, indent=2)
        
        return filename
        
    def load_config_file(self, config_file: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Validate required fields
            required_fields = ['orgs']
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate org configurations
            for i, org in enumerate(config['orgs']):
                org_required = ['instance', 'client_id']
                for field in org_required:
                    if field not in org:
                        raise ValueError(f"Org {i+1} missing required field: {field}")
                
                # Set defaults
                org.setdefault('client_secret', '')
                org.setdefault('cleanup_type', '1')
                org.setdefault('flow_names', [])
                org.setdefault('skip_production_check', False)
                org.setdefault('auto_confirm_production', False)
                org.setdefault('callback_port', 8080)
            
            return config
            
        except FileNotFoundError:
            print(f"❌ Configuration file not found: {config_file}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in configuration file: {e}")
            return None
        except ValueError as e:
            print(f"❌ Configuration validation error: {e}")
            return None
    
    def get_user_input(self) -> Dict[str, str]:
        """Get user input for instance and cleanup options"""
        print("=== Salesforce Flow Version Cleanup Tool ===\n")
        
        # Check if user wants to use config file
        use_config = input("Do you want to use a configuration file? (y/n): ").strip().lower()
        if use_config in ['y', 'yes']:
            config_file = input("Enter path to configuration file: ").strip()
            config = self.load_config_file(config_file)
            if config:
                return {'config': config, 'mode': 'batch'}
            else:
                print("Falling back to interactive mode...")
        
        # Interactive mode
        # Get Salesforce instance
        instance = input("Enter your Salesforce instance URL (e.g., mycompany.my.salesforce.com): ").strip()
        if not instance.startswith('http'):
            instance = f"https://{instance}"
        if not instance.endswith('.my.salesforce.com'):
            instance = f"{instance}.my.salesforce.com"
        
        # Get callback port
        print("\n=== OAuth Callback Configuration ===")
        print("The script will start a local server to receive OAuth callbacks.")
        print("Default port: 8080")
        
        port_input = input("Enter callback port (press Enter for default 8080): ").strip()
        if port_input:
            try:
                port = int(port_input)
                if port < 1024 or port > 65535:
                    print("⚠️  Warning: Port should be between 1024-65535. Using default 8080.")
                    port = 8080
                else:
                    print(f"✅ Using custom port: {port}")
                    print("⚠️  IMPORTANT: Update your Salesforce Connected App callback URL to:")
                    print(f"   http://localhost:{port}/callback")
            except ValueError:
                print("❌ Invalid port number. Using default 8080.")
                port = 8080
        else:
            port = 8080
        
        # Get cleanup scope
        print("\nWhat would you like to clean up?")
        print("1. All old Flow versions (not latest and not active)")
        print("2. Specific Flow versions (you'll provide the Flow names)")
        
        choice = input("Enter your choice (1 or 2): ").strip()
        
        # If specific flows, get the flow names now
        flow_names = []
        if choice == "2":
            print("\n=== Specific Flow Selection ===")
            print("Enter the API names of the Flows you want to clean up.")
            print("(Press Enter on an empty line when done)")
            
            while True:
                flow_name = input("Flow API name: ").strip()
                if not flow_name:
                    break
                flow_names.append(flow_name)
            
            if not flow_names:
                print("❌ No Flow names provided. Exiting.")
                sys.exit(1)
            
            print(f"✅ Selected {len(flow_names)} Flow(s): {', '.join(flow_names)}")
        
        return {
            'instance': instance,
            'cleanup_type': choice,
            'flow_names': flow_names,
            'port': port,
            'mode': 'interactive'
        }
    
    def get_client_credentials(self) -> tuple:
        """Get client ID and secret from user"""
        print("\n=== Connected App Configuration ===")
        print("Enter your Salesforce Connected App credentials:")
        
        client_id = input("Client ID (Consumer Key): ").strip()
        if not client_id:
            print("❌ Client ID is required")
            return None, None
        
        client_secret = input("Client Secret (Consumer Secret) [optional]: ").strip()
        
        return client_id, client_secret
    
    def authenticate(self, instance_url: str, client_id: str = None, client_secret: str = None, silent: bool = False, port: int = 8080) -> bool:
        """Authenticate using OAuth 2.0 Web Server Flow with PKCE and local callback server"""
        if not silent:
            print("\n=== Authentication ===")
            print(f"Starting local callback server on port {port}...")
        
        # Get client credentials
        if not client_id:
            client_id, client_secret = self.get_client_credentials()
            if not client_id:
                self.log_message("Authentication failed: No client ID provided")
                return False
        else:
            if not silent:
                print("Using provided client credentials...")
        
        self.log_message(f"Authentication started for instance: {instance_url}")
        self.log_message(f"Client ID provided: {client_id[:8]}...")
        self.log_message(f"Using callback port: {port}")
        
        # Use configurable port for callback server
        redirect_uri = f"http://localhost:{port}/callback"
        
        # Generate PKCE parameters
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).decode('utf-8').rstrip('=')
        
        # Start local server
        try:
            server = HTTPServer(('localhost', port), CallbackHandler)
            server.auth_code = None
            server.auth_error = None
            
            # Start server in a separate thread
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"❌ Port {port} is already in use. Please close any other applications using this port.")
                print(f"💡 You can try a different port or check what's using port {port} with:")
                print(f"   lsof -i :{port} (macOS/Linux) or netstat -ano | findstr :{port} (Windows)")
                return False
            else:
                print(f"❌ Failed to start server on port {port}: {e}")
                return False
        
        try:
            # Build authorization URL with PKCE
            auth_params = {
                'response_type': 'code',
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'scope': 'api refresh_token',
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256'
            }
            
            auth_url = f"{instance_url}/services/oauth2/authorize?" + urllib.parse.urlencode(auth_params)
            
            print(f"Opening browser to: {auth_url}")
            print("⏳ Waiting for you to complete authentication in your browser...")
            webbrowser.open(auth_url)
            
            # Wait for callback with proper timeout
            timeout = 300  # 5 minutes
            start_time = time.time()
            last_progress_time = 0
            
            while server.auth_code is None and server.auth_error is None:
                time.sleep(0.1)
                elapsed_time = time.time() - start_time
                
                # Check for timeout
                if elapsed_time > timeout:
                    print(f"⏰ Authentication timed out after {timeout} seconds")
                    break
                
                # Show progress every 15 seconds
                if elapsed_time - last_progress_time >= 15:
                    remaining = int(timeout - elapsed_time)
                    print(f"⏳ Still waiting for authentication... ({remaining} seconds remaining)")
                    last_progress_time = elapsed_time
            
            # Check for errors
            if server.auth_error:
                print(f"❌ Authentication failed: {server.auth_error}")
                self.log_message(f"Authentication failed: {server.auth_error}")
                return False
            
            if server.auth_code is None:
                print("❌ Authentication timed out or was cancelled")
                self.log_message("Authentication timed out or was cancelled")
                return False
            
            auth_code = server.auth_code
            print("✅ Authorization code received!")
            
            # Exchange code for token with PKCE
            token_url = f"{instance_url}/services/oauth2/token"
            token_data = {
                'grant_type': 'authorization_code',
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'code': auth_code,
                'code_verifier': code_verifier
            }
            
            # Add client secret if provided
            if client_secret:
                token_data['client_secret'] = client_secret
            
            try:
                response = requests.post(token_url, data=token_data)
                response.raise_for_status()
                
                token_response = response.json()
                self.access_token = token_response['access_token']
                self.instance_url = instance_url
                
                print("✅ Authentication successful!")
                self.log_message("Authentication successful")
                return True
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Token exchange failed: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_detail = e.response.json()
                        print(f"Error details: {error_detail}")
                        self.log_message(f"Token exchange failed: {error_detail}")
                    except:
                        print(f"Response text: {e.response.text}")
                        self.log_message(f"Token exchange failed: {e.response.text}")
                return False
            except KeyError:
                print("❌ Invalid response from Salesforce. Check your Connected App configuration.")
                self.log_message("Invalid response from Salesforce")
                return False
                
        finally:
            # Clean up server
            print("🔄 Shutting down callback server...")
            server.shutdown()
            server.server_close()
    
    
    def check_if_production(self) -> bool:
        """Check if the current instance is production by querying Organization.IsSandbox"""
        print("\n=== Checking Instance Type ===")
        print("🔍 Determining if this is a production or sandbox instance...")
        
        # SOQL query to check if this is a sandbox
        soql_query = "SELECT IsSandbox, Name FROM Organization LIMIT 1"
        
        query_url = f"{self.instance_url}/services/data/{self.api_version}/query"
        params = {'q': soql_query}
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            print("📡 Querying organization information...")
            response = requests.get(query_url, params=params, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            org_info = result.get('records', [{}])[0]
            
            is_sandbox = org_info.get('IsSandbox', True)  # Default to True for safety
            org_name = org_info.get('Name', 'Unknown')
            
            if is_sandbox:
                print(f"✅ Sandbox instance detected: {org_name}")
                print("🧪 Safe to proceed with cleanup operations")
                self.log_message(f"Sandbox instance detected: {org_name}")
                return False
            else:
                print(f"🚨 PRODUCTION instance detected: {org_name}")
                print("⚠️  Extra caution required for production operations")
                self.log_message(f"PRODUCTION instance detected: {org_name}")
                return True
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to check instance type: {e}")
            print("⚠️  Assuming PRODUCTION for safety")
            print("🚨 Extra caution will be required")
            self.log_message(f"Failed to check instance type: {e}")
            return True
    
    def query_old_flow_versions(self) -> List[Dict]:
        """Query for old Flow versions that can be deleted"""
        print("\n=== Querying Old Flow Versions ===")
        print("🔍 Searching for old Flow versions that can be safely deleted...")
        
        # SOQL query to find old Flow versions (single line to avoid URL encoding issues)
        # Note: We'll query all Flow versions and filter out the latest ones programmatically
        soql_query = "SELECT Id, MasterLabel, VersionNumber, Status, DefinitionId, Definition.DeveloperName, Definition.MasterLabel FROM Flow WHERE Status != 'Active' ORDER BY Definition.DeveloperName, VersionNumber DESC"
        
        query_url = f"{self.instance_url}/services/data/{self.api_version}/tooling/query"
        params = {'q': soql_query}
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            print("📡 Sending query to Salesforce...")
            self.log_message("Querying old Flow versions")
            response = requests.get(query_url, params=params, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            all_flows = result.get('records', [])
            
            print(f"✅ Query completed successfully!")
            print(f"📊 Found {len(all_flows)} Flow versions (excluding active ones)")
            
            # Filter out the latest version of each Flow definition
            flows_to_delete = []
            definition_latest_versions = {}
            
            # First pass: find the latest version number for each definition
            for flow in all_flows:
                def_id = flow['DefinitionId']
                version_num = flow['VersionNumber']
                
                if def_id not in definition_latest_versions or version_num > definition_latest_versions[def_id]:
                    definition_latest_versions[def_id] = version_num
            
            # Second pass: collect flows that are not the latest version
            for flow in all_flows:
                def_id = flow['DefinitionId']
                version_num = flow['VersionNumber']
                
                if version_num < definition_latest_versions[def_id]:
                    flows_to_delete.append(flow)
            
            print(f"🔍 After filtering out latest versions: {len(flows_to_delete)} old Flow versions can be deleted")
            self.log_message(f"Found {len(flows_to_delete)} old Flow versions to delete")
            
            if flows_to_delete:
                for i, flow in enumerate(flows_to_delete, 1):
                    print(f"   {i:3d}. {flow['Definition']['DeveloperName']} v{flow['VersionNumber']} ({flow['Status']}) - {flow['Id']}")
            else:
                print("   No old Flow versions found (all versions are the latest).")
            
            return flows_to_delete
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Query failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   Error details: {error_detail}")
                    self.log_message(f"Query failed: {error_detail}")
                except:
                    print(f"   Response text: {e.response.text}")
                    self.log_message(f"Query failed: {e.response.text}")
            return []
    
    def query_specific_flows(self, flow_names: List[str]) -> List[Dict]:
        """Query for specific Flow versions by name"""
        print(f"\n=== Querying Specific Flows: {', '.join(flow_names)} ===")
        print(f"🔍 Searching for old versions of: {', '.join(flow_names)}...")
        
        # Build SOQL query for specific flows (single line to avoid URL encoding issues)
        # Note: We'll query all versions and filter out the latest ones programmatically
        flow_conditions = " OR ".join([f"Definition.DeveloperName = '{name}'" for name in flow_names])
        soql_query = f"SELECT Id, MasterLabel, VersionNumber, Status, DefinitionId, Definition.DeveloperName, Definition.MasterLabel FROM Flow WHERE ({flow_conditions}) AND Status != 'Active' ORDER BY Definition.DeveloperName, VersionNumber DESC"
        
        query_url = f"{self.instance_url}/services/data/{self.api_version}/tooling/query"
        params = {'q': soql_query}
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            print("📡 Sending query to Salesforce...")
            self.log_message(f"Querying specific flows: {', '.join(flow_names)}")
            response = requests.get(query_url, params=params, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            all_flows = result.get('records', [])
            
            print(f"✅ Query completed successfully!")
            print(f"📊 Found {len(all_flows)} Flow versions for specified flows (excluding active ones)")
            
            # Filter out the latest version of each Flow definition
            flows_to_delete = []
            definition_latest_versions = {}
            
            # First pass: find the latest version number for each definition
            for flow in all_flows:
                def_id = flow['DefinitionId']
                version_num = flow['VersionNumber']
                
                if def_id not in definition_latest_versions or version_num > definition_latest_versions[def_id]:
                    definition_latest_versions[def_id] = version_num
            
            # Second pass: collect flows that are not the latest version
            for flow in all_flows:
                def_id = flow['DefinitionId']
                version_num = flow['VersionNumber']
                
                if version_num < definition_latest_versions[def_id]:
                    flows_to_delete.append(flow)
            
            print(f"🔍 After filtering out latest versions: {len(flows_to_delete)} old versions can be deleted")
            self.log_message(f"Found {len(flows_to_delete)} old versions for specified flows")
            
            if flows_to_delete:
                for i, flow in enumerate(flows_to_delete, 1):
                    print(f"   {i:3d}. {flow['Definition']['DeveloperName']} v{flow['VersionNumber']} ({flow['Status']}) - {flow['Id']}")
            else:
                print("   No old versions found for the specified flows (all versions are the latest).")
            
            return flows_to_delete
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Query failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   Error details: {error_detail}")
                    self.log_message(f"Query failed: {error_detail}")
                except:
                    print(f"   Response text: {e.response.text}")
                    self.log_message(f"Query failed: {e.response.text}")
            return []
    
    def bulk_delete_flows(self, flow_ids: List[str]) -> Dict:
        """Delete multiple Flow versions using composite API with batching"""
        print(f"\n=== Deleting {len(flow_ids)} Flow Versions ===")
        print("🗑️  Preparing bulk delete request...")
        
        # Salesforce Composite API limit is 25 operations per request
        batch_size = 25
        total_batches = (len(flow_ids) + batch_size - 1) // batch_size
        
        print(f"📦 Processing {len(flow_ids)} deletions in {total_batches} batch(es) of up to {batch_size} each")
        
        composite_url = f"{self.instance_url}/services/data/{self.api_version}/tooling/composite"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        total_successful = 0
        total_failed = 0
        
        try:
            self.log_message(f"Starting bulk delete of {len(flow_ids)} Flow versions in {total_batches} batches")
            
            # Process in batches
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(flow_ids))
                batch_flow_ids = flow_ids[start_idx:end_idx]
                
                print(f"\n📦 Processing batch {batch_num + 1}/{total_batches} ({len(batch_flow_ids)} items)")
                
                # Build composite request for this batch
                composite_request = {
                    "allOrNone": False,
                    "compositeRequest": []
                }
                
                for i, flow_id in enumerate(batch_flow_ids):
                    composite_request["compositeRequest"].append({
                        "method": "DELETE",
                        "url": f"/services/data/{self.api_version}/tooling/sobjects/Flow/{flow_id}",
                        "referenceId": f"batch{batch_num + 1}_del{i + 1}"
                    })
                
                # Send composite request for this batch
                print(f"📡 Sending batch {batch_num + 1} delete request to Salesforce...")
                response = requests.post(composite_url, json=composite_request, headers=headers)
                response.raise_for_status()
                
                result = response.json()
                print(f"✅ Batch {batch_num + 1} delete request completed!")
                
                # Process results for this batch
                batch_successful = 0
                batch_failed = 0
                
                print(f"\n📋 Batch {batch_num + 1} Results:")
                for sub_response in result.get('compositeResponse', []):
                    ref_id = sub_response.get('referenceId', 'unknown')
                    status_code = sub_response.get('httpStatusCode', 0)
                    
                    if status_code == 204:  # Success
                        batch_successful += 1
                        print(f"   ✅ {ref_id}: Successfully deleted")
                    else:
                        batch_failed += 1
                        error_body = sub_response.get('body', [])
                        print(f"   ❌ {ref_id}: Failed (Status: {status_code})")
                        if error_body:
                            print(f"      Error: {error_body}")
                
                total_successful += batch_successful
                total_failed += batch_failed
                
                print(f"📊 Batch {batch_num + 1} Summary: {batch_successful} successful, {batch_failed} failed")
            
            print(f"\n📊 Overall Summary: {total_successful} successful, {total_failed} failed")
            self.log_message(f"Delete completed: {total_successful} successful, {total_failed} failed")
            
            if total_successful > 0:
                print("🎉 Cleanup completed successfully!")
            
            return {"total_successful": total_successful, "total_failed": total_failed}
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Bulk delete failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   Error details: {error_detail}")
                    self.log_message(f"Bulk delete failed: {error_detail}")
                except:
                    print(f"   Response text: {e.response.text}")
                    self.log_message(f"Bulk delete failed: {e.response.text}")
            return {}
    
    def run_cleanup(self, user_input: Dict):
        """Main cleanup execution"""
        print("\n🚀 Starting Flow cleanup process...")
        self.log_message("Starting Flow cleanup process")
        flows_to_delete = []
        
        if user_input['cleanup_type'] == '1':
            # All old Flow versions
            print("📋 Option selected: Clean up all old Flow versions")
            flows_to_delete = self.query_old_flow_versions()
        elif user_input['cleanup_type'] == '2':
            # Specific Flow versions
            print("📋 Option selected: Clean up specific Flow versions")
            flow_names = user_input.get('flow_names', [])
            print(f"🎯 Looking for old versions of: {', '.join(flow_names)}")
            flows_to_delete = self.query_specific_flows(flow_names)
        
        if not flows_to_delete:
            print("\n✨ No Flow versions found to delete.")
            print("💡 This could mean:")
            print("   - All Flow versions are already the latest")
            print("   - All Flow versions are currently active")
            print("   - No Flows exist in this org")
            self.log_message("No Flow versions found to delete")
            return
        
        # Save deletion list to file
        print(f"\n💾 Saving deletion list to file...")
        save_filename = self.save_deletion_list(flows_to_delete)
        if save_filename:
            print(f"📄 Deletion list saved to: {save_filename}")
            self.log_message(f"Deletion list saved to: {save_filename}")
        
        # Confirm deletion
        print(f"\n⚠️  CONFIRMATION REQUIRED")
        print(f"📊 About to delete {len(flows_to_delete)} Flow versions")
        if user_input['is_production']:
            print("🚨 PRODUCTION INSTANCE - This action cannot be undone!")
            print("🚨 PRODUCTION INSTANCE - Please verify this is what you want to do!")
        else:
            print("🧪 SANDBOX INSTANCE - Safe to proceed")
        
        print("\n📝 Summary of what will be deleted:")
        for i, flow in enumerate(flows_to_delete[:5], 1):  # Show first 5
            print(f"   {i}. {flow['Definition']['DeveloperName']} v{flow['VersionNumber']} ({flow['Status']})")
        if len(flows_to_delete) > 5:
            print(f"   ... and {len(flows_to_delete) - 5} more")
        
        confirm = input(f"\nAre you sure you want to delete {len(flows_to_delete)} Flow versions? Type 'DELETE' to confirm: ").strip()
        if confirm != 'DELETE':
            print("❌ Operation cancelled by user.")
            self.log_message("Operation cancelled by user")
            return
        
        print(f"\n🎯 Proceeding with deletion of {len(flows_to_delete)} Flow versions...")
        self.log_message(f"User confirmed deletion of {len(flows_to_delete)} Flow versions")
        
        # Extract Flow IDs
        flow_ids = [flow['Id'] for flow in flows_to_delete]
        
        # Perform bulk delete
        self.bulk_delete_flows(flow_ids)
    
    def run_batch_cleanup(self, config: Dict):
        """Run cleanup for multiple orgs from configuration file"""
        print(f"\n🚀 Starting Batch Flow Cleanup")
        print(f"📊 Processing {len(config['orgs'])} organizations...")
        
        total_orgs = len(config['orgs'])
        successful_orgs = 0
        failed_orgs = 0
        
        for i, org_config in enumerate(config['orgs'], 1):
            print(f"\n{'='*60}")
            print(f"🏢 Processing Org {i}/{total_orgs}: {org_config['instance']}")
            print(f"{'='*60}")
            
            try:
                # Update instance URL for logging
                self.instance_url = org_config['instance']
                
                # Authenticate with stored credentials
                port = org_config.get('callback_port', 8080)
                if not self.authenticate(org_config['instance'], org_config['client_id'], org_config['client_secret'], silent=True, port=port):
                    print(f"❌ Authentication failed for {org_config['instance']}")
                    failed_orgs += 1
                    continue
                
                # Check if production (unless skipped)
                if not org_config.get('skip_production_check', False):
                    is_production = self.check_if_production()
                    if is_production:
                        print(f"⚠️  PRODUCTION instance detected!")
                        if not org_config.get('auto_confirm_production', False):
                            print(f"⏭️  Skipping production org (set 'auto_confirm_production': true to override)")
                            failed_orgs += 1
                            continue
                        else:
                            print(f"🤖 Auto-confirming production deletion (configured)")
                else:
                    is_production = False
                
                # Prepare user input for this org
                org_user_input = {
                    'instance': org_config['instance'],
                    'cleanup_type': org_config['cleanup_type'],
                    'is_production': is_production,
                    'flow_names': org_config.get('flow_names', [])
                }
                
                # Run cleanup for this org
                self.run_cleanup(org_user_input)
                successful_orgs += 1
                
            except Exception as e:
                print(f"❌ Error processing {org_config['instance']}: {e}")
                self.log_message(f"Error processing {org_config['instance']}: {e}")
                failed_orgs += 1
        
        # Final summary
        print(f"\n{'='*60}")
        print(f"📊 BATCH CLEANUP SUMMARY")
        print(f"{'='*60}")
        print(f"✅ Successful: {successful_orgs}")
        print(f"❌ Failed: {failed_orgs}")
        print(f"📝 Log file: {self.log_file}")
        
        if successful_orgs > 0:
            print("🎉 Batch cleanup completed!")
        else:
            print("⚠️  No organizations were processed successfully")

if __name__ == "__main__":
    cleanup = SalesforceFlowCleanup()
    user_input = cleanup.get_user_input()
    
    if user_input['mode'] == 'batch':
        # Batch mode - process multiple orgs
        print(f"\nBatch mode: Processing {len(user_input['config']['orgs'])} organizations")
        cleanup.instance_url = "Multiple Organizations"
        cleanup.setup_logging()
        cleanup.run_batch_cleanup(user_input['config'])
    else:
        # Interactive mode - single org
        print(f"\nInstance: {user_input['instance']}")
        print(f"Cleanup type: {user_input['cleanup_type']}")
        
        # Setup logging
        cleanup.instance_url = user_input['instance']
        cleanup.setup_logging()
        
        # Authenticate
        port = user_input.get('port', 8080)
        if cleanup.authenticate(user_input['instance'], port=port):
            # Check if this is a production instance
            print("\n🔍 Checking instance type...")
            is_production = cleanup.check_if_production()
            
            if is_production:
                print(f"\n⚠️  WARNING: This is a PRODUCTION instance!")
                confirm = input("Are you sure you want to proceed? Type 'YES' to continue: ").strip()
                if confirm != 'YES':
                    print("Operation cancelled.")
                    cleanup.log_message("Operation cancelled: User declined production confirmation")
                    sys.exit(0)
            
            # Update user_input with production status
            user_input['is_production'] = is_production
            
            print("Ready to proceed with cleanup...")
            cleanup.run_cleanup(user_input)
        else:
            print("Authentication failed. Exiting.")
            cleanup.log_message("Authentication failed. Exiting.")
            sys.exit(1)
