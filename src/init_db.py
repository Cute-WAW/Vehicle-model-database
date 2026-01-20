import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent))
from db_supabase import hash_password

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load env
load_dotenv(Path(__file__).parent.parent / '.env')
DATABASE_URL = os.getenv("DATABASE_URL")

def init_database():
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in .env")
        return

    try:
        engine = create_engine(DATABASE_URL)
        logger.info(f"Connecting to database...")
        
        with engine.connect() as conn:
            # 1. Read and execute schema
            schema_path = Path(__file__).parent.parent / 'supabase_schema.sql'
            if schema_path.exists():
                logger.info(f"Executing schema from {schema_path}")
                sql_content = schema_path.read_text(encoding='utf-8')
                # Split by ; to execute statements individually if needed, 
                # but sqlalchemy execute might handle it or we use text()
                # For safety with plpgsql triggers, we might need to be careful with splitting.
                # Let's try executing the whole block if possible, or split carefully.
                # Actually, simple splitting by semicolon might break function definitions ($$).
                # Supabase/Postgres usually can handle the whole script if sent as one command via some drivers,
                # but SQLAlchemy might prefer individual statements.
                # Let's try sending the whole thing first.
                try:
                    conn.execute(text(sql_content))
                    conn.commit()
                    logger.info("Schema executed successfully.")
                except Exception as e:
                    logger.warning(f"Batch execution failed, trying to split: {e}")
                    # Very simple split, might fail on complex PL/SQL
                    statements = sql_content.split(';')
                    for stmt in statements:
                        if stmt.strip():
                            try:
                                conn.execute(text(stmt))
                                conn.commit()
                            except Exception as ex:
                                logger.error(f"Statement failed: {stmt[:50]}... Error: {ex}")

            # 2. Create test user
            username = "admin"
            password = "password123"
            hashed_pw = hash_password(password)
            
            # Check if exists
            check = conn.execute(
                text("SELECT id FROM users WHERE username = :u"),
                {"u": username}
            ).fetchone()
            
            if not check:
                logger.info(f"Creating test user: {username} / {password}")
                conn.execute(
                    text("""
                        INSERT INTO users (username, password_hash, nickname, role, status)
                        VALUES (:u, :p, '管理员', 'admin', 'active')
                    """),
                    {"u": username, "p": hashed_pw}
                )
                conn.commit()
                logger.info("Test user created.")
            else:
                logger.info(f"Test user '{username}' already exists.")
                
            logger.info("Database initialization completed.")
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

if __name__ == "__main__":
    init_database()
