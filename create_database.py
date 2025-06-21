#!/usr/bin/env python3
# create_database.py - JACET CAT データベース初期化スクリプト

import sqlite3
import pandas as pd
from datetime import datetime
import os

def create_database():
    """
    JACET CAT システム用のSQLiteデータベースを作成・初期化
    """
    
    print("JACET CAT データベースを初期化中...")
    
    # 既存のデータベースファイルがある場合のバックアップ
    if os.path.exists('jacet_cat.db'):
        backup_name = f'jacet_cat_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        os.rename('jacet_cat.db', backup_name)
        print(f"既存データベースを {backup_name} にバックアップしました")
    
    # 新しいデータベース接続
    conn = sqlite3.connect('jacet_cat.db')
    cursor = conn.cursor()
    
    # 1. テストセッションテーブル
    cursor.execute('''
        CREATE TABLE test_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            final_theta REAL,
            final_se REAL,
            vocabulary_size INTEGER,
            items_administered INTEGER,
            status TEXT DEFAULT 'active',
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ test_sessions テーブルを作成しました")
    
    # 2. 回答記録テーブル
    cursor.execute('''
        CREATE TABLE responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            item_id INTEGER,
            item_word TEXT,
            item_level INTEGER,
            response INTEGER,
            correct_answer TEXT,
            user_answer TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            theta_before REAL,
            theta_after REAL,
            se_after REAL,
            response_time REAL,
            FOREIGN KEY (session_id) REFERENCES test_sessions (session_id)
        )
    ''')
    print("✓ responses テーブルを作成しました")
    
    # 3. 項目統計テーブル
    cursor.execute('''
        CREATE TABLE item_statistics (
            item_id INTEGER PRIMARY KEY,
            item_word TEXT,
            item_level INTEGER,
            exposure_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            total_responses INTEGER DEFAULT 0,
            p_value REAL DEFAULT 0.0,
            discrimination REAL,
            difficulty REAL,
            guessing REAL,
            last_used TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ item_statistics テーブルを作成しました")
    
    # 4. 項目バンクテーブル
    cursor.execute('''
        CREATE TABLE item_bank (
            item_id INTEGER PRIMARY KEY,
            level INTEGER,
            item_word TEXT,
            part_of_speech TEXT,
            correct_answer TEXT,
            distractor_1 TEXT,
            distractor_2 TEXT,
            distractor_3 TEXT,
            discrimination REAL,
            difficulty REAL,
            guessing REAL,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ item_bank テーブルを作成しました")
    
    # 5. システム設定テーブル
    cursor.execute('''
        CREATE TABLE system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ system_settings テーブルを作成しました")
    
    # インデックスの作成
    indexes = [
        "CREATE INDEX idx_sessions_status ON test_sessions(status)",
        "CREATE INDEX idx_sessions_start_time ON test_sessions(start_time)",
        "CREATE INDEX idx_responses_session_id ON responses(session_id)",
        "CREATE INDEX idx_responses_item_id ON responses(item_id)",
        "CREATE INDEX idx_responses_timestamp ON responses(timestamp)",
        "CREATE INDEX idx_item_stats_level ON item_statistics(item_level)",
        "CREATE INDEX idx_item_bank_level ON item_bank(level)",
        "CREATE INDEX idx_item_bank_active ON item_bank(active)"
    ]
    
    for index_sql in indexes:
        cursor.execute(index_sql)
    print("✓ インデックスを作成しました")
    
    # 項目バンクデータの読み込み
    try:
        print("項目パラメータファイルを読み込み中...")
        df = pd.read_csv('jacet_parameters.csv')
        print(f"✓ {len(df)} 項目のパラメータファイルを読み込みました")
        
        # 項目バンクテーブルへデータ挿入
        for index, row in df.iterrows():
            cursor.execute('''
                INSERT INTO item_bank 
                (item_id, level, item_word, part_of_speech, correct_answer,
                 distractor_1, distractor_2, distractor_3, 
                 discrimination, difficulty, guessing, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                index + 1,
                row['Level'],
                row['Item'],
                row['PartOfSpeech'],
                row['CorrectAnswer'],
                row['Distractor_1'],
                row['Distractor_2'],
                row['Distractor_3'],
                row['Dscrimination'],
                row['Difficulty'],
                row['Guessing']
            ))
        
        # 項目統計テーブルの初期化
        for index, row in df.iterrows():
            cursor.execute('''
                INSERT INTO item_statistics
                (item_id, item_word, item_level, discrimination, difficulty, guessing)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                index + 1,
                row['Item'],
                row['Level'],
                row['Dscrimination'],
                row['Difficulty'],
                row['Guessing']
            ))
        
        print(f"✓ {len(df)} 項目をitem_bankテーブルに挿入しました")
        print(f"✓ {len(df)} 項目をitem_statisticsテーブルに挿入しました")
        
    except FileNotFoundError:
        print("⚠️  警告: jacet_parameters.csv が見つかりません")
        print("   項目バンクデータは後で手動で追加してください")
    except Exception as e:
        print(f"❌ エラー: 項目データの読み込みに失敗しました: {e}")
    
    # システム設定の初期値
    default_settings = [
        ('se_threshold', '0.4', 'CAT終了のためのSE閾値'),
        ('max_items', '30', 'CAT最大出題数'),
        ('min_items', '5', 'CAT最小出題数'),
        ('time_limit_per_item', '180', '項目あたりの制限時間（秒）'),
        ('exposure_control', '1', '項目露出制御の有効/無効'),
        ('admin_password', 'admin123', '管理者パスワード（要変更）'),
        ('system_version', '1.0.0', 'システムバージョン')
    ]
    
    for key, value, desc in default_settings:
        cursor.execute('''
            INSERT INTO system_settings (setting_key, setting_value, description)
            VALUES (?, ?, ?)
        ''', (key, value, desc))
    
    print("✓ システム設定の初期値を設定しました")
    
    # トリガーの作成（updated_atの自動更新）
    trigger_sql = '''
        CREATE TRIGGER update_item_stats_timestamp 
        AFTER UPDATE ON item_statistics
        BEGIN
            UPDATE item_statistics 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE item_id = NEW.item_id;
        END
    '''
    cursor.execute(trigger_sql)
    print("✓ 自動更新トリガーを作成しました")
    
    # コミットしてデータベースを閉じる
    conn.commit()
    conn.close()
    
    print("\n" + "="*50)
    print("✅ JACET CAT データベースの初期化が完了しました！")
    print("="*50)
    print(f"データベースファイル: jacet_cat.db")
    print(f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # データベース情報の表示
    conn = sqlite3.connect('jacet_cat.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM item_bank WHERE active = 1")
    active_items = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT level) FROM item_bank WHERE active = 1")
    levels = cursor.fetchone()[0]
    
    print(f"有効項目数: {active_items}")
    print(f"レベル数: {levels}")
    
    # レベル別項目数
    cursor.execute('''
        SELECT level, COUNT(*) 
        FROM item_bank 
        WHERE active = 1 
        GROUP BY level 
        ORDER BY level
    ''')
    level_counts = cursor.fetchall()
    
    print("\nレベル別項目数:")
    for level, count in level_counts:
        print(f"  Level {level}: {count} 項目")
    
    conn.close()
    
    print("\n次のステップ:")
    print("1. app.py を実行してWebアプリケーションを起動")
    print("2. ブラウザで http://localhost:5000 にアクセス")
    print("3. 管理者画面は http://localhost:5000/admin/statistics")
    print("\n⚠️  本番環境では admin_password を必ず変更してください！")

def verify_database():
    """
    データベースの整合性を確認
    """
    print("\nデータベースの整合性を確認中...")
    
    try:
        conn = sqlite3.connect('jacet_cat.db')
        cursor = conn.cursor()
        
        # テーブル存在確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['test_sessions', 'responses', 'item_statistics', 'item_bank', 'system_settings']
        
        for table in expected_tables:
            if table in tables:
                print(f"✓ {table} テーブルが存在します")
            else:
                print(f"❌ {table} テーブルが見つかりません")
        
        # 項目バンクデータ確認
        cursor.execute("SELECT COUNT(*) FROM item_bank")
        item_count = cursor.fetchone()[0]
        
        if item_count > 0:
            print(f"✓ 項目バンクに {item_count} 項目が登録されています")
        else:
            print("⚠️  項目バンクにデータがありません")
        
        conn.close()
        print("✅ データベース検証完了")
        
    except Exception as e:
        print(f"❌ データベース検証エラー: {e}")

if __name__ == "__main__":
    create_database()
    verify_database()