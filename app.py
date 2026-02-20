import os
import json
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
DATA_FILE = 'data.json'

# ── Service config ─────────────────────────────────────────────────────────────
NETBOX_URL        = os.getenv('NETBOX_URL', '').rstrip('/')
NETBOX_TOKEN      = os.getenv('NETBOX_TOKEN', '')
NETBOX_ROLES      = [r.strip() for r in os.getenv('NETBOX_DEVICE_ROLE', 'access-switch').split(',') if r.strip()]
NETBOX_VERIFY_SSL = os.getenv('NETBOX_VERIFY_SSL', 'true').lower() != 'false'

LIBRENMS_URL        = os.getenv('LIBRENMS_URL', '').rstrip('/')
LIBRENMS_TOKEN      = os.getenv('LIBRENMS_TOKEN', '')
LIBRENMS_VERIFY_SSL = os.getenv('LIBRENMS_VERIFY_SSL', 'true').lower() != 'false'

NETBOX_ENABLED   = bool(NETBOX_URL and NETBOX_TOKEN)
LIBRENMS_ENABLED = bool(LIBRENMS_URL and LIBRENMS_TOKEN)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ── Persistence ────────────────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        'switches':       [],   # manual mode switch list
        'cached_devices': [],   # netbox mode: cached device list
        'positions':      {},   # netbox mode: {str(device_id): {x, y}}
        'floorplan':      None,
    }


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── NetBox ─────────────────────────────────────────────────────────────────────

def fetch_netbox_devices():
    """Fetch all devices with the configured role from NetBox (handles pagination)."""
    headers = {
        'Authorization': f'Token {NETBOX_TOKEN}',
        'Accept': 'application/json',
    }
    devices = []
    url = f'{NETBOX_URL}/api/dcim/devices/'
    params = {'role': NETBOX_ROLES, 'limit': 500}
    while url:
        resp = requests.get(url, headers=headers, params=params,
                            timeout=15, verify=NETBOX_VERIFY_SSL)
        resp.raise_for_status()
        payload = resp.json()
        for d in payload.get('results', []):
            devices.append({
                'id':            str(d['id']),
                'name':          d['name'],
                'netbox_status': d.get('status', {}).get('value', 'unknown'),
            })
        url = payload.get('next')
        params = {}   # next URL already includes all query params
    return devices


def merge_devices_with_positions(cached_devices, positions):
    """Combine cached NetBox devices with locally stored floor-plan positions."""
    result = []
    for dev in cached_devices:
        pos = positions.get(dev['id'])
        result.append({
            'id':            dev['id'],
            'name':          dev['name'],
            'netbox_status': dev.get('netbox_status', 'unknown'),
            'x':             pos['x'] if pos else None,
            'y':             pos['y'] if pos else None,
            'placed':        pos is not None,
            'status':        'unknown',
        })
    return result


# ── LibreNMS ───────────────────────────────────────────────────────────────────

def fetch_librenms_details(hostname):
    """Return a dict with status, ip, cpu_load, mem_percent, up_ports, total_ports.

    Searches LibreNMS by displayname so hostname mapping doesn't need to match exactly.
    """
    headers = {
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }
    result = {'status': 'unknown', 'hostname': hostname}

    # ── Find device by displayname ────────────────────────────────────────────
    device = None
    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': hostname},
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
        )
        if resp.ok:
            candidates = resp.json().get('devices', [])
            hn = hostname.lower()
            # Prefer exact displayname match, fall back to partial
            device = next(
                (d for d in candidates if d.get('display', '').lower() == hn),
                None,
            ) or next(
                (d for d in candidates if hn in d.get('hostname', '').lower()),
                None,
            )
    except requests.RequestException:
        pass

    if device is None:
        return result

    # ── Extract device info ───────────────────────────────────────────────────
    result['status'] = 'online' if device.get('status', 0) == 1 else 'offline'
    # Try multiple possible IP field names from LibreNMS
    result['ip'] = (
        device.get('ip') or
        device.get('hostname') or
        device.get('sysName') or
        ''
    )

    # ── CPU from processor health ─────────────────────────────────────────────
    device_id = device.get('device_id') or device.get('hostname')
    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/health/processor',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
        )
        if resp.ok:
            sensors = resp.json().get('health', [])
            values = [s.get('sensor_current') for s in sensors if s.get('sensor_current') is not None]
            if values:
                result['cpu_load'] = round(sum(values) / len(values))
    except requests.RequestException:
        pass

    # ── Memory from mempool health ────────────────────────────────────────────
    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/health/mempool',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
        )
        if resp.ok:
            pools = resp.json().get('health', [])
            values = [p.get('mempool_perc') for p in pools if p.get('mempool_perc') is not None]
            if values:
                result['mem_percent'] = round(sum(values) / len(values))
    except requests.RequestException:
        pass

    # ── Port summary + traffic ────────────────────────────────────────────────
    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/ports',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
            params={'columns': 'ifOperStatus,ifInOctets_rate,ifOutOctets_rate,ifSpeed'},
        )
        if resp.ok:
            ports = resp.json().get('ports', [])
            result['total_ports'] = len(ports)
            result['up_ports']    = sum(1 for p in ports if p.get('ifOperStatus') == 'up')

            total_traffic_bps  = 0.0
            total_capacity_bps = 0.0
            for p in ports:
                if p.get('ifOperStatus') != 'up':
                    continue
                in_rate  = float(p.get('ifInOctets_rate')  or 0)
                out_rate = float(p.get('ifOutOctets_rate') or 0)
                speed    = float(p.get('ifSpeed')          or 0)
                total_traffic_bps  += (in_rate + out_rate) * 8
                if speed > 0:
                    total_capacity_bps += speed

            result['total_traffic_bps'] = round(total_traffic_bps)
            if total_capacity_bps > 0:
                result['traffic_util'] = round(
                    min(1.0, total_traffic_bps / total_capacity_bps), 4
                )
    except requests.RequestException:
        pass

    return result


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── Config ─────────────────────────────────────────────────────────────────────

