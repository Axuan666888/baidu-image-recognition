import os
import json
import time
import base64
import sqlite3
import hashlib
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'database.db')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== 百度AI配置 =====
# 请到 https://console.bce.baidu.com/ 创建应用后填入以下信息
BAIDU_API_KEY = os.environ.get('BAIDU_API_KEY', 'your_api_key_here')
BAIDU_SECRET_KEY = os.environ.get('BAIDU_SECRET_KEY', 'your_secret_key_here')

# 可用识别类型：
#   general_basic  - 通用物体与场景识别（推荐）
#   advanced_general - 图像主体检测
#   plant          - 植物识别
#   animal         - 动物识别
#   dish           - 菜品识别
#   logo           - 品牌LOGO识别
RECOGNIZE_TYPE = 'general_basic'

# ======================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER,
            upload_time TEXT NOT NULL,
            recognize_type TEXT,
            recognize_result TEXT,
            recognize_time TEXT,
            status TEXT DEFAULT 'pending',
            tags TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Access Token 缓存，避免频繁请求
_token_cache = {'token': None, 'expires_at': 0}

def get_baidu_access_token():
    now = time.time()
    if _token_cache['token'] and now < _token_cache['expires_at']:
        return _token_cache['token']

    url = 'https://aip.baidubce.com/oauth/2.0/token'
    params = {
        'grant_type': 'client_credentials',
        'client_id': BAIDU_API_KEY,
        'client_secret': BAIDU_SECRET_KEY
    }
    try:
        resp = requests.post(url, params=params, timeout=10)
        result = resp.json()
        token = result.get('access_token')
        if token:
            expires_in = result.get('expires_in', 2592000)
            _token_cache['token'] = token
            _token_cache['expires_at'] = now + expires_in - 60  # 提前60秒过期
        return token
    except Exception as e:
        print(f'[百度Token获取失败] {e}')
        return None

