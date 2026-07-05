#!/bin/bash
# =============================================================================
# Sovereign Backend Deployment Script
# =============================================================================
# Usage: ./deploy.sh [--restart] [--test]
#
# This script deploys the Sovereign Backend to the production VPS.
# It pulls the latest changes from the repository and restarts the service.
#
# Requirements:
# - SSH access to VPS with root privileges
# - Git repository with latest code
# - Environment variables configured on VPS
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
VPS_HOST="${VPS_HOST:-arelorian.de}"
VPS_PORT="${VPS_PORT:-21}"
VPS_USER="${VPS_USER:-root}"
REPO_PATH="/opt/sovereign-backend"
SERVICE_NAME="sovereign-backend"
BACKEND_PORT="${BACKEND_PORT:-8080}"

# =============================================================================
# Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_ssh() {
    log_info "Checking SSH connection to ${VPS_USER}@${VPS_HOST}:${VPS_PORT}..."
    ssh -p "${VPS_PORT}" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" "echo 'SSH OK' && uname -a" || {
        log_error "SSH connection failed. Check credentials and network."
        exit 1
    }
}

backup_current() {
    log_info "Creating backup of current deployment..."
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "cd ${REPO_PATH} && \
        cp -r app.py app.py.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true"
}

pull_latest() {
    log_info "Pulling latest code from repository..."
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "cd ${REPO_PATH} && \
        git pull origin main || git pull origin master"
}

install_dependencies() {
    log_info "Installing Python dependencies..."
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "cd ${REPO_PATH} && \
        pip3 install --quiet psycopg2-binary flask flask-cors requests gunicorn || \
        pip install --quiet psycopg2-binary flask flask-cors requests gunicorn"
}

restart_service() {
    log_info "Restarting ${SERVICE_NAME} service..."
    
    # Try different service management approaches
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        if command -v systemctl &> /dev/null; then \
            systemctl restart ${SERVICE_NAME} || true; \
        fi; \
        if command -v service &> /dev/null; then \
            service ${SERVICE_NAME} restart 2>/dev/null || true; \
        fi; \
        # Fallback: kill and restart manually
        pkill -f 'python.*app.py' 2>/dev/null || true; \
        sleep 2; \
        cd ${REPO_PATH} && \
        nohup python3 app.py > /var/log/${SERVICE_NAME}.log 2>&1 &"
}

check_service() {
    log_info "Checking service health..."
    sleep 3
    
    local status=$(ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        curl -s -o /dev/null -w '%{http_code}' http://localhost:${BACKEND_PORT}/health 2>/dev/null || \
        curl -s -o /dev/null -w '%{http_code}' http://localhost:${BACKEND_PORT}/api/admin/ping 2>/dev/null || \
        echo '000'")
    
    if [ "$status" = "200" ] || [ "$status" = "401" ]; then
        log_info "Service is running (HTTP ${status})"
        return 0
    else
        log_warn "Service health check returned HTTP ${status}"
        return 1
    fi
}

show_logs() {
    log_info "Recent service logs:"
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "tail -20 /var/log/${SERVICE_NAME}.log 2>/dev/null || \
        journalctl -u ${SERVICE_NAME} -n 20 2>/dev/null || \
        echo 'No logs available'"
}

# =============================================================================
# Main Script
# =============================================================================

main() {
    echo "========================================"
    echo "Sovereign Backend Deployment Script"
    echo "========================================"
    echo ""
    
    # Parse arguments
    local do_restart=false
    local do_test=false
    
    for arg in "$@"; do
        case $arg in
            --restart|-r)
                do_restart=true
                ;;
            --test|-t)
                do_test=true
                ;;
            --help|-h)
                echo "Usage: $0 [--restart] [--test]"
                echo ""
                echo "Options:"
                echo "  --restart, -r    Restart the service after deployment"
                echo "  --test, -t       Test deployment without restarting"
                echo "  --help, -h       Show this help message"
                exit 0
                ;;
        esac
    done
    
    # Check SSH connection
    check_ssh
    
    # Deployment steps
    log_info "Starting deployment to ${VPS_HOST}..."
    
    backup_current
    pull_latest
    install_dependencies
    
    if [ "$do_restart" = true ]; then
        restart_service
        sleep 2
        check_service
    fi
    
    if [ "$do_test" = true ]; then
        log_info "Test mode: skipping service restart"
    fi
    
    show_logs
    
    echo ""
    log_info "Deployment completed!"
    echo ""
    echo "Next steps:"
    echo "  1. Visit https://sovereign-backend.arelorian.de/admin"
    echo "  2. Check the Audit Log for deployment events"
    echo "  3. Run health checks on LLM routes and tools"
}

# Run main function
main "$@"
