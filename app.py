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
    # 1. CHECK CACHE FIRST (Instant Speed)
    if track_name in url_cache:
        print(f"Cache Hit: {track_name}")
        return url_cache[track_name]

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
            url = info['url']
            
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
    track_name = request.args.get('track')
    url = get_youtube_stream_url(track_name)
    if url: return jsonify({"stream_url": url})
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
