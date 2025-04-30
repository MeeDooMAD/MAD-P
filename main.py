"""
Main entry point for the application.
Directly imports app from app_pg
"""
from app_pg import app

# For Gunicorn
application = app