"""
Entry point for the app on port 5001.
This is used for the vehicle_dropoff_system workflow.
"""
from app_pg import app

if __name__ == "__main__":
    # Use port 5001 to avoid conflict with gunicorn on 5000
    app.run(host='0.0.0.0', port=5001, debug=True)