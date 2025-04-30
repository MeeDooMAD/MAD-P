import os
import psycopg2
import logging

logging.basicConfig(level=logging.DEBUG)

# Get database connection string from environment
database_url = os.environ.get('DATABASE_URL')
print(f"DATABASE_URL exists: {database_url is not None}")

try:
    print("Attempting to connect to PostgreSQL database...")
    conn = psycopg2.connect(database_url)
    print("Successfully connected to PostgreSQL database!")
    
    # Check if users table exists
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = cur.fetchall()
    print("Available tables:")
    for table in tables:
        print(f"- {table[0]}")
    
    # Try to query users table if it exists
    if ('users',) in tables:
        print("\nQuerying users table:")
        cur.execute("SELECT id, username, role FROM users")
        users = cur.fetchall()
        for user in users:
            print(f"User ID: {user[0]}, Username: {user[1]}, Role: {user[2]}")
    else:
        print("\nUsers table does not exist yet.")
        
except Exception as e:
    print(f"\nError connecting to the database: {e}")
finally:
    if 'conn' in locals() and conn:
        if 'cur' in locals() and cur:
            cur.close()
        conn.close()
        print("Database connection closed.")
