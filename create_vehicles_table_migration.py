"""
Script to create the vehicles table and migrate existing vehicle data from dropoffs.
This will create a vehicles table for tracking vehicle history by Registration Number (Rego).
"""

import os
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from collections import defaultdict

def create_vehicles_table():
    """Create vehicles table if it doesn't exist."""
    # Connect to PostgreSQL database
    conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
    
    try:
        with conn.cursor() as cursor:
            # Check if vehicles table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'vehicles'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                print("Creating vehicles table...")
                
                # Create vehicles table
                cursor.execute("""
                    CREATE TABLE vehicles (
                        id SERIAL PRIMARY KEY,
                        rego VARCHAR(20) NOT NULL UNIQUE,
                        name VARCHAR(100),
                        category VARCHAR(50),
                        current_km INTEGER DEFAULT 0,
                        service_due_km INTEGER DEFAULT 0,
                        rego_expiry DATE,
                        cof_expiry DATE,
                        last_dropoff_date TIMESTAMP,
                        total_dropoffs INTEGER DEFAULT 0,
                        total_trip_km INTEGER DEFAULT 0,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                conn.commit()
                print("Vehicles table created successfully.")
                
                # Populate with existing data from dropoffs
                populate_vehicles_from_dropoffs(conn)
            else:
                print("Vehicles table already exists.")
    except Exception as e:
        conn.rollback()
        print(f"Error creating vehicles table: {e}")
    finally:
        conn.close()

def populate_vehicles_from_dropoffs(conn):
    """Populate vehicles table with data from existing dropoffs."""
    try:
        with conn.cursor() as cursor:
            # Check if dropoffs table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'dropoffs'
                );
            """)
            dropoffs_exists = cursor.fetchone()[0]
            
            if not dropoffs_exists:
                print("Dropoffs table doesn't exist yet. Skipping data migration.")
                return
                
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            # Get unique vehicles from dropoffs
            cursor.execute("""
                SELECT 
                    rego,
                    name,
                    vehicle_category,
                    MAX(km_dropoff) as current_km,
                    MAX(service_due_km) as service_due_km,
                    MAX(rego_expiry) as rego_expiry,
                    MAX(cof_expiry) as cof_expiry,
                    MAX(date_returned) as last_dropoff_date,
                    COUNT(*) as total_dropoffs,
                    SUM(trip_km) as total_trip_km
                FROM dropoffs
                GROUP BY rego, name, vehicle_category
                ORDER BY rego;
            """)
            vehicles = cursor.fetchall()
            
            # Insert each vehicle into vehicles table
            for vehicle in vehicles:
                cursor.execute("""
                    INSERT INTO vehicles (
                        rego, name, category, current_km, service_due_km,
                        rego_expiry, cof_expiry, last_dropoff_date,
                        total_dropoffs, total_trip_km, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    vehicle['rego'],
                    vehicle['name'],
                    vehicle['vehicle_category'],
                    vehicle['current_km'] or 0,
                    vehicle['service_due_km'] or 0,
                    vehicle['rego_expiry'],
                    vehicle['cof_expiry'],
                    vehicle['last_dropoff_date'],
                    vehicle['total_dropoffs'],
                    vehicle['total_trip_km'] or 0,
                    datetime.now(),
                    datetime.now()
                ))
            
            conn.commit()
            print(f"Migrated {len(vehicles)} vehicles from dropoffs data.")
    except Exception as e:
        conn.rollback()
        print(f"Error populating vehicles table: {e}")

if __name__ == "__main__":
    create_vehicles_table()
    print("Migration completed.")