from flask import Flask, send_file, render_template, make_response
from flask_restful import Api, Resource, reqparse, fields, marshal_with, abort
from flask_sqlalchemy import SQLAlchemy
import os
import yt_dlp
from flasgger import Swagger

# CONFIGURATION
app = Flask(__name__, template_folder="./templates")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///downloads.db"
db = SQLAlchemy(app)
api = Api(app)

# Swagger configuration
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "YT Clipper API",
        "description": "API to download full or clipped video in Youtube",
        "version": "1.0.0"
    },
    "basePath": "/",
    "consumes": ["application/json"],
    "produces": ["application/json"]
}
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,  # include all endpoints
            "model_filter": lambda tag: True,  # include all models
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/"  # This sets the URL to /docs
}

swagger = Swagger(app, template=swagger_template, config=swagger_config)

# Define download folder
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# DATABASE MODEL
class Download(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    start = db.Column(db.Integer, nullable=True)
    end = db.Column(db.Integer, nullable=True)
    file_path = db.Column(db.String(500), nullable=False)

# Create the database
with app.app_context():
    db.create_all()

# ARGUMENT TO GET
video_args = reqparse.RequestParser()
video_args.add_argument("url", type=str, required=True, help="YouTube URL is required.")
video_args.add_argument("start", type=int)
video_args.add_argument("end", type=int)

# FIELDS
video_fields = {
    "id": fields.Integer,
    "name": fields.String,
    "url": fields.String,
    "start": fields.Integer,
    "end": fields.Integer,
    "file_path": fields.String
}

# ENDPOINTS

# Video Download
class VideoDownload(Resource):
    """
    Video Download Endpoint
    ---
    get:
      description: Retrieve a list of all downloaded videos.
      responses:
        200:
          description: A list of video objects.
    post:
      description: Download a video from a YouTube URL.
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
            required:
              - url
            properties:
              url:
                type: string
                description: The YouTube URL to download.
              start:
                type: integer
                description: Start time in seconds for clipping.
              end:
                type: integer
                description: End time in seconds for clipping.
      responses:
        200:
          description: Returns the downloaded video file.
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
        500:
          description: Error during video download.
    """
    @marshal_with(video_fields)
    def get(self):
        """
        Retrieve a list of all downloaded videos.
        ---
        responses:
          200:
            description: A list of video objects.
        """
        videos = Download.query.all()
        return videos

    def post(self):
        """
        Download a video from a YouTube URL.
        ---
        parameters:
          - in: body
            name: body
            required: true
            schema:
              type: object
              required:
                - url
              properties:
                url:
                  type: string
                  description: The YouTube URL to download.
                start:
                  type: integer
                  description: Start time in seconds for clipping.
                end:
                  type: integer
                  description: End time in seconds for clipping.
        responses:
          200:
            description: Returns the downloaded video file.
          500:
            description: Error during video download.
        """
        args = video_args.parse_args()
        video_url = args["url"]

        # Get video title
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_title = info.get("title", "downloaded_video").replace(" ", "_")
            video_extension = info.get("ext", "mp4")

        # Generate filename
        filename = f"{video_title}.{video_extension}"
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)

        start_time = args["start"]
        end_time = args["end"]

        if (start_time is not None) and (end_time is not None):
          
          # Define the download range function
          def download_range(info_dict, ydl):
              return [{'start_time': start_time, 'end_time': end_time}]
          
          print(f"Downloading clip from {start_time} sec to {end_time} sec...")
          # Download settings for clip
          # ydl_opts = {
          #   'format': 'bestvideo+bestaudio/best',
          #   'outtmpl': file_path,
          #   'postprocessor_args': [
          #       # Use "accurate seek" for precise cuts
          #       '-ss', str(start_time),
          #       '-to', str(end_time),
          #       # Force cuts at keyframes
          #       '-force_key_frames', f'expr:gte(n,n_forced*1)'
          #   ],
          #   # Ensure postprocessors handle keyframes
          #   'force_keyframe_at_cuts': True,
          #   # Avoid fragmented downloads
          #   'noprogress': True,
          #   'cachedir': False
          # }
          ydl_opts = {
          'format': 'bestvideo+bestaudio/best',
          'outtmpl': file_path,
          # Use the download range helper function to specify the section of video to download.
          'download_ranges': download_range,
          }
        else:
            print("Downloading full video...")
            # Download settings full video
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': file_path
            }

        # Download the video
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            # Save to database
            new_download = Download(name=video_title, url=video_url, start=start_time, end=end_time, file_path=file_path)
            db.session.add(new_download)
            db.session.commit()

            return send_file(file_path, as_attachment=True, download_name=filename)


        except Exception as e:
            print(e)
            return {"error": str(e)}, 500
        

# Video Info
class VideoInfo(Resource):
    """
    Video Info Endpoint
    ---
    get:
      description: Retrieve details of a specific video by its ID.
      parameters:
        - in: path
          name: video_id
          type: integer
          required: true
          description: The ID of the video.
      responses:
        200:
          description: A video object.
        404:
          description: Video not found.
    delete:
      description: Delete a video by its ID.
      parameters:
        - in: path
          name: video_id
          type: integer
          required: true
          description: The ID of the video to delete.
      responses:
        200:
          description: Deletion confirmation.
        404:
          description: Video not found.
    """
    @marshal_with(video_fields)
    def get(self, video_id):
        video = Download.query.get(video_id)
        if not video:
            abort(404, message="Video not found.")
        return video

    def delete(self, video_id):
        video = Download.query.get(video_id)
        if not video:
            abort(404, message="Video not found.")

        # Delete file from disk
        if os.path.exists(video.file_path):
            os.remove(video.file_path)

        # Remove from DB
        db.session.delete(video)
        db.session.commit()

        return {"message": "Video deleted successfully"}, 200

# ASSIGN ENDPOINTS
api.add_resource(VideoDownload, "/api/download")
api.add_resource(VideoInfo, "/api/video/<int:video_id>")

# ROUTES
@app.route("/")
def home():
    return render_template("main.html")

if __name__ == "__main__":
    app.run(debug=True)
