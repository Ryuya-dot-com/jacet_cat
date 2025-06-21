#!/usr/bin/env python3
# setup.py - JACET CAT環境設定スクリプト

import os
import subprocess
import sys
from pathlib import Path

def check_python_version():
    """Python バージョンチェック"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8以上が必要です")
        print(f"現在のバージョン: {sys.version}")
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def install_python_packages():
    """Python パッケージのインストール"""
    print("\nPython パッケージをインストール中...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✓ Python パッケージのインストール完了")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Python パッケージのインストールに失敗: {e}")
        return False

def check_r_installation():
    """R インストール確認"""
    try:
        result = subprocess.run(["R", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ R がインストールされています")
            return True
        else:
            print("❌ R がインストールされていません")
            return False
    except FileNotFoundError:
        print("❌ R がインストールされていません")
        print("R をインストールしてください: https://www.r-project.org/")
        return False

def install_r_packages():
    """R パッケージのインストール"""
    print("\nR パッケージをインストール中...")
    
    r_script = '''
    # 必要なRパッケージのインストール
    packages <- c("catR", "ltm", "mirt", "jsonlite")
    
    for (pkg in packages) {
      if (!require(pkg, character.only = TRUE)) {
        cat(paste("Installing", pkg, "...\\n"))
        install.packages(pkg, dependencies = TRUE, repos = "https://cran.rstudio.com/")
        library(pkg, character.only = TRUE)
      } else {
        cat(paste("✓", pkg, "is already installed\\n"))
      }
    }
    
    cat("R packages installation completed!\\n")
    '''
    
    try:
        with open("install_r_packages.R", "w") as f:
            f.write(r_script)
        
        result = subprocess.run(["R", "--vanilla", "-f", "install_r_packages.R"], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ R パッケージのインストール完了")
            os.remove("install_r_packages.R")
            return True
        else:
            print(f"❌ R パッケージのインストールに失敗: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ R パッケージのインストール中にエラー: {e}")
        return False

def create_directory_structure():
    """ディレクトリ構造の作成"""
    print("\nディレクトリ構造を確認中...")
    
    directories = [
        "templates",
        "static",
        "static/css",
        "static/js", 
        "static/images",
        "data",
        "logs",
        "backups"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ {directory}/ ディレクトリ")
    
    return True

def create_config_files():
    """設定ファイルの作成"""
    print("\n設定ファイルを作成中...")
    
    # .env ファイル
    env_content = '''# JACET CAT Environment Configuration
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-change-this-in-production
DATABASE_URL=sqlite:///jacet_cat.db
ADMIN_PASSWORD=admin123
MAX_ITEMS=30
SE_THRESHOLD=0.4
MIN_ITEMS=5
'''
    
    with open(".env", "w") as f:
        f.write(env_content)
    print("✓ .env ファイルを作成しました")
    
    # .gitignore ファイル
    gitignore_content = '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
env.bak/
venv.bak/

# Flask
instance/
.webassets-cache

# Database
*.db
*.sqlite
*.sqlite3

# Logs
logs/
*.log

# Backups
backups/

# Environment variables
.env

# R
.Rhistory
.RData
.Ruserdata

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Temporary files
*.tmp
temp/
'''
    
    with open(".gitignore", "w") as f:
        f.write(gitignore_content)
    print("✓ .gitignore ファイルを作成しました")
    
    return True

def convert_excel_to_csv():
    """Excel ファイルをCSVに変換"""
    print("\nExcel ファイルをCSVに変換中...")
    
    if not os.path.exists("VST_NJ8_Parameter.xlsx"):
        print("⚠️  VST_NJ8_Parameter.xlsx が見つかりません")
        print("   手動でパラメータファイルを配置してください")
        return False
    
    try:
        import pandas as pd
        
        # Excelファイルを読み込み
        df = pd.read_excel('VST_NJ8_Parameter.xlsx', sheet_name='Sheet1')
        
        # 列名を統一
        df.columns = ['Level', 'Item', 'PartOfSpeech', 'CorrectAnswer', 
                      'Distractor_1', 'Distractor_2', 'Distractor_3',
                      'Dscrimination', 'Difficulty', 'Guessing']
        
        # CSVファイルとして保存
        df.to_csv('jacet_parameters.csv', index=False, encoding='utf-8')
        
        print(f"✓ {len(df)} 項目をCSVファイルに変換しました")
        return True
        
    except Exception as e:
        print(f"❌ Excel変換エラー: {e}")
        return False

def create_startup_script():
    """起動スクリプトの作成"""
    print("\n起動スクリプトを作成中...")
    
    # Windows用バッチファイル
    bat_content = '''@echo off
echo JACET CAT システムを起動中...
python app.py
pause
'''
    
    with open("start_jacet_cat.bat", "w") as f:
        f.write(bat_content)
    
    # Unix/Linux/Mac用シェルスクリプト
    sh_content = '''#!/bin/bash
echo "JACET CAT システムを起動中..."
python3 app.py
'''
    
    with open("start_jacet_cat.sh", "w") as f:
        f.write(sh_content)
    
    # 実行権限を付与
    try:
        os.chmod("start_jacet_cat.sh", 0o755)
    except:
        pass
    
    print("✓ 起動スクリプトを作成しました")
    return True

def main():
    """メイン実行関数"""
    print("="*60)
    print("JACET CAT システム環境設定")
    print("="*60)
    
    success = True
    
    # Python バージョンチェック
    success &= check_python_version()
    
    # ディレクトリ構造作成
    success &= create_directory_structure()
    
    # Python パッケージインストール
    success &= install_python_packages()
    
    # R インストール確認
    success &= check_r_installation()
    
    # R パッケージインストール
    success &= install_r_packages()
    
    # 設定ファイル作成
    success &= create_config_files()
    
    # Excel → CSV 変換
    convert_excel_to_csv()  # 失敗してもcontinue
    
    # 起動スクリプト作成
    success &= create_startup_script()
    
    print("\n" + "="*60)
    if success:
        print("✅ 環境設定が完了しました！")
        print("\n次のステップ:")
        print("1. python create_database.py を実行してデータベースを作成")
        print("2. python app.py を実行してWebアプリケーションを起動")
        print("3. ブラウザで http://localhost:5000 にアクセス")
    else:
        print("⚠️  一部の設定で問題が発生しました")
        print("エラーメッセージを確認して、手動で設定を完了してください")
    
    print("="*60)

if __name__ == "__main__":
    main()