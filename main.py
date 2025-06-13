from flask import Flask, request, jsonify, Response, stream_with_context
import requests
import re
import json
from urllib.parse import quote, unquote
import io
from werkzeug.exceptions import BadRequest

app = Flask(__name__)

class TikTokAPI:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.api_url = "https://tikwm.com/api/"

    def extract_video_id(self, url):
        """Extract video ID from TikTok URL"""
        patterns = [
            r'(?:https?://)?(?:www\.)?tiktok\.com/@[\w.-]+/video/(\d+)',
            r'(?:https?://)?(?:vm\.tiktok\.com|vt\.tiktok\.com)/(\w+)',
            r'(?:https?://)?(?:www\.)?tiktok\.com/t/(\w+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_video_info(self, url):
        """Get video information from TikTok URL"""
        try:
            params = {
                'url': url,
                'hd': '1'
            }

            response = requests.get(self.api_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == 0:
                return data.get('data')
            else:
                return None

        except Exception as e:
            return None

    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:100]

# Initialize TikTok API
tiktok_api = TikTokAPI()

@app.route('/')
def home():
    """API documentation"""
    docs = {
        "name": "TikTok Downloader API",
        "version": "1.0",
        "description": "Download TikTok videos and audio without saving on server",
        "endpoints": {
            "/info": {
                "method": "GET",
                "description": "Get video information",
                "parameters": {
                    "url": "TikTok video URL (required)"
                },
                "example": "/info?url=https://www.tiktok.com/@username/video/1234567890"
            },
            "/download/video": {
                "method": "GET",
                "description": "Download video file",
                "parameters": {
                    "url": "TikTok video URL (required)"
                },
                "example": "/download/video?url=https://www.tiktok.com/@username/video/1234567890"
            },
            "/download/audio": {
                "method": "GET",
                "description": "Download audio file",
                "parameters": {
                    "url": "TikTok video URL (required)"
                },
                "example": "/download/audio?url=https://www.tiktok.com/@username/video/1234567890"
            },
            "/download/thumbnail": {
                "method": "GET",
                "description": "Download video thumbnail image",
                "parameters": {
                    "url": "TikTok video URL (required)",
                    "quality": "Thumbnail quality: 'high', 'medium', 'low' (optional, default: 'high')"
                },
                "example": "/download/thumbnail?url=https://www.tiktok.com/@username/video/1234567890&quality=high"
            },
            "/thumbnails": {
                "method": "GET",
                "description": "Get all available thumbnail URLs",
                "parameters": {
                    "url": "TikTok video URL (required)"
                },
                "example": "/thumbnails?url=https://www.tiktok.com/@username/video/1234567890"
            }
        },
        "supported_formats": [
            "https://www.tiktok.com/@username/video/1234567890",
            "https://vm.tiktok.com/ZMxxxxxx/",
            "https://vt.tiktok.com/ZSxxxxxx/"
        ]
    }
    return jsonify(docs)

@app.route('/info', methods=['GET'])
def get_info():
    """Get TikTok video information"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({
                "error": "Missing 'url' parameter",
                "message": "Please provide a TikTok URL"
            }), 400

        # Get video info
        video_info = tiktok_api.get_video_info(url)
        if not video_info:
            return jsonify({
                "error": "Failed to fetch video information",
                "message": "Invalid URL or video not accessible"
            }), 404

        # Extract relevant information
        info = {
            "success": True,
            "data": {
                "id": video_info.get('id'),
                "title": video_info.get('title'),
                "duration": video_info.get('duration'),
                "author": {
                    "username": video_info.get('author', {}).get('unique_id'),
                    "nickname": video_info.get('author', {}).get('nickname'),
                    "avatar": video_info.get('author', {}).get('avatar')
                },
                "stats": {
                    "views": video_info.get('play_count'),
                    "likes": video_info.get('digg_count'),
                    "comments": video_info.get('comment_count'),
                    "shares": video_info.get('share_count')
                },
                "created_at": video_info.get('create_time'),
                "has_video": bool(video_info.get('play')),
                "has_audio": bool(video_info.get('music')),
                "thumbnails": {
                    "cover": video_info.get('cover'),
                    "origin_cover": video_info.get('origin_cover'),
                    "dynamic_cover": video_info.get('dynamic_cover')
                },
                "download_urls": {
                    "video": f"/download/video?url={quote(url)}",
                    "audio": f"/download/audio?url={quote(url)}",
                    "thumbnail": f"/download/thumbnail?url={quote(url)}",
                    "thumbnails_info": f"/thumbnails?url={quote(url)}"
                }
            }
        }

        return jsonify(info)

    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/download/video', methods=['GET'])
def download_video():
    """Download TikTok video"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({
                "error": "Missing 'url' parameter",
                "message": "Please provide a TikTok URL"
            }), 400

        # Get video info
        video_info = tiktok_api.get_video_info(url)
        if not video_info:
            return jsonify({
                "error": "Failed to fetch video information",
                "message": "Invalid URL or video not accessible"
            }), 404

        video_url = video_info.get('play')
        if not video_url:
            return jsonify({
                "error": "Video URL not found",
                "message": "This video may not be available for download"
            }), 404

        # Generate filename
        title = video_info.get('title', 'TikTok Video')
        author = video_info.get('author', {}).get('unique_id', 'unknown')
        video_id = video_info.get('id', 'unknown')

        safe_title = tiktok_api.sanitize_filename(title)
        filename = f"{author}_{safe_title}_{video_id}.mp4"

        # Stream the video file
        def generate():
            try:
                response = requests.get(video_url, headers=tiktok_api.headers, stream=True)
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                yield b''

        return Response(
            stream_with_context(generate()),
            mimetype='video/mp4',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'video/mp4'
            }
        )

    except Exception as e:
        return jsonify({
            "error": "Download failed",
            "message": str(e)
        }), 500

