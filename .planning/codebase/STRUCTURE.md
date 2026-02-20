# Codebase Structure

**Analysis Date:** 2026-02-20

## Directory Layout

```
/c/Users/mkeller/Development/private/lal/
├── app.py                  # Flask application entry point
├── data.json              # Data persistence file
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container configuration
├── docker-compose.yml     # Docker services
├── .gitlab-ci.yml        # CI/CD configuration
├── .env                  # Environment variables
├── .dockerignore         # Docker build exclusions
├── .venv/               # Python virtual environment (excluded)
├── static/               # Static web assets
│   ├── css/             # Stylesheets
│   │   └── style.css    # Main application styles
│   ├── js/              # JavaScript files
│   │   └── app.js       # Main application logic
│   └── uploads/         # User uploaded files
│       └── [floorplan images]
├── templates/           # HTML templates
│   └── index.html       # Main page template
└── .planning/          # Documentation (excluded)
```

## Directory Purposes

**Root Directory:**
- Purpose: Application root and entry point
- Contains: Main application file, configuration, build files
- Key files: `app.py` (Flask app), `data.json` (persistence), `requirements.txt` (deps)

**static/:**
- Purpose: Frontend static assets served by Flask
- Contains: CSS, JavaScript, uploaded files
- Key files: `static/js/app.js` (SPA logic), `static/css/style.css` (styling)

**static/uploads/:**
- Purpose: File storage for user uploads
- Contains: Floor plan images with UUID prefixes
- Generated: Yes (created by Flask on upload)
- Committed: No (excluded by .gitignore in production)

**templates/:**
- Purpose: HTML templates for Flask rendering
- Contains: Single page template
- Key files: `templates/index.html` (main UI)

## Key File Locations

**Entry Points:**
- `/app.py`: Flask application with API routes
- `/templates/index.html`: Main UI page
- `/static/js/app.js`: Frontend SPA logic

**Configuration:**
- `/requirements.txt`: Python dependencies
- `/Dockerfile`: Container setup
- `/docker-compose.yml`: Multi-container deployment
- `/gitlab-ci.yml`: CI/CD pipeline
- `/.env`: Environment variables (secret tokens, API URLs)

**Data:**
- `/data.json`: Device positions and floorplan data
- `/static/uploads/`: Floor plan images

## Naming Conventions

**Files:**
- Python: snake_case (`app.py`, `data.json`)
- JavaScript: camelCase for variables/functions, kebab-case for file names
- HTML: lowercase with hyphens for classes

**Functions:**
- Backend: snake_case (`load_data()`, `fetch_netbox_devices()`)
- Frontend: camelCase (`init()`, `renderOverlay()`, `onMarkerMouseDown`)
- API routes: kebab-case (`/api/switches/sync`)

**Variables:**
- Backend: snake_case with underscores
- Frontend: camelCase with firstWordCapital for constants

**Classes:**
- Not heavily used in this codebase

## Where to Add New Code

**New Frontend Feature:**
- Primary code: `/static/js/app.js` (add new functions, event handlers)
- Styles: `/static/css/style.css` (add new styles)
- HTML: `/templates/index.html` (add new DOM elements)

**New API Endpoint:**
- Implementation: `/app.py` (add new route function)
- Test via: Frontend JavaScript calls to new endpoint

**New Data Field:**
- Backend: Update `data.json` structure and `load_data()`/`save_data()` functions
- Frontend: Update TypeScript interfaces and rendering logic in `app.js`

**New External Integration:**
- Backend: Add new API client functions similar to NetBox/LibreNMS
- Configuration: Add new environment variables to `.env`
- Testing: Test with existing switch management flow

## Special Directories

**.venv/:**
- Purpose: Python virtual environment
- Generated: Yes
- Committed: No (excluded from git, created on setup)

**static/uploads/:**
- Purpose: Runtime file storage
- Generated: Yes (created on first upload)
- Committed: No (user-generated content)

**.planning/:**
- Purpose: GSD documentation
- Generated: Yes (by GSD commands)
- Committed: Yes (documentation should be version controlled)

---

*Structure analysis: 2026-02-20*