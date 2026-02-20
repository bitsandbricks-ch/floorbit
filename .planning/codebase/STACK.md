# Technology Stack

**Analysis Date:** 2026-02-20

## Languages

**Primary:**
- Python 3.11 - Application logic, REST API, data processing

**Secondary:**
- HTML/CSS/JavaScript - Frontend UI components
  - Custom JavaScript in `static/js/app.js`
  - CSS in `static/css/style.css`

## Runtime

**Environment:**
- Python 3.11 - Core runtime
- Flask 3.0+ - Web framework

**Package Manager:**
- pip - Python package management
- requirements.txt - Lockfile present

## Frameworks

**Core:**
- Flask 3.0+ - REST API, template rendering, static file serving
- Werkzeug 3.0+ - WSGI utility library

**Testing:**
- No dedicated testing framework configured

**Build/Dev:**
- Docker - Containerization
- GitLab CI - CI/CD pipeline

## Key Dependencies

**Critical:**
- Flask 3.0+ - Web framework for API and web serving
- requests 2.31+ - HTTP client for external API calls
- python-dotenv 1.0+ - Environment variable management

**Infrastructure:**
- Standard library only - no external data storage

## Configuration

**Environment:**
- Environment variables via `.env` file
- Docker environment variables in `docker-compose.yml`
- GitLab CI variables for deployment

**Build:**
- Dockerfile for containerization
- GitLab CI configuration for automated builds

## Platform Requirements

**Development:**
- Python 3.11
- pip
- Docker (for containerized development)

**Production:**
- Docker container runtime
- Port 5000 exposed
- Volume mounts for data persistence: `data.json`, `static/uploads`

---

*Stack analysis: 2026-02-20*
```