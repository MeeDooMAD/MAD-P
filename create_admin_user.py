"""
Script to create the initial admin user for the MAD Pitstop system.
This should be run once after the database is set up.
"""

import os
import sys
from datetime import datetime
from app_pg import app, db
from models_pg import User

def create_admin_user(username, password):
    """Create an admin user with the given username and password."""
    
    # Check if user already exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        print(f"User '{username}' already exists.")
        return False
    
    # Create new admin user
    admin = User(
        username=username,
        role='admin',
        created_at=datetime.now()
    )
    admin.set_password(password)
    
    # Save to database
    db.session.add(admin)
    db.session.commit()
    
    print(f"Admin user '{username}' created successfully!")
    return True

def create_default_admin():
    """Create the default admin user if no users exist."""
    
    # Check if there are any users in the database
    user_count = User.query.count()
    if user_count > 0:
        print(f"There are already {user_count} users in the database.")
        
        # Check if there's an admin user
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count > 0:
            print(f"There are already {admin_count} admin users in the database.")
            return
        
        print("No admin users found. Creating default admin...")
    else:
        print("No users found in the database. Creating default admin...")
    
    # Default admin credentials
    default_username = "admin"
    default_password = "madpitstop2025"  # This will be changed after first login
    
    # Create the admin user
    create_admin_user(default_username, default_password)
    print()
    print("*** IMPORTANT: Please change the default admin password immediately! ***")
    print(f"Default username: {default_username}")
    print(f"Default password: {default_password}")

if __name__ == "__main__":
    with app.app_context():
        if len(sys.argv) == 3:
            # Create user with provided credentials
            username = sys.argv[1]
            password = sys.argv[2]
            create_admin_user(username, password)
        else:
            # Create default admin user
            create_default_admin()