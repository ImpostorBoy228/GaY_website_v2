from flask import Flask
from flask_socketio import SocketIO
from config import CONFIG
from extensions import db, migrate, login_manager, jwt
from flask_login import login_required
from youtube_downloader import YouTubeDownloader
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__, template_folder='templates')
    
    # Apply configuration
    logger.info("Applying configuration")
    app.config.from_object(CONFIG)
    
    # Debug configuration
    logger.info(f"App config after from_object: {dict(app.config)}")
    logger.info(f"SQLALCHEMY_DATABASE_URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    
    # Explicitly set critical config as fallback
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        logger.warning("SQLALCHEMY_DATABASE_URI not set by from_object, setting explicitly")
        app.config['SQLALCHEMY_DATABASE_URI'] = getattr(CONFIG, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///app.db')
    
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        logger.error("SQLALCHEMY_DATABASE_URI is still not set")
        raise ValueError("SQLALCHEMY_DATABASE_URI must be set")
    
    # Initialize SocketIO
    socketio = SocketIO(app)
    
    # Initialize extensions
    try:
        db.init_app(app)
        migrate.init_app(app, db)
        login_manager.init_app(app)
        jwt.init_app(app)
    except Exception as e:
        logger.error(f"Failed to initialize extensions: {e}")
        raise

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

    # Initialize YouTubeDownloader
    try:
        app.downloader = YouTubeDownloader(app, socketio)
        logger.info("YouTubeDownloader initialized and attached to app")
    except Exception as e:
        logger.error(f"Failed to initialize YouTubeDownloader: {e}")
        raise

    # Create database schema and initialize components
    with app.app_context():
        try:
            create_app_schema()
            init_app_components(app)
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            raise

    return app, socketio

def create_app_schema():
    logger.info("Calling create_app_schema")
    try:
        db.create_all()
        logger.info("Schema 'app' created or already exists")
    except Exception as e:
        logger.error(f"Error creating schema: {e}")
        raise

def init_app_components(app):
    logger.info("Calling init_app_components")
    logger.info(f"Templates path: {os.path.join(os.path.dirname(__file__), 'templates')}")
    logger.info("Starting initialization of application components")
    try:
        from routes import init_routes
        init_routes(app, logger)
    except Exception as e:
        logger.error(f"Error initializing application components: {e}")
        raise

if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, debug=True)