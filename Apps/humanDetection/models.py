from app import db
from datetime import datetime

class Camera(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rtsp_url = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    video_file = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class Detection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    confidence = db.Column(db.Float)
    entry_people = db.Column(db.Integer, nullable=False)
    exit_people = db.Column(db.Integer, nullable=False)