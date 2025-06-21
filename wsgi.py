# wsgi.py - PythonAnywhere Web App Configuration

import sys
import os

# プロジェクトディレクトリのパスを設定
# PythonAnywhereでは /home/yourusername/jacet_cat に変更してください
project_home = '/home/yourusername/jacet_cat'

if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# 環境変数の設定
os.environ.setdefault('FLASK_ENV', 'production')

# Flaskアプリケーションをインポート
from app import app as application

# デバッグ情報の設定（本番環境では False に設定）
application.debug = False

if __name__ == "__main__":
    application.run()