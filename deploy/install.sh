#!/bin/bash
# JARVIS MK1 Lite Installation Script
# This script installs JARVIS MK1 Lite as a systemd service on Ubuntu VPS
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Variables
INSTALL_DIR=/opt/jarvis-mk1
VENV_DIR=$INSTALL_DIR/venv
SERVICE_USER=jarvis

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Error handler
handle_error() {
    log_error "Installation failed at line $1"
    log_error "Please check the error above and try again"
    exit 1
}

trap 'handle_error $LINENO' ERR

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Starting JARVIS MK1 Lite installation..."

# Check prerequisites
log_info "Checking prerequisites..."

# Find available Python 3.11+
PYTHON_CMD=""
for py in python3.12 python3.11 python3; do
    if command -v $py &> /dev/null; then
        PY_VERSION=$($py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
        PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
        if [[ $PY_MAJOR -ge 3 && $PY_MINOR -ge 11 ]]; then
            PYTHON_CMD=$py
            log_info "Found Python $PY_VERSION at $(which $py)"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    log_error "Python 3.11+ is required but not found"
    log_error "Please install Python 3.11 or later:"
    log_error "  sudo apt update && sudo apt install python3.11 python3.11-venv"
    exit 1
fi

# Check for required files
if [[ ! -f "pyproject.toml" ]]; then
    log_error "pyproject.toml not found. Please run this script from the project root directory"
    exit 1
fi

if [[ ! -f ".env" ]]; then
    log_warn ".env file not found. Please create it from .env.production.example"
    log_warn "  cp .env.production.example .env && nano .env"
fi

# Create service user if it doesn't exist
log_info "Setting up service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d $INSTALL_DIR -c "JARVIS MK1 Service User" $SERVICE_USER
    log_info "Created service user: $SERVICE_USER"
else
    log_info "Service user $SERVICE_USER already exists"
fi

# Create installation directory
log_info "Creating installation directory..."
mkdir -p $INSTALL_DIR

# Backup existing installation if present
if [[ -d "$INSTALL_DIR/src" ]]; then
    log_warn "Existing installation found, creating backup..."
    BACKUP_DIR="${INSTALL_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
    cp -r $INSTALL_DIR $BACKUP_DIR
    log_info "Backup created at: $BACKUP_DIR"
fi

# Copy files
log_info "Copying project files..."
cp -r src/ $INSTALL_DIR/
cp -r prompts/ $INSTALL_DIR/
cp pyproject.toml $INSTALL_DIR/
if [[ -f ".env" ]]; then
    cp .env $INSTALL_DIR/
fi

# Create virtual environment and install
log_info "Creating virtual environment with $PYTHON_CMD..."
$PYTHON_CMD -m venv $VENV_DIR

log_info "Installing dependencies..."
$VENV_DIR/bin/pip install --upgrade pip
$VENV_DIR/bin/pip install -e $INSTALL_DIR

# Set permissions
log_info "Setting permissions..."
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR

# Install systemd service
log_info "Installing systemd service..."
cp deploy/jarvis.service /etc/systemd/system/
systemctl daemon-reload

# Enable and start service
log_info "Enabling and starting service..."
systemctl enable jarvis
systemctl start jarvis

# Verify service is running
sleep 2
if systemctl is-active --quiet jarvis; then
    log_info "Service started successfully!"
else
    log_error "Service failed to start. Check logs with: journalctl -u jarvis -f"
    exit 1
fi

echo ""
log_info "============================================"
log_info "JARVIS MK1 Lite installed successfully!"
log_info "============================================"
echo ""
log_info "Useful commands:"
log_info "  Status:   systemctl status jarvis"
log_info "  Logs:     journalctl -u jarvis -f"
log_info "  Restart:  systemctl restart jarvis"
log_info "  Stop:     systemctl stop jarvis"
echo ""
