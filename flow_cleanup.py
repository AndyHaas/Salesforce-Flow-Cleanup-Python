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
import argparse
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
from typing import List, Dict, Optional, Tuple

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
        self.client_id = None
        self.client_secret = None
        # Ensure configs folder exists and move any root config files
        self.ensure_configs_folder()
        
    def ensure_configs_folder(self):
        """Ensure configs folder exists and move any config files from root for security"""
        configs_dir = "configs"
        os.makedirs(configs_dir, exist_ok=True)
        
        # Find config files in root directory
        moved_files = []
        for filename in os.listdir('.'):
            if filename.startswith('config') and filename.endswith('.json') and os.path.isfile(filename):
                source_path = filename
                dest_path = os.path.join(configs_dir, filename)
                
                # Move the file
                try:
                    # If destination exists, rename with timestamp
                    if os.path.exists(dest_path):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        name, ext = os.path.splitext(filename)
                        dest_path = os.path.join(configs_dir, f"{name}_{timestamp}{ext}")
                    
                    os.rename(source_path, dest_path)
                    moved_files.append((filename, dest_path))
                except Exception as e:
                    print(f"⚠️  Warning: Could not move {filename}: {e}")
        
        # Display message if files were moved
        if moved_files:
            print("="*60)
            print("🔒 SECURITY: Configuration Files Moved")
            print("="*60)
            print("The following configuration files were found in the root directory")
            print("and have been automatically moved to the 'configs/' folder:")
            print()
            for filename, dest_path in moved_files:
                print(f"  • {filename} → {dest_path}")
            print()
            print("This ensures your configuration files with sensitive credentials")
            print("will never be accidentally committed to git.")
            print("="*60)
            print()
        
    def setup_logging(self):
        """Setup logging to file with masked sensitive information"""
        # Ensure logs directory exists
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        
        log_filename = os.path.join(logs_dir, f"flow_cleanup_{self.session_id}.log")
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
        
        # Ensure deletion_lists directory exists
        deletion_lists_dir = "deletion_lists"
        os.makedirs(deletion_lists_dir, exist_ok=True)
        
        filename = os.path.join(deletion_lists_dir, f"flows_to_delete_{self.session_id}.json")
        
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
    
    def list_existing_configs(self) -> List[str]:
        """List existing config files in the configs directory"""
        configs_dir = "configs"
        if not os.path.exists(configs_dir):
            return []
        
        config_files = []
        for filename in os.listdir(configs_dir):
            if filename.endswith('.json') and filename != 'config_example.json':
                config_files.append(filename)
        
        return sorted(config_files)
    
    def save_config(self, user_input: Dict, config_filename: str = None, add_to_existing: bool = False) -> bool:
        """Save configuration to a file"""
        # Ensure configs directory exists
        configs_dir = "configs"
        os.makedirs(configs_dir, exist_ok=True)
        
        # Determine filename
        if config_filename:
            if not config_filename.endswith('.json'):
                config_filename += '.json'
            config_path = os.path.join(configs_dir, config_filename)
        else:
            # Generate default name
            instance_name = user_input['instance'].replace('https://', '').replace('.my.salesforce.com', '').replace('--', '_')
            config_filename = f"config_{instance_name}.json"
            config_path = os.path.join(configs_dir, config_filename)
        
        # Prepare org configuration
        org_config = {
            "instance": user_input['instance'],
            "client_id": self.client_id or "",
            "client_secret": self.client_secret or "",
            "cleanup_type": user_input['cleanup_type'],
            "flow_names": user_input.get('flow_names', []),
            "skip_production_check": False,
            "auto_confirm_production": user_input.get('is_production', False),
            "callback_port": user_input.get('port', 8080)
        }
        
        # Load existing config or create new
        if add_to_existing and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                # Add new org to existing config
                config['orgs'].append(org_config)
            except (FileNotFoundError, json.JSONDecodeError):
                # If file exists but can't be read, create new
                config = {"orgs": [org_config]}
        else:
            # Create new config
            config = {"orgs": [org_config]}
        
        # Save config
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✅ Configuration saved to: {config_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to save configuration: {e}")
            return False
    
    def offer_save_config(self, user_input: Dict) -> None:
        """Offer to save configuration after interactive mode"""
        if not self.client_id:
            # No credentials to save
            return
        
        print("\n" + "="*60)
        print("💾 Save Configuration")
        print("="*60)
        save_choice = input("Would you like to save this configuration for future use? (y/n): ").strip().lower()
        
        if save_choice not in ['y', 'yes']:
            return
        
        # List existing configs
        existing_configs = self.list_existing_configs()
        
        if existing_configs:
            print("\nExisting configuration files:")
            for i, config_file in enumerate(existing_configs, 1):
                print(f"  {i}. {config_file}")
            print(f"  {len(existing_configs) + 1}. Create new configuration file")
            
            choice = input(f"\nSelect option (1-{len(existing_configs) + 1}): ").strip()
            
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(existing_configs):
                    # Add to existing config
                    config_filename = existing_configs[choice_num - 1]
                    self.save_config(user_input, config_filename, add_to_existing=True)
                elif choice_num == len(existing_configs) + 1:
                    # Create new config
                    config_name = input("Enter name for new configuration file (without .json): ").strip()
                    if config_name:
                        self.save_config(user_input, config_name, add_to_existing=False)
                    else:
                        print("❌ No name provided. Configuration not saved.")
                else:
                    print("❌ Invalid choice. Configuration not saved.")
            except ValueError:
                print("❌ Invalid input. Configuration not saved.")
        else:
            # No existing configs, create new
            config_name = input("Enter name for configuration file (without .json, or press Enter for default): ").strip()
            if config_name:
                self.save_config(user_input, config_name, add_to_existing=False)
            else:
                self.save_config(user_input, add_to_existing=False)
    
    def prompt_cleanup_options(self, defaults: Dict = None) -> Tuple[str, List[str]]:
        """Prompt for cleanup type and flow scope. Used when not --silent.
        defaults: optional dict with 'cleanup_type' and 'flow_names' to show as current/defaults."""
        defaults = defaults or {}
        default_type = defaults.get('cleanup_type', '1')
        default_flows = defaults.get('flow_names', [])
        
        print("\n=== Cleanup Options ===")
        print("What type of cleanup do you want to do?")
        print("1. All old Flow versions (not latest and not active)")
        print("2. Specific Flows only (you'll provide the Flow API names)")
        print("3. Browse flows with old versions (select from list after connecting)")
        
        type_prompt = "Enter your choice (1, 2, or 3)"
        if default_type:
            type_prompt += f" [default: {default_type}]"
        type_prompt += ": "
        
        choice = input(type_prompt).strip() or default_type
        if choice not in ('1', '2', '3'):
            choice = '1'
        
        flow_names = []
        if choice == "2":
            print("\n=== Specific Flow Selection ===")
            print("Enter the API names of the Flows you want to clean up.")
            if default_flows:
                print(f"(Current in config: {', '.join(default_flows)})")
            print("(Press Enter on an empty line when done)")
            
            while True:
                flow_name = input("Flow API name: ").strip()
                if not flow_name:
                    break
                flow_names.append(flow_name)
            
            if not flow_names and default_flows:
                flow_names = default_flows
            if not flow_names:
                print("❌ No Flow names provided. Exiting.")
                sys.exit(1)
            
            print(f"✅ Selected {len(flow_names)} Flow(s): {', '.join(flow_names)}")
        
        return choice, flow_names
    
    def get_user_input(self, silent: bool = False, config_path: str = None) -> Dict[str, str]:
        """Get user input for instance and cleanup options.
        When silent=True, config_path must be provided; config is used as-is (headless).
        When silent=False, user is prompted for all options (cleanup type, all/specific flows, etc.)."""
        print("=== Salesforce Flow Version Cleanup Tool ===\n")
        
        # Headless: require config, no prompts
        if silent:
            if not config_path:
                print("❌ --silent requires a config file. Use: python flow_cleanup.py --silent --config configs/your_config.json")
                sys.exit(1)
            path_to_load = config_path
            if not os.path.isabs(config_path) and not os.path.isfile(config_path):
                path_to_load = os.path.join("configs", config_path)
            config = self.load_config_file(path_to_load)
            if not config:
                sys.exit(1)
            return {'config': config, 'mode': 'batch', 'silent': True}
        
        # Not silent: config file is optional; if used, we still prompt for cleanup options
        use_config = False
        config_file = config_path
        
        if not config_file:
            use_config_choice = input("Do you want to use a configuration file? (y/n): ").strip().lower()
            use_config = use_config_choice in ['y', 'yes']
        
        if use_config or config_file:
            if not config_file:
                existing_configs = self.list_existing_configs()
                if existing_configs:
                    print("\nAvailable configuration files:")
                    for i, cfg in enumerate(existing_configs, 1):
                        print(f"  {i}. {cfg}")
                    print(f"  {len(existing_configs) + 1}. Enter custom path")
                    choice = input(f"\nSelect option (1-{len(existing_configs) + 1}): ").strip()
                    try:
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(existing_configs):
                            config_file = os.path.join("configs", existing_configs[choice_num - 1])
                        elif choice_num == len(existing_configs) + 1:
                            config_file = input("Enter path to configuration file: ").strip()
                        else:
                            config_file = None
                    except ValueError:
                        config_file = None
                else:
                    config_file = input("Enter path to configuration file: ").strip()
            
            if config_file:
                path_to_load = config_file
                if not os.path.isabs(config_file) and not os.path.isfile(config_file):
                    path_to_load = os.path.join("configs", config_file)
                config = self.load_config_file(path_to_load)
                if config:
                    # Prompt for cleanup options (anything in config should be asked when not silent)
                    first_org = config['orgs'][0]
                    cleanup_type, flow_names = self.prompt_cleanup_options({
                        'cleanup_type': first_org.get('cleanup_type', '1'),
                        'flow_names': first_org.get('flow_names', [])
                    })
                    return {
                        'config': config,
                        'mode': 'batch',
                        'cleanup_type': cleanup_type,
                        'flow_names': flow_names,
                        'silent': False
                    }
                if not config:
                    print("Falling back to interactive mode...")
        
        # Interactive mode: no config or load failed — ask for everything
        instance = input("Enter your Salesforce instance URL (e.g., mycompany.my.salesforce.com): ").strip()
        if not instance.startswith('http'):
            instance = f"https://{instance}"
        if not instance.endswith('.my.salesforce.com'):
            instance = f"{instance}.my.salesforce.com"
        
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
                port = 8080
        else:
            port = 8080
        
        cleanup_type, flow_names = self.prompt_cleanup_options()
        
        return {
            'instance': instance,
            'cleanup_type': cleanup_type,
            'flow_names': flow_names,
            'port': port,
            'mode': 'interactive',
            'silent': False
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
            # Store credentials for potential config saving
            self.client_id = client_id
            self.client_secret = client_secret
        else:
            if not silent:
                print("Using provided client credentials...")
            # Store credentials for potential config saving
            self.client_id = client_id
            self.client_secret = client_secret
        
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
    
    def list_flows_with_old_version_counts(self) -> List[Dict]:
        """Query for distinct flows that have old versions, with count of versions that would be deleted.
        Returns list of dicts: [{"developer_name": str, "count": int, "master_label": str}, ...]"""
        print("\n=== Listing Flows with Old Versions ===")
        print("🔍 Finding flows that have old versions to delete...")
        
        soql_query = "SELECT Id, VersionNumber, DefinitionId, Definition.DeveloperName, Definition.MasterLabel FROM Flow WHERE Status != 'Active' ORDER BY Definition.DeveloperName, VersionNumber DESC"
        query_url = f"{self.instance_url}/services/data/{self.api_version}/tooling/query"
        params = {'q': soql_query}
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            self.log_message("Querying flows for browse list")
            response = requests.get(query_url, params=params, headers=headers)
            response.raise_for_status()
            result = response.json()
            all_flows = result.get('records', [])
            
            # Find latest version per definition
            definition_latest = {}
            for flow in all_flows:
                def_id = flow['DefinitionId']
                ver = flow['VersionNumber']
                if def_id not in definition_latest or ver > definition_latest[def_id]:
                    definition_latest[def_id] = ver
            
            # Count old (deletable) versions per definition and collect distinct flow info
            definition_counts = {}
            definition_labels = {}
            for flow in all_flows:
                def_id = flow['DefinitionId']
                if flow['VersionNumber'] < definition_latest[def_id]:
                    definition_counts[def_id] = definition_counts.get(def_id, 0) + 1
                    definition_labels[def_id] = (
                        flow['Definition']['DeveloperName'],
                        flow['Definition'].get('MasterLabel') or flow['Definition']['DeveloperName']
                    )
            
            flow_list = []
            for def_id, count in definition_counts.items():
                dev_name, master_label = definition_labels[def_id]
                flow_list.append({
                    'developer_name': dev_name,
                    'count': count,
                    'master_label': master_label
                })
            flow_list.sort(key=lambda x: x['developer_name'].lower())
            
            print(f"✅ Found {len(flow_list)} flow(s) with old versions")
            self.log_message(f"Browse list: {len(flow_list)} flows with old versions")
            return flow_list
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Query failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    self.log_message(f"Browse list query failed: {error_detail}")
                except Exception:
                    self.log_message(f"Browse list query failed: {e.response.text}")
            return []
    
    def prompt_flow_selection_from_list(self, flow_list: List[Dict]) -> List[str]:
        """Display numbered list of flows with version counts; prompt user to select by number.
        Accepts input like '1,3,5' or '1 3 5' or 'all'. Returns list of flow developer names."""
        if not flow_list:
            return []
        
        print("\n=== Select Flows to Clean Up ===")
        print("Flows with old versions (number = versions that will be deleted):")
        print()
        for i, item in enumerate(flow_list, 1):
            print(f"  {i:3d}. {item['developer_name']} ({item['count']} version{'s' if item['count'] != 1 else ''})")
        print()
        print("Enter the number(s) to clean up, separated by commas or spaces (e.g. 1,3,5 or 1 3 5), or 'all':")
        
        raw = input("Selection: ").strip().lower()
        if not raw:
            print("❌ No selection entered. Exiting.")
            return []
        
        if raw == 'all':
            return [item['developer_name'] for item in flow_list]
        
        # Parse numbers: allow "1,3,5" or "1 3 5" or "1, 3, 5"
        parts = re.split(r'[\s,]+', raw)
        indices = set()
        for p in parts:
            p = p.strip()
            if not p:
                continue
            try:
                num = int(p)
                if 1 <= num <= len(flow_list):
                    indices.add(num - 1)
                else:
                    print(f"⚠️  Ignoring out-of-range number: {num}")
            except ValueError:
                print(f"⚠️  Ignoring non-numeric input: {p}")
        
        if not indices:
            print("❌ No valid selection. Exiting.")
            return []
        
        selected = [flow_list[i]['developer_name'] for i in sorted(indices)]
        print(f"✅ Selected {len(selected)} flow(s): {', '.join(selected)}")
        return selected
    
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
    
    def run_cleanup(self, user_input: Dict) -> Optional[List[str]]:
        """Main cleanup execution. Returns selected flow names when cleanup_type is '3' (browse), else None."""
        print("\n🚀 Starting Flow cleanup process...")
        self.log_message("Starting Flow cleanup process")
        flows_to_delete = []
        selected_flow_names = None  # Used for type 3 so batch can reuse selection
        
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
        elif user_input['cleanup_type'] == '3':
            # Browse: list flows with counts, user selects by number
            print("📋 Option selected: Browse flows and select from list")
            flow_list = self.list_flows_with_old_version_counts()
            if not flow_list:
                print("\n✨ No flows with old versions found.")
                self.log_message("Browse: no flows with old versions")
                return
            flow_names = self.prompt_flow_selection_from_list(flow_list)
            if not flow_names:
                return None
            selected_flow_names = flow_names
            flows_to_delete = self.query_specific_flows(flow_names)
        else:
            flows_to_delete = []
        
        if not flows_to_delete:
            print("\n✨ No Flow versions found to delete.")
            print("💡 This could mean:")
            print("   - All Flow versions are already the latest")
            print("   - All Flow versions are currently active")
            print("   - No Flows exist in this org")
            self.log_message("No Flow versions found to delete")
            return selected_flow_names
        
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
            return selected_flow_names
        
        print(f"\n🎯 Proceeding with deletion of {len(flows_to_delete)} Flow versions...")
        self.log_message(f"User confirmed deletion of {len(flows_to_delete)} Flow versions")
        
        # Extract Flow IDs
        flow_ids = [flow['Id'] for flow in flows_to_delete]
        
        # Perform bulk delete
        self.bulk_delete_flows(flow_ids)
        return selected_flow_names
    
    def run_batch_cleanup(self, config: Dict, overrides: Dict = None):
        """Run cleanup for multiple orgs from configuration file.
        overrides: optional dict with cleanup_type and flow_names; when provided (e.g. from interactive prompts), use for all orgs."""
        overrides = overrides or {}
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
                
                # Use overrides when provided (interactive run with config), else use org config
                cleanup_type = overrides['cleanup_type'] if 'cleanup_type' in overrides else org_config['cleanup_type']
                flow_names = overrides['flow_names'] if 'flow_names' in overrides else org_config.get('flow_names', [])
                
                # Type 3 (browse) with pre-filled flow_names in config (e.g. silent): use as type 2
                if cleanup_type == '3' and flow_names and not overrides:
                    cleanup_type = '2'
                # If first org used type 3 (browse), reuse the selected flow names for remaining orgs
                elif cleanup_type == '3' and overrides.get('flow_names'):
                    cleanup_type = '2'
                    flow_names = overrides['flow_names']
                
                org_user_input = {
                    'instance': org_config['instance'],
                    'cleanup_type': cleanup_type,
                    'is_production': is_production,
                    'flow_names': flow_names
                }
                
                # Run cleanup for this org; type 3 returns selected flow names for batch reuse
                selected = self.run_cleanup(org_user_input)
                if cleanup_type == '3' and selected:
                    overrides['flow_names'] = selected
                    overrides['cleanup_type'] = '2'
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

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Salesforce Flow Version Cleanup - remove old Flow versions via Tooling API"
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Headless mode: use config file as-is without prompting. Requires --config.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to config file (e.g. configs/your_config.json). Required when using --silent.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cleanup = SalesforceFlowCleanup()
    user_input = cleanup.get_user_input(silent=args.silent, config_path=args.config)
    
    if user_input['mode'] == 'batch':
        # Batch mode - process multiple orgs
        print(f"\nBatch mode: Processing {len(user_input['config']['orgs'])} organizations")
        cleanup.instance_url = "Multiple Organizations"
        cleanup.setup_logging()
        overrides = None
        if not user_input.get('silent', True):
            overrides = {
                'cleanup_type': user_input.get('cleanup_type'),
                'flow_names': user_input.get('flow_names', []),
            }
        cleanup.run_batch_cleanup(user_input['config'], overrides=overrides)
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
            
            # Offer to save configuration
            cleanup.offer_save_config(user_input)
        else:
            print("Authentication failed. Exiting.")
            cleanup.log_message("Authentication failed. Exiting.")
            sys.exit(1)
