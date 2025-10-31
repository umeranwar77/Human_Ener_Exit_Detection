import asyncio
import cv2
import numpy as np
import threading
from collections import defaultdict
from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription
from av import VideoFrame
from .utils import HumanDetector
from .models import Detection, db, Camera
from .centroid_tracker import CentroidTracker
from app import socketio
from multiprocessing import Process
import time



camera_clients = defaultdict(dict)  
video_tracks = {}
detector = HumanDetector()
trackers = {}
entry_exit_count = {}
line_position = 300
previous_x = defaultdict(dict)


class SharedFrameManager:
    def __init__(self):
        self.frames = {}  
        self.locks = {}   
        self.processing_threads = {}  
        self.running = {}  
        
    def start_camera(self, camera_id, rtsp_url, video_file=None):
        camera_id = str(camera_id)
        
        if camera_id in self.processing_threads and self.running.get(camera_id):
            return
            
        self.locks[camera_id] = threading.Lock()
        self.frames[camera_id] = offline_frame(camera_id)
        self.running[camera_id] = True
        if camera_id not in trackers:
            trackers[camera_id] = CentroidTracker(max_disappeared=15)
            entry_exit_count[camera_id] = {"entry": 0, "exit": 0}
            previous_x[camera_id] = {}
        
        thread = threading.Thread(
            target=self._process_camera,
            args=(camera_id, rtsp_url, video_file),
            daemon=True
        )
        self.processing_threads[camera_id] = thread
        thread.start()


    def start_camera_process(camera_id, rtsp_url, video_file=None):
        camera_id = str(camera_id)
        if frame_manager.is_running(camera_id):
            print(f"Camera {camera_id} already running")
            return
        frame_manager.start_camera(camera_id, rtsp_url, video_file)
        p = Process(target=frame_manager._process_camera, args=(camera_id, rtsp_url, video_file))
        p.daemon = True
        p.start()
    
    def _process_camera(self, camera_id, rtsp_url, video_file):
        if video_file:
            source = video_file
        elif rtsp_url == "0":
            source = 0
        else:
            source = rtsp_url
        cap = None
        for _ in range(5):  
            cap = cv2.VideoCapture(source)
            if video_file:
                cap.set(cv2.CAP_PROP_FPS, 30)
            if cap.isOpened():
                break
            cv2.waitKey(1000)
        
        if not cap or not cap.isOpened():
            print(f"Failed to open camera {camera_id}")
            self.running[camera_id] = False
            return
        
        prev_time = time.time()
        
        while self.running.get(camera_id, False):
            ret, frame = cap.read()
            
            if ret:
                frame = cv2.resize(frame, (640, 480))
                processed = process_frame(frame, camera_id, detection_enabled=True)
                with self.locks[camera_id]:
                    self.frames[camera_id] = processed.copy()
                if video_file:
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30
                    frame_delay = max(1.0 / min(fps, 30), 0.03)
                    now = time.time()
                    diff = now - prev_time
                    if diff < frame_delay:
                        time.sleep(frame_delay - diff)
                    prev_time = time.time()
            else:
                with self.locks[camera_id]:
                    self.frames[camera_id] = offline_frame(camera_id)
                
                if video_file:
                  
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                else:
                    time.sleep(0.1)
    
        cap.release()
        print(f"Camera {camera_id} processing thread stopped")
    
    def get_frame(self, camera_id):
        camera_id = str(camera_id)
        if camera_id not in self.locks:
            return offline_frame(camera_id)
        
        if camera_id not in self.frames:
            return offline_frame(camera_id)
        
        with self.locks[camera_id]:
            frame = self.frames.get(camera_id, offline_frame(camera_id)).copy()
            return frame
    
    def stop_camera(self, camera_id):
        camera_id = str(camera_id)
        self.running[camera_id] = False
        if camera_id in self.processing_threads:
            del self.processing_threads[camera_id]
        print(f"Stopped camera {camera_id}")
    
    def is_running(self, camera_id):

        return self.running.get(str(camera_id), False)
frame_manager = SharedFrameManager()

class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, camera_id):
        super().__init__()
        self.camera_id = str(camera_id)
        self._running = True
        self._frame_count = 0
    
    async def recv(self):
        if not self._running:
            raise Exception("Track stopped")
            
        pts, time_base = await self.next_timestamp()
        frame = frame_manager.get_frame(self.camera_id)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._frame_count += 1
        if self._frame_count <= 3 or self._frame_count % 100 == 0:
            print(f"Camera {self.camera_id} - Sending frame #{self._frame_count}, shape: {frame.shape}")
        
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame
    
    def stop(self):
        self._running = False
        super().stop()


