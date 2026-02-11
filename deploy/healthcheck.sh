#!/bin/bash
# Check if JARVIS service is running
if systemctl is-active --quiet jarvis; then
    echo "JARVIS is running"
    exit 0
else
    echo "JARVIS is NOT running"
    exit 1
fi
