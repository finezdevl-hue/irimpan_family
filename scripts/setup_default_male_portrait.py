#!/usr/bin/env python
"""
Script to set up custom default male portrait image.

Usage:
    Place your custom male portrait image at:
    media/photos/custom_male_portrait.jpg
    
    Then run:
    python scripts/setup_default_male_portrait.py
    
    The script will copy it to default-male-portrait.jpg
"""

import os
import shutil
from pathlib import Path

def setup_default_portrait():
    """Copy custom male portrait to default location."""
    base_dir = Path(__file__).resolve().parent.parent
    photos_dir = base_dir / 'media' / 'photos'
    
    custom_source = photos_dir / 'custom_male_portrait.jpg'
    default_dest = photos_dir / 'default-male-portrait.jpg'
    
    if not custom_source.exists():
        print(f"❌ Error: Custom portrait not found at {custom_source}")
        print("\nPlease place your custom male portrait image at:")
        print(f"  {custom_source}")
        print("\nThen run this script again.")
        return False
    
    try:
        shutil.copy2(custom_source, default_dest)
        print(f"✓ Successfully set custom male portrait as default!")
        print(f"  Source: {custom_source}")
        print(f"  Destination: {default_dest}")
        return True
    except Exception as e:
        print(f"❌ Error copying file: {e}")
        return False

if __name__ == '__main__':
    setup_default_portrait()
