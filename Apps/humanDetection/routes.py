from asyncio.log import logger
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from flask import Blueprint
from app import csrf
from .models import Camera, Detection
from app import  db
import os
import time


active_cameras = {}
detection = Blueprint('detection', __name__)


@detection.route("/dashboard")
@login_required
def dashboard():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10  
        pagination = Camera.query.paginate(page=page, per_page=per_page, error_out=False)
        cameras = pagination.items  
        return render_template("detection/dashboard_webrtc.html", cameras=cameras)
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return render_template("detection/dashboard_webrtc.html", cameras=[])

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@detection.route("/add_camera", methods=["GET", "POST"])
@login_required
def add_camera():
    if request.method == "POST":
        name = request.form.get("name")
        rtsp_url = request.form.get("rtsp_url", "").strip()
        video = request.files.get("video_file")

        if not name:
            return jsonify({"error": "Camera name is required"}), 400

        file_path = None
        if video and video.filename != "":
            filename = f"{int(time.time())}_{name.replace(' ', '_')}.mp4"
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            video.save(file_path)
            rtsp_url = None  
        if not rtsp_url and not file_path:
            return jsonify({"error": "RTSP URL or Video file required"}), 400

        camera = Camera(
            name=name,
            rtsp_url=rtsp_url,
            video_file=file_path,
        )

        try:
            db.session.add(camera)
            db.session.commit()
            return jsonify({"message": "Camera added successfully"}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    return render_template("detection/add_camera.html")



@detection.route("/update_camera/<int:camera_id>", methods=["GET", "POST"])
@login_required
def update_camera(camera_id):
    camera = Camera.query.get_or_404(camera_id)
    
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        name = data.get("name")
        rtsp_url = data.get("rtsp_url")
        if not name or not rtsp_url:
            return jsonify({"error": "Name and RTSP URL are required"}), 400

        try:
            camera.name = name
            camera.rtsp_url = rtsp_url
            db.session.commit()
            return jsonify({"message": "Camera updated successfully"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Failed to update camera: {str(e)}"}), 500

    return render_template("detection/update_camera.html", camera=camera)



@detection.route("/delete_camera/<int:camera_id>", methods=["DELETE"])
@csrf.exempt
@login_required
def delete_camera(camera_id):
    try:
        camera = Camera.query.get_or_404(camera_id)
        if camera_id in active_cameras:
            active_cameras[camera_id]["active"] = False
        Detection.query.filter_by(camera_id=camera_id).delete()

        db.session.delete(camera)
        db.session.commit()

        return jsonify({"message": "Camera deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting camera {camera_id}: {str(e)}")
        return jsonify({"error": f"Failed to delete camera: {str(e)}"}), 500

@detection.route("/camera/<int:camera_id>", methods=["GET"])
@login_required
def get_camera(camera_id):
    camera = Camera.query.get_or_404(camera_id)
    return jsonify({
        "id": camera.id,
        "name": camera.name,
        "rtsp_url": camera.rtsp_url,
        "is_active": camera.is_active
    })



