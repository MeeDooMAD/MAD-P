"""
Main entry point for the PostgreSQL version of the application.
"""
from app_pg import app

if __name__ == "__main__":
    # Run the Flask application on a different port to avoid conflicts
    app.run(host='0.0.0.0', port=5001, debug=True)