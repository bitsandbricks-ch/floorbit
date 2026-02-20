# Architecture

**Analysis Date:** 2026-02-20

## Pattern Overview

**Overall:** Single-page application with REST backend

**Key Characteristics:**
- Flask web server serving static files and API endpoints
- Client-side JavaScript SPA with canvas-based visualization
- Real-time device monitoring with external integrations
- File-based JSON persistence
- Multi-source device management (manual + NetBox)

## Layers

**Backend Layer:**
- Purpose: API server and data persistence
- Location: `app.py`
- Contains: Flask app, API endpoints, data persistence logic, external service integrations
- Depends on: Flask, requests, python-dotenv libraries
- Used by: Frontend JavaScript via HTTP API

**Frontend Layer:**
- Purpose: User interface and visualization
- Location: `templates/index.html`, `static/js/app.js`, `static/css/style.css`
- Contains: DOM manipulation, canvas rendering, user interactions, API client
- Depends on: Browser APIs, external CSS framework
- Used by: End users via web browser

**Data Layer:**
- Purpose: Data persistence and caching
- Location: `data.json`
- Contains: Switch positions, floorplan, cached NetBox devices
- Depends on: File system
- Used by: Backend application for state persistence

**Integration Layer:**
- Purpose: External system integrations
- Location: `app.py` (NetBox and LibreNMS functions)
- Contains: API client for NetBox and LibreNMS
- Depends on: External API endpoints, authentication tokens
- Used by: Backend for real-time device monitoring

## Data Flow

**Device Status Update:**
1. Frontend triggers status refresh (manual or automatic every 10s)
2. Frontend sends GET `/api/switches/{id}/status`
3. Backend makes API calls to LibreNMS for device details
4. Backend returns status, CPU, memory, port information
5. Frontend updates UI with live data and heatmap visualization

**Device Placement:**
1. User clicks on floorplan in "Add" mode
2. Frontend calculates coordinates and opens placement modal
3. User chooses source (NetBox or manual)
4. Frontend sends POST `/api/switches` or PUT `/api/switches/{id}` with coordinates
5. Backend persists position to `data.json`
6. Frontend updates display with new switch marker

**NetBox Sync:**
1. User clicks "Sync Devices"
2. Frontend sends POST `/api/switches/sync`
3. Backend fetches all devices from NetBox API
4. Backend merges with existing positions and saves to `data.json`
5. Frontend displays unplaced devices for manual positioning

## Key Abstractions

**Switch Device:**
- Purpose: Represents a network switch with position and status
- Examples: `app.py` lines 299-307, `data.json` structure
- Pattern: Data class with id, name, position, status, source properties

**Floor Plan:**
- Purpose: Background image for device placement
- Examples: `/api/floorplan` endpoints, `static/uploads/` directory
- Pattern: File-based image with coordinate system (0-100% normalized)

**External Services:**
- Purpose: Integration with network management systems
- Examples: `fetch_netbox_devices()`, `fetch_librenms_details()` functions
- Pattern: API client with error handling and pagination support

## Entry Points

**Web Application:**
- Location: `app.py` line 211 (`@app.route('/')`)
- Triggers: HTTP GET request to root URL
- Responsibilities: Serve main HTML page with embedded CSS

**API Entry Point:**
- Location: `app.py` line 218 (`@app.route('/api/config')`)
- Triggers: Frontend configuration requests
- Responsibilities: Return configuration data for feature availability

**Floor Plan API:**
- Location: `app.py` lines 229-254
- Triggers: File upload and floor plan display requests
- Responsibilities: Handle floor plan image storage and URL serving

**Switch Management API:**
- Location: `app.py` lines 259-372
- Triggers: Frontend CRUD operations for switches
- Responsibilities: Create, read, update, delete switch data

## Error Handling

**Strategy:** HTTP status codes with JSON error responses

**Patterns:**
- 400 for invalid requests (missing coordinates, invalid file types)
- 404 for missing switches
- 502 for external API failures
- Graceful degradation when external services unavailable

## Cross-Cutting Concerns

**Logging:** Basic Flask logging, console errors in browser
**Validation:** Input validation for coordinates, filenames, API responses
**Authentication:** Token-based authentication for external APIs via environment variables
**Error Recovery:** Retry logic for external API calls with timeout handling

---

*Architecture analysis: 2026-02-20*