@app.route('/thumbnails', methods=['GET'])
def get_thumbnails():
    """Get all available thumbnail URLs"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({
                "error": "Missing 'url' parameter",
                "message": "Please provide a TikTok URL"
            }), 400

        # Get video info
        video_info = tiktok_api.get_video_info(url)
        if not video_info:
            return jsonify({
                "error": "Failed to fetch video information",
                "message": "Invalid URL or video not accessible"
            }), 404

        thumbnails = {
            "success": True,
            "data": {
                "cover": video_info.get('cover'),
                "origin_cover": video_info.get('origin_cover'), 
                "dynamic_cover": video_info.get('dynamic_cover'),
                "download_urls": {
                    "cover": f"/download/thumbnail?url={quote(url)}&quality=high",
                    "origin_cover": f"/download/thumbnail?url={quote(url)}&quality=medium", 
                    "dynamic_cover": f"/download/thumbnail?url={quote(url)}&quality=low"
                }
            }
        }

        return jsonify(thumbnails)

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch thumbnails",
            "message": str(e)
        }), 500

@app.route('/download/thumbnail', methods=['GET'])
def download_thumbnail():
    """Download TikTok video thumbnail"""
    try:
        url = request.args.get('url')
        quality = request.args.get('quality', 'high').lower()

        if not url:
            return jsonify({
                "error": "Missing 'url' parameter",
                "message": "Please provide a TikTok URL"
            }), 400

        # Get video info
        video_info = tiktok_api.get_video_info(url)
        if not video_info:
            return jsonify({
                "error": "Failed to fetch video information",
                "message": "Invalid URL or video not accessible"
            }), 404

        # Select thumbnail based on quality
        thumbnail_url = None
        if quality == 'high':
            thumbnail_url = video_info.get('cover')
        elif quality == 'medium':
            thumbnail_url = video_info.get('origin_cover')
        elif quality == 'low':
            thumbnail_url = video_info.get('dynamic_cover')
        else:
            thumbnail_url = video_info.get('cover')  # Default to high quality

        if not thumbnail_url:
            return jsonify({
                "error": "Thumbnail URL not found",
                "message": "This video may not have available thumbnails"
            }), 404

        # Generate filename
        title = video_info.get('title', 'TikTok Thumbnail')
        author = video_info.get('author', {}).get('unique_id', 'unknown')
        video_id = video_info.get('id', 'unknown')

        safe_title = tiktok_api.sanitize_filename(title)
        filename = f"{author}_{safe_title}_{video_id}_{quality}.jpg"

        # Stream the thumbnail file
        def generate():
            try:
                response = requests.get(thumbnail_url, headers=tiktok_api.headers, stream=True)
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                yield b''

        return Response(
            stream_with_context(generate()),
            mimetype='image/jpeg',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'image/jpeg'
            }
        )

    except Exception as e:
        return jsonify({
            "error": "Thumbnail download failed",
            "message": str(e)
        }), 500

@app.route('/download/audio', methods=['GET'])
def download_audio():
    """Download TikTok audio"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({
                "error": "Missing 'url' parameter",
                "message": "Please provide a TikTok URL"
            }), 400

        # Get video info
        video_info = tiktok_api.get_video_info(url)
        if not video_info:
            return jsonify({
                "error": "Failed to fetch video information",
                "message": "Invalid URL or video not accessible"
            }), 404

        audio_url = video_info.get('music')
        if not audio_url:
            return jsonify({
                "error": "Audio URL not found",
                "message": "This video may not have extractable audio"
            }), 404

        # Generate filename
        title = video_info.get('title', 'TikTok Audio')
        author = video_info.get('author', {}).get('unique_id', 'unknown')
        video_id = video_info.get('id', 'unknown')

        safe_title = tiktok_api.sanitize_filename(title)
        filename = f"{author}_{safe_title}_{video_id}.mp3"

        # Stream the audio file
        def generate():
            try:
                response = requests.get(audio_url, headers=tiktok_api.headers, stream=True)
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                yield b''

        return Response(
            stream_with_context(generate()),
            mimetype='audio/mpeg',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'audio/mpeg'
            }
        )

    except Exception as e:
        return jsonify({
            "error": "Download failed",
            "message": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "message": "TikTok Downloader API is running"
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "message": "Please check the API documentation at '/'"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal server error",
        "message": "Something went wrong on our end"
    }), 500

if __name__ == '__main__':
    print("🚀 Starting TikTok Downloader API...")
    print("📚 API Documentation: http://localhost:5000/")
    print("🔍 Get Info: http://localhost:5000/info?url=TIKTOK_URL")
    print("📹 Download Video: http://localhost:5000/download/video?url=TIKTOK_URL")
    print("🎵 Download Audio: http://localhost:5000/download/audio?url=TIKTOK_URL")
    print("🖼️  Download Thumbnail: http://localhost:5000/download/thumbnail?url=TIKTOK_URL")
    print("🖼️  Get Thumbnails: http://localhost:5000/thumbnails?url=TIKTOK_URL")
    print("💚 Health Check: http://localhost:5000/health")

    app.run(debug=True, host='0.0.0.0', port=5000)
