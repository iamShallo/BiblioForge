#!/usr/bin/env python
"""Test script to verify sheets sync configuration is valid."""

import json
from pathlib import Path

# Test 1: Check if config file exists
config_path = Path("biblioforge/data/processed/sheets_sync_config.json")
print(f"Config file exists: {config_path.exists()}")

if config_path.exists():
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    print(f"Config loaded: {json.dumps(config_data, indent=2)}")
    
    # Test 2: Check if service account file can be resolved
    service_account_file = config_data.get("service_account_file", "")
    print(f"\nService account file path from config: {service_account_file}")
    
    # Simulate resolution logic
    project_root = Path(__file__).resolve().parent
    package_root = project_root / "biblioforge"
    state_path = package_root / "data" / "processed" / "sheets_sync_state.json"
    state_path_parent = state_path.parent
    
    print(f"Project root: {project_root}")
    print(f"Package root: {package_root}")
    print(f"State path parent: {state_path_parent}")
    
    # Test candidates
    candidates = [
        Path.cwd() / service_account_file,
        state_path_parent / service_account_file,
        package_root / service_account_file,
        project_root / service_account_file,
    ]
    
    print("\nTesting candidates:")
    for i, candidate in enumerate(candidates):
        exists = candidate.exists()
        print(f"  {i+1}. {candidate} -> exists: {exists}")
        if exists:
            print(f"     ✓ FOUND!")
            break
    else:
        print("  ✗ File not found in any candidate")
    
    # Test 3: Check if the actual file exists in processed directory
    print(f"\nDirect file check in processed directory:")
    actual_file = Path("biblioforge/data/processed/la-cicogna-triste-3e46a5bc4715.json")
    print(f"  {actual_file} -> exists: {actual_file.exists()}")
    if actual_file.exists():
        sa_data = json.loads(actual_file.read_text(encoding="utf-8"))
        print(f"  Service account type: {sa_data.get('type')}")
        print(f"  Project ID: {sa_data.get('project_id')}")
        print(f"  ✓ Service account file is valid")

