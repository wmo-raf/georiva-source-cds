#!/bin/bash
set -euo pipefail
# Run by georiva when the plugin is uninstalled.
# Undo this plugin's migrations:
./georiva migrate georiva_source_cds zero
