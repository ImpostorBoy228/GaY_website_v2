import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
logger.info(f"Loading .env from: {dotenv_path}")
if not os.path.exists(dotenv_path):
    logger.error(f".env file not found at: {dotenv_path}")
load_dotenv(dotenv_path=dotenv_path)

# Debug environment variables
supabase_db_uri = os.getenv('SUPABASE_DB_URI')
logger.info(f"SUPABASE_DB_URI from environment: {supabase_db_uri}")

SUPABASE_CONFIG = {
    'url': os.getenv('SUPABASE_URL', 'https://dyrirazjssnbxzfyxvjv.supabase.co'),
    'key': os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR5cmlyYXpqc3NuYnh6Znl4dmp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU3NTM0MjUsImV4cCI6MjA2MTMyOTQyNX0.wDP9iE_Fza0rqswjT_OUcu30InKVHihHGeF5ODiEWxA'),
    'service_role_key': os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR5cmlyYXpqc3NuYnh6Znl4dmp2Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NTc1MzQyNSwiZXhwIjoyMDYxMzI5NDI1fQ.oN6daIHZiigth060-skoW6DF8m3ht5X4jMUYBdJmPHY'),
    'jwt_secret': os.getenv('SUPABASE_JWT_SECRET', 'your-supabase-jwt-secret'),
    'db_uri': supabase_db_uri if supabase_db_uri else 'postgresql://postgres.dyrirazjssnbxzfyxvjv:dicksuck228@aws-0-eu-west-3.pooler.supabase.com:6543/postgres',
    'storage_path': os.getenv('STORAGE_PATH', '/home/impostorboy/prjcts/Leather_outfit_v2_backup/static/videos'),
}

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key')
    SQLALCHEMY_DATABASE_URI = supabase_db_uri if supabase_db_uri else 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', '/home/impostorboy/prjcts/Leather_outfit_v2_backup/credentials.json')
    SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE', '/home/impostorboy/prjcts/Leather_outfit_v2_backup/service_account.json')
    AVG_VIDEO_SIZE_MB = 100
    AVG_DOWNLOAD_SPEED_MBPS = 10

CONFIG = Config()

logger.info(f"CONFIG attributes: {vars(CONFIG)}")