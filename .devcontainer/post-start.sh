#!/bin/bash
echo "🔧 Fleet Mechanic Codespace Booting..."
echo "Token: $(if [ -n "$GITHUB_TOKEN" ]; then echo available; else echo MISSING - set GITHUB_TOKEN; fi)"
echo "Python: $(python3 --version)"
echo "Ready. Run: python3 boot.py"
