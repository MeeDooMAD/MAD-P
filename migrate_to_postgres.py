"""
Script to migrate data from SQLite to PostgreSQL database.
This will read all data from the SQLite database and insert it into PostgreSQL.
"""
import sqlite3
import json
import logging
from datetime import datetime
from sqlalchemy import text
from app_pg import app, db
from models_pg import Dropoff, MaintenanceAlert

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# SQLite database path
SQLITE_DB_PATH = "dropoff.db"

def convert_date(date_str):
    """Convert date string to Python date object if not None"""
    if not date_str:
        return None
    
    try:
        # Try different date formats
        for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
    except Exception as e:
        logger.error(f"Error converting date {date_str}: {str(e)}")
        return None

def convert_adblue_level(adblue_value):
    """Convert AdBlue level from integer to string format"""
    if adblue_value is None:
        return 'Not applicable'
    
    # Check if it's already a string
    if isinstance(adblue_value, str):
        # If it's a string, check if it matches our expected values
        if adblue_value in ['Full', 'Need top up', 'Not applicable']:
            return adblue_value
        # Otherwise, it might be another string value, return as is
        return adblue_value
        
    # Convert integer values to strings
    try:
        level = int(adblue_value)
        if level == 0:
            return 'Not applicable'
        elif level == 25 or level == 50 or level == 75:
            return 'Need top up'
        elif level == 100:
            return 'Full'
        else:
            return 'Not applicable'
    except (ValueError, TypeError):
        logger.warning(f"Could not convert AdBlue level: {adblue_value}")
        return 'Not applicable'

def migrate_dropoffs():
    """Migrate dropoff data from SQLite to PostgreSQL"""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Get all records from SQLite
        c.execute("SELECT * FROM dropoffs")
        dropoffs = [dict(row) for row in c.fetchall()]
        logger.info(f"Found {len(dropoffs)} dropoff records in SQLite")
        
        # Insert records into PostgreSQL
        for dropoff in dropoffs:
            # Parse additional_damage_images JSON if not None
            additional_images = None
            if dropoff['additional_damage_images']:
                try:
                    additional_images = json.loads(dropoff['additional_damage_images'])
                except:
                    additional_images = []
            
            # Get or convert AdBlue level
            adblue_level_text = convert_adblue_level(dropoff.get('adblue_level'))
            
            # Use adblue_level_text from the column if it exists
            if 'adblue_level_text' in dropoff and dropoff['adblue_level_text']:
                adblue_level_text = dropoff['adblue_level_text']
                
            # Create new Dropoff record
            new_dropoff = Dropoff(
                id=dropoff['id'],  # Keep the same ID
                rego=dropoff['rego'],
                name=dropoff['name'],
                insurance_status=dropoff['insurance_status'],
                rego_expiry=convert_date(dropoff['rego_expiry']),
                cof_expiry=convert_date(dropoff['cof_expiry']),
                on_road_issues=dropoff['on_road_issues'],
                current_rucs=dropoff['current_rucs'],
                next_hire_date=convert_date(dropoff['next_hire_date']),
                next_hire_length=dropoff['next_hire_length'],
                km_pickup=dropoff['km_pickup'],
                km_dropoff=dropoff['km_dropoff'],
                trip_km=dropoff['trip_km'],
                service_due_km=dropoff['service_due_km'],
                windscreen_condition=dropoff['windscreen_condition'],
                fuel_level=dropoff['fuel_level'],
                adblue_level=adblue_level_text,
                keys_working=dropoff['keys_working'],
                remote_working=dropoff['remote_working'],
                safe_emptied=dropoff['safe_emptied'],
                damage_check=dropoff['damage_check'],
                review_requested=dropoff['review_requested'],
                customer_notes=dropoff['customer_notes'],
                mad_challenge_status=dropoff['mad_challenge_status'],
                date_returned=convert_date(dropoff['date_returned']),
                status=dropoff['status'],
                damage_image_filename=dropoff['damage_image_filename'],
                additional_damage_images=additional_images,
                urgent_assessment=dropoff['urgent_assessment'],
                dropoff_eta=convert_date(dropoff['dropoff_eta'])
            )
            
            db.session.add(new_dropoff)
        
        db.session.commit()
        logger.info("Successfully migrated dropoff records to PostgreSQL")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error migrating dropoffs: {str(e)}")
        raise
    finally:
        conn.close()

def migrate_maintenance_alerts():
    """Migrate maintenance alerts from SQLite to PostgreSQL"""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Get all records from SQLite
        c.execute("SELECT * FROM maintenance_alerts")
        alerts = [dict(row) for row in c.fetchall()]
        logger.info(f"Found {len(alerts)} maintenance alert records in SQLite")
        
        # Insert records into PostgreSQL
        for alert in alerts:
            new_alert = MaintenanceAlert(
                id=alert['id'],  # Keep the same ID
                dropoff_id=alert['dropoff_id'],
                rego=alert['rego'],
                name=alert['name'],
                issue_type=alert['issue_type'],
                details=alert['details'],
                status=alert['status'],
                date_created=convert_date(alert['date_created']),
                date_fixed=convert_date(alert['date_fixed'])
            )
            
            db.session.add(new_alert)
        
        db.session.commit()
        logger.info("Successfully migrated maintenance alert records to PostgreSQL")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error migrating maintenance alerts: {str(e)}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting migration from SQLite to PostgreSQL...")
    
    try:
        with app.app_context():
            # Reset PostgreSQL sequences - first check if tables exist
            try:
                # Check if tables exist first
                result = db.session.execute(text("SELECT to_regclass('public.dropoffs')")).scalar()
                if result:
                    # Tables exist, truncate them
                    db.session.execute(text('TRUNCATE dropoffs, maintenance_alerts RESTART IDENTITY CASCADE'))
                    db.session.commit()
                else:
                    # Create tables
                    db.create_all()
            except Exception as table_err:
                logger.error(f"Error checking/truncating tables: {str(table_err)}")
                # Create tables if error occurred (possibly tables don't exist)
                db.create_all()
                db.session.commit()
            
            migrate_dropoffs()
            migrate_maintenance_alerts()
            
            # Get counts to verify migration
            dropoff_count = Dropoff.query.count()
            alert_count = MaintenanceAlert.query.count()
            print(f"Migration complete! Migrated {dropoff_count} dropoffs and {alert_count} maintenance alerts.")
    except Exception as e:
        print(f"Migration failed: {str(e)}")