@app.route('/api/config')
def get_config():
    return jsonify({
        'netbox_enabled':    NETBOX_ENABLED,
        'librenms_enabled':  LIBRENMS_ENABLED,
        'netbox_device_roles': NETBOX_ROLES,
    })


# ── Floor Plan ─────────────────────────────────────────────────────────────────

@app.route('/api/floorplan', methods=['GET'])
def get_floorplan():
    data = load_data()
    filename = data.get('floorplan')
    if filename:
        return jsonify({'url': f'/static/uploads/{filename}'})
    return jsonify({'url': None})


@app.route('/api/floorplan', methods=['POST'])
def upload_floorplan():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    data = load_data()
    data['floorplan'] = filename
    save_data(data)
    return jsonify({'url': f'/static/uploads/{filename}'})


# ── Switches ───────────────────────────────────────────────────────────────────

@app.route('/api/switches', methods=['GET'])
def get_switches():
    data = load_data()
    manual = data.get('switches', [])
    if NETBOX_ENABLED:
        netbox = merge_devices_with_positions(
            data.get('cached_devices', []),
            data.get('positions', {}),
        )
        return jsonify(netbox + manual)
    return jsonify(manual)


@app.route('/api/switches/sync', methods=['POST'])
def sync_switches():
    """Re-fetch device list from NetBox and persist it (NetBox mode only)."""
    if not NETBOX_ENABLED:
        return jsonify({'error': 'NetBox is not configured'}), 400
    try:
        devices = fetch_netbox_devices()
    except requests.RequestException as exc:
        return jsonify({'error': f'NetBox request failed: {exc}'}), 502

    data = load_data()
    data['cached_devices'] = devices
    data.setdefault('positions', {})
    save_data(data)
    return jsonify(merge_devices_with_positions(devices, data['positions']))


@app.route('/api/switches', methods=['POST'])
def add_switch():
    """Create and place a manual switch (available in both manual and NetBox mode)."""
    body = request.get_json(force=True)
    try:
        x = float(body['x'])
        y = float(body['y'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid numeric x and y coordinates are required'}), 400

    switch = {
        'id':     str(uuid.uuid4()),
        'name':   body.get('name', 'Switch'),
        'x':      x,
        'y':      y,
        'placed': True,
        'source': 'manual',
        'status': 'unknown',
    }
    data = load_data()
    data.setdefault('switches', []).append(switch)
    save_data(data)
    return jsonify(switch), 201


@app.route('/api/switches/<switch_id>', methods=['PUT'])
def update_switch(switch_id):
    body = request.get_json(force=True)
    data = load_data()

    if NETBOX_ENABLED:
        device = next(
            (d for d in data.get('cached_devices', []) if d['id'] == switch_id),
            None,
        )
        if device:
            positions = data.setdefault('positions', {})
            pos = positions.get(switch_id, {})
            if 'x' in body and 'y' in body:
                try:
                    pos = {'x': float(body['x']), 'y': float(body['y'])}
                except (TypeError, ValueError):
                    return jsonify({'error': 'Invalid coordinates'}), 400
            positions[switch_id] = pos
            save_data(data)
            return jsonify({
                'id':            device['id'],
                'name':          device['name'],
                'netbox_status': device.get('netbox_status', 'unknown'),
                'x':             pos.get('x'),
                'y':             pos.get('y'),
                'placed':        True,
                'status':        'unknown',
            })
        # Fall through to handle manual switches in NetBox mode

    for switch in data.get('switches', []):
        if switch['id'] == switch_id:
            for key in ('name', 'x', 'y'):
                if key in body:
                    switch[key] = body[key]
            save_data(data)
            return jsonify(switch)
    return jsonify({'error': 'Switch not found'}), 404


@app.route('/api/switches/<switch_id>', methods=['DELETE'])
def delete_switch(switch_id):
    data = load_data()

    if NETBOX_ENABLED:
        positions = data.setdefault('positions', {})
        if switch_id in positions:
            del positions[switch_id]
            save_data(data)
            return jsonify({'success': True})
        # Fall through to handle manual switches in NetBox mode

    before = len(data.get('switches', []))
    data['switches'] = [s for s in data['switches'] if s['id'] != switch_id]
    if len(data['switches']) == before:
        return jsonify({'error': 'Switch not found'}), 404
    save_data(data)
    return jsonify({'success': True})


# ── Status ─────────────────────────────────────────────────────────────────────

@app.route('/api/switches/<switch_id>/status', methods=['GET'])
def get_switch_status(switch_id):
    if not LIBRENMS_ENABLED:
        return jsonify({
            'id':      switch_id,
            'status':  'unknown',
            'message': 'LibreNMS is not configured',
        })

    data = load_data()
    # Check manual switches first (present in both modes)
    switch = next((s for s in data.get('switches', []) if s['id'] == switch_id), None)
    if switch:
        hostname = switch['name']
    elif NETBOX_ENABLED:
        device = next(
            (d for d in data.get('cached_devices', []) if d['id'] == switch_id),
            None,
        )
        hostname = device['name'] if device else switch_id
    else:
        hostname = switch_id

    details = fetch_librenms_details(hostname)
    return jsonify({'id': switch_id, **details})


if __name__ == '__main__':
    app.run(debug=True)
