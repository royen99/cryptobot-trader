#!/bin/bash

# Read coins.json and output only the coin name if enabled.
# Example coins.json structure:
# {
#   "coins": {
#     "AVAX": {
#       "enabled": true
#     },
#     "ETH": {
#       "enabled": false
#     },
#     "BTC": {
#       "enabled": true
#     }
#   }
# }

jq -r '.coins | to_entries[] | select(.value.enabled == true) | .key' coins.json