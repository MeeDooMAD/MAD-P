import sqlite3
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)

DB_PATH = 'dropoff.db'

def add_missing_columns():
    """Add missing columns to the SQLite database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if the column exists before trying to add it
        columns_info = c.execute("PRAGMA table_info(dropoffs)").fetchall()
        column_names = [column[1] for column in columns_info]
        
        # Add staff_name column if it doesn't exist
        if 'staff_name' not in column_names:
            logging.info("Adding staff_name column to dropoffs table")
            c.execute("ALTER TABLE dropoffs ADD COLUMN staff_name TEXT")
        else:
            logging.info("staff_name column already exists")
        
        # Add vehicle_category column if it doesn't exist
        if 'vehicle_category' not in column_names:
            logging.info("Adding vehicle_category column to dropoffs table")
            c.execute("ALTER TABLE dropoffs ADD COLUMN vehicle_category TEXT")
        else:
            logging.info("vehicle_category column already exists")
            
        conn.commit()
        conn.close()
        logging.info("Migration completed successfully")
        return True
    except Exception as e:
        logging.error(f"Error in migration: {str(e)}")
        return False

if __name__ == "__main__":
    add_missing_columns()