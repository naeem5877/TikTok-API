from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import re
import json
from urllib.parse import quote, unquote
import io
from werkzeug.exceptions import BadRequest

app = Flask(__name__)

# Configure CORS - Allow all origins for development
# For production, replace "*" with your specific domain(s)
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Change to ["https://yourdomain.com"] in production
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
        "supports_credentials": False
    }
})

class TikTokAPI:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        # Multiple API endpoints for fallback
        self.api_endpoints = [
            "https://tikwm.com/api/",
            "https://www.tikwm.com/api/",
            "https://api.tikwm.com/api/"
        ]

    def extract_video_id(self, url):
        """Extract video ID from TikTok URL"""
        patterns = [
            r'(?:https?://)?(?:www\.)?tiktok\.com/@[\w.-]+/video/(\d+)',
            r'(?:https?://)?(?:vm\.tiktok\.com|vt\.tiktok\.com)/(\w+)',
            r'(?:https?://)?(?:www\.)?tiktok\.com/t/(\w+)',
            r'(?:https?://)?(?:m\.)?tiktok\.com/@[\w.-]+/video/(\d+)',
            r'tiktok\.com.*?/video/(\d+)',
            r'/video/(\d+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def normalize_url(self, url):
        """Normalize TikTok URL to standard format"""
        # If it's a short URL, try to expand it first
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url or 'tiktok.com/t/' in url:
            try:
                response = requests.head(url, allow_redirects=True, timeout=10)
                url = response.url
            except:
                pass
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        return url

    def get_video_info(self, url):
        """Get video information from TikTok URL with multiple fallback methods"""
        # Normalize the URL first
        normalized_url = self.normalize_url(url)
        
        # Try each API endpoint
        for api_url in self.api_endpoints:
            try:
                print(f"Trying API: {api_url}")
                params = {
                    'url': normalized_url,
                    'hd': '1'
                }

                response = requests.get(
                    api_url, 
                    params=params, 
                    headers=self.headers, 
                    timeout=15,
                    verify=False  # Some APIs might have SSL issues
                )
                
                print(f"Response status: {response.status_code}")
                print(f"Response content: {response.text[:500]}...")
                
                response.raise_for_status()
                data = response.json()

                if data.get('code') == 0 and data.get('data'):
                    print("Success! Got video data")
                    return data.get('data')
                elif data.get('code') == -1:
                    print(f"API returned error: {data.get('msg', 'Unknown error')}")
                    continue
                else:
                    print(f"Unexpected response code: {data.get('code')}")
                    continue

            except requests.exceptions.RequestException as e:
                print(f"Request error with {api_url}: {str(e)}")
                continue
            except json.JSONDecodeError as e:
                print(f"JSON decode error with {api_url}: {str(e)}")
                continue
            except Exception as e:
                print(f"Unexpected error with {api_url}: {str(e)}")
                continue

        # If all APIs fail, try alternative method
        return self.get_video_info_alternative(normalized_url)

    def get_video_info_alternative(self, url):
        """Alternative method to get video info"""
        try:
            # Try different API service
            alt_api = "https://tikmate.online/api/v1/video/details"
            response = requests.post(
                alt_api,
                json={"url": url},
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return self.format_alternative_data(data.get('data', {}))
                    
        except Exception as e:
            print(f"Alternative API failed: {str(e)}")
            
        return None

    def format_alternative_data(self, data):
        """Format data from alternative API to match expected structure"""
        return {
            'id': data.get('id'),
            'title': data.get('title', ''),
            'duration': data.get('duration'),
            'author': {
                'unique_id': data.get('author', {}).get('username'),
                'nickname': data.get('author', {}).get('nickname'),
                'avatar': data.get('author', {}).get('avatar')
            },
            'play_count': data.get('stats', {}).get('views'),
            'digg_count': data.get('stats', {}).get('likes'),
            'comment_count': data.get('stats', {}).get('comments'),
            'share_count': data.get('stats', {}).get('shares'),
            'create_time': data.get('created_at'),
            'play': data.get('video_url'),
            'music': data.get('audio_url'),
            'cover': data.get('thumbnail'),
            'origin_cover': data.get('thumbnail'),
            'dynamic_cover': data.get('thumbnail')
        }

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
        "cors_enabled": True,
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

        print(f"Received URL: {url}")
        
        # Validate URL format
        if 'tiktok.com' not in url and 'vm.tiktok.com' not in url and 'vt.tiktok.com' not in url:
            return jsonify({
                "error": "Invalid TikTok URL",
                "message": "Please provide a valid TikTok URL"
            }), 400

        # Get video info with detailed logging
        video_info = tiktok_api.get_video_info(url)
        if not video_info:
            return jsonify({
                "error": "Failed to fetch video information",
                "message": "The video might be private, deleted, or the URL is invalid. Please check the URL and try again.",
                "troubleshooting": {
                    "tips": [
                        "Make sure the TikTok video is public",
                        "Try copying the URL directly from TikTok app/website",
                        "Check if the video still exists",
                        "Try with a different TikTok video URL to test the API"
                    ],
                    "supported_formats": [
                        "https://www.tiktok.com/@username/video/1234567890123456789",
                        "https://vm.tiktok.com/ZMxxxxxx/",
                        "https://vt.tiktok.com/ZSxxxxxx/"
                    ]
                }
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
        print(f"Error in get_info: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "message": str(e),
            "debug_info": "Check server logs for more details"
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
                'Content-Type': 'video/mp4',
                'Access-Control-Allow-Origin': '*'
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
                'Content-Type': 'image/jpeg',
                'Access-Control-Allow-Origin': '*'
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
                'Content-Type': 'audio/mpeg',
                'Access-Control-Allow-Origin': '*'
            }
        )

    except Exception as e:
        return jsonify({
            "error": "Download failed",
            "message": str(e)
        }), 500

@app.route('/test', methods=['GET'])
def test_api():
    """Test endpoint to debug API issues"""
    try:
        url = request.args.get('url', 'https://www.tiktok.com/@selenagomez/video/7001245956863126789')
        
        # Test URL validation
        video_id = tiktok_api.extract_video_id(url)
        normalized_url = tiktok_api.normalize_url(url)
        
        # Test each API endpoint
        results = []
        for api_url in tiktok_api.api_endpoints:
            try:
                params = {'url': normalized_url, 'hd': '1'}
                response = requests.get(api_url, params=params, headers=tiktok_api.headers, timeout=10)
                results.append({
                    "api": api_url,
                    "status": response.status_code,
                    "response_preview": response.text[:200] + "..." if len(response.text) > 200 else response.text
                })
            except Exception as e:
                results.append({
                    "api": api_url,
                    "error": str(e)
                })
        
        return jsonify({
            "test_url": url,
            "video_id": video_id,
            "normalized_url": normalized_url,
            "api_tests": results,
            "headers_used": tiktok_api.headers
        })
        
    except Exception as e:
        return jsonify({
            "error": "Test failed",
            "message": str(e)
        }), 500

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
    print("🚀 Starting TikTok Downloader API with CORS enabled...")
    print("🌐 CORS: Enabled for all origins")
    print("📚 API Documentation: http://localhost:5000/")
    print("🔍 Get Info: http://localhost:5000/info?url=TIKTOK_URL")
    print("📹 Download Video: http://localhost:5000/download/video?url=TIKTOK_URL")
    print("🎵 Download Audio: http://localhost:5000/download/audio?url=TIKTOK_URL")
    print("🖼️  Download Thumbnail: http://localhost:5000/download/thumbnail?url=TIKTOK_URL")
    print("🖼️  Get Thumbnails: http://localhost:5000/thumbnails?url=TIKTOK_URL")
    print("💚 Health Check: http://localhost:5000/health")

    app.run(debug=True, host='0.0.0.0', port=5000)
