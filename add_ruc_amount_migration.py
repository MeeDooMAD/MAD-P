"""
Script to add ruc_amount column to the dropoffs table.
This column is used to store calculated Road User Charges (RUCs) for diesel vehicles.
"""

import os
import logging
import psycopg2
from psycopg2 import sql

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def add_ruc_amount_column():
    """Add ruc_amount column if it doesn't exist."""
    # Get database connection string from environment variable
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    if not DATABASE_URL:
        logging.error("DATABASE_URL environment variable not set")
        return False
    
    try:
        # Connect to PostgreSQL database
        logging.info("Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Check if column exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'dropoffs' AND column_name = 'ruc_amount';
        """)
        
        if cur.fetchone() is None:
            # Add column if it doesn't exist
            logging.info("Adding ruc_amount column to dropoffs table...")
            cur.execute("""
                ALTER TABLE dropoffs 
                ADD COLUMN ruc_amount DOUBLE PRECISION DEFAULT 0.0;
            """)
            
            # Commit the transaction
            conn.commit()
            logging.info("Migration completed successfully.")
            result = True
        else:
            logging.info("ruc_amount column already exists, skipping migration.")
            result = True
        
        # Close cursor and connection
        cur.close()
        conn.close()
        return result
        
    except Exception as e:
        logging.error(f"Migration failed: {str(e)}")
        return False

# Run the migration if script is executed directly
if __name__ == "__main__":
    if add_ruc_amount_column():
        logging.info("Migration successful.")
    else:
        logging.error("Migration failed.")
