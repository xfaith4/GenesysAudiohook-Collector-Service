# Copilot Instructions - Genesys AudioHook Collector Service

## Project Overview

This is a Python service that collects AudioHook operational events from Genesys Cloud and ships them to Elasticsearch. The service acts as a bridge between Genesys Cloud's Notifications API and Elasticsearch, providing reliable event collection with auto-reconnection, batching, and resilience features.

### Business Domain Context

The application serves as a monitoring and observability solution for Genesys Cloud AudioHook integrations. AudioHook is Genesys Cloud's mechanism for streaming real-time audio data and operational events from phone calls to external systems. This collector specifically focuses on operational events (not audio data) that indicate the health, status, and performance of AudioHook integrations.

The service addresses several business needs:
- **Operational Monitoring**: Track AudioHook integration health and performance metrics
- **Alerting & KPIs**: Normalize operational events for downstream alerting systems
- **Historical Analysis**: Store events in Elasticsearch for trend analysis and troubleshooting
- **Resilience**: Maintain event collection even during network interruptions or service restarts

Key stakeholders include:
- **Operations Teams**: Monitor AudioHook integration health and troubleshoot issues
- **DevOps Engineers**: Deploy and maintain the collector service infrastructure
- **Business Analysts**: Analyze AudioHook usage patterns and performance trends

## Technical Architecture

### Technology Stack

- **Runtime**: Python 3.9+ (with aiohttp as the primary dependency)
- **Authentication**: OAuth2 Client Credentials flow with Genesys Cloud
- **Communication**: WebSocket connections for real-time event streaming
- **Data Storage**: Elasticsearch with configurable index patterns and data streams
- **Deployment**: Cross-platform service deployment (Windows Service, Linux systemd)

### Core System Components

**Authentication Module**: Handles OAuth2 client credentials authentication with Genesys Cloud. Manages token refresh and ensures continuous authentication for API access.

**Topic Discovery**: Auto-discovers available Notifications API topics containing AudioHook operational signals. Uses configurable regex patterns to filter relevant topics and falls back to predefined topic lists when auto-discovery is unavailable.

**WebSocket Manager**: Maintains persistent WebSocket connections to Genesys Cloud's Notifications API with automatic reconnection and resubscription capabilities. Handles connection failures gracefully and implements exponential backoff for reconnection attempts.

**Event Processing**: Normalizes incoming operational events to extract key fields like severity, entity IDs, integration IDs, and error codes. Prepares events for downstream alerting and KPI systems.

**Bulk Shipping**: Batches events and ships them to Elasticsearch using the _bulk API with configurable batch sizes, timeouts, and concurrency limits. Implements retry logic with exponential backoff for failed requests.

**Health Monitoring**: Exposes HTTP endpoints for health checks and runtime statistics to support operational monitoring and load balancer health checks.

### Configuration Management

The service uses environment variables for all configuration, enabling containerized deployments and service-based installations. Key configuration categories include:

- **Genesys Integration**: Environment, client ID, client secret
- **Topic Management**: Auto-discovery settings, include/exclude patterns, fallback topics
- **Elasticsearch**: URL, authentication, index configuration, data stream support
- **Batching Behavior**: Maximum documents per batch, batch timeouts, concurrency levels
- **Retry Logic**: Base sleep intervals, maximum sleep times for exponential backoff
- **Health Server**: Enable/disable, host binding, port configuration

## Development Standards

### Code Organization

The codebase follows a single-file architecture (`collector.py`) with clear functional separation:

- **Configuration Loading**: Environment variable processing with type conversion and defaults
- **Authentication Handling**: Token management and refresh logic
- **Topic Management**: Discovery, filtering, and subscription management  
- **WebSocket Operations**: Connection management, message handling, reconnection logic
- **Event Processing**: Normalization, transformation, and preparation for Elasticsearch
- **Bulk Operations**: Batching, shipping, retry logic, and error handling
- **Health Endpoints**: Statistics collection and HTTP server management

### Python Coding Standards

**Type Hints**: Use type annotations for function parameters and return values to improve code clarity and enable better IDE support.

**Async/Await Patterns**: Leverage asyncio properly with aiohttp for all I/O operations. Avoid blocking calls in async contexts and use appropriate async context managers.

**Error Handling**: Implement comprehensive error handling with specific exception types. Log errors with appropriate severity levels and include context for troubleshooting.

**Configuration Validation**: Validate all environment variables at startup and fail fast with clear error messages for missing or invalid configuration.

**Resource Management**: Use async context managers for HTTP sessions, WebSocket connections, and other resources. Ensure proper cleanup in exception scenarios.

### Logging and Monitoring

**Structured Logging**: Use consistent log formats with structured data (JSON) for operational events. Include correlation IDs and timestamps for distributed tracing.

