# Configuration Files

This folder contains your Salesforce Flow Cleanup configuration files.

## First Time Setup

1. **Copy the example file**:
   ```bash
   cp config_example.json config_myorg.json
   ```

2. **Edit your config file** with your Salesforce org details:
   - Update `instance` with your Salesforce instance URL
   - Add your `client_id` (Consumer Key from Connected App)
   - Add your `client_secret` (Consumer Secret, if required)
   - Configure `cleanup_type` and other settings

3. **Use your config**:
   - When running the script, select "Use configuration file"
   - Choose your config file from the list

## Security

⚠️ **Important**: All files in this folder (except `config_example.json`) are ignored by git to protect your sensitive credentials. Never commit your personal configuration files!

## Example Structure

```json
{
  "orgs": [
    {
      "instance": "https://yourorg.sandbox.my.salesforce.com",
      "client_id": "your_client_id_here",
      "client_secret": "your_client_secret_here",
      "cleanup_type": "1",
      "flow_names": [],
      "skip_production_check": false,
      "auto_confirm_production": false,
      "callback_port": 8080
    }
  ]
}
```

## Auto-Save Feature

After running cleanup in interactive mode, the script will offer to save your configuration automatically. This makes it easy to build up a collection of configurations for different orgs.

## Multiple Orgs

You can add multiple orgs to a single config file:

```json
{
  "orgs": [
    {
      "instance": "https://org1.sandbox.my.salesforce.com",
      "client_id": "client_id_1",
      ...
    },
    {
      "instance": "https://org2.sandbox.my.salesforce.com",
      "client_id": "client_id_2",
      ...
    }
  ]
}
```

