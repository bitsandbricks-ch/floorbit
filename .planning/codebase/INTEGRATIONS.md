# External Integrations

**Analysis Date:** 2026-02-20

## APIs & External Services

**Network Infrastructure:**
- NetBox - Network inventory and device management
  - SDK/Client: requests library (REST API)
  - Auth: Token-based (`NETBOX_TOKEN`)
  - Endpoint: `/api/dcim/devices/`
  - Features: Device listing, role filtering, pagination support

- LibreNMS - Network monitoring and device health
  - SDK/Client: requests library (REST API)
  - Auth: X-Auth-Token header (`LIBRENMS_TOKEN`)
  - Endpoints: `/api/v0/devices/`, `/api/v0/devices/{id}/health/`
  - Features: Device discovery, CPU/memory monitoring, port status, traffic analysis

## Data Storage

**Databases:**
- Local JSON file - Primary data persistence
  - Location: `data.json`
  - Stores: Switch positions, floorplan, cached devices
  - Client: Native JSON operations

**File Storage:**
- Local filesystem - Static file uploads
  - Location: `static/uploads/`
  - Features: Floorplan image uploads, UUID-based filename generation
  - Allowed formats: PNG, JPG, JPEG, GIF, SVG, WebP

**Caching:**
- In-memory caching - Device data from NetBox
  - Persistence: Saved to `data.json`
  - Refresh: Via `/api/switches/sync` endpoint

## Authentication & Identity

**Auth Provider:**
- Custom - Basic token-based authentication
  - Implementation: REST API tokens for external services
  - No user authentication required for web interface

## Monitoring & Observability

**Error Tracking:**
- Basic HTTP error handling - 404, 400, 502 responses
- Custom error messages for external API failures

**Logs:**
- Flask built-in logging
- Docker healthcheck for service monitoring

## CI/CD & Deployment

**Hosting:**
- Docker container deployment
- GitLab CI for build and push pipeline
- Port 5000 exposed

**CI Pipeline:**
- GitLab CI with 3 stages: build, test, push
- Docker build and deployment
- Healthcheck validation

## Environment Configuration

**Required env vars:**
- `NETBOX_URL` - NetBox instance URL
- `NETBOX_TOKEN` - NetBox API token
- `NETBOX_DEVICE_ROLE` - Device roles to fetch (default: access-switch)
- `NETBOX_VERIFY_SSL` - SSL verification flag
- `LIBRENMS_URL` - LibreNMS instance URL
- `LIBRENMS_TOKEN` - LibreNMS API token
- `LIBRENMS_VERIFY_SSL` - SSL verification flag

**Secrets location:**
- `.env` file for local development
- GitLab CI variables for production

## Webhooks & Callbacks

**Incoming:**
- HTTP endpoints for device management
  - `/api/switches` - CRUD operations for switches
  - `/api/floorplan` - Upload floorplan images
  - `/api/switches/<id>/status` - Device status polling

**Outgoing:**
- HTTP requests to external APIs
  - NetBox API for device listing
  - LibreNMS API for device health and status

---

*Integration audit: 2026-02-20*
```