**Metrics Collection**: Maintain in-memory counters for success/error rates, batch processing statistics, and connection health metrics. Expose these via the `/stats` endpoint.

**Health Checks**: Implement comprehensive health checks that verify Genesys Cloud connectivity, Elasticsearch availability, and WebSocket connection status.

## Genesys Cloud Integration Patterns

### OAuth2 Authentication Flow

Implement the client credentials grant type for machine-to-machine authentication. Handle token expiration gracefully with automatic refresh. Store tokens securely and never log sensitive authentication data.

### Notifications API Usage

Subscribe to relevant topic patterns that contain AudioHook operational data. Handle subscription acknowledgments and resubscribe after connection interruptions. Implement proper topic filtering to avoid processing irrelevant events.

### Event Processing Patterns

**Event Normalization**: Extract standardized fields from Genesys event payloads including:
- Event timestamps and severity levels
- Entity identifiers (conversation IDs, participant IDs, integration IDs)
- Error codes and descriptive messages
- AudioHook-specific operational metrics

**Event Enrichment**: Add metadata fields for downstream processing such as:
- Collection timestamps
- Service instance identifiers
- Processing pipeline markers

### Error Scenarios and Resilience

**Connection Failures**: Implement exponential backoff for WebSocket reconnection attempts. Log connection attempts and failures with appropriate detail for troubleshooting.

**Authentication Expiration**: Detect authentication failures and refresh tokens automatically. Handle edge cases where token refresh fails during active connections.

**Elasticsearch Outages**: Queue events in memory during Elasticsearch unavailability with configurable limits. Implement circuit breaker patterns to avoid overwhelming failed services.

## Deployment and Operations

### Service Installation Patterns

**Windows Deployment**: Support installation as a Windows Service using PowerShell scripts. Include service registration, startup configuration, and log file management.

**Linux Deployment**: Support systemd service installation with proper dependency management and automatic restart configuration.

**Container Deployment**: Support Docker containerization with appropriate health checks, volume mounts for configuration, and proper signal handling for graceful shutdowns.

### Configuration Management

**Environment Variables**: Use a comprehensive .env file pattern with clear documentation for all configuration options. Provide sensible defaults for non-critical settings.

**Secret Management**: Support multiple authentication patterns for Elasticsearch (basic auth, API keys, bearer tokens) and ensure secrets are not logged or exposed.

**Topic Configuration**: Support both auto-discovery and manual topic configuration through JSON files. Allow runtime topic list updates without service restart.

### Operational Monitoring

**Health Endpoints**: Provide `/health` for basic service status and `/stats` for detailed operational metrics. Return appropriate HTTP status codes for automated monitoring systems.

**Log Management**: Generate structured logs suitable for centralized logging systems. Include sufficient detail for troubleshooting without overwhelming log volumes.

**Performance Metrics**: Track and expose metrics for batch processing rates, WebSocket connection stability, and Elasticsearch indexing success rates.

## AI Assistant Guidelines

### Code Generation Preferences

**Async Patterns**: When generating WebSocket or HTTP client code, always use async/await patterns with proper context managers. Avoid synchronous blocking calls in the asyncio event loop.

**Error Handling**: Generate comprehensive error handling with specific exception types. Include retry logic with exponential backoff for network operations.

**Configuration Processing**: When adding new configuration options, follow the existing pattern of environment variable loading with type conversion and validation.

### Testing Approach

**Unit Tests**: Generate tests that mock external dependencies (Genesys Cloud API, Elasticsearch) and focus on business logic validation.

**Integration Tests**: Create tests that validate end-to-end workflows using test fixtures and mock services. Include scenarios for connection failures and recovery.

**Configuration Tests**: Validate that all configuration combinations work correctly and that invalid configurations are rejected with clear error messages.

### Documentation Requirements

**Inline Documentation**: Generate docstrings for all functions and classes with parameter descriptions and return value specifications. Include usage examples for complex functions.

**Configuration Documentation**: Update environment variable documentation when adding new configuration options. Include example values and explain the impact of different settings.

**Deployment Documentation**: Maintain installation and configuration documentation for different deployment scenarios (Windows, Linux, Docker).

### Performance Considerations

**Memory Management**: Be mindful of memory usage when batching events. Implement appropriate limits and monitoring to prevent memory exhaustion.

**Connection Pooling**: Use connection pooling for HTTP clients and implement appropriate timeouts for all network operations.

**Batching Optimization**: Consider batch size optimization based on Elasticsearch cluster capacity and network latency characteristics.

This context enables AI-assisted development that understands both the technical requirements of real-time event collection and the specific business needs of Genesys Cloud AudioHook monitoring and observability.