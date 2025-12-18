# Salesforce Flow Cleanup Tool

A comprehensive Python tool for cleaning up old Flow versions in Salesforce orgs. This tool supports both interactive single-org processing and automated batch processing across multiple orgs.

## Features

- **Interactive & Batch Modes**: Process single orgs interactively or multiple orgs via configuration file
- **Automatic OAuth Authentication**: Browser-based authentication with local callback server
- **Configurable Ports**: Use default port 8080 or specify custom ports for OAuth callbacks
- **Production Safety**: Special confirmation prompts and detection for production instances
- **Flexible Cleanup Options**:
  - Clean up all old Flow versions (not latest and not active)
  - Clean up specific Flow versions by name
- **Bulk Delete**: Uses Salesforce Composite API for efficient bulk deletion
- **Comprehensive Logging**: Detailed audit trails with masked sensitive data
- **Deletion Lists**: Save what will be deleted before confirmation
- **Silent Mode**: Use stored credentials for automated runs
- **Multi-Org Support**: Process multiple Salesforce orgs in a single batch operation

## Files

- **`flow_cleanup.py`** - Main script (supports both interactive and batch modes)
- **`configs/config_example.json`** - Example configuration file for batch processing
- **`requirements.txt`** - Python dependencies
- **`README.md`** - This documentation

## Folder Structure

The tool organizes files into specific folders:

- **`configs/`** - Configuration files (ignored by git, contains sensitive credentials)
  - Store your custom configuration files here
  - Example: `configs/config_production.json`, `configs/config_qa.json`
  - **Note**: The script automatically moves any config files found in the root directory to this folder for security
  - Example template: `configs/config_example.json`
- **`logs/`** - Log files (ignored by git)
  - All log files are automatically saved here
  - Format: `logs/flow_cleanup_YYYYMMDD_HHMMSS.log`
- **`deletion_lists/`** - Deletion list files (ignored by git)
  - JSON files listing flows to be deleted are saved here
  - Format: `deletion_lists/flows_to_delete_YYYYMMDD_HHMMSS.json`
- **`venv/`** - Python virtual environment (ignored by git)
  - Created when setting up the project

## Quick Start

### Interactive Mode

```bash
python flow_cleanup.py
```

### Batch Mode

1. Create a configuration file based on `config_example.json` and save it in the `configs/` folder
2. Run the script and select configuration file mode
3. Choose from existing configs in `configs/` folder or specify a custom path

## Port Configuration

The tool uses port 8080 by default for OAuth callbacks. You can:

- **Use default**: Press Enter when prompted for port (interactive mode)
- **Custom port**: Specify any port 1024-65535
- **Batch mode**: Configure `callback_port` in your JSON file

**Important**: If using a custom port, update your Salesforce Connected App callback URL to `http://localhost:[PORT]/callback`

## Prerequisites

- Python 3.7+
- Salesforce org with appropriate permissions
- Connected App configured in Salesforce

## Setup

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Connected App in Salesforce**:
   - Go to Setup → App Manager → New External Client App
   - Enable OAuth Settings
   - Set Callback URL to: `http://localhost:8080/callback` (default) or `http://localhost:[PORT]/callback` (if using custom port)
   - Add OAuth Scopes: `Access and manage your data (api)`, `Perform requests on your behalf at any time (refresh_token, offline_access)`
   - Enable PKCE (Proof Key for Code Exchange)
   - Note the Consumer Key (Client ID)

## Usage

### Interactive Mode

Run the script:

```bash
python flow_cleanup.py
```

The script will:

1. Ask if you want to use a configuration file or interactive mode
   - If using config: Lists available configs from `configs/` folder or allows custom path
2. Ask what type of cleanup you want to perform
3. If specific flows: Ask for Flow API names to clean up
4. Ask for your Salesforce instance URL
5. Ask for callback port (default 8080)
6. Start a local server and open your browser for authentication
7. Automatically receive the OAuth callback
8. Check if it's a production instance and require confirmation
9. Query for Flow versions to delete
10. Show you what will be deleted and ask for confirmation
11. Perform the bulk deletion and report results
12. **Offer to save configuration** - After cleanup, you can save your settings:
    - Add to an existing config file in `configs/` folder
    - Create a new config file with a custom name
    - Auto-generate a filename based on your instance URL

### Batch Mode

Create a configuration file in the `configs/` folder (see `configs/config_example.json` for format):

```json
{
  "orgs": [
    {
      "instance": "https://yourorg.sandbox.my.salesforce.com",
      "client_id": "your_client_id",
      "client_secret": "your_client_secret",
      "cleanup_type": "1",
      "flow_names": [],
      "skip_production_check": false,
      "auto_confirm_production": false,
      "callback_port": 8080
    }
  ]
}
```

Run the script and select configuration file mode:

```bash
python flow_cleanup.py
```

When prompted, you can:
- Select from existing config files in the `configs/` folder (numbered list)
- Enter a custom path to a configuration file

