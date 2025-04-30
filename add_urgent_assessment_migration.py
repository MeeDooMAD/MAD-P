"""
Script to add urgent_assessment column to the dropoffs table.
This column is used to mark vehicles that need urgent assessment.
"""
import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "dropoff.db"

def add_urgent_assessment_column():
    """Add urgent_assessment column if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Check if the column already exists
        c.execute("PRAGMA table_info(dropoffs)")
        columns = [info[1] for info in c.fetchall()]
        
        if 'urgent_assessment' not in columns:
            logger.info("Adding urgent_assessment column to dropoffs table...")
            c.execute("""
                ALTER TABLE dropoffs
                ADD COLUMN urgent_assessment TEXT DEFAULT 'No'
            """)
            conn.commit()
            logger.info("Successfully added urgent_assessment column.")
        else:
            logger.info("urgent_assessment column already exists.")
            
    except Exception as e:
        logger.error(f"Error adding urgent_assessment column: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_urgent_assessment_column()
    print("Migration complete!")