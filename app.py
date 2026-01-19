import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')

def get_spotify_client():
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    return spotipy.Spotify(auth_manager=auth_manager)

# --- GLOBAL CACHE (Optional) ---
url_cache = {}

# --- FIXED YouTube Stream URL Fetcher ---
def get_youtube_stream_url(track_name):
    cookie_path = 'cookies/youtube.txt'

    if not os.path.exists(cookie_path):
        return None

    # Cache check
    if track_name in url_cache:
        return url_cache[track_name]

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'cookiefile': cookie_path,
        'nocheckcertificate': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch:{track_name}", download=False)

            if not results or 'entries' not in results or not results['entries']:
                return None

            url = results['entries'][0]['url']

            # save to cache
            url_cache[track_name] = url
            return url

    except Exception as e:
        print(f"yt-dlp error: {e}")
        return None


@app.route('/')
def index():
    return "Backend is running"

# --- RECOMMENDATIONS ---
@app.route('/recommendations')
def get_recommendations():
    try:
        sp = get_spotify_client()
        results = sp.search(q='genre:pop', type='track', limit=12)

        tracks = [{
            'id': t['id'],
            'name': t['name'],
            'artists': [{'name': a['name']} for a in t['artists']],
            'album': {'images': t['album']['images']}
        } for t in results['tracks']['items']]

        return jsonify(tracks)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- SEARCH ---
@app.route('/search')
def search_tracks():
    query = request.args.get('q', '')

    try:
        sp = get_spotify_client()
        results = sp.search(q=query, type='track', limit=12)

        tracks = [{
            'id': t['id'],
            'name': t['name'],
            'artists': [{'name': a['name']} for a in t['artists']],
            'album': {'images': t['album']['images']}
        } for t in results['tracks']['items']]

        return jsonify(tracks)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- STREAM TRACK ---
@app.route('/stream_track')
def stream_track():
    if not os.path.exists('cookies/youtube.txt'):
        return jsonify({"error": "YouTube cookies not uploaded"}), 400

    track_name = request.args.get('track')

    if not track_name:
        return jsonify({"error": "Track name missing"}), 400

    stream_url = get_youtube_stream_url(track_name)

    if stream_url:
        return jsonify({"stream_url": stream_url})
    else:
        return jsonify({"error": "Could not get stream URL"}), 404

# --- UPLOAD COOKIE ---
@app.route('/upload_youtube_cookie', methods=['POST'])
def upload_youtube_cookie():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']

    if not file.filename.endswith('.txt'):
        return jsonify({"error": "Only .txt cookie files allowed"}), 400

    os.makedirs('cookies', exist_ok=True)

    save_path = os.path.join('cookies', 'youtube.txt')
    file.save(save_path)

    return jsonify({
        "status": "success",
        "message": "YouTube cookies uploaded successfully"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