**Tip**: After running interactive mode, you can save your configuration for future batch runs!

#### Configuration File Options

| Field                     | Required | Valid Options                                                     |
| ------------------------- | -------- | ----------------------------------------------------------------- |
| `instance`                | Yes      | Salesforce instance URL (e.g., `https://myorg.my.salesforce.com`) |
| `client_id`               | Yes      | Connected App Consumer Key (15+ character string)                 |
| `client_secret`           | No       | Connected App Consumer Secret (if required)                       |
| `cleanup_type`            | No       | `"1"` (all old versions) or `"2"` (specific flows)                |
| `flow_names`              | No       | Array of Flow API names (e.g., `["MyFlow", "AccountFlow"]`)       |
| `skip_production_check`   | No       | `true` or `false` (default: `false`)                              |
| `auto_confirm_production` | No       | `true` or `false` (default: `false`)                              |
| `callback_port`           | No       | Integer 1024-65535 (default: `8080`)                              |

### Port Configuration

#### Interactive Mode

When running in interactive mode, you'll be prompted for a callback port:

- **Default**: 8080 (press Enter to use default)
- **Custom**: Enter any port between 1024-65535
- **Important**: If using a custom port, update your Salesforce Connected App callback URL to `http://localhost:[PORT]/callback`

#### Batch Mode

Configure the port in your JSON configuration file:

```json
{
  "orgs": [
    {
      "instance": "https://yourorg.sandbox.my.salesforce.com",
      "client_id": "your_client_id",
      "callback_port": 8081
    }
  ]
}
```

#### Port Conflicts

If port 8080 is already in use:

- **macOS/Linux**: `lsof -i :8080` to see what's using it
- **Windows**: `netstat -ano | findstr :8080` to see what's using it
- **Solution**: Use a different port and update your Connected App

## Safety Features

- **Production Detection**: Queries Organization.IsSandbox to accurately detect production instances
- **Confirmation Prompts**: Multiple confirmation steps before deletion
- **Detailed Preview**: Shows exactly what will be deleted before proceeding
- **Audit Trails**: Comprehensive logging with masked sensitive data
- **Error Handling**: Graceful handling of authentication and API errors
- **Port Conflict Detection**: Clear error messages and troubleshooting for port conflicts
- **Batch Safety**: Individual org success/failure tracking with comprehensive summaries

## Generated Files

All generated files are automatically organized into folders:

- **Log files**: `logs/flow_cleanup_YYYYMMDD_HHMMSS.log` - Complete audit trail with masked sensitive data
- **Deletion lists**: `deletion_lists/flows_to_delete_YYYYMMDD_HHMMSS.json` - JSON file with flows to be deleted
- **Configuration files**: `configs/config_*.json` - Custom JSON files for batch processing with per-org settings

**Note**: All folders (`configs/`, `logs/`, `deletion_lists/`, `venv/`) are ignored by git to protect sensitive data and avoid committing generated files.

## Saving Configurations

After completing cleanup in interactive mode, the tool offers to save your configuration:

1. **Save to existing config**: Add this org to an existing config file in `configs/` folder
2. **Create new config**: Create a new config file with a custom name
3. **Auto-named config**: Automatically generate a filename based on your instance URL

Saved configurations include:
- Instance URL
- Client ID and Secret (if provided)
- Cleanup type and flow names
- Production settings
- Callback port

This makes it easy to build up a collection of configurations for different orgs and reuse them in batch mode.

## Security

- All sensitive data (client IDs, secrets, auth codes) are masked in logs
- Configuration files with credentials are stored in `configs/` folder (ignored by git)
- Logs and deletion lists are stored in separate folders (ignored by git)
- Comprehensive audit trails for compliance
- Production safety checks and confirmations

## Troubleshooting

### Authentication Issues

- **Invalid client credentials**: Check your Connected App Consumer Key and Secret
- **Callback URL mismatch**: Ensure your Connected App callback URL matches the port you're using
- **PKCE errors**: Make sure PKCE is enabled in your Connected App
- **Port conflicts**: Use a different port if 8080 is already in use

### Port 8080 Already in Use

- If you get "Port 8080 is already in use", close any applications using that port
- Common applications that use port 8080: web servers, development servers, other OAuth tools
- You can check what's using the port with: `lsof -i :8080` (macOS/Linux) or `netstat -ano | findstr :8080` (Windows)

### Query Errors

- **MALFORMED_QUERY**: The script uses correct SOQL syntax for the Tooling API
- **Permission errors**: Ensure your user has appropriate permissions to query Flow objects
- **API version**: The script uses API version 60.0, which supports all current Flow features

### Batch Processing Issues

- **Configuration validation**: Check your JSON syntax and required fields
- **Individual org failures**: The script continues processing other orgs if one fails
- **Production confirmations**: Set `auto_confirm_production: true` to skip manual confirmations

## Support

For issues or questions, refer to the troubleshooting section above or check the generated log files for detailed error information.
