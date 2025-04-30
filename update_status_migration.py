import sqlite3
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)

DB_PATH = 'dropoff.db'

def update_status_column():
    """Update the default value for the status column in the dropoffs table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Update existing statuses
        c.execute("UPDATE dropoffs SET status = 'To be Dropped Off' WHERE status = 'To be D/OFF'")
        c.execute("UPDATE dropoffs SET status = 'Drop Off Completed' WHERE status = 'D/OFF Completed'")
        
        conn.commit()
        conn.close()
        logging.info("Status values updated successfully")
        return True
    except Exception as e:
        logging.error(f"Error in migration: {str(e)}")
        return False

if __name__ == "__main__":
    update_status_column()