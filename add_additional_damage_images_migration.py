"""
Script to add additional_damage_images column to the dropoffs table.
This column is used to store multiple damage images uploaded during dropoff completion.
"""
import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "dropoff.db"

def add_additional_damage_images_column():
    """Add additional_damage_images column if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Check if the column already exists
        c.execute("PRAGMA table_info(dropoffs)")
        columns = [info[1] for info in c.fetchall()]
        
        if 'additional_damage_images' not in columns:
            logger.info("Adding additional_damage_images column to dropoffs table...")
            c.execute("""
                ALTER TABLE dropoffs
                ADD COLUMN additional_damage_images TEXT
            """)
            conn.commit()
            logger.info("Successfully added additional_damage_images column.")
        else:
            logger.info("additional_damage_images column already exists.")
            
    except Exception as e:
        logger.error(f"Error adding additional_damage_images column: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_additional_damage_images_column()
    print("Migration complete!")