#!/bin/bash
# =============================================================================
# Sovereign Backend Deployment Script
# =============================================================================
# Usage: ./deploy.sh [--rebuild] [--test]
#
# This script deploys the Sovereign Backend to the production VPS.
# It builds a new Docker image and restarts the service with automatic migrations.
#
# Requirements:
# - SSH access to VPS with root privileges
# - Docker and docker-compose installed on VPS
# - Environment variables configured in .env file
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VPS_HOST="${VPS_HOST:-46.202.154.25}"
VPS_PORT="${VPS_PORT:-22}"
VPS_USER="${VPS_USER:-root}"
REMOTE_PATH="/opt/sovereign-backend"
SERVICE_NAME="sovereign-backend"

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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
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
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        cd ${REMOTE_PATH} && \
        cp -r app.py app.py.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true && \
        cp docker-compose.yml docker-compose.yml.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true && \
        cp Dockerfile Dockerfile.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true"
}

deploy_files() {
    log_info "Deploying files to VPS..."
    
    # Create a temporary directory for files
    TEMP_DIR=$(mktemp -d)
    
    # Copy necessary files
    cp app.py "${TEMP_DIR}/"
    cp Dockerfile "${TEMP_DIR}/"
    cp docker-compose.yml "${TEMP_DIR}/"
    cp auto-migrate.sh "${TEMP_DIR}/"
    cp .env.example "${TEMP_DIR}/" 2>/dev/null || true
    
    # Upload files
    scp -P "${VPS_PORT}" \
        "${TEMP_DIR}/app.py" \
        "${TEMP_DIR}/Dockerfile" \
        "${TEMP_DIR}/docker-compose.yml" \
        "${TEMP_DIR}/auto-migrate.sh" \
        "${VPS_USER}@${VPS_HOST}:${REMOTE_PATH}/"
    
    # Cleanup
    rm -rf "${TEMP_DIR}"
    
    log_info "Files deployed successfully"
}

rebuild_container() {
    log_step "Rebuilding Docker container..."
    
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        cd ${REMOTE_PATH} && \
        chmod +x auto-migrate.sh && \
        docker compose down && \
        docker compose up -d --build"
    
    log_info "Container rebuilt successfully"
}

start_container() {
    log_step "Starting Docker container..."
    
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        cd ${REMOTE_PATH} && \
        docker compose up -d"
    
    log_info "Container started successfully"
}

restart_container() {
    log_step "Restarting Docker container..."
    
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        cd ${REMOTE_PATH} && \
        docker compose restart"
    
    log_info "Container restarted successfully"
}

check_service() {
    log_info "Checking service health..."
    
    local status=$(ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        curl -s -k -o /dev/null -w '%{http_code}' https://localhost:8788/api/admin/ping 2>/dev/null || \
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
    log_info "Recent container logs:"
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        docker logs --tail 20 ${SERVICE_NAME}-1 2>&1 || \
        echo 'No logs available'"
}

show_status() {
    log_info "Container status:"
    ssh -p "${VPS_PORT}" "${VPS_USER}@${VPS_HOST}" "\
        docker ps --filter 'name=${SERVICE_NAME}' 2>/dev/null || \
        echo 'Container not running'"
}

# =============================================================================
# Main Script
# =============================================================================

main() {
    echo "========================================"
    echo " Sovereign Backend Deployment Script"
    echo "========================================"
    echo ""
    
    # Parse arguments
    local do_rebuild=false
    local do_restart=false
    local do_test=false
    
    for arg in "$@"; do
        case $arg in
            --rebuild|-r)
                do_rebuild=true
                ;;
            --restart|-s)
                do_restart=true
                ;;
            --test|-t)
                do_test=true
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --rebuild, -r    Rebuild Docker image and restart (full deploy)"
                echo "  --restart, -s    Restart container without rebuilding"
                echo "  --test, -t       Test deployment without restarting"
                echo "  --help, -h       Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0 --rebuild     # Full rebuild and deploy"
                echo "  $0 --restart    # Just restart the container"
                echo "  $0 --test       # Deploy files without restart"
                exit 0
                ;;
        esac
    done
    
    # Check SSH connection
    check_ssh
    
    # Deployment steps
    echo ""
    log_step "Starting deployment to ${VPS_HOST}..."
    echo ""
    
    # Always backup current deployment
    backup_current
    
    # Deploy files
    deploy_files
    
    if [ "$do_rebuild" = true ]; then
        # Full rebuild
        rebuild_container
        sleep 5
        show_status
        check_service
    elif [ "$do_restart" = true ]; then
        # Just restart
        restart_container
        sleep 3
        show_status
        check_service
    elif [ "$do_test" = true ]; then
        log_info "Test mode: files deployed, no restart performed"
    else
        # Default: just start (for updates that don't need rebuild)
        start_container
        sleep 3
        show_status
        check_service
    fi
    
    echo ""
    show_logs
    
    echo ""
    echo "========================================"
    log_info "Deployment completed!"
    echo "========================================"
    echo ""
    echo "Admin Panel: https://sovereign-backend.arelorian.de/admin"
    echo "API Key: Use the key configured in .env file"
    echo ""
}

# Run main function
main "$@"
