import asyncio
import threading
import logging
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from config import Config
from flask_migrate import Migrate 
from flask_wtf.csrf import CSRFProtect

# logging.basicConfig(
#     level=logging.DEBUG,
#     format='%(asctime)s %(levelname)s: %(message)s',
#     handlers=[
#         logging.FileHandler('app.log'),
#         logging.StreamHandler()
#     ]
# )
# logger = logging.getLogger(__name__)


db = SQLAlchemy()
migrate = Migrate()  
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    global loop
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    # logger.debug("Started")
    
    @app.route('/')
    def index():
        # logger.debug("Redirecting to login page")
        return redirect(url_for('auth.login'))
    from Apps.Auth.routes import auth
    from Apps.humanDetection.routes import detection
    from Apps.humanDetection import websocket_routes

    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(detection, url_prefix='/detection')
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            return None
    from Apps.Auth.models import User
    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = User.query.get(int(user_id))
            return user
        except Exception as e:

            return None
    
    return app

