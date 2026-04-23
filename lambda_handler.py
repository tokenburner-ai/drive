"""Lambda entry point — wraps Flask app for Lambda function URL."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from main import app

app.static_folder = os.path.join(os.path.dirname(__file__), "static")

from apig_wsgi import make_lambda_handler

handler = make_lambda_handler(app)
