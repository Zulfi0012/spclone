import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# We use the keys for "Guest Access" (No Login Required)
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')

# Proxy for YouTube (Optional)
PROXY_URL = os.environ.get('PROXY_URL', None)

def get_spotify_client():
    # This auth method DOES NOT need a Redirect URI, so it won't fail!
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    return spotipy.Spotify(auth_manager=auth_manager)

# --- ADD THIS NEAR THE TOP OF app.py ---
url_cache = {} # Memory to store links so we don't search twice

# --- REPLACE THE OLD get_youtube_stream_url FUNCTION WITH THIS ---
def get_youtube_stream_url(track_name):
    cookie_path = 'cookies/youtube.txt'

    if not os.path.exists(cookie_path):
        return None

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'cookiefile': cookie_path,
        'nocheckcertificate': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        results = ydl.extract_info(f"ytsearch:{track_name}", download=False)
        if not results or 'entries' not in results or not results['entries']:
            return None
        return results['entries'][0]['url']

            
            # 2. SAVE TO CACHE
            url_cache[track_name] = url 
            return url
        except Exception as e:
            print(f"Error: {e}")
            return None

@app.route('/')
def index():
    return "SpTube Guest Backend is Running."

# --- SIMPLIFIED ENDPOINTS (NO LOGIN CHECK) ---

@app.route('/recommendations')
def get_recommendations():
    try:
        sp = get_spotify_client()
        # Since we have no user history, we fetch "New Releases" or a specific playlist
        # Let's fetch "Global Top 50" style tracks via search to simulate a home page
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

@app.route('/stream_track')
def stream_track():
    if not os.path.exists('cookies/youtube.txt'):
        return jsonify({
            "error": "YouTube cookies not uploaded"
        }), 400

    track_name = request.args.get('track')
    if not track_name:
        return jsonify({"error": "Track name missing"}), 400

    stream_url = get_youtube_stream_url(track_name)

    if stream_url:
        return jsonify({"stream_url": stream_url})
    else:
        return jsonify({"error": "Could not get stream URL"}), 404

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
