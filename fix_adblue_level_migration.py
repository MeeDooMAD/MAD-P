import sqlite3
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)

DB_PATH = 'dropoff.db'

def fix_adblue_level_column():
    """Change adblue_level column to TEXT if it's INTEGER"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Unfortunately, SQLite doesn't allow altering column types directly
        # We need to create a new table with the correct schema, copy data, and rename tables
        
        # First, let's back up the current data
        c.execute("CREATE TABLE IF NOT EXISTS dropoffs_backup AS SELECT * FROM dropoffs")
        
        # Now create a new table with the corrected schema
        c.execute("""
        CREATE TABLE dropoffs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rego TEXT NOT NULL,
            name TEXT NOT NULL,
            staff_name TEXT,
            vehicle_category TEXT,
            insurance_status TEXT,
            rego_expiry TEXT,
            cof_expiry TEXT,
            on_road_issues TEXT,
            current_rucs INTEGER,
            next_hire_date TEXT,
            next_hire_length INTEGER,
            km_pickup INTEGER DEFAULT 0,
            windscreen_condition TEXT,
            fuel_level INTEGER,
            adblue_level TEXT DEFAULT 'Not applicable',
            keys_working TEXT,
            remote_working TEXT,
            safe_emptied TEXT,
            damage_check TEXT,
            review_requested TEXT,
            customer_notes TEXT,
            mad_challenge_status TEXT,
            date_returned TEXT,
            status TEXT DEFAULT 'To be Dropped Off',
            km_dropoff INTEGER DEFAULT 0,
            trip_km INTEGER DEFAULT 0,
            service_due_km INTEGER DEFAULT 0,
            damage_image_filename TEXT,
            dropoff_eta TEXT,
            damage_areas TEXT,
            additional_damage_images TEXT,
            urgent_assessment TEXT DEFAULT 'No'
        )
        """)
        
        # Copy data, converting adblue_level to TEXT
        c.execute("""
        INSERT INTO dropoffs_new
        SELECT id, rego, name, staff_name, vehicle_category, insurance_status, rego_expiry, cof_expiry,
               on_road_issues, current_rucs, next_hire_date, next_hire_length, km_pickup,
               windscreen_condition, fuel_level, 
               CASE 
                   WHEN adblue_level = 0 THEN 'Not applicable'
                   WHEN adblue_level = 25 THEN 'Need top up'
                   WHEN adblue_level = 50 THEN 'Need top up'
                   WHEN adblue_level = 75 THEN 'Need top up'
                   WHEN adblue_level = 100 THEN 'Full'
                   ELSE 'Not applicable'
               END AS adblue_level,
               keys_working, remote_working, safe_emptied, damage_check, review_requested,
               customer_notes, mad_challenge_status, date_returned, status, km_dropoff, trip_km,
               service_due_km, damage_image_filename, dropoff_eta, damage_areas, additional_damage_images,
               urgent_assessment
        FROM dropoffs
        """)
        
        # Drop old table and rename new one
        c.execute("DROP TABLE dropoffs")
        c.execute("ALTER TABLE dropoffs_new RENAME TO dropoffs")
        
        conn.commit()
        conn.close()
        logging.info("adblue_level column fixed successfully")
        return True
    except Exception as e:
        logging.error(f"Error in migration: {str(e)}")
        return False

if __name__ == "__main__":
    fix_adblue_level_column()