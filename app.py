#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JACET語彙サイズテスト Computer Adaptive Testing (CAT) システム

Author: JACET Vocabulary Research Team
Version: 1.0.0
License: MIT

最初に以下のコードで仮装環境
source jacet_env/bin/activate
"""

from flask import Flask, render_template, request, session, jsonify, redirect, url_for, flash, Response
import subprocess
import json
import os
import tempfile
import uuid
import sqlite3
import shutil
import pandas as pd
from datetime import datetime
import logging
from functools import wraps
import random

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/jacet_cat.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flaskアプリケーション初期化
app = Flask(__name__)
app.secret_key = 'jacet-cat-secret-key-change-this-in-production'

# アプリケーション設定
app.config.update(
    PERMANENT_SESSION_LIFETIME=3600,  # 1時間
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    SEND_FILE_MAX_AGE_DEFAULT=300,  # 5分
    SESSION_COOKIE_SECURE=False,  # 本番環境ではTrueに
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# 必要なディレクトリを作成
for directory in ['logs', 'backups', 'temp']:
    os.makedirs(directory, exist_ok=True)

# ============================================================================
# ユーティリティ関数
# ============================================================================

def run_r_script(script_content, input_data=None, timeout=30):
    """
    R スクリプトを実行し、結果を返す
    
    Args:
        script_content (str): 実行するRスクリプト
        input_data (dict): 入力データ（JSON形式）
        timeout (int): タイムアウト時間（秒）
    
    Returns:
        tuple: (stdout, stderr)
    """
    try:
        # 一時ファイル作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.R', delete=False) as f:
            f.write(script_content)
            r_script_path = f.name
        
        input_path = None
        if input_data:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(input_data, f)
                input_path = f.name
        
        # R スクリプト実行
        env = os.environ.copy()
        env['R_LIBS_USER'] = os.path.expanduser('~/R/library')
        
        result = subprocess.run(
            ['Rscript', r_script_path], 
            capture_output=True, 
            text=True, 
            env=env,
            timeout=timeout
        )
        
        # 一時ファイル削除
        os.unlink(r_script_path)
        if input_path:
            os.unlink(input_path)
        
        if result.returncode != 0:
            logger.error(f"R script error: {result.stderr}")
            raise Exception(f"R script error: {result.stderr}")
        
        return result.stdout.strip(), result.stderr
    
    except subprocess.TimeoutExpired:
        logger.error("R script timeout")
        raise Exception("R script execution timeout")
    except Exception as e:
        logger.error(f"R script execution error: {e}")
        return None, str(e)

def get_db_connection():
    """データベース接続を取得"""
    try:
        conn = sqlite3.connect('jacet_cat.db', timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def require_admin(f):
    """管理者認証デコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def shuffle_options(correct_answer, distractors):
    """選択肢をシャッフルして返す"""
    all_options = [correct_answer] + list(distractors)
    random.shuffle(all_options)
    return all_options

def log_user_action(action, session_id=None, details=None):
    """ユーザーアクションをログに記録"""
    logger.info(f"Action: {action}, Session: {session_id}, Details: {details}")

# ============================================================================
# エラーハンドラー
# ============================================================================

@app.errorhandler(404)
def page_not_found(e):
    """404エラーハンドラー"""
    return render_template('error.html', 
                         error_code=404, 
                         error_message="ページが見つかりません"), 404

@app.errorhandler(500)
def internal_error(e):
    """500エラーハンドラー"""
    logger.error(f"Internal server error: {e}")
    return render_template('error.html', 
                         error_code=500, 
                         error_message="内部サーバーエラーが発生しました"), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """予期しないエラーのハンドラー"""
    logger.error(f"Unhandled exception: {e}")
    return render_template('error.html', 
                         error_code=500, 
                         error_message="予期しないエラーが発生しました"), 500

# ============================================================================
# メインルート
# ============================================================================

@app.route('/')
def index():
    """トップページ"""
    try:
        # システム統計の簡単な表示
        conn = get_db_connection()
        total_sessions = conn.execute('SELECT COUNT(*) FROM test_sessions').fetchone()[0]
        completed_sessions = conn.execute('SELECT COUNT(*) FROM test_sessions WHERE status = "completed"').fetchone()[0]
        conn.close()
        
        return render_template('index.html', 
                             total_sessions=total_sessions,
                             completed_sessions=completed_sessions)
    except Exception as e:
        logger.error(f"Index page error: {e}")
        return render_template('index.html', 
                             total_sessions=0,
                             completed_sessions=0)

