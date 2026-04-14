"""Pytest configuration for fleet-mechanic tests."""
import sys
import os

# Ensure src/ is on the path so we can import mechanic modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
