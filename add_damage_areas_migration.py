"""
Script to add damage_areas column to the dropoffs table.
This column is used to store information about affected damage areas from the interactive damage map.
"""
import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "dropoff.db"

def add_damage_areas_column():
    """Add damage_areas column if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Check if the column already exists
        c.execute("PRAGMA table_info(dropoffs)")
        columns = [info[1] for info in c.fetchall()]
        
        if 'damage_areas' not in columns:
            logger.info("Adding damage_areas column to dropoffs table...")
            c.execute("""
                ALTER TABLE dropoffs
                ADD COLUMN damage_areas TEXT
            """)
            conn.commit()
            logger.info("Successfully added damage_areas column.")
        else:
            logger.info("damage_areas column already exists.")
            
    except Exception as e:
        logger.error(f"Error adding damage_areas column: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_damage_areas_column()
    print("Migration complete!")