#!/usr/bin/env python3
"""Compass production Django management CLI. Python 3.12+."""
import os
import sys
if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "compassapp.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
