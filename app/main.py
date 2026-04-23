"""Token Drive — Flask app entry point."""

import os
from flask import Flask, jsonify

app = Flask(__name__, static_folder='../static')

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

from drive_api import drive_bp
app.register_blueprint(drive_bp)


@app.route('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=False, use_reloader=False)
