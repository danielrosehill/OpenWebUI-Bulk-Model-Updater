#!/usr/bin/env python3
"""
Script to update all models in OpenWebUI to Microsoft's phi-4-multimodal-instruct model
Created: 2025-03-28
"""

import requests
import json
import sys
import time
from datetime import datetime
import argparse
from colorama import init, Fore, Style
import os

# Initialize colorama
init()

# Configuration
DEFAULT_CONFIG = {
    "openwebui_url": "https://chat.example.com",
    "api_base_path": "/api/v1",
    "target_model": "openrouter.microsoft/phi-4-multimodal-instruct",
    "api_key": os.environ.get("OPENWEBUI_API_KEY", "default_api_key"),
    "cf_access_client_id": os.environ.get("CF_ACCESS_CLIENT_ID", "default_client_id"),
    "cf_access_client_secret": os.environ.get("CF_ACCESS_CLIENT_SECRET", "default_client_secret"),
    "debug": False
}

# Function to display messages with timestamp
def log(level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if level == "INFO":
        print(f"{Fore.BLUE}[INFO]{Style.RESET_ALL} {timestamp} - {message}")
    elif level == "SUCCESS":
        print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} {timestamp} - {message}")
    elif level == "WARNING":
        print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} {timestamp} - {message}")
    elif level == "ERROR":
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {timestamp} - {message}")
    elif level == "DEBUG" and config["debug"]:
        print(f"{Fore.YELLOW}[DEBUG]{Style.RESET_ALL} {timestamp} - {message}")

# Function to make API calls with proper headers
def make_api_call(method, endpoint, data=None, params=None):
    url = f"{config['openwebui_url']}{config['api_base_path']}{endpoint}"
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "CF-Access-Client-Id": config['cf_access_client_id'],
        "CF-Access-Client-Secret": config['cf_access_client_secret'],
        "Content-Type": "application/json"
    }
    
    log("DEBUG", f"Executing API call: {method} {config['api_base_path']}{endpoint}")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, params=params)
        else:
            log("ERROR", f"Unsupported HTTP method: {method}")
            return None
        
        # Try to parse response as JSON
        try:
            return response.json()
        except json.JSONDecodeError:
            log("DEBUG", f"Response is not JSON: {response.text[:500]}")
            return response.text
            
    except requests.exceptions.RequestException as e:
        log("ERROR", f"API call failed: {str(e)}")
        return None

def update_models():
    log("INFO", "Starting model update process...")
    log("INFO", f"Target model: {config['target_model']}")
    log("INFO", f"Using OpenWebUI URL: {config['openwebui_url']}{config['api_base_path']}")
    
    # Try different API endpoints to get models
    endpoints = [
        "/models",
        "/models/",
        "/models/list",
        "/v1/models"
    ]
    
    models_response = None
    
    for endpoint in endpoints:
        log("INFO", f"Trying to fetch models from endpoint: {endpoint}")
        response = make_api_call("GET", endpoint)
        
        if response and isinstance(response, list):
            log("SUCCESS", f"Successfully fetched models from endpoint: {endpoint}")
            models_response = response
            break
        elif response and isinstance(response, dict) and ('models' in response or 'data' in response):
            log("SUCCESS", f"Successfully fetched models from endpoint: {endpoint}")
            models_response = response.get('models', response.get('data', []))
            break
    
    if not models_response:
        log("ERROR", "Failed to fetch models from any endpoint")
        sys.exit(1)
    
    log("DEBUG", f"Raw models response: {json.dumps(models_response)[:500]}...")
    
    # Extract models
    models = models_response if isinstance(models_response, list) else []
    model_count = len(models)
    
    if model_count == 0:
        log("ERROR", "No models found in the API response")
        sys.exit(1)
    
    log("INFO", f"Found {model_count} models to update")
    
    # Counter for successful updates
    successful_updates = 0
    
    # Loop through each model and update it
    for model in models:
        model_id = model.get('id', 'unknown')
        model_name = model.get('name', 'unknown')
        current_base_model = model.get('base_model_id', 'unknown')
        
        # Skip if we couldn't get a valid ID
        if model_id == 'unknown' or model_id is None:
            log("WARNING", f"Skipping model with missing ID. Model data: {json.dumps(model)}")
            continue
        
        log("INFO", f"Processing model: {model_name} (ID: {model_id})")
        log("INFO", f"Current base model: {current_base_model}")
        
        # Create a complete update payload, preserving all existing fields
        # and only updating the base_model_id
        update_payload = model.copy()
        update_payload['base_model_id'] = config['target_model']
        
        # Ensure required fields are present
        if 'name' not in update_payload:
            update_payload['name'] = model_name
        
        if 'meta' not in update_payload:
            update_payload['meta'] = {
                "profile_image_url": "/static/favicon.png",
                "description": f"{model_name} using {config['target_model']}",
                "capabilities": {}
            }
        
        if 'params' not in update_payload:
            update_payload['params'] = {}
        
        log("DEBUG", f"Update payload: {json.dumps(update_payload)}")
        
        # Update the model
        log("INFO", f"Updating model {model_name} to use {config['target_model']}...")
        
        # Try different update endpoints
        update_endpoints = [
            "/models/model/update",
            "/models/update"
        ]
        
        update_success = False
        
        for update_endpoint in update_endpoints:
            update_response = make_api_call("POST", update_endpoint, data=update_payload, params={"id": model_id})
            
            log("DEBUG", f"Update response: {json.dumps(update_response) if isinstance(update_response, (dict, list)) else update_response}")
            
            # Check if the update was successful
            if update_response and isinstance(update_response, dict) and update_response.get('id') == model_id:
                log("SUCCESS", f"Successfully updated model: {model_name}")
                successful_updates += 1
                update_success = True
                break
        
        if not update_success:
            log("ERROR", f"Failed to update model: {model_name}")
        
        # Add a small delay to avoid overwhelming the API
        time.sleep(1)
    
    # Summary
    log("INFO", "Model update process completed")
    log("INFO", f"Successfully updated {successful_updates} out of {model_count} models to use {config['target_model']}")
    
    if successful_updates < model_count:
        log("WARNING", "Some models could not be updated. Please check the logs above for details")
    else:
        log("SUCCESS", f"All models have been successfully updated to use {config['target_model']}")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Update all models in OpenWebUI to use a specific model')
    parser.add_argument('--url', help='OpenWebUI URL')
    parser.add_argument('--api-path', help='API base path')
    parser.add_argument('--target-model', help='Target model to update to')
    parser.add_argument('--api-key', help='API key for authentication')
    parser.add_argument('--cf-id', help='Cloudflare Access Client ID')
    parser.add_argument('--cf-secret', help='Cloudflare Access Client Secret')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Create config from default and command line arguments
    config = DEFAULT_CONFIG.copy()
    
    if args.url:
        config['openwebui_url'] = args.url
    if args.api_path:
        config['api_base_path'] = args.api_path
    if args.target_model:
        config['target_model'] = args.target_model
    if args.api_key:
        config['api_key'] = args.api_key
    if args.cf_id:
        config['cf_access_client_id'] = args.cf_id
    if args.cf_secret:
        config['cf_access_client_secret'] = args.cf_secret
    if args.debug:
        config['debug'] = True
    
    # Run the update process
    update_models()