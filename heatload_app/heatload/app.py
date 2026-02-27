from flask import Flask, request, jsonify, render_template
import os
import math
import re
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

ALLOWED_EXTENSIONS = {'dxf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_dxf(dxf_path, wall_layers, window_layers):
    """
    Parse DXF file and extract:
    - Room names from TEXT/MTEXT entities
    - Wall lines from specified layers
    - Window lines from specified layers
    Returns dict: { room_name: { walls: [lengths], windows: [lengths] } }
    """
    wall_layers = [l.strip().upper() for l in wall_layers if l.strip()]
    window_layers = [w.strip().upper() for w in window_layers if w.strip()]

    with open(dxf_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    lines = content.split('\n')
    lines = [l.rstrip() for l in lines]

    entities = []
    i = 0
    # Find ENTITIES section
    while i < len(lines):
        if lines[i].strip() == 'ENTITIES':
            i += 1
            break
        i += 1

    # Parse entities
    while i < len(lines):
        if lines[i].strip() == 'ENDSEC':
            break
        if lines[i].strip() == '0' and i + 1 < len(lines):
            etype = lines[i+1].strip()
            entity = {'type': etype, 'data': {}}
            i += 2
            while i < len(lines):
                if lines[i].strip() == '0':
                    break
                code = lines[i].strip()
                val = lines[i+1].strip() if i+1 < len(lines) else ''
                entity['data'][code] = entity['data'].get(code, val)  # first occurrence
                # Store multiple occurrences for coordinates
                if code not in entity['data']:
                    entity['data'][code] = val
                i += 2
            entities.append(entity)
        else:
            i += 1

    # Re-parse more carefully to handle multiple coordinate groups
    entities = parse_entities_carefully(lines)

    # Collect room text labels with positions
    rooms_text = []
    walls = []
    windows = []

    for ent in entities:
        etype = ent['type']
        layer = ent.get('layer', '').upper()

        if etype in ('TEXT', 'MTEXT'):
            text_val = ent.get('text', '')
            x = float(ent.get('x', 0))
            y = float(ent.get('y', 0))
            if text_val:
                rooms_text.append({'name': text_val, 'x': x, 'y': y})

        elif etype == 'LINE':
            x1 = float(ent.get('x1', 0))
            y1 = float(ent.get('y1', 0))
            x2 = float(ent.get('x2', 0))
            y2 = float(ent.get('y2', 0))
            length = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            cx = (x1+x2)/2
            cy = (y1+y2)/2
            seg = {'length': length, 'cx': cx, 'cy': cy, 'layer': layer}
            if layer in wall_layers:
                walls.append(seg)
            if layer in window_layers:
                windows.append(seg)

        elif etype in ('LWPOLYLINE', 'POLYLINE'):
            pts = ent.get('points', [])
            layer_segs = []
            for j in range(len(pts)):
                p1 = pts[j]
                p2 = pts[(j+1) % len(pts)] if ent.get('closed') else (pts[j+1] if j+1 < len(pts) else None)
                if p2 is None:
                    continue
                length = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
                cx = (p1[0]+p2[0])/2
                cy = (p1[1]+p2[1])/2
                layer_segs.append({'length': length, 'cx': cx, 'cy': cy, 'layer': layer})
            if layer in wall_layers:
                walls.extend(layer_segs)
            if layer in window_layers:
                windows.extend(layer_segs)

    # Group walls and windows by nearest room label
    result = {}
    if not rooms_text:
        # No room labels found — put everything in one group
        result['Unknown Room'] = {
            'walls': [w['length'] for w in walls],
            'windows': [w['length'] for w in windows]
        }
        return result

    for rt in rooms_text:
        result[rt['name']] = {'walls': [], 'windows': [], 'rx': rt['x'], 'ry': rt['y']}

    def nearest_room(cx, cy):
        best = None
        best_d = float('inf')
        for rt in rooms_text:
            d = math.sqrt((cx - rt['x'])**2 + (cy - rt['y'])**2)
            if d < best_d:
                best_d = d
                best = rt['name']
        return best

    for w in walls:
        rname = nearest_room(w['cx'], w['cy'])
        if rname:
            result[rname]['walls'].append(w['length'])

    for w in windows:
        rname = nearest_room(w['cx'], w['cy'])
        if rname:
            result[rname]['windows'].append(w['length'])

    # Clean up helper coords
    for k in result:
        result[k].pop('rx', None)
        result[k].pop('ry', None)

    return result


def parse_entities_carefully(lines):
    """More careful entity parser that handles repeated group codes (coordinates)"""
    entities = []
    in_entities = False
    i = 0

    while i < len(lines):
        if lines[i].strip() == 'ENTITIES':
            in_entities = True
            i += 1
            continue
        if in_entities and lines[i].strip() == 'ENDSEC':
            break
        if not in_entities:
            i += 1
            continue

        if lines[i].strip() == '0' and i+1 < len(lines):
            etype = lines[i+1].strip()
            i += 2
            raw = {}
            coord_sets = []  # for polylines
            current_pt = {}

            while i < len(lines) - 1:
                if lines[i].strip() == '0':
                    break
                code = lines[i].strip()
                val = lines[i+1].strip() if i+1 < len(lines) else ''
                i += 2

                if code == '8':
                    raw['layer'] = val
                elif code == '1':
                    raw['text'] = val
                elif code == '10':
                    if '10' in current_pt:
                        coord_sets.append(current_pt)
                        current_pt = {}
                    current_pt['x'] = val
                elif code == '20':
                    current_pt['y'] = val
                elif code == '11':
                    raw['x2'] = val
                elif code == '21':
                    raw['y2'] = val
                elif code == '70':
                    raw['flags'] = val
                else:
                    if code not in raw:
                        raw[code] = val

            if current_pt:
                coord_sets.append(current_pt)

            ent = {'type': etype}
            ent['layer'] = raw.get('layer', '')
            ent['text'] = raw.get('text', '')

            if etype == 'LINE':
                if coord_sets:
                    ent['x1'] = coord_sets[0].get('x', 0)
                    ent['y1'] = coord_sets[0].get('y', 0)
                if len(coord_sets) > 1:
                    ent['x2'] = coord_sets[1].get('x', 0)
                    ent['y2'] = coord_sets[1].get('y', 0)
                elif 'x2' in raw:
                    ent['x2'] = raw['x2']
                    ent['y2'] = raw.get('y2', 0)

            elif etype in ('TEXT', 'MTEXT'):
                if coord_sets:
                    ent['x'] = coord_sets[0].get('x', 0)
                    ent['y'] = coord_sets[0].get('y', 0)

            elif etype in ('LWPOLYLINE', 'POLYLINE'):
                ent['points'] = [(float(p.get('x', 0)), float(p.get('y', 0))) for p in coord_sets]
                flags = int(raw.get('flags', 0))
                ent['closed'] = bool(flags & 1)

            entities.append(ent)
        else:
            i += 1

    return entities


def evaluate_formula(formula, variables):
    """
    Safely evaluate a formula string with given variables.
    Supports: +, -, *, /, (, ), and variable names.
    """
    # Replace variable names with values
    # Sort by length descending to avoid partial replacements
    for var in sorted(variables.keys(), key=len, reverse=True):
        formula = re.sub(r'\b' + re.escape(var) + r'\b', str(variables[var]), formula)

    # Only allow safe characters
    if re.search(r'[^0-9+\-*/().\s]', formula):
        raise ValueError(f"Formula contains invalid characters after substitution: {formula}")

    return eval(formula)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Only DXF files are allowed. Please convert your DWG file to DXF first (e.g. using AutoCAD or an online converter).'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        dxf_path = filepath

        # Get layer names
        wall_layers = request.form.get('wall_layers', '').split(',')
        window_layers = request.form.get('window_layers', '').split(',')

        room_data = parse_dxf(dxf_path, wall_layers, window_layers)

        return jsonify({'success': True, 'rooms': room_data, 'filename': filename})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.json
        rooms = data['rooms']
        formula = data['formula']
        params = data['params']  # { wall_height, U_wall, U_window, T_inside, T_outside, ... }
        
        delta_T = float(params.get('T_inside', 20)) - float(params.get('T_outside', 0))
        
        results = []
        total_wattage = 0

        for room_name, room in rooms.items():
            wall_lengths = room.get('walls', [])
            window_lengths = room.get('windows', [])
            
            wall_height = float(params.get('wall_height', 2.8))
            
            total_wall_length = sum(wall_lengths)
            total_window_length = sum(window_lengths)
            
            # Net wall length (subtract window openings)
            net_wall_length = max(0, total_wall_length - total_window_length)

            variables = {
                'wall_length': net_wall_length,
                'window_length': total_window_length,
                'wall_height': wall_height,
                'wall_area': net_wall_length * wall_height,
                'window_area': total_window_length * wall_height,
                'U_wall': float(params.get('U_wall', 0.3)),
                'U_window': float(params.get('U_window', 1.4)),
                'delta_T': delta_T,
                'T_inside': float(params.get('T_inside', 20)),
                'T_outside': float(params.get('T_outside', 0)),
            }
            # Add any extra custom params
            for k, v in params.items():
                if k not in variables:
                    try:
                        variables[k] = float(v)
                    except:
                        variables[k] = v

            wattage = evaluate_formula(formula, variables)
            total_wattage += wattage

            results.append({
                'room': room_name,
                'wall_count': len(wall_lengths),
                'window_count': len(window_lengths),
                'total_wall_length': round(total_wall_length / 1000, 2),  # mm to m
                'total_window_length': round(total_window_length / 1000, 2),
                'wattage': round(wattage, 1),
                'variables': {k: round(v, 3) if isinstance(v, float) else v for k, v in variables.items()}
            })

        results.sort(key=lambda x: x['wattage'], reverse=True)

        return jsonify({
            'success': True,
            'results': results,
            'total_wattage': round(total_wattage, 1),
            'delta_T': round(delta_T, 1)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analyze_image', methods=['POST'])
def analyze_image():
    """Accept a screenshot upload and return basic info"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        img = request.files['image']
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(img.filename))
        img.save(img_path)
        return jsonify({'success': True, 'message': 'Screenshot saved. Please ensure your DXF/DWG layer names match what you see in the drawing.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