@app.route('/start_test', methods=['POST'])
def start_test():
    """テスト開始"""
    try:
        user_id = request.form.get('user_id', 'anonymous')
        session_id = str(uuid.uuid4())
        
        # セッション情報を保存
        session['cat_session_id'] = session_id
        session['user_id'] = user_id
        session['start_time'] = datetime.now().isoformat()
        
        # データベースに記録
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO test_sessions (session_id, user_id, start_time, status, ip_address, user_agent)
            VALUES (?, ?, ?, 'active', ?, ?)
        ''', (session_id, user_id, datetime.now(), 
              request.environ.get('REMOTE_ADDR', 'unknown'),
              request.environ.get('HTTP_USER_AGENT', 'unknown')))
        conn.commit()
        conn.close()
        
        log_user_action('test_started', session_id, f'user_id: {user_id}')
        
        # R でCATセッション初期化
        r_script = '''
        source('jacet_cat_function.r')
        library(jsonlite)
        
        # 項目バンク読み込み
        item_bank <- read.csv('jacet_parameters.csv', stringsAsFactors = FALSE)
        
        # CATセッション初期化
        cat_session <- list(
            item_bank = item_bank,
            administered_items = c(),
            responses = c(),
            current_theta = 0,
            current_se = Inf,
            se_threshold = 0.4,
            max_items = 30,
            min_items = 20,
            exposure_count = rep(0, nrow(item_bank))
        )
        
        # 最初の項目選択（ランダムに中程度の難易度から）
        initial_items <- which(item_bank$Level %in% c(3, 4, 5))
        next_item <- sample(initial_items, 1)
        
        # 結果をJSON形式で出力
        result <- list(
            current_theta = cat_session$current_theta,
            current_se = cat_session$current_se,
            items_count = length(cat_session$administered_items),
            should_continue = TRUE,
            next_item = list(
                id = next_item,
                word = item_bank$Item[next_item],
                level = item_bank$Level[next_item],
                correct_answer = item_bank$CorrectAnswer[next_item],
                distractors = c(
                    item_bank$Distractor_1[next_item],
                    item_bank$Distractor_2[next_item],
                    item_bank$Distractor_3[next_item]
                )
            ),
            administered_items = cat_session$administered_items,
            responses = cat_session$responses
        )
        
        cat(toJSON(result, auto_unbox = TRUE))
        '''
        
        output, error = run_r_script(r_script)
        
        if error and not output:
            logger.error(f"R script error in start_test: {error}")
            flash('テストの初期化に失敗しました。しばらく待ってから再試行してください。', 'error')
            return redirect(url_for('index'))
        
        try:
            result = json.loads(output)
            session['cat_state'] = result
            return redirect(url_for('test_interface'))
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in start_test: {e}")
            flash('テストの初期化でエラーが発生しました。', 'error')
            return redirect(url_for('index'))
    
    except Exception as e:
        logger.error(f"Error in start_test: {e}")
        flash('テスト開始時にエラーが発生しました。', 'error')
        return redirect(url_for('index'))

@app.route('/test')
def test_interface():
    """テスト画面"""
    if 'cat_session_id' not in session:
        flash('有効なテストセッションがありません。', 'warning')
        return redirect(url_for('index'))
    
    cat_state = session.get('cat_state', {})
    if not cat_state.get('should_continue', True):
        return redirect(url_for('show_results'))
    
    next_item = cat_state.get('next_item', {})
    if not next_item:
        flash('次の問題の取得に失敗しました。', 'error')
        return redirect(url_for('show_results'))
    
    # 選択肢をシャッフル
    correct_answer = next_item.get('correct_answer')
    distractors = next_item.get('distractors', [])
    shuffled_options = shuffle_options(correct_answer, distractors)
    
    return render_template('test.html', 
                         next_item=next_item,
                         shuffled_options=shuffled_options,
                         progress=cat_state.get('items_count', 0))

@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    """回答送信処理"""
    if 'cat_session_id' not in session:
        return jsonify({'error': 'No active session'}), 400
    
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        user_answer = data.get('answer')
        response_time = data.get('response_time', 0)
        
        # 現在のCAT状態取得
        cat_state = session.get('cat_state', {})
        current_item = cat_state.get('next_item', {})

        # ------------------------------------------------------------------
        # jsonlite::toJSON(auto_unbox = TRUE) で要素数 1 のベクトルがスカラーに
        # 化けるため、Python 側で必ずリストに正規化しておく
        admin_items    = cat_state.get('administered_items', [])
        if not isinstance(admin_items, list):
            admin_items = [admin_items]

        responses_prev = cat_state.get('responses', [])
        if not isinstance(responses_prev, list):
            responses_prev = [responses_prev]
        # ------------------------------------------------------------------
        
        # 正答判定
        correct_answer = current_item.get('correct_answer')
        is_correct = 1 if user_answer == correct_answer else 0
        
        log_user_action('answer_submitted', session['cat_session_id'], 
                       f'item_id: {item_id}, correct: {is_correct}')
        
        # R で回答処理と次項目選択
        r_script = f'''
        source('jacet_cat_function.r')
        library(jsonlite)
        
        # 現在のセッション状態を復元
        administered_items <- c({",".join(map(str, admin_items))})
        responses <- c({",".join(map(str, responses_prev))})
        
        # 項目バンク読み込み
        item_bank <- read.csv('jacet_parameters.csv', stringsAsFactors = FALSE)
        
        # 3PLモデルの確率関数
        prob_3pl <- function(theta, a, b, c) {{
            return(c + (1 - c) / (1 + exp(-a * (theta - b))))
        }}
        
        # 項目情報関数
        item_info_3pl <- function(theta, a, b, c) {{
            p <- prob_3pl(theta, a, b, c)
            q <- 1 - p
            if(p <= c || p >= 1) return(0)
            info <- (a^2 * q * (p - c)^2) / (p * (1 - c)^2)
            return(info)
        }}
        
        # EAP推定
        estimate_ability_eap <- function(items, responses, item_bank) {{
            if(length(responses) == 0) {{
                return(list(theta = 0, se = Inf))
            }}
            
            theta_range <- seq(-4, 4, by = 0.01)
            prior <- dnorm(theta_range, 0, 1)
            likelihood <- rep(1, length(theta_range))
            
            for(i in 1:length(items)) {{
                item_idx <- items[i]
                response <- responses[i]
                
                a <- item_bank$Dscrimination[item_idx]
                b <- item_bank$Difficulty[item_idx]
                c <- item_bank$Guessing[item_idx]
                
                prob <- prob_3pl(theta_range, a, b, c)
                
                if(response == 1) {{
                    likelihood <- likelihood * prob
                }} else {{
                    likelihood <- likelihood * (1 - prob)
                }}
            }}
            
            posterior <- likelihood * prior
            posterior <- posterior / sum(posterior)
            
            theta_eap <- sum(theta_range * posterior)
            variance <- sum((theta_range - theta_eap)^2 * posterior)
            se <- sqrt(variance)
            
            return(list(theta = theta_eap, se = se))
        }}
        
        # 回答を記録
        administered_items <- c(administered_items, {item_id})
        responses <- c(responses, {is_correct})
        
        # 能力値更新
        ability_result <- estimate_ability_eap(administered_items, responses, item_bank)
        current_theta <- ability_result$theta
        current_se <- ability_result$se
        
        # 終了条件チェック
        min_items      <- 20         # 最小出題数
        max_items      <- 30         # 最大出題数
        se_threshold   <- 0.4        # 精度基準 (標準誤差)

        required_high  <- 2          # Level 7+ を最低 2 問
        high_admin     <- sum(item_bank$Level[administered_items] >= 7)

        should_continue <- (
            current_se > se_threshold ||            # 精度がまだ低い
            length(administered_items) < min_items  # 最小数未満
            || high_admin < required_high           # 高レベル項目が足りない
        ) && length(administered_items) < max_items
        
        if(should_continue) {{
            # 次項目選択（最大情報量基準）
            available_items <- setdiff(1:nrow(item_bank), administered_items)

            # 高レベル必須数を満たすまでは Level 7+ を優先
            if(high_admin < required_high){{ 
                hi_candidates <- intersect(available_items, which(item_bank$Level >= 7))
                if(length(hi_candidates) > 0){{ 
                    available_items <- hi_candidates
                }} 
            }}

            if(length(available_items) > 0) {{
                info_values <- sapply(available_items, function(i) {{
                    a <- item_bank$Dscrimination[i]
                    b <- item_bank$Difficulty[i]
                    c <- item_bank$Guessing[i]
                    return(item_info_3pl(current_theta, a, b, c))
                }})

                next_item_idx <- available_items[which.max(info_values)]

                result <- list(
                    current_theta = current_theta,
                    current_se = current_se,
                    items_count = length(administered_items),
                    should_continue = TRUE,
                    next_item = list(
                        id = next_item_idx,
                        word = item_bank$Item[next_item_idx],
                        level = item_bank$Level[next_item_idx],
                        correct_answer = item_bank$CorrectAnswer[next_item_idx],
                        distractors = c(
                            item_bank$Distractor_1[next_item_idx],
                            item_bank$Distractor_2[next_item_idx],
                            item_bank$Distractor_3[next_item_idx]
                        )
                    ),
                    administered_items = administered_items,
                    responses = responses
                )
            }} else {{
                should_continue <- FALSE
            }}
        }}
        
        if(!should_continue) {{
            # 語彙サイズ推定
            level_difficulties <- c(-2.206, -1.512, -0.701, -0.075, 0.748, 1.152, 1.504, 2.089)
            vocab_size <- 0
            for(i in 1:8) {{
                prob_mastery <- 1 / (1 + exp(-(current_theta - level_difficulties[i])))
                vocab_size <- vocab_size + 1000 * prob_mastery
            }}
            
            result <- list(
                current_theta = current_theta,
                current_se = current_se,
                items_count = length(administered_items),
                should_continue = FALSE,
                final_result = list(
                    final_theta = current_theta,
                    final_se = current_se,
                    vocabulary_size = round(vocab_size),
                    items_administered = length(administered_items),
                    efficiency = length(administered_items) / 160
                ),
                administered_items = administered_items,
                responses = responses
            )
        }}
        
        cat(toJSON(result, auto_unbox = TRUE))
        '''
        
        output, error = run_r_script(r_script)
        
        if error and not output:
            logger.error(f"R script error in submit_answer: {error}")
            return jsonify({'error': f'回答処理エラー: {error}'}), 500
        
        try:
            result = json.loads(output)
            
            # データベースに回答記録
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO responses 
                (session_id, item_id, item_word, item_level, response, 
                 correct_answer, user_answer, timestamp, theta_before, theta_after, se_after, response_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session['cat_session_id'],
                item_id,
                current_item.get('word'),
                current_item.get('level'),
                is_correct,
                correct_answer,
                user_answer,
                datetime.now(),
                cat_state.get('current_theta', 0),
                result.get('current_theta'),
                result.get('current_se'),
                response_time
            ))
            
            # 項目統計更新
            conn.execute('''
                UPDATE item_statistics 
                SET exposure_count = exposure_count + 1,
                    total_responses = total_responses + 1,
                    correct_count = correct_count + ?,
                    p_value = CAST(correct_count AS FLOAT) / total_responses,
                    last_used = CURRENT_TIMESTAMP
                WHERE item_id = ?
            ''', (is_correct, item_id))
            
            conn.commit()
            conn.close()
            
            # セッション状態更新
            session['cat_state'] = result
            
            return jsonify(result)
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in submit_answer: {e}")
            return jsonify({'error': 'JSON解析エラー'}), 500
    
    except Exception as e:
        logger.error(f"Error in submit_answer: {e}")
        return jsonify({'error': '回答処理中にエラーが発生しました'}), 500

@app.route('/results')
def show_results():
    """結果表示"""
    if 'cat_session_id' not in session:
        flash('有効なテストセッションがありません。', 'warning')
        return redirect(url_for('index'))
    
    cat_state = session.get('cat_state', {})
    final_result = cat_state.get('final_result')
    
    if not final_result:
        flash('テスト結果が見つかりません。', 'error')
        return redirect(url_for('test_interface'))
    
    try:
        # データベースに最終結果保存
        conn = get_db_connection()
        conn.execute('''
            UPDATE test_sessions 
            SET end_time = ?, final_theta = ?, final_se = ?, 
                vocabulary_size = ?, items_administered = ?, status = 'completed'
            WHERE session_id = ?
        ''', (
            datetime.now(),
            final_result.get('final_theta'),
            final_result.get('final_se'),
            final_result.get('vocabulary_size'),
            final_result.get('items_administered'),
            session['cat_session_id']
        ))
        
        # 回答履歴取得
        cursor = conn.execute('''
            SELECT item_word, item_level, response, theta_after, timestamp
            FROM responses 
            WHERE session_id = ? 
            ORDER BY timestamp
        ''', (session['cat_session_id'],))
        
        response_history = cursor.fetchall()
        conn.commit()
        conn.close()
        
        log_user_action('test_completed', session['cat_session_id'], 
                       f'vocab_size: {final_result.get("vocabulary_size")}')
        
        return render_template('results.html', 
                             result=final_result,
                             response_history=response_history)
    
    except Exception as e:
        logger.error(f"Error in show_results: {e}")
        flash('結果の保存中にエラーが発生しました。', 'error')
        return render_template('results.html', 
                             result=final_result,
                             response_history=[])

# ============================================================================
# 管理者機能
# ============================================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """管理者ログイン"""
    if request.method == 'POST':
        password = request.form.get('password')
        
        try:
            # データベースから管理者パスワードを取得
            conn = get_db_connection()
            cursor = conn.execute('SELECT setting_value FROM system_settings WHERE setting_key = "admin_password"')
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0] == password:
                session['admin_logged_in'] = True
                session.permanent = True
                log_user_action('admin_login', details='successful')
                flash('ログインしました。', 'success')
                return redirect(url_for('admin_statistics'))
            else:
                log_user_action('admin_login', details='failed')
                flash('パスワードが間違っています。', 'error')
        
        except Exception as e:
            logger.error(f"Admin login error: {e}")
            flash('ログイン処理でエラーが発生しました。', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """管理者ログアウト"""
    session.pop('admin_logged_in', None)
    log_user_action('admin_logout')
    flash('ログアウトしました。', 'info')
    return redirect(url_for('index'))

@app.route('/admin/statistics')
@require_admin
def admin_statistics():
    """管理者統計ダッシュボード"""
    try:
        conn = get_db_connection()
        
        # 基本統計
        stats = {}
        stats['total_sessions'] = conn.execute('SELECT COUNT(*) FROM test_sessions').fetchone()[0]
        stats['completed_sessions'] = conn.execute('SELECT COUNT(*) FROM test_sessions WHERE status = "completed"').fetchone()[0]
        
        avg_vocab = conn.execute('SELECT AVG(vocabulary_size) FROM test_sessions WHERE status = "completed"').fetchone()[0]
        stats['avg_vocabulary_size'] = avg_vocab if avg_vocab else 0
        
        avg_items = conn.execute('SELECT AVG(items_administered) FROM test_sessions WHERE status = "completed"').fetchone()[0]
        stats['avg_items_administered'] = avg_items if avg_items else 0
        
        # 語彙サイズ分布
        vocab_distribution = conn.execute('''
            SELECT 
                CASE 
                    WHEN vocabulary_size < 1000 THEN '0-999'
                    WHEN vocabulary_size < 2000 THEN '1000-1999'
                    WHEN vocabulary_size < 3000 THEN '2000-2999'
                    WHEN vocabulary_size < 4000 THEN '3000-3999'
                    WHEN vocabulary_size < 5000 THEN '4000-4999'
                    WHEN vocabulary_size < 6000 THEN '5000-5999'
                    WHEN vocabulary_size < 7000 THEN '6000-6999'
                    ELSE '7000+'
                END as range,
                COUNT(*) as count
            FROM test_sessions 
            WHERE status = 'completed' AND vocabulary_size IS NOT NULL
            GROUP BY range
            ORDER BY 
                CASE range
                    WHEN '0-999' THEN 1
                    WHEN '1000-1999' THEN 2
                    WHEN '2000-2999' THEN 3
                    WHEN '3000-3999' THEN 4
                    WHEN '4000-4999' THEN 5
                    WHEN '5000-5999' THEN 6
                    WHEN '6000-6999' THEN 7
                    ELSE 8
                END
        ''').fetchall()
        
        conn.close()
        
        return render_template('admin_statistics.html', 
                             stats=stats, 
                             vocab_distribution=vocab_distribution)
    
    except Exception as e:
        logger.error(f"Admin statistics error: {e}")
        flash('統計データの取得でエラーが発生しました。', 'error')
        return render_template('admin_statistics.html', 
                             stats={}, 
                             vocab_distribution=[])

@app.route('/admin/item_statistics')
@require_admin
def admin_item_statistics():
    """項目統計API"""
    try:
        conn = get_db_connection()
        cursor = conn.execute('''
            SELECT 
                s.item_id,
                s.item_word,
                s.item_level,
                s.exposure_count,
                s.correct_count,
                s.total_responses,
                CASE 
                    WHEN s.total_responses > 0 THEN CAST(s.correct_count AS FLOAT) / s.total_responses
                    ELSE 0.0
                END as p_value,
                s.discrimination,
                s.difficulty,
                s.guessing,
                s.last_used
            FROM item_statistics s
            ORDER BY s.item_level, s.item_id
        ''')
        
        items = []
        for row in cursor.fetchall():
            items.append({
                'item_id': row[0],
                'word': row[1],
                'level': row[2],
                'exposure_count': row[3],
                'correct_count': row[4],
                'total_responses': row[5],
                'p_value': row[6],
                'discrimination': row[7],
                'difficulty': row[8],
                'guessing': row[9],
                'last_used': row[10]
            })
        
        conn.close()
        return jsonify(items)
    
    except Exception as e:
        logger.error(f"Item statistics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/export/<data_type>')
@require_admin
def admin_export(data_type):
    """データエクスポート機能"""
    try:
        conn = get_db_connection()
        
        if data_type == 'sessions':
            df = pd.read_sql_query('SELECT * FROM test_sessions ORDER BY start_time DESC', conn)
            filename = f'sessions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        elif data_type == 'responses':
            df = pd.read_sql_query('SELECT * FROM responses ORDER BY timestamp DESC', conn)
            filename = f'responses_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        elif data_type == 'statistics':
            df = pd.read_sql_query('SELECT * FROM item_statistics ORDER BY item_level, item_id', conn)
            filename = f'statistics_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        else:
            conn.close()
            return "Invalid data type", 400
        
        conn.close()
        
        # CSVファイルとして出力
        output = df.to_csv(index=False, encoding='utf-8-sig')
        
        log_user_action('data_export', details=f'type: {data_type}')
        
        return Response(
            output,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment;filename={filename}'}
        )
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        flash('データエクスポートでエラーが発生しました。', 'error')
        return redirect(url_for('admin_statistics'))

@app.route('/admin/backup', methods=['POST'])
@require_admin
def admin_backup():
    """データベースバックアップ"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f'jacet_cat_backup_{timestamp}.db'
        backup_path = os.path.join('backups', backup_filename)
        
        # バックアップディレクトリ作成
        os.makedirs('backups', exist_ok=True)
        
        # データベースファイルをコピー
        shutil.copy2('jacet_cat.db', backup_path)
        
        log_user_action('database_backup', details=f'file: {backup_filename}')
        
        return jsonify({
            'success': True,
            'filename': backup_filename,
            'timestamp': timestamp
        })
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/admin/settings', methods=['GET', 'POST'])
@require_admin
def admin_settings():
    """システム設定管理"""
    try:
        conn = get_db_connection()
        
        if request.method == 'POST':
            # 設定更新
            settings = request.form.to_dict()
            
            for key, value in settings.items():
                conn.execute('''
                    UPDATE system_settings 
                    SET setting_value = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE setting_key = ?
                ''', (value, key))
            
            conn.commit()
            log_user_action('settings_updated', details=f'keys: {list(settings.keys())}')
            flash('設定を更新しました。', 'success')
        
        # 現在の設定を取得
        cursor = conn.execute('SELECT setting_key, setting_value, description FROM system_settings')
        settings = cursor.fetchall()
        
        conn.close()
        
        return render_template('admin_settings.html', settings=settings)
    
    except Exception as e:
        logger.error(f"Settings error: {e}")
        flash('設定の処理でエラーが発生しました。', 'error')
        return redirect(url_for('admin_statistics'))

@app.route('/admin/update_statistics', methods=['POST'])
@require_admin
def admin_update_statistics():
    """項目統計手動更新"""
    try:
        conn = get_db_connection()
        
        # 各項目の統計を計算
        cursor = conn.execute('''
            SELECT 
                r.item_id,
                COUNT(*) as total_responses,
                SUM(r.response) as correct_count
            FROM responses r
            GROUP BY r.item_id
        ''')
        
        stats = cursor.fetchall()
        
        for item_id, total_responses, correct_count in stats:
            p_value = correct_count / total_responses if total_responses > 0 else 0
            
            conn.execute('''
                UPDATE item_statistics 
                SET 
                    exposure_count = ?,
                    total_responses = ?,
                    correct_count = ?,
                    p_value = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
            ''', (total_responses, total_responses, correct_count, p_value, item_id))
        
        # 最後に使用された日時を更新
        conn.execute('''
            UPDATE item_statistics 
            SET last_used = (
                SELECT MAX(timestamp) 
                FROM responses 
                WHERE responses.item_id = item_statistics.item_id
            )
            WHERE item_id IN (SELECT DISTINCT item_id FROM responses)
        ''')
        
        conn.commit()
        conn.close()
        
        log_user_action('statistics_manual_update')
        
        return jsonify({'success': True, 'message': '統計を更新しました'})
    
    except Exception as e:
        logger.error(f"Statistics update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# API エンドポイント
# ============================================================================

@app.route('/api/system_status')
def api_system_status():
    """システム状態API"""
    try:
        conn = get_db_connection()
        
        # 基本統計
        total_sessions = conn.execute('SELECT COUNT(*) FROM test_sessions').fetchone()[0]
        active_sessions = conn.execute('SELECT COUNT(*) FROM test_sessions WHERE status = "active"').fetchone()[0]
        completed_today = conn.execute('''
            SELECT COUNT(*) FROM test_sessions 
            WHERE status = "completed" AND DATE(end_time) = DATE('now')
        ''').fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'completed_today': completed_today,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"System status error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/vocabulary_distribution')
def api_vocabulary_distribution():
    """語彙サイズ分布API"""
    try:
        conn = get_db_connection()
        
        cursor = conn.execute('''
            SELECT vocabulary_size, COUNT(*) as count
            FROM test_sessions 
            WHERE status = 'completed' AND vocabulary_size IS NOT NULL
            GROUP BY vocabulary_size
            ORDER BY vocabulary_size
        ''')
        
        distribution = [{'vocabulary_size': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify(distribution)
    
    except Exception as e:
        logger.error(f"Vocabulary distribution error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# メイン実行部
# ============================================================================

if __name__ == '__main__':
    # データベースファイルの存在確認
    if not os.path.exists('jacet_cat.db'):
        logger.warning("Database file not found. Please run create_database.py first.")
        print("⚠️  データベースファイルが見つかりません")
        print("先に create_database.py を実行してください")
    
    # パラメータファイルの存在確認
    if not os.path.exists('jacet_parameters.csv'):
        logger.warning("Parameter file not found. Please ensure jacet_parameters.csv exists.")
        print("⚠️  パラメータファイルが見つかりません")
        print("jacet_parameters.csv ファイルを配置してください")
    
    # R関数ファイルの存在確認
    if not os.path.exists('jacet_cat_function.r'):
        logger.warning("R function file not found. Please ensure jacet_cat_function.r exists.")
        print("⚠️  R関数ファイルが見つかりません")
        print("jacet_cat_function.r ファイルを配置してください")
    
    logger.info("Starting JACET CAT application...")
    print("🚀 JACET CAT システムを起動中...")
    print("🌐 http://localhost:5001 でアクセスできます")
    print("👤 管理者画面: http://localhost:5001/admin/login")
    print("🔑 初期パスワード: admin123")
    
    # 開発環境での実行
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)