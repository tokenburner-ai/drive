"""File Drive — browse, upload, preview and manage S3 documents.

All files live under s3://{DRIVE_BUCKET}/drive/

DynamoDB index (DRIVE_TABLE) provides sub-millisecond folder listings:
  pk=folder#{prefix}  sk={filename}     → file item
  pk=folder#{prefix}  sk={name}/        → sub-folder item
  pk=__meta__         sk=tree           → full sidebar tree JSON
"""

import json
import os
import time
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template_string, request, send_from_directory

import aws

drive_bp = Blueprint('drive_bp', __name__)

DRIVE_BUCKET = os.environ.get('DRIVE_BUCKET', '')
DRIVE_PREFIX = 'drive/'
DRIVE_TABLE  = os.environ.get('DRIVE_TABLE', 'tokendrive-index')
API_KEY_VAR  = os.environ.get('DRIVE_API_KEY', '')


# ── auth ──────────────────────────────────────────────────────────────────────

def _require_key(f):
    """Check X-Drive-Key header or ?key= query param against DRIVE_API_KEY."""
    @wraps(f)
    def w(*a, **kw):
        provided = (
            request.headers.get('X-Drive-Key') or
            request.args.get('key') or
            request.cookies.get('drive_key') or
            ''
        )
        if not API_KEY_VAR or provided != API_KEY_VAR:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*a, **kw)
    return w


def _s3():
    return aws.get_session().client('s3')


def _table():
    return aws.get_session().resource('dynamodb').Table(DRIVE_TABLE)


def _safe_key(key):
    if not key or '..' in key or not key.startswith(DRIVE_PREFIX):
        return None
    return key


def _safe_prefix(prefix):
    if not prefix:
        return DRIVE_PREFIX
    if '..' in prefix or not prefix.startswith(DRIVE_PREFIX):
        return None
    if not prefix.endswith('/'):
        prefix += '/'
    return prefix


# ── pages ─────────────────────────────────────────────────────────────────────

@drive_bp.route('/')
@drive_bp.route('/drive/')
def drive_page():
    from flask import current_app
    return send_from_directory(current_app.static_folder, 'drive.html')


@drive_bp.route('/docs')
@drive_bp.route('/docs/')
def docs_page():
    return render_template_string(SWAGGER_HTML)


SWAGGER_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>API Docs</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>
    body { margin: 0; background: #050508; }
    #swagger-ui .swagger-ui { background: #050508; }
    #swagger-ui .swagger-ui .topbar { background: #0d0d12; border-bottom: 1px solid #1a1a24; }
    #swagger-ui .swagger-ui .info .title { color: #f0f0f0; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      spec: ''' + _OPENAPI_SPEC_JSON + ''',
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: 'BaseLayout',
      requestInterceptor: function(req) {
        const key = sessionStorage.getItem('drive_api_key') || new URLSearchParams(location.search).get('key') || '';
        if (key) req.headers['X-Drive-Key'] = key;
        return req;
      },
    });
  </script>
