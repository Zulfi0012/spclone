import os
from flask import Flask, request, jsonify, redirect, make_response
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import mysql.connector
import yt_dlp
import uuid

app = Flask(__name__)
CORS(app, supports_credentials=True)

# --- SECURITY UPDATE ---
# We now load keys from Railway Variables.
# If these variables are missing, the app will fail to start (which is good for security).
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_fallback')

# PROXY SETUP
PROXY_URL = os.environ.get('PROXY_URL', None)

# REDIRECT URI
# We still trick Spotify into thinking we are localhost to match the key settings
SPOTIFY_REDIRECT_URI = 'http://localhost:5000/callback'

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get('MYSQLHOST', 'localhost'),
        user=os.environ.get('MYSQLUSER', 'root'),
        password=os.environ.get('MYSQLPASSWORD', 'shikari'),
        database=os.environ.get('MYSQLDATABASE', 'spotify_clone'),
        port=os.environ.get('MYSQLPORT', 3306)
    )

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            spotify_id VARCHAR(255) UNIQUE NOT NULL,
            display_name VARCHAR(255),
            email VARCHAR(255),
            access_token TEXT,
            refresh_token TEXT,
            session_token VARCHAR(255) UNIQUE
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def get_youtube_stream_url(track_name):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'nocheckcertificate': True,
    }
    
    if PROXY_URL:
        ydl_opts['proxy'] = PROXY_URL

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{track_name}", download=False)['entries'][0]
            return info['url']
        except Exception as e:
            print(f"YT-DLP Error: {e}")
            return None

@app.route('/')
def index():
    return "SpTube Secure Backend is Running."

@app.route('/login')
def spotify_login():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope='user-read-private playlist-read-private streaming'
    )
    return redirect(sp_oauth.get_authorize_url())

@app.route('/callback')
def spotify_callback():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope='user-read-private playlist-read-private streaming'
    )
    
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "No code provided"}), 400

    try:
        token_info = sp_oauth.get_access_token(code)
    except Exception as e:
        return jsonify({"error": "Token exchange failed", "details": str(e)}), 400

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_info = sp.current_user()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    session_token = str(uuid.uuid4())
    
    try:
        cursor.execute('''
            INSERT INTO users 
            (spotify_id, display_name, email, access_token, refresh_token, session_token) 
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            access_token = %s, refresh_token = %s, session_token = %s
        ''', (
            user_info['id'], 
            user_info['display_name'], 
            user_info.get('email', ''), 
            token_info['access_token'], 
            token_info['refresh_token'],
            session_token,
            token_info['access_token'], 
            token_info['refresh_token'],
            session_token
        ))
        conn.commit()
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        cursor.close()
        conn.close()
    
    # Return JSON success with token
    resp = make_response(jsonify({
        "status": "success", 
        "session_token": session_token,
        "user": user_info['display_name']
    }))
    resp.set_cookie('session_token', session_token, httponly=True, secure=True, samesite='None')
    return resp

@app.route('/check_session')
def check_session():
    session_token = request.cookies.get('session_token')
    if not session_token: return jsonify({"authenticated": False})
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM users WHERE session_token = %s', (session_token,))
        user = cursor.fetchone()
        return jsonify({
            "authenticated": bool(user),
            "user": {"display_name": user['display_name']} if user else None
        })
    finally:
        cursor.close()
        conn.close()

@app.route('/recommendations')
def get_recommendations():
    session_token = request.cookies.get('session_token')
    if not session_token: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT access_token FROM users WHERE session_token = %s', (session_token,))
        user = cursor.fetchone()
        if not user: return jsonify({"error": "Invalid session"}), 401
        
        sp = spotipy.Spotify(auth=user['access_token'])
        top_tracks = sp.current_user_top_tracks(limit=5, time_range='medium_term')
        
        if top_tracks['items']:
            seed_track_id = top_tracks['items'][0]['id']
            recommendations = sp.recommendations(seed_tracks=[seed_track_id], limit=12)
            tracks = [{
                'id': t['id'],
                'name': t['name'],
                'artists': [{'name': a['name']} for a in t['artists']],
                'album': {'images': t['album']['images']}
            } for t in recommendations['tracks']]
            return jsonify(tracks)
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/search')
def search_tracks():
    session_token = request.cookies.get('session_token')
    if not session_token: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT access_token FROM users WHERE session_token = %s', (session_token,))
        user = cursor.fetchone()
        if not user: return jsonify({"error": "Invalid session"}), 401
        
        query = request.args.get('q', '')
        sp = spotipy.Spotify(auth=user['access_token'])
        results = sp.search(q=query, type='track', limit=12)
        tracks = [{
            'id': t['id'],
            'name': t['name'],
            'artists': [{'name': a['name']} for a in t['artists']],
            'album': {'images': t['album']['images']}
        } for t in results['tracks']['items']]
        return jsonify(tracks)
    finally:
        cursor.close()
        conn.close()

@app.route('/stream_track')
def stream_track():
    track_name = request.args.get('track')
    url = get_youtube_stream_url(track_name)
    if url: return jsonify({"stream_url": url})
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    try: init_db()
    except: pass
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
