#!/bin/bash
# Build script for LLM Proxy Docker images

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME=${IMAGE_NAME:-"llmproxy"}
VERSION=${VERSION:-"latest"}
TARGET=${TARGET:-"production"}

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    # Enable BuildKit
    export DOCKER_BUILDKIT=1
    
    log_info "Prerequisites OK"
}

# Build image
build_image() {
    log_info "Building image: ${IMAGE_NAME}:${VERSION} (target: ${TARGET})"
    
    docker build \
        --target "${TARGET}" \
        -t "${IMAGE_NAME}:${VERSION}" \
        -t "${IMAGE_NAME}:latest" \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --cache-from "${IMAGE_NAME}:latest" \
        .
    
    log_info "Build completed successfully"
}

# Show image info
show_info() {
    log_info "Image information:"
    docker images "${IMAGE_NAME}:${VERSION}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    
    echo ""
    log_info "Layer information:"
    docker history "${IMAGE_NAME}:${VERSION}" --format "table {{.Size}}\t{{.CreatedBy}}" | head -20
}

# Run tests
run_tests() {
    log_info "Running container tests..."
    
    # Test that container starts
    CONTAINER_ID=$(docker run -d --rm -p 8080:8080 "${IMAGE_NAME}:${VERSION}")
    
    # Wait for health check
    log_info "Waiting for health check..."
    sleep 5
    
    # Test health endpoint
    if curl -f http://localhost:8080/health &> /dev/null; then
        log_info "Health check passed"
    else
        log_error "Health check failed"
        docker logs "${CONTAINER_ID}"
        docker stop "${CONTAINER_ID}"
        exit 1
    fi
    
    # Stop test container
    docker stop "${CONTAINER_ID}" &> /dev/null
    log_info "Tests passed"
}

# Security scan
security_scan() {
    if command -v trivy &> /dev/null; then
        log_info "Running security scan..."
        trivy image --exit-code 0 --severity HIGH,CRITICAL "${IMAGE_NAME}:${VERSION}"
    else
        log_warn "Trivy not installed, skipping security scan"
        log_info "Install Trivy: https://aquasecurity.github.io/trivy/"
    fi
}

# Push to registry
push_image() {
    if [ -n "${REGISTRY}" ]; then
        log_info "Pushing to registry: ${REGISTRY}"
        
        docker tag "${IMAGE_NAME}:${VERSION}" "${REGISTRY}/${IMAGE_NAME}:${VERSION}"
        docker tag "${IMAGE_NAME}:${VERSION}" "${REGISTRY}/${IMAGE_NAME}:latest"
        
        docker push "${REGISTRY}/${IMAGE_NAME}:${VERSION}"
        docker push "${REGISTRY}/${IMAGE_NAME}:latest"
        
        log_info "Push completed"
    fi
}

# Main
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --target|-t)
                TARGET="$2"
                shift 2
                ;;
            --version|-v)
                VERSION="$2"
                shift 2
                ;;
            --registry|-r)
                REGISTRY="$2"
                shift 2
                ;;
            --test)
                RUN_TESTS=1
                shift
                ;;
            --scan)
                RUN_SCAN=1
                shift
                ;;
            --push)
                PUSH_IMAGE=1
                shift
                ;;
            --all)
                RUN_TESTS=1
                RUN_SCAN=1
                PUSH_IMAGE=1
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --target, -t     Build target (production|development|builder)"
                echo "  --version, -v    Image version tag"
                echo "  --registry, -r   Docker registry URL"
                echo "  --test           Run container tests"
                echo "  --scan           Run security scan"
                echo "  --push           Push to registry"
                echo "  --all            Run tests, scan, and push"
                echo "  --help, -h       Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Execute
    check_prerequisites
    build_image
    show_info
    
    if [ -n "${RUN_TESTS}" ]; then
        run_tests
    fi
    
    if [ -n "${RUN_SCAN}" ]; then
        security_scan
    fi
    
    if [ -n "${PUSH_IMAGE}" ]; then
        push_image
    fi
    
    log_info "Build script completed"
}

main "$@"
