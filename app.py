import os
import logging
import yt_dlp
import json
import uuid
import re
import subprocess
from flask import Flask, request, jsonify, render_template, session, send_from_directory
from werkzeug.exceptions import BadRequest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FLASK_SECRET_KEY = '146e321c7dead66979bd65744c37aa911a24aa168898720164b07441cb88b4f9'

# Config from environment
FLASK_SECRET_KEY = os.getenv(FLASK_SECRET_KEY, 'default_secret_key')

# Flask setup
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# File storage
OUTPUT_FOLDER = os.path.join(os.path.expanduser("~"), "Desktop", "mySongs")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# User data file (optional, can remove if not used anymore)
USER_DATA_FILE = 'users.json'

# Load/save user data (optional, if you want to keep track)
def load_users():
    if not os.path.exists(USER_DATA_FILE):
        return {}
    with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(data):
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

users = load_users()

# Helpers
def sanitize_title(title):
    return re.sub(r'[\\/:"*?<>|]+', '_', title)

def generate_m3u(playlist_name, file_paths):
    m3u_path = os.path.join(OUTPUT_FOLDER, f"{playlist_name}.m3u")
    with open(m3u_path, 'w', encoding='utf-8') as m3u_file:
        m3u_file.write("#EXTM3U\n")
        for path in file_paths:
            m3u_file.write(f"{path}\n")
    logger.info(f"M3U playlist created: {m3u_path}")
    return m3u_path

def download_mp3(url, quality='192'):
    if not url.startswith(('https://www.youtube.com', 'https://youtu.be')):
        raise ValueError("請輸入有效的 YouTube 連結喔！")
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get("title", "下載音訊")
    safe_title = sanitize_title(title)
    mp3_path = os.path.join(OUTPUT_FOLDER, f"{safe_title}.mp3")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(OUTPUT_FOLDER, safe_title) + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
        'noplaylist': True,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not os.path.isfile(mp3_path):
        raise FileNotFoundError(f"MP3 file not found: {mp3_path}")

    return mp3_path, safe_title

def convert_mp3_to_m4a(mp3_file):
    m4a_file = mp3_file.replace('.mp3', '.m4a')
    subprocess.run([
        'ffmpeg', '-y', '-i', mp3_file, '-c:a', 'aac', m4a_file
    ], check=True)
    return m4a_file

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/service', methods=['POST'])
def run_service():
    try:
        if not request.is_json:
            raise BadRequest("請使用 JSON 格式的請求")

        data = request.get_json()
        url = data.get('input')
        selected_format = data.get('format', 'mp3')
        quality = data.get('quality', '192')

        download_links = {}
        m3u_files = []

        if selected_format == "mp3":
            mp3_path, safe_title = download_mp3(url, quality=quality)
            download_links["mp3"] = f"/download/{os.path.basename(mp3_path)}"
            m3u_files.append(os.path.basename(mp3_path))

        elif selected_format == "m4a":
            mp3_path, safe_title = download_mp3(url, quality=quality)
            m4a_path = convert_mp3_to_m4a(mp3_path)
            download_links["m4a"] = f"/download/{os.path.basename(m4a_path)}"
            m3u_files.append(os.path.basename(m4a_path))

        else:
            raise BadRequest("不支援的格式類型，請選擇 mp3 或 m4a。")

        m3u_path = generate_m3u(safe_title, m3u_files)
        download_links["m3u"] = f"/download/{os.path.basename(m3u_path)}"

        return jsonify({
            'status': 'success',
            'message': f'{safe_title} 已成功處理！',
            'download_links': download_links
        })

    except BadRequest as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Service error: {str(e)}")
        return jsonify({'status': 'error', 'message': '伺服器發生錯誤，請稍後再試。'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'status': 'error', 'message': '找不到檔案喔！'}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
