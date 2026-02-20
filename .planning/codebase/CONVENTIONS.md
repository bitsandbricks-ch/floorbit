# Coding Conventions

**Analysis Date:** 2026-02-20

## Naming Patterns

**Files:**
- All lowercase with hyphens: `app.py`, `style.css`, `app.js`
- Single file application structure

**Functions:**
- Snake_case for Python functions: `load_data()`, `fetch_netbox_devices()`, `merge_devices_with_positions()`
- camelCase for JavaScript functions: `init()`, `renderAll()`, `createMarker()`
- Descriptive names that clearly indicate purpose

**Variables:**
- Snake_case for Python: `data_file`, `netbox_url`, `allowed_extensions`
- camelCase for JavaScript: `config`, `switches`, `currentTool`
- Constants: UPPER_SNAKE_CASE in Python (`NETBOX_URL`, `ZOOM_MIN`)
- const declarations for JavaScript constants

**Types:**
- PascalCase for classes: Not detected (no classes used)
- Interfaces/Types: Not explicitly typed (no TypeScript detected)

## Code Style

**Formatting:**
- Python: Black-style formatting with 4-space indentation
- JavaScript: Standard formatting with 2-space indentation
- Line length: Generally wrapped at reasonable limits
- Trailing commas: Used in JavaScript arrays and objects

**Linting:**
- No linter configuration detected (no .eslintrc, .prettierrc, etc.)
- Basic PEP 8 compliance in Python
- Consistent formatting within files

## Import Organization

**Python:**
```python
import os
import json
import uuid
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
```
- Standard library first
- Third-party imports second
- Local imports third
- Alphabetical order within groups

**JavaScript:**
- No import statements (all inline)
- Uses `const` for global constants, `let` for mutable state
- Strict mode enabled: `'use strict';`

## Error Handling

**Python Patterns:**
```python
try:
    devices = fetch_netbox_devices()
except requests.RequestException as exc:
    return jsonify({'error': f'NetBox request failed: {exc}'}), 502

# File operations
try:
    with open(DATA_FILE, 'r') as f:
        return json.load(f)
except FileNotFoundError:
    return default_data
```
- Specific exception handling
- Graceful degradation
- HTTP status codes for API errors

**JavaScript Patterns:**
```javascript
try {
    const data = await api('GET', `/api/switches/${selectedId}/status`);
    // Handle success
} catch (e) {
    alert('Failed to refresh status: ' + e.message);
}

// Optional chaining for null safety
data.up_ports != null ? `${data.up_ports} / ${data.total_ports}` : '—'
```
- Try-catch for async operations
- User-friendly error messages
- Graceful handling of missing data

## Logging

**Framework:** Python `logging` not detected, JavaScript `console`
**Patterns:**
```javascript
// Error logging
console.error('Error refreshing status:', error);

// Debug logging
console.log('Switch count:', switches.length);
```
- Minimal logging present
- No centralized logging configuration
- Console-based for development

## Comments

**When to Comment:**
- Complex algorithm explanations (NetBox pagination, LibreNMS API calls)
- Configuration section headers
- Todo/FIXME items not detected
- Key business logic comments

**JSDoc/TSDoc:**
- Minimal JSDoc usage in JavaScript
- No TypeScript documentation detected
- Some inline comments explaining complex logic

## Function Design

**Size:**
- Python functions: 5-30 lines (generally well-sized)
- JavaScript functions: 5-50 lines (some longer functions)
- Single responsibility principle generally followed

**Parameters:**
- Python: Keyword arguments where appropriate, positional for simple cases
- JavaScript: Object destructuring not used, direct parameter access

**Return Values:**
- Python: Consistent return types (dict/list for data, None for void)
- JavaScript: Promise-based async returns, direct sync returns

## Module Design

**Exports:**
- Python: Function-based module
- JavaScript: No modules, global namespace with IIFE pattern

**Barrel Files:**
- Not used (single file structure)

## Error Handling Patterns

**API Error Handling:**
```javascript
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.json();
}
```

**Validation:**
- Type checking for coordinates: `float(body['x'])`
- File type validation: `allowed_file(filename)`
- Existence checks before operations

---

*Convention analysis: 2026-02-20*