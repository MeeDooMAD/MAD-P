import sqlite3
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)

DB_PATH = 'dropoff.db'

def update_adblue_column():
    """Add adblue_level_text column and populate it from adblue_level"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # First add a new text column for adblue level
        c.execute("ALTER TABLE dropoffs ADD COLUMN adblue_level_text TEXT DEFAULT 'Not applicable'")
        
        # Update the new column based on the existing integer values
        c.execute("""
        UPDATE dropoffs SET adblue_level_text = 
            CASE 
                WHEN adblue_level = 0 THEN 'Not applicable'
                WHEN adblue_level = 25 THEN 'Need top up'
                WHEN adblue_level = 50 THEN 'Need top up'
                WHEN adblue_level = 75 THEN 'Need top up'
                WHEN adblue_level = 100 THEN 'Full'
                ELSE 'Not applicable'
            END
        """)
        
        conn.commit()
        conn.close()
        logging.info("adblue_level_text column added successfully")
        return True
    except Exception as e:
        logging.error(f"Error in migration: {str(e)}")
        return False

if __name__ == "__main__":
    update_adblue_column()