def save_detection(camera_id, is_entry):
    try:
        new_detect = Detection(
            camera_id=int(camera_id),
            confidence=None,
            entry_people=1 if is_entry else 0,
            exit_people=0 if is_entry else 1
        )
        db.session.add(new_detect)
        db.session.commit()
    except Exception as e:
        print("DB Error:", e)


def process_frame(frame, camera_id, detection_enabled=True):
    if frame is None:
        return frame
    
    camera_id = str(camera_id)
    if camera_id not in trackers:
        trackers[camera_id] = CentroidTracker(max_disappeared=15)
        entry_exit_count[camera_id] = {"entry": 0, "exit": 0}
        previous_x[camera_id] = {}
    
    detections = []
    if detection_enabled:
        try:
            detections = detector.detect_humans(frame)
        except Exception as e:
            print(f"Detection error camera {camera_id}: {e}")
    
    rects = []
    for d in detections:
        cx = int(d["x"] + d["w"] / 2)
        cy = int(d["y"] + d["h"] / 2)
        rects.append((cx, cy))
    
    objects = trackers[camera_id].update(rects)
    
    for object_id, (cx, cy) in objects.items():
        prev_cx = previous_x[camera_id].get(object_id, cx)
        if prev_cx < line_position <= cx:
            entry_exit_count[camera_id]["entry"] += 1
            save_detection(camera_id, True)
        elif prev_cx > line_position >= cx:
            entry_exit_count[camera_id]["exit"] += 1
            save_detection(camera_id, False)
        
        previous_x[camera_id][object_id] = cx
        cv2.circle(frame, (cx, cy), 4, (255, 0, 0), -1)
    socketio.emit("people_count", {
        "camera_id": camera_id,
        "entry": entry_exit_count[camera_id]["entry"],
        "exit": entry_exit_count[camera_id]["exit"]
    })
    cv2.line(frame, (line_position, 0), (line_position, frame.shape[0]), (0, 0, 255), 2)
    frame = detector.draw_detections(frame, detections)
    
    return frame


def offline_frame(camera_id):
    frame = np.zeros((480, 640, 3), np.uint8)
    cv2.putText(frame, f'Camera {camera_id} Offline',
                (100, 250), cv2.FONT_HERSHEY_SIMPLEX,
                1, (255, 255, 255), 2)
    return frame


async def create_offer(camera_id, rtsp_url, socket_id):
    camera_id = str(camera_id)
    if not frame_manager.is_running(camera_id):
        camera = Camera.query.get(int(camera_id))
        video_file = camera.video_file if camera else None
        frame_manager.start_camera(camera_id, rtsp_url, video_file)
    else:
        print(f"processing for camera {camera_id}")
    pc = RTCPeerConnection()
    camera_clients[camera_id][socket_id] = pc
    track = CameraVideoTrack(camera_id)
    pc.addTrack(track)
    video_tracks[socket_id] = track
    
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


async def handle_answer(camera_id, socket_id, answer_data):
    camera_id = str(camera_id)
    
    pc = camera_clients.get(camera_id, {}).get(socket_id)
    if not pc:
        raise ValueError(f"No peer connection for camera {camera_id}, socket {socket_id}")
    if pc.signalingState != "have-local-offer":
        raise ValueError(f"Cannot handle answer in signaling state '{pc.signalingState}'")
    
    answer = RTCSessionDescription(
        sdp=answer_data["sdp"],
        type=answer_data["type"]
    )
    await pc.setRemoteDescription(answer)


async def close_connection(camera_id, socket_id):
    camera_id = str(camera_id)
    if camera_id in camera_clients and socket_id in camera_clients[camera_id]:
        pc = camera_clients[camera_id].pop(socket_id)
        try:
            current_state = pc.connectionState
            if current_state not in ['closed', 'failed']:
                for transceiver in pc.getTransceivers():
                    if transceiver.sender and transceiver.sender.track:
                        transceiver.sender.track.stop()
                await asyncio.wait_for(pc.close(), timeout=5.0)
            else:
                print(f"Connection already in {current_state} state")
                
        except asyncio.TimeoutError:
            print(f"Timeout while closing peer connection")
        except Exception as e:
            print(f"Error closing peer connection: {type(e).__name__} - {e}")
    track = video_tracks.pop(socket_id, None)
    if track:
        try:
            track.stop()
        except:
            pass
    if camera_id in camera_clients and len(camera_clients[camera_id]) == 0:
        frame_manager.stop_camera(camera_id)
        del camera_clients[camera_id]
    else:
        remaining = len(camera_clients.get(camera_id, {}))


def client_count(camera_id):
    camera_id = str(camera_id)
    return len(camera_clients.get(camera_id, {}))


def all_connections():
    result = {}
    for cam_id, clients in camera_clients.items():
        result[cam_id] = {
            'client_count': len(clients),
            'clients': list(clients.keys()),
            'camera_running': frame_manager.is_running(cam_id)
        }
    return result
