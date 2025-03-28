#!/usr/bin/env python3
"""
Script to update all models in OpenWebUI to a user-specified base model
This script uses the OpenWebUI API directly via the container's IP address
Created: 2025-03-28
"""

import requests
import json
import sys
import time
from datetime import datetime
import argparse
from colorama import init, Fore, Style
import concurrent.futures

# Try to import tqdm, implement a simple version if not available
try:
    from tqdm import tqdm
except ImportError:
    print("tqdm not installed, using simple progress indicator")
    class SimpleTqdm:
        def __init__(self, total, desc=None, unit=None):
            self.total = total
            self.desc = desc or ""
            self.unit = unit or ""
            self.n = 0
            self.last_print = 0
            print(f"{self.desc}: 0/{self.total} {self.unit} (0%)")
            
        def update(self, n=1):
            self.n += n
            # Only print every 5% to avoid console spam
            current_percent = int(self.n / self.total * 100)
            if current_percent >= self.last_print + 5 or self.n == self.total:
                self.last_print = current_percent
                print(f"{self.desc}: {self.n}/{self.total} {self.unit} ({current_percent}%)")
                
        def close(self):
            print(f"{self.desc}: {self.n}/{self.total} {self.unit} (100%) - Complete")
    
    tqdm = SimpleTqdm

# Initialize colorama
init()

# Configuration
DEFAULT_CONFIG = {
    "openwebui_url": "http://docker-ip-address-for-db-container-or-owui:8080",
    "api_base_path": "/api/v1",
    "default_target_model": "openrouter.google/gemini-2.5-pro-exp-03-25:free",
    "api_key": "replace-with-your-key",
    "debug": False,
    "batch_mode": True,  # Default to batch mode
    "max_workers": 10    # Number of parallel workers
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
        "Content-Type": "application/json"
    }
    
    if config["debug"]:
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
            if config["debug"]:
                log("DEBUG", f"Response is not JSON: {response.text[:500]}")
            return response.text
            
    except requests.exceptions.RequestException as e:
        log("ERROR", f"API call failed: {str(e)}")
        return None

def update_single_model(model, target_model, progress_bar=None):
    """
    Update a single model to use the target base model
    Returns True if successful, False otherwise
    """
    model_id = model.get('id', 'unknown')
    model_name = model.get('name', 'unknown')
    current_base_model = model.get('base_model_id', 'unknown')
    
    # Skip if we couldn't get a valid ID
    if model_id == 'unknown' or model_id is None:
        if progress_bar:
            progress_bar.update(1)
        return False
    
    # Skip if the model already uses the target model
    if current_base_model == target_model:
        if progress_bar:
            progress_bar.update(1)
        return True
    
    # Create a complete update payload, preserving all existing fields
    # and only updating the base_model_id
    update_payload = model.copy()
    update_payload['base_model_id'] = target_model
    
    # Ensure required fields are present
    if 'name' not in update_payload:
        update_payload['name'] = model_name
    
    if 'meta' not in update_payload:
        update_payload['meta'] = {
            "profile_image_url": "/static/favicon.png",
            "description": f"{model_name} using {target_model}",
            "capabilities": {}
        }
    
    if 'params' not in update_payload:
        update_payload['params'] = {}
    
    # Update the model - try the most likely endpoint first
    update_endpoint = "/models/model/update"
    update_response = make_api_call("POST", update_endpoint, data=update_payload, params={"id": model_id})
    
    # If first attempt fails, try alternative endpoint
    if not (update_response and isinstance(update_response, dict) and update_response.get('id') == model_id):
        update_endpoint = "/models/update"
        update_response = make_api_call("POST", update_endpoint, data=update_payload, params={"id": model_id})
    
    success = update_response and isinstance(update_response, dict) and update_response.get('id') == model_id
    
    if progress_bar:
        progress_bar.update(1)
    
    return success

def update_models():
    """
    Main function to update all models in OpenWebUI
    """
    log("INFO", "Starting model update process...")
    
    # Use hardcoded target model
    target_model = "openrouter.google/gemini-2.5-pro-exp-03-25:free"
    log("INFO", f"Using target model: {target_model}")
    log("INFO", f"Using OpenWebUI URL: {config['openwebui_url']}{config['api_base_path']}")
    
    # Fetch models - try the most common endpoint first
    log("INFO", "Fetching models...")
    models_response = make_api_call("GET", "/models")
    
    # If first attempt fails, try alternatives
    if not (models_response and isinstance(models_response, list)):
        for endpoint in ["/models/", "/models/list", "/v1/models"]:
            models_response = make_api_call("GET", endpoint)
            if models_response and (isinstance(models_response, list) or 
                                   (isinstance(models_response, dict) and 
                                    ('models' in models_response or 'data' in models_response))):
                break
    
    # Extract models from response
    if isinstance(models_response, dict):
        models = models_response.get('models', models_response.get('data', []))
    else:
        models = models_response if isinstance(models_response, list) else []
    
    model_count = len(models)
    
    if model_count == 0:
        log("ERROR", "No models found in the API response")
        sys.exit(1)
    
    log("INFO", f"Found {model_count} models to update")
    
    # Create progress bar
    progress_bar = tqdm(total=model_count, desc="Updating models", unit="model")
    
    # Initialize counters
    successful_updates = 0
    failed_updates = 0
    skipped_updates = 0
    
    # Process models in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=config["max_workers"]) as executor:
        # Submit all tasks
        future_to_model = {
            executor.submit(update_single_model, model, target_model, progress_bar): model
            for model in models
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_model):
            model = future_to_model[future]
            model_name = model.get('name', 'unknown')
            
            try:
                success = future.result()
                if success:
                    successful_updates += 1
                else:
                    current_base_model = model.get('base_model_id', 'unknown')
                    if current_base_model == target_model:
                        skipped_updates += 1
                    else:
                        failed_updates += 1
            except Exception as e:
                log("ERROR", f"Exception updating model {model_name}: {str(e)}")
                failed_updates += 1
    
    # Close progress bar
    progress_bar.close()
    
    # Summary
    log("INFO", "Model update process completed")
    log("INFO", f"Successfully updated: {successful_updates} models")
    log("INFO", f"Skipped (already using target model): {skipped_updates} models")
    log("INFO", f"Failed to update: {failed_updates} models")
    
    if failed_updates > 0:
        log("WARNING", "Some models could not be updated")
    else:
        log("SUCCESS", f"All applicable models have been successfully updated to use {target_model}")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Update all models in OpenWebUI to use a specific model')
    parser.add_argument('--url', help='OpenWebUI URL')
    parser.add_argument('--api-path', help='API base path')
    parser.add_argument('--api-key', help='API key for authentication')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--no-batch', action='store_true', help='Disable batch mode (not recommended)')
    parser.add_argument('--workers', type=int, help='Number of parallel workers')
    
    args = parser.parse_args()
    
    # Create config from default and command line arguments
    config = DEFAULT_CONFIG.copy()
    
    if args.url:
        config['openwebui_url'] = args.url
    if args.api_path:
        config['api_base_path'] = args.api_path
    if args.api_key:
        config['api_key'] = args.api_key
    if args.debug:
        config['debug'] = True
    if args.no_batch:
        config['batch_mode'] = False
    if args.workers:
        config['max_workers'] = args.workers
    
    # Run the update process
    update_models()