def recognize_image(image_path, rtype=None):
    access_token = get_baidu_access_token()
    if not access_token:
        return {'error': '获取百度 AccessToken 失败，请检查 API Key 和 Secret Key 是否正确'}

    use_type = rtype or RECOGNIZE_TYPE
    api_map = {
        'general_basic':    'https://aip.baidubce.com/rest/2.0/image-classify/v2/advanced_general',
        'advanced_general': 'https://aip.baidubce.com/rest/2.0/image-classify/v2/advanced_general',
        'plant':            'https://aip.baidubce.com/rest/2.0/image-classify/v1/plant',
        'animal':           'https://aip.baidubce.com/rest/2.0/image-classify/v1/animal',
        'dish':             'https://aip.baidubce.com/rest/2.0/image-classify/v2/dish',
        'logo':             'https://aip.baidubce.com/rest/2.0/image-classify/v2/logo',
    }
    api_url = api_map.get(use_type, api_map['general_basic'])
    api_url += f'?access_token={access_token}'

    try:
        with open(image_path, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {'image': img_data}
        resp = requests.post(api_url, headers=headers, data=data, timeout=20)
        result = resp.json()

        print(f'[百度API响应] type={use_type}, log_id={result.get("log_id")}, keys={list(result.keys())}')

        if 'error_code' in result:
            error_msg = result.get('error_msg', '未知错误')
            print(f'[百度API错误] code={result["error_code"]}, msg={error_msg}')
            return {'error': f"百度API错误: {error_msg} (错误码: {result['error_code']})"}

        # 统一结果格式，兼容不同接口返回字段
        raw_items = result.get('result', [])
        normalized = []
        for item in raw_items[:10]:
            keyword = item.get('keyword') or item.get('name') or '未知'
            score = round(float(item.get('score', 0)), 4)
            root = item.get('root', '')
            if not root and isinstance(item.get('baike_info'), dict):
                root = item['baike_info'].get('description', '')[:30]
            normalized.append({'keyword': keyword, 'score': score, 'root': root})

        return {
            'demo': False,
            'type': use_type,
            'result': normalized,
            'log_id': str(result.get('log_id', ''))
        }
    except Exception as e:
        print(f'[识别异常] {e}')
        return {'error': f'识别请求失败: {str(e)}'}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ===== 路由 =====

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '文件名为空'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': '不支持的文件类型'}), 400

    original_name = file.filename
    ext = original_name.rsplit('.', 1)[1].lower()
    ts = str(int(time.time() * 1000))
    h = hashlib.md5(ts.encode()).hexdigest()[:8]
    filename = f"{h}_{ts}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO images (filename, original_name, file_size, upload_time, status)
        VALUES (?, ?, ?, ?, 'pending')
    ''', (filename, original_name, file_size, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    img_id = c.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'id': img_id, 'filename': filename})

@app.route('/api/recognize/<int:img_id>', methods=['POST'])
def recognize(img_id):
    rtype = request.json.get('type') if request.is_json else None

    conn = get_db()
    row = conn.execute('SELECT * FROM images WHERE id = ?', (img_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '图片不存在'}), 404

    filepath = os.path.join(UPLOAD_FOLDER, row['filename'])
    if not os.path.exists(filepath):
        conn.close()
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    result = recognize_image(filepath, rtype)
    result_json = json.dumps(result, ensure_ascii=False)

    conn.execute('''
        UPDATE images SET recognize_result = ?, recognize_type = ?, recognize_time = ?, status = ?
        WHERE id = ?
    ''', (result_json, rtype or RECOGNIZE_TYPE, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          'error' if 'error' in result else 'done', img_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'result': result})

@app.route('/api/images', methods=['GET'])
def list_images():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 12))
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '')
    recognize_type = request.args.get('recognize_type', '').strip()

    offset = (page - 1) * per_page
    conditions = []
    params = []

    if search:
        conditions.append('(original_name LIKE ? OR tags LIKE ? OR recognize_result LIKE ?)')
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if status:
        conditions.append('status = ?')
        params.append(status)
    if recognize_type:
        conditions.append('recognize_type = ?')
        params.append(recognize_type)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    conn = get_db()
    total = conn.execute(f'SELECT COUNT(*) FROM images {where}', params).fetchone()[0]
    rows = conn.execute(
        f'SELECT * FROM images {where} ORDER BY id DESC LIMIT ? OFFSET ?',
        params + [per_page, offset]
    ).fetchall()
    conn.close()

    items = []
    for r in rows:
        item = dict(r)
        if item.get('recognize_result'):
            try:
                item['recognize_result'] = json.loads(item['recognize_result'])
            except:
                pass
        items.append(item)

    return jsonify({'success': True, 'items': items, 'total': total, 'page': page, 'per_page': per_page})

@app.route('/api/images/<int:img_id>', methods=['GET'])
def get_image(img_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM images WHERE id = ?', (img_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'message': '不存在'}), 404
    item = dict(row)
    if item.get('recognize_result'):
        try:
            item['recognize_result'] = json.loads(item['recognize_result'])
        except:
            pass
    return jsonify({'success': True, 'item': item})

@app.route('/api/images/<int:img_id>', methods=['PUT'])
def update_image(img_id):
    data = request.json or {}
    tags = data.get('tags', '')
    notes = data.get('notes', '')
    conn = get_db()
    conn.execute('UPDATE images SET tags = ?, notes = ? WHERE id = ?', (tags, notes, img_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/images/<int:img_id>', methods=['DELETE'])
def delete_image(img_id):
    conn = get_db()
    row = conn.execute('SELECT filename FROM images WHERE id = ?', (img_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '不存在'}), 404
    filepath = os.path.join(UPLOAD_FOLDER, row['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)
    conn.execute('DELETE FROM images WHERE id = ?', (img_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/test-token', methods=['GET'])
def test_token():
    token = get_baidu_access_token()
    if token:
        return jsonify({'success': True, 'message': '百度AI连接成功', 'token_preview': token[:8] + '...'})
    return jsonify({'success': False, 'message': '获取Token失败，请检查API Key / Secret Key'})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM images').fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM images WHERE status='done'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM images WHERE status='pending'").fetchone()[0]
    error = conn.execute("SELECT COUNT(*) FROM images WHERE status='error'").fetchone()[0]

    # 各识别类型数量（已成功识别的）
    type_rows = conn.execute(
        "SELECT recognize_type, COUNT(*) as cnt FROM images WHERE status='done' AND recognize_type IS NOT NULL GROUP BY recognize_type"
    ).fetchall()
    type_counts = {}
    for row in type_rows:
        t = row['recognize_type']
        # advanced_general 并入 general_basic
        key = 'general_basic' if t in ('general_basic', 'advanced_general') else t
        type_counts[key] = type_counts.get(key, 0) + row['cnt']

    conn.close()
    return jsonify({'total': total, 'done': done, 'pending': pending, 'error': error, 'type_counts': type_counts})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
