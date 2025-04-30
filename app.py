"""
Direct entry point for the app.
This completely skips the redirect mechanism and directly imports from app_pg.py.
"""
from app_pg import app

if __name__ == "__main__":
    # Use port 5001 to avoid conflict with gunicorn on 5000
    app.run(host='0.0.0.0', port=5001, debug=True)