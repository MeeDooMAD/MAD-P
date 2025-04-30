"""
Script to add permission columns to the users table.
This will add granular permission control for different areas of the application.
"""

import os
import sys
import logging
import psycopg2
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

def add_user_permissions():
    """Add permission columns to the users table if they don't exist."""
    # Get database connection details from environment
    db_url = os.environ.get("DATABASE_URL")
    
    if not db_url:
        logging.error("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    try:
        # Connect to PostgreSQL database
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND (column_name = 'dashboard_access' 
                OR column_name = 'dropoff_access'
                OR column_name = 'ta_checklist_access'
                OR column_name = 'maintenance_alerts_access'
                OR column_name = 'vehicle_management_access'
                OR column_name = 'reports_access')
        """)
        existing_columns = [col[0] for col in cursor.fetchall()]
        
        # Add new columns if they don't exist
        columns_to_add = []
        
        if 'dashboard_access' not in existing_columns:
            columns_to_add.append("dashboard_access BOOLEAN DEFAULT TRUE")
        
        if 'dropoff_access' not in existing_columns:
            columns_to_add.append("dropoff_access BOOLEAN DEFAULT TRUE")
        
        if 'ta_checklist_access' not in existing_columns:
            columns_to_add.append("ta_checklist_access BOOLEAN DEFAULT TRUE")
        
        if 'maintenance_alerts_access' not in existing_columns:
            columns_to_add.append("maintenance_alerts_access BOOLEAN DEFAULT TRUE")
        
        if 'vehicle_management_access' not in existing_columns:
            columns_to_add.append("vehicle_management_access BOOLEAN DEFAULT TRUE")
        
        if 'reports_access' not in existing_columns:
            columns_to_add.append("reports_access BOOLEAN DEFAULT TRUE")
        
        # Execute the migration
        if columns_to_add:
            add_columns_sql = "ALTER TABLE users ADD " + ", ADD ".join(columns_to_add)
            cursor.execute(add_columns_sql)
            
            # Update existing admin users to have all permissions
            cursor.execute("""
                UPDATE users
                SET dashboard_access = TRUE,
                    dropoff_access = TRUE,
                    ta_checklist_access = TRUE,
                    maintenance_alerts_access = TRUE,
                    vehicle_management_access = TRUE,
                    reports_access = TRUE
                WHERE role = 'admin'
            """)
            
            conn.commit()
            logging.info(f"Added {len(columns_to_add)} permission columns to users table")
        else:
            logging.info("All permission columns already exist in users table")
        
    except Exception as e:
        logging.error(f"Error adding permission columns: {str(e)}")
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    add_user_permissions()
    print("User permissions migration completed successfully!")