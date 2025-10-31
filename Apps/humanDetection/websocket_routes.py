from flask_socketio import emit, join_room
from flask import request
from app import socketio
from .webrtc_service import create_offer, handle_answer, close_connection
from .models import Camera
from .webrtc_service import client_count, frame_manager, all_connections
import threading
import asyncio
import time


socket_camera_map = {}
webrtc_loop = None
webrtc_thread = None

def web_loop():
    global webrtc_loop, webrtc_thread
    
    if webrtc_loop is None:
        def run_loop():
            global webrtc_loop
            webrtc_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(webrtc_loop)
            webrtc_loop.run_forever()
        
        webrtc_thread = threading.Thread(target=run_loop, daemon=True)
        webrtc_thread.start()
        time.sleep(0.1) 

web_loop()

def run_coroutine(coro):
    if webrtc_loop is None:
        web_loop()
    
    future = asyncio.run_coroutine_threadsafe(coro, webrtc_loop)
    try:
        return future.result(timeout=10.0)
    except Exception as e:
        print(f"Coroutine execution error: {e}")
        return None


@socketio.on('connect', namespace='/camera')
def connect():
    socket_id = request.sid
    camera_id = request.args.get('camera_id') 
    if camera_id:
        camera_id = str(camera_id)
        socket_camera_map[socket_id] = camera_id
        join_room(f"camera_{camera_id}")
        emit('ready', {'status': 'connected', 'camera_id': camera_id})
    else:
        emit('ready', {'status': 'waiting_for_camera'})


@socketio.on('disconnect', namespace='/camera')
def disconnect():
    socket_id = request.sid
    camera_id = socket_camera_map.get(socket_id)
    
    if camera_id:
        def cleanup():
            try:
                run_coroutine(close_connection(camera_id, socket_id))
            except Exception as e:
                print(f"Cleanup error: {e}")
        cleanup_thread = threading.Thread(target=cleanup, daemon=True)
        cleanup_thread.start()
        
        socket_camera_map.pop(socket_id, None)
    else:
        print(f"Client {socket_id} disconnected (no camera)")


@socketio.on('request_offer', namespace='/camera')
def request_offer(data):
    socket_id = request.sid
    camera_id = data.get('camera_id') or socket_camera_map.get(socket_id)
    
    if not camera_id:
        emit('error', {'message': 'No camera_id provided'})
        return
    camera_id = str(camera_id)
    if socket_id in socket_camera_map and socket_camera_map[socket_id] == camera_id:
        return
    socket_camera_map[socket_id] = camera_id
    join_room(f"camera_{camera_id}")  
    try:
        camera = Camera.query.get(int(camera_id))
        if not camera:
            emit('error', {'message': f'Camera {camera_id} not found'})
            return
        
        rtsp_url = camera.rtsp_url or "0"
        offer = run_coroutine(create_offer(camera_id, rtsp_url, socket_id))
        
        if not offer:
            emit('error', {'message': 'Failed to create WebRTC offer'})
            return
        emit('webrtc_offer', offer)
        
    except Exception as e:
        print(f"Error creating offer: {e}")
        import traceback
        traceback.print_exc()
        emit('error', {'message': str(e)})


@socketio.on('webrtc_answer', namespace='/camera')
def webrtc_answer(data):
    socket_id = request.sid
    camera_id = socket_camera_map.get(socket_id)
    
    if not camera_id:
        emit('error', {'message': 'No camera_id associated with socket'})
        return
    try:
        result = run_coroutine(handle_answer(camera_id, socket_id, data))
        
        if result is not None:
            print(f"Processed answer from client {socket_id} for camera {camera_id}")
        
    except Exception as e:
        print(f"Error handling answer: {e}")
        import traceback
        traceback.print_exc()
        emit('error', {'message': str(e)})


@socketio.on('ice_candidate', namespace='/camera')
def ice_candidate(data):
    socket_id = request.sid
    camera_id = socket_camera_map.get(socket_id)
    if camera_id:
        pass

@socketio.on('ping', namespace='/camera')
def ping():
    emit('pong', {'timestamp': time.time()})


@socketio.on('get_stats', namespace='/camera')
def get_stats():
    socket_id = request.sid
    camera_id = socket_camera_map.get(socket_id)
    stats = {
        'socket_id': socket_id,
        'camera_id': camera_id,
        'total_clients': client_count(camera_id) if camera_id else 0,
        'camera_running': frame_manager.is_running(camera_id) if camera_id else False,
        'all_connections': all_connections()
    }
    emit('stats', stats)