</body>
</html>'''

_OPENAPI_SPEC_JSON = '''
{
  "openapi": "3.0.0",
  "info": { "title": "Token Drive API", "version": "1.0" },
  "servers": [{ "url": "/" }],
  "components": {
    "securitySchemes": {
      "ApiKey": { "type": "apiKey", "in": "header", "name": "X-Drive-Key" }
    }
  },
  "security": [{ "ApiKey": [] }],
  "paths": {
    "/api/drive/list": {
      "get": {
        "summary": "List files and folders",
        "parameters": [{ "name": "prefix", "in": "query", "schema": { "type": "string" }, "example": "drive/" }],
        "responses": { "200": { "description": "File listing" }, "401": { "description": "Unauthorized" } }
      }
    },
    "/api/drive/tree": {
      "get": {
        "summary": "Full folder tree",
        "responses": { "200": { "description": "Tree JSON" }, "401": { "description": "Unauthorized" } }
      }
    },
    "/api/drive/url": {
      "get": {
        "summary": "Presigned download URL",
        "parameters": [{ "name": "key", "in": "query", "required": true, "schema": { "type": "string" } }],
        "responses": { "200": { "description": "Presigned URL" }, "401": { "description": "Unauthorized" } }
      }
    },
    "/api/drive/presign-upload": {
      "post": {
        "summary": "Presigned upload URL",
        "requestBody": {
          "required": true,
          "content": { "application/json": { "schema": {
            "type": "object",
            "properties": { "key": { "type": "string" }, "content_type": { "type": "string" } }
          }}}
        },
        "responses": { "200": { "description": "Presigned URL + fields" }, "401": { "description": "Unauthorized" } }
      }
    },
    "/api/drive/delete": {
      "delete": {
        "summary": "Delete a file",
        "parameters": [{ "name": "key", "in": "query", "required": true, "schema": { "type": "string" } }],
        "responses": { "200": { "description": "Deleted" }, "401": { "description": "Unauthorized" } }
      }
    },
    "/api/drive/rename": {
      "post": {
        "summary": "Rename a file",
        "requestBody": {
          "required": true,
          "content": { "application/json": { "schema": {
            "type": "object",
            "properties": { "old_key": { "type": "string" }, "new_key": { "type": "string" } }
          }}}
        },
        "responses": { "200": { "description": "Renamed" }, "401": { "description": "Unauthorized" } }
      }
    }
  }
}
'''


# ── folder listing ────────────────────────────────────────────────────────────

@drive_bp.route('/api/drive/list')
@_require_key
def list_folder():
    prefix = _safe_prefix(request.args.get('prefix', DRIVE_PREFIX))
    if prefix is None:
        return jsonify({'error': 'Invalid prefix'}), 400

    try:
        from boto3.dynamodb.conditions import Key
        resp = _table().query(KeyConditionExpression=Key('pk').eq(f'folder#{prefix}'))
        items = resp.get('Items', [])
        while 'LastEvaluatedKey' in resp:
            resp = _table().query(
                KeyConditionExpression=Key('pk').eq(f'folder#{prefix}'),
                ExclusiveStartKey=resp['LastEvaluatedKey'],
            )
            items.extend(resp.get('Items', []))
    except Exception:
        items = []

    if not items:
        return _list_folder_from_s3(prefix)

    folders, files = [], []
    for item in items:
        if item.get('type') == 'folder':
            folders.append({'name': item['name'], 'prefix': item['prefix']})
        elif item.get('type') == 'file':
            sk = item.get('sk', '')
            if sk == '.keep':
                continue
            files.append({
                'name': sk,
                'key': item['key'],
                'size': int(item.get('size', 0)),
                'last_modified': item.get('last_modified', ''),
                'ext': item.get('ext', ''),
            })

    folders.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())
    return jsonify({'prefix': prefix, 'folders': folders, 'files': files})


def _list_folder_from_s3(prefix):
    folders, files = [], []
    paginator = _s3().get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=DRIVE_BUCKET, Prefix=prefix, Delimiter='/'):
        for cp in page.get('CommonPrefixes') or []:
            p = cp['Prefix']
            name = p.rstrip('/').split('/')[-1]
            folders.append({'name': name, 'prefix': p})
        for obj in page.get('Contents') or []:
            k = obj['Key']
            if k == prefix:
                continue
            name = k.split('/')[-1]
            if not name or name == '.keep':
                continue
            ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
            files.append({
                'name': name,
                'key': k,
                'size': obj['Size'],
                'last_modified': obj['LastModified'].isoformat(),
                'ext': ext,
            })
    folders.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())
    return jsonify({'prefix': prefix, 'folders': folders, 'files': files})


# ── folder tree ───────────────────────────────────────────────────────────────

@drive_bp.route('/api/drive/tree')
@_require_key
def get_tree():
    try:
        resp = _table().get_item(Key={'pk': '__meta__', 'sk': 'tree'})
        item = resp.get('Item')
        if item:
            return jsonify({'tree': json.loads(item['data'])})
        tree = _build_tree_from_s3()
        _table().put_item(Item={'pk': '__meta__', 'sk': 'tree', 'data': json.dumps(tree)})
        return jsonify({'tree': tree})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@drive_bp.route('/api/drive/tree/refresh', methods=['POST'])
@_require_key
def refresh_tree():
    try:
        _rebuild_tree_in_dynamo()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _rebuild_tree_in_dynamo():
    from boto3.dynamodb.conditions import Attr
    table = _table()
    all_prefixes = set()
    resp = table.scan(FilterExpression=Attr('type').eq('folder'))
    items = resp.get('Items', [])
    while 'LastEvaluatedKey' in resp:
        resp = table.scan(
            FilterExpression=Attr('type').eq('folder'),
            ExclusiveStartKey=resp['LastEvaluatedKey'],
        )
        items.extend(resp.get('Items', []))
    for item in items:
        all_prefixes.add(item['prefix'])
    tree = _build_tree_from_prefixes(all_prefixes)
    table.put_item(Item={'pk': '__meta__', 'sk': 'tree', 'data': json.dumps(tree)})
    return tree


def _build_tree_from_s3():
    all_prefixes = set()
    paginator = _s3().get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=DRIVE_BUCKET, Prefix=DRIVE_PREFIX):
        for obj in page.get('Contents') or []:
            key = obj['Key']
            rel = key[len(DRIVE_PREFIX):]
            parts = rel.split('/')
            for i in range(1, len(parts)):
                all_prefixes.add(DRIVE_PREFIX + '/'.join(parts[:i]) + '/')
    return _build_tree_from_prefixes(all_prefixes)


def _build_tree_from_prefixes(all_prefixes):
    def get_children(parent):
        children = []
        for p in sorted(all_prefixes):
            if p == parent:
                continue
            rel = p[len(parent):]
            if rel and rel.endswith('/') and '/' not in rel[:-1]:
                name = rel[:-1]
                children.append({'name': name, 'prefix': p, 'children': get_children(p)})
        return children
    return get_children(DRIVE_PREFIX)


# ── file view / download ──────────────────────────────────────────────────────

@drive_bp.route('/api/drive/url')
@_require_key
def get_file_url():
    key = _safe_key(request.args.get('key', ''))
    if not key:
        return jsonify({'error': 'Invalid key'}), 400
    ext = key.rsplit('.', 1)[-1].lower() if '.' in key else ''
    MIME_MAP = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
        'png': 'image/png', 'gif': 'image/gif',
        'webp': 'image/webp', 'svg': 'image/svg+xml', 'bmp': 'image/bmp',
        'txt': 'text/plain', 'rtf': 'text/rtf',
    }
    params: dict = {'Bucket': DRIVE_BUCKET, 'Key': key}
    if ext in MIME_MAP:
        params['ResponseContentDisposition'] = 'inline'
        params['ResponseContentType'] = MIME_MAP[ext]
    try:
        url = _s3().generate_presigned_url('get_object', Params=params, ExpiresIn=3600)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'url': url})


@drive_bp.route('/api/drive/download')
@_require_key
def download_file():
    key = _safe_key(request.args.get('key', ''))
    if not key:
        return 'Invalid key', 400
    filename = key.split('/')[-1]
    try:
        url = _s3().generate_presigned_url(
            'get_object',
            Params={
                'Bucket': DRIVE_BUCKET,
                'Key': key,
                'ResponseContentDisposition': f'attachment; filename="{filename}"',
            },
            ExpiresIn=300,
        )
    except Exception as e:
        return str(e), 500
    return redirect(url)


# ── upload ────────────────────────────────────────────────────────────────────

@drive_bp.route('/api/drive/presign-upload', methods=['POST'])
@_require_key
def presign_upload():
    data = request.json or {}
    key = _safe_key(data.get('key', ''))
    if not key:
        return jsonify({'error': 'Invalid key'}), 400
    content_type = data.get('content_type') or 'application/octet-stream'
    try:
        url = _s3().generate_presigned_url(
            'put_object',
            Params={'Bucket': DRIVE_BUCKET, 'Key': key, 'ContentType': content_type},
            ExpiresIn=300,
            HttpMethod='PUT',
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'url': url, 'key': key})


@drive_bp.route('/api/drive/index-file', methods=['POST'])
@_require_key
def index_file():
    data = request.json or {}
    key = _safe_key(data.get('key', ''))
    if not key:
        return jsonify({'error': 'Invalid key'}), 400
    filename = key.split('/')[-1]
    if not filename:
        return jsonify({'error': 'Invalid key (no filename)'}), 400

    parent_prefix = key[:key.rfind('/') + 1]
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    size = int(data.get('size', 0))
    last_modified = data.get('last_modified', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))

    try:
        table = _table()
        table.put_item(Item={
            'pk': f'folder#{parent_prefix}',
            'sk': filename,
            'type': 'file',
            'key': key,
            'size': size,
            'last_modified': last_modified,
            'ext': ext,
        })
        _upsert_folder_items(parent_prefix)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'ok': True})


def _upsert_folder_items(prefix):
    table = _table()
    current = prefix
    while current and current != DRIVE_PREFIX:
        stripped = current.rstrip('/')
        last_slash = stripped.rfind('/')
        if last_slash < 0:
            break
        parent = stripped[:last_slash + 1]
        if not parent.startswith(DRIVE_PREFIX):
            break
        name = stripped[last_slash + 1:]
        table.put_item(Item={
            'pk': f'folder#{parent}',
            'sk': name + '/',
            'type': 'folder',
            'prefix': current,
            'name': name,
        })
        current = parent


# ── delete ────────────────────────────────────────────────────────────────────

@drive_bp.route('/api/drive/delete', methods=['DELETE'])
@_require_key
def delete_file():
    key = _safe_key(request.json.get('key', '') if request.json else '')
    if not key:
        return jsonify({'error': 'Invalid key'}), 400
    try:
        _s3().delete_object(Bucket=DRIVE_BUCKET, Key=key)
        filename = key.split('/')[-1]
        parent_prefix = key[:key.rfind('/') + 1]
        _table().delete_item(Key={'pk': f'folder#{parent_prefix}', 'sk': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})


# ── rename ────────────────────────────────────────────────────────────────────

@drive_bp.route('/api/drive/rename', methods=['POST'])
@_require_key
def rename_file():
    data = request.json or {}
    src = _safe_key(data.get('from', ''))
    dst = _safe_key(data.get('to', ''))
    if not src or not dst:
        return jsonify({'error': 'Invalid key'}), 400
    try:
        _s3().copy_object(
            Bucket=DRIVE_BUCKET,
            CopySource={'Bucket': DRIVE_BUCKET, 'Key': src},
            Key=dst,
        )
        _s3().delete_object(Bucket=DRIVE_BUCKET, Key=src)

        src_filename = src.split('/')[-1]
        src_parent   = src[:src.rfind('/') + 1]
        dst_filename = dst.split('/')[-1]
        dst_parent   = dst[:dst.rfind('/') + 1]
        ext = dst_filename.rsplit('.', 1)[-1].lower() if '.' in dst_filename else ''

        table = _table()
        old = table.get_item(Key={'pk': f'folder#{src_parent}', 'sk': src_filename}).get('Item', {})
        table.delete_item(Key={'pk': f'folder#{src_parent}', 'sk': src_filename})
        table.put_item(Item={
            'pk': f'folder#{dst_parent}',
            'sk': dst_filename,
            'type': 'file',
            'key': dst,
            'size': old.get('size', 0),
            'last_modified': old.get('last_modified', ''),
            'ext': ext,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True, 'key': dst})


# ── reindex (admin) ───────────────────────────────────────────────────────────

@drive_bp.route('/api/drive/reindex', methods=['POST'])
@_require_key
def reindex():
    """Full reindex: scan all S3 objects under drive/ → populate DynamoDB."""
    try:
        count = _full_reindex()
        return jsonify({'ok': True, 'indexed': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _full_reindex():
    all_items = []
    all_prefixes = set()

    paginator = _s3().get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=DRIVE_BUCKET, Prefix=DRIVE_PREFIX):
        for obj in page.get('Contents') or []:
            key = obj['Key']
            filename = key.split('/')[-1]
            if not filename:
                continue

            parent_prefix = key[:key.rfind('/') + 1]
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

            all_items.append({
                'pk': f'folder#{parent_prefix}',
                'sk': filename,
                'type': 'file',
                'key': key,
                'size': obj['Size'],
                'last_modified': obj['LastModified'].isoformat(),
                'ext': ext,
            })

            rel = key[len(DRIVE_PREFIX):]
            parts = rel.split('/')
            for i in range(1, len(parts)):
                all_prefixes.add(DRIVE_PREFIX + '/'.join(parts[:i]) + '/')

    for folder_prefix in all_prefixes:
        stripped = folder_prefix.rstrip('/')
        last_slash = stripped.rfind('/')
        if last_slash < 0:
            continue
        parent = stripped[:last_slash + 1]
        if not parent.startswith(DRIVE_PREFIX):
            continue
        name = stripped[last_slash + 1:]
        all_items.append({
            'pk': f'folder#{parent}',
            'sk': name + '/',
            'type': 'folder',
            'prefix': folder_prefix,
            'name': name,
        })

    tree = _build_tree_from_prefixes(all_prefixes)
    all_items.append({'pk': '__meta__', 'sk': 'tree', 'data': json.dumps(tree)})

    table = _table()
    with table.batch_writer() as bw:
        for item in all_items:
            bw.put_item(Item=item)

    return len(all_items)
