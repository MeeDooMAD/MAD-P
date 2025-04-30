import sqlite3
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)

DB_PATH = 'dropoff.db'

def add_service_due_km_column():
    """Add the service_due_km column if it doesn't exist"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if the column exists before trying to add it
        columns_info = c.execute("PRAGMA table_info(dropoffs)").fetchall()
        column_names = [column[1] for column in columns_info]
        
        # Add service_due_km column if it doesn't exist
        if 'service_due_km' not in column_names:
            logging.info("Adding service_due_km column to dropoffs table")
            c.execute("ALTER TABLE dropoffs ADD COLUMN service_due_km INTEGER DEFAULT 0")
        else:
            logging.info("service_due_km column already exists")
            
        conn.commit()
        conn.close()
        logging.info("Migration completed successfully")
        return True
    except Exception as e:
        logging.error(f"Error in migration: {str(e)}")
        return False

if __name__ == "__main__":
    add_service_due_km_column()