from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response, jsonify, session, g
import flask_excel as excel
from datetime import datetime, timedelta, date
import logging
import os
import json
import pdfkit
import tempfile
import csv
from io import BytesIO, StringIO
import uuid
import re
import math
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
from sqlalchemy import or_, case, text, func, and_
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models_pg import db, Dropoff, MaintenanceAlert, SentEmailReport, Vehicle, User, SessionLog

# Configure file uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Configure logging
import sys
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s', handlers=[
    logging.StreamHandler(sys.stdout),
    logging.FileHandler('app.log')
])

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Configure PostgreSQL database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)
excel.init_excel(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Specify the login route

# Custom template filters for date/time formatting
@app.template_filter('format_date')
def format_date(value):
    """Format date to British English format (DD/MM/YYYY)"""
    if not value:
        return ""
    
    # Handle both datetime and date objects
    if isinstance(value, datetime):
        date_obj = value.date()
    else:
        date_obj = value
    
    # Get today and tomorrow for comparison
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    # Format based on if it's today, tomorrow or another date
    if date_obj == today:
        return "Today"
    elif date_obj == tomorrow:
        return "Tomorrow"
    else:
        return date_obj.strftime('%d/%m/%Y')

@app.template_filter('format_time')
def format_time(value):
    """Format time to 12-hour clock (HH:MM am/pm) using British English format"""
    if not value or not isinstance(value, datetime):
        return ""
    
    # Format as 12-hour clock and remove leading zero, then convert AM/PM to lowercase
    return value.strftime('%I:%M %p').lstrip('0').replace('AM', 'am').replace('PM', 'pm')

@app.template_filter('format_datetime')
def format_datetime(value):
    """Format datetime to British English format with 12-hour clock"""
    if not value:
        return ""
    
    # Handle both datetime and date objects
    if isinstance(value, datetime):
        # Get formatted date and time
        formatted_date = format_date(value)
        formatted_time = format_time(value)
        
        # Combine date and time
        return f"{formatted_date} - {formatted_time}"
    else:
        # It's a date object, just format the date
        return format_date(value)

@app.template_filter('is_past_date')
def is_past_date(value):
    """Check if a date is in the past"""
    if not value:
        return False
    
    # Handle both datetime and date objects
    if isinstance(value, datetime):
        date_obj = value.date()
    else:
        date_obj = value
    
    return date_obj < date.today()

@app.template_filter('format_currency')
def format_currency(value):
    """Format currency in New Zealand Dollars (NZD)
    
    Requirements:
    - Currency symbol must be "NZ$" (not just $)
    - Use comma for thousands separator
    - Always show 2 decimal places
    - No currency shown without the NZ$ prefix
    
    Example: NZ$1,234.56
    """
    if value is None:
        return 'N/A'
    
    # Format with NZ$ prefix, commas for thousands, and 2 decimal places
    return f"NZ${value:,.2f}"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# File upload helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_image(file):
    if file and allowed_file(file.filename):
        # Create a unique filename to prevent conflicts
        filename = secure_filename(file.filename)
        file_extension = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)  # Ensure directory exists
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return unique_filename
    return None

# Helper function to get all dropoffs
def get_all_dropoffs():
    return Dropoff.query.order_by(Dropoff.date_returned.desc()).all()

# Helper function to get a specific dropoff
def get_dropoff(dropoff_id):
    return Dropoff.query.get_or_404(dropoff_id)

# Helper function to get all maintenance alerts
def get_maintenance_alerts():
    return MaintenanceAlert.query.order_by(MaintenanceAlert.date_created.desc()).all()

# Vehicle management helper functions
def get_vehicle_by_rego(rego):
    """Get a vehicle by its registration number"""
    return Vehicle.query.filter_by(rego=rego).first()

def get_all_vehicles():
    """Get all vehicles in the system"""
    return Vehicle.query.order_by(Vehicle.rego).all()

def calculate_ruc_amount(vehicle_category, trip_km):
    """
    Calculate Road User Charges (RUCs) for diesel vehicles
    
    Rules:
    - Only applies to MAD EXPLORER and MAD TRACKER vehicles
    - $95 NZD for first 1000 km
    - $9 NZD for every additional 100 km (or part thereof)
    
    Args:
        vehicle_category: The category of the vehicle
        trip_km: The distance traveled in km
        
    Returns:
        float: The calculated RUC amount in NZD or 0 if not applicable
    """
    # Check if vehicle is eligible for RUC calculation
    if vehicle_category not in ['MAD EXPLORER', 'MAD TRACKER']:
        return 0.0
        
    # Base charge for first 1000 km
    if trip_km <= 0:
        return 0.0
    elif trip_km <= 1000:
        return 95.0
    else:
        # Calculate additional charges for distance over 1000 km
        # Math.ceil to round up for partial 100km increments
        additional_segments = math.ceil((trip_km - 1000) / 100)
        additional_charge = additional_segments * 9.0
        
        # Total charge
        return 95.0 + additional_charge

def update_vehicle_record(dropoff):
    """Update or create a vehicle record based on dropoff information"""
    try:
        # Look for existing vehicle by rego
        vehicle = get_vehicle_by_rego(dropoff.rego)
        now = datetime.now()
        
        if vehicle:
            # Update existing vehicle record
            vehicle.name = dropoff.name  # Update from latest drop-off
            
            # Only update category if it's provided in this dropoff
            if dropoff.vehicle_category:
                vehicle.category = dropoff.vehicle_category
            
            # Only update KM if it's higher than current (avoid overwriting with older data)
            if dropoff.km_dropoff and dropoff.km_dropoff > vehicle.current_km:
                vehicle.current_km = dropoff.km_dropoff
            
            # If KM pickup exists but dropoff doesn't, use pickup KM
            elif not dropoff.km_dropoff and dropoff.km_pickup and dropoff.km_pickup > vehicle.current_km:
                vehicle.current_km = dropoff.km_pickup
            
            # Update service due KM if it's provided
            if dropoff.service_due_km:
                vehicle.service_due_km = dropoff.service_due_km
            
            # Update expiry dates if they're newer
            if dropoff.rego_expiry:
                if not vehicle.rego_expiry or dropoff.rego_expiry > vehicle.rego_expiry:
                    vehicle.rego_expiry = dropoff.rego_expiry
            
            if dropoff.cof_expiry:
                if not vehicle.cof_expiry or dropoff.cof_expiry > vehicle.cof_expiry:
                    vehicle.cof_expiry = dropoff.cof_expiry
            
            # Update last dropoff date
            if dropoff.date_returned:
                vehicle.last_dropoff_date = dropoff.date_returned
            
            # Increment total dropoffs
            vehicle.total_dropoffs += 1
            
            # Add trip kilometers to total if available
            if dropoff.trip_km:
                vehicle.total_trip_km = (vehicle.total_trip_km or 0) + dropoff.trip_km
            
            # Update timestamp
            vehicle.updated_at = now
        else:
            # Create a new vehicle record
            vehicle = Vehicle(
                rego=dropoff.rego,
                name=dropoff.name,
                category=dropoff.vehicle_category,
                current_km=dropoff.km_dropoff or dropoff.km_pickup or 0,
                service_due_km=dropoff.service_due_km or 0,
                rego_expiry=dropoff.rego_expiry,
                cof_expiry=dropoff.cof_expiry,
                last_dropoff_date=dropoff.date_returned,
                total_dropoffs=1,
                total_trip_km=dropoff.trip_km or 0,
                created_at=now,
                updated_at=now
            )
            db.session.add(vehicle)
        
        db.session.commit()
        return vehicle
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating vehicle record: {str(e)}")
        return None

# Helper function to track user activity in the system
def track_user_activity(action_type, details=None, page_url=None):
    """
    Track user activity for monitoring and analytics
    
    Args:
        action_type: Type of action (page_view, form_submit, file_upload, error, etc.)
        details: Additional details about the action (JSON serializable)
        page_url: URL of the page where action occurred (defaults to current request path)
    """
    if not current_user.is_authenticated:
        return  # Don't track if no user is logged in
        
    # Get the page URL if not provided
    if page_url is None:
        page_url = request.path
        
    # Get IP address and user agent
    ip_address = request.remote_addr
    user_agent = request.user_agent.string
    
    # Determine device type based on user agent
    device_type = 'desktop'
    if request.user_agent.platform in ['android', 'iphone', 'ipad']:
        device_type = 'mobile'
    elif request.user_agent.platform == 'tablet':
        device_type = 'tablet'
        
    # Create log entry
    log_entry = SessionLog(
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        device_type=device_type,
        page_url=page_url,
        action_type=action_type,
        action_details=details or {},
        timestamp=datetime.now()
    )
    
    try:
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error tracking user activity: {str(e)}")

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect to dashboard if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password.', 'warning')
            return render_template('login.html')
            
        # Find user by username
        user = User.query.filter_by(username=username).first()
        
        # Check if user exists and password is correct
        if user and user.check_password(password):
            # Update last login time
            user.last_login = datetime.now()
            db.session.commit()
            
            # Log in the user
            login_user(user)
            
            # Log the login action
            track_user_activity('login', {'username': username})
            
            # Redirect to the requested page or dashboard
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('dashboard')
                
            flash(f'Welcome, {user.username}!', 'success')
            return redirect(next_page)
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    # Log the logout action
    track_user_activity('logout')
    
    # Log out the user
    logout_user()
    
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Add an admin panel to view session logs
@app.route('/admin/session-logs')
@login_required
def admin_session_logs():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Log the page view
    track_user_activity('page_view')
        
    # Get all logs, ordered by timestamp
    logs = SessionLog.query.order_by(SessionLog.timestamp.desc()).all()
    
    # Group logs by user
    user_logs = {}
    for log in logs:
        if log.user_id not in user_logs:
            user_logs[log.user_id] = {
                'username': log.user.username,
                'role': log.user.role,
                'logs': []
            }
        user_logs[log.user_id]['logs'].append(log)
    
    return render_template('admin_session_logs.html', user_logs=user_logs)

# Admin user management
@app.route('/admin/users')
@login_required
def admin_users():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Log the page view
    track_user_activity('page_view')
    
    # Get all users
    users = User.query.all()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@login_required
def admin_add_user():
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get form data
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    # Get permissions from form
    dashboard_access = bool(request.form.get('dashboard_access'))
    dropoff_access = bool(request.form.get('dropoff_access'))
    ta_checklist_access = bool(request.form.get('ta_checklist_access'))
    maintenance_alerts_access = bool(request.form.get('maintenance_alerts_access'))
    vehicle_management_access = bool(request.form.get('vehicle_management_access'))
    reports_access = bool(request.form.get('reports_access'))
    
    # Validate input
    if not username or not password:
        flash('Please provide both username and password.', 'warning')
        return redirect(url_for('admin_users'))
    
    # Check if username already exists
    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'danger')
        return redirect(url_for('admin_users'))
    
    try:
        # Create new user with permissions
        new_user = User(
            username=username, 
            role=role,
            dashboard_access=dashboard_access,
            dropoff_access=dropoff_access,
            ta_checklist_access=ta_checklist_access,
            maintenance_alerts_access=maintenance_alerts_access,
            vehicle_management_access=vehicle_management_access,
            reports_access=reports_access
        )
        new_user.set_password(password)
        
        # If user is admin, force all permissions to be true
        if role == 'admin':
            new_user.dashboard_access = True
            new_user.dropoff_access = True
            new_user.ta_checklist_access = True
            new_user.maintenance_alerts_access = True
            new_user.vehicle_management_access = True
            new_user.reports_access = True
        
        # Save to database
        db.session.add(new_user)
        db.session.commit()
        
        # Log the action
        track_user_activity(
            'user_create', 
            {
                'username': username, 
                'role': role,
                'permissions': {
                    'dashboard_access': dashboard_access,
                    'dropoff_access': dropoff_access,
                    'ta_checklist_access': ta_checklist_access,
                    'maintenance_alerts_access': maintenance_alerts_access,
                    'vehicle_management_access': vehicle_management_access,
                    'reports_access': reports_access
                }
            }
        )
        
        flash(f'User "{username}" has been created successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating user: {str(e)}")
        flash(f'Error creating user: {str(e)}', 'danger')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/edit', methods=['POST'])
@login_required
def admin_edit_user(user_id):
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get user to edit
    user = User.query.get_or_404(user_id)
    
    # Get form data
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    # Get permissions from form
    dashboard_access = bool(request.form.get('dashboard_access'))
    dropoff_access = bool(request.form.get('dropoff_access'))
    ta_checklist_access = bool(request.form.get('ta_checklist_access'))
    maintenance_alerts_access = bool(request.form.get('maintenance_alerts_access'))
    vehicle_management_access = bool(request.form.get('vehicle_management_access'))
    reports_access = bool(request.form.get('reports_access'))
    
    # Track changes for logging
    changes = {}
    
    try:
        # Update username if changed
        if username and username != user.username:
            # Check if new username already exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user and existing_user.id != user.id:
                flash(f'Username "{username}" already exists.', 'danger')
                return redirect(url_for('admin_users'))
            
            changes['username'] = {'old': user.username, 'new': username}
            user.username = username
        
        # Update password if provided
        if password:
            user.set_password(password)
            changes['password'] = {'changed': True}
        
        # Update role if changed
        if role and role != user.role:
            # Check if this is the last admin user
            if user.role == 'admin' and role != 'admin':
                # Count admin users
                admin_count = User.query.filter_by(role='admin').count()
                if admin_count <= 1:
                    flash('Cannot change role. There must be at least one administrator.', 'danger')
                    return redirect(url_for('admin_users'))
            
            changes['role'] = {'old': user.role, 'new': role}
            user.role = role
            
            # If changed to admin, force all permissions to true
            if role == 'admin':
                dashboard_access = True
                dropoff_access = True
                ta_checklist_access = True
                maintenance_alerts_access = True
                vehicle_management_access = True
                reports_access = True
        
        # Update permissions if changed
        permission_changes = {}
        
        if user.dashboard_access != dashboard_access:
            permission_changes['dashboard_access'] = {'old': user.dashboard_access, 'new': dashboard_access}
            user.dashboard_access = dashboard_access
            
        if user.dropoff_access != dropoff_access:
            permission_changes['dropoff_access'] = {'old': user.dropoff_access, 'new': dropoff_access}
            user.dropoff_access = dropoff_access
            
        if user.ta_checklist_access != ta_checklist_access:
            permission_changes['ta_checklist_access'] = {'old': user.ta_checklist_access, 'new': ta_checklist_access}
            user.ta_checklist_access = ta_checklist_access
            
        if user.maintenance_alerts_access != maintenance_alerts_access:
            permission_changes['maintenance_alerts_access'] = {'old': user.maintenance_alerts_access, 'new': maintenance_alerts_access}
            user.maintenance_alerts_access = maintenance_alerts_access
            
        if user.vehicle_management_access != vehicle_management_access:
            permission_changes['vehicle_management_access'] = {'old': user.vehicle_management_access, 'new': vehicle_management_access}
            user.vehicle_management_access = vehicle_management_access
            
        if user.reports_access != reports_access:
            permission_changes['reports_access'] = {'old': user.reports_access, 'new': reports_access}
            user.reports_access = reports_access
            
        if permission_changes:
            changes['permissions'] = permission_changes
        
        # Save to database
        db.session.commit()
        
        # Log the action if there were changes
        if changes:
            track_user_activity(
                'user_edit', 
                {'user_id': user_id, 'changes': changes}
            )
            
            flash(f'User "{user.username}" has been updated successfully.', 'success')
        else:
            flash('No changes were made.', 'info')
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating user: {str(e)}")
        flash(f'Error updating user: {str(e)}', 'danger')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    # Check if user is admin
    if not current_user.is_admin():
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Don't allow deleting self
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin_users'))
    
    # Get user to delete
    user = User.query.get_or_404(user_id)
    
    # Check if this is the last admin user
    if user.role == 'admin':
        # Count admin users
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash('Cannot delete the last administrator account.', 'danger')
            return redirect(url_for('admin_users'))
    
    try:
        # Store user info for logging
        username = user.username
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        # Log the action
        track_user_activity(
            'user_delete', 
            {'user_id': user_id, 'username': username}
        )
        
        flash(f'User "{username}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting user: {str(e)}")
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    return redirect(url_for('admin_users'))

# Apply login_required to all protected routes using before_request
@app.before_request
def check_login():
    # Public routes that don't require login
    public_routes = ['login', 'static']
    
    # Check if route needs authentication
    if request.endpoint and request.endpoint not in public_routes and not current_user.is_authenticated:
        return redirect(url_for('login', next=request.url))
    
    # Check permissions for authenticated users
    if current_user.is_authenticated and request.endpoint and request.endpoint not in public_routes:
        # Admin routes require admin role
        admin_routes = ['admin_users', 'admin_session_logs', 'admin_add_user', 'admin_edit_user', 'admin_delete_user']
        if request.endpoint in admin_routes and not current_user.is_admin():
            flash('You do not have permission to access that page.', 'danger')
            return redirect(url_for('dashboard'))
            
        # Map routes to permissions
        permission_map = {
            # Dashboard routes
            'dashboard': 'dashboard',
            
            # Dropoff routes
            'dropoff': 'dropoff',
            'all_dropoffs': 'dropoff',
            'pre_dropoff': 'dropoff',
            'to_be_dropped_off': 'dropoff',
            'complete_dropoff': 'dropoff',
            'dropoff_summary': 'dropoff',
            
            # TA Checklist routes (MAD Challenge)
            'mad_challenge_summary': 'ta_checklist',
            'export_mad_challenge_to_excel': 'ta_checklist',
            'export_mad_challenge_to_pdf': 'ta_checklist',
            
            # Maintenance routes
            'maintenance_alerts': 'maintenance_alerts',
            'generate_maintenance_alerts': 'maintenance_alerts',
            'mark_alert_fixed': 'maintenance_alerts',
            'mark_alert_pending': 'maintenance_alerts',
            'export_maintenance_alerts_to_excel': 'maintenance_alerts',
            'export_maintenance_alerts_to_pdf': 'maintenance_alerts',
            
            # Vehicle management routes
            'vehicles': 'vehicle_management',
            'vehicle_detail': 'vehicle_management',
            'service_calendar': 'vehicle_management',
            'priority_list': 'vehicle_management',
            'update_next_hire_date': 'vehicle_management',
            
            # Reports routes
            'export_all_dropoffs_to_excel': 'reports',
            'export_all_dropoffs_to_pdf': 'reports',
            'search': 'reports',
            'email_report': 'reports'
        }
        
        # Check if current route requires specific permission
        if request.endpoint in permission_map:
            required_permission = permission_map[request.endpoint]
            if not current_user.has_permission(required_permission):
                flash(f'You do not have permission to access that feature.', 'danger')
                return redirect(url_for('dashboard'))
        
    # Track page views for authenticated users
    if current_user.is_authenticated and request.method == 'GET' and request.endpoint != 'static':
        track_user_activity('page_view')

@app.route('/')
@login_required
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get current date
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    # Get dropoff statistics
    total_dropoffs = Dropoff.query.count()
    completed = Dropoff.query.filter_by(status='Drop Off Completed').count()
    pending = Dropoff.query.filter_by(status='To be Dropped Off').count()
    
    # Get today and tomorrow pickup counts (based on next hire date)
    todays_pickups = Dropoff.query.filter(
        Dropoff.next_hire_date == today
    ).count()
    
    tomorrows_pickups = Dropoff.query.filter(
        Dropoff.next_hire_date == tomorrow
    ).count()
    
    # Get today and tomorrow dropoff counts (based on dropoff_eta)
    todays_dropoffs = Dropoff.query.filter(
        func.date(Dropoff.dropoff_eta) == today
    ).count()
    
    tomorrows_dropoffs = Dropoff.query.filter(
        func.date(Dropoff.dropoff_eta) == tomorrow
    ).count()
    
    # Get completion ratio
    completion_ratio = f"{completed}/{pending}" if pending > 0 else f"{completed}/0"
    
    # Get vehicle fleet statistics
    total_vehicles = Vehicle.query.count()
    total_trip_km = db.session.query(func.sum(Vehicle.total_trip_km)).scalar() or 0
    
    # Get vehicle categories breakdown
    vehicle_categories = db.session.query(
        Vehicle.category, 
        func.count(Vehicle.id)
    ).filter(Vehicle.category.isnot(None)).group_by(Vehicle.category).all()
    
    # Get recent dropoffs
    recent_dropoffs = Dropoff.query.filter_by(status='Drop Off Completed').order_by(Dropoff.date_returned.desc()).limit(5).all()
    
    # Get pending dropoffs
    pending_dropoffs = Dropoff.query.filter_by(status='To be Dropped Off').order_by(Dropoff.date_returned.desc()).limit(5).all()
    
    # Get MAD challenge stats
    mad_total = Dropoff.query.filter(Dropoff.mad_challenge_status.isnot(None)).filter(Dropoff.mad_challenge_status != '').count()
    mad_completed = Dropoff.query.filter_by(mad_challenge_status='Completed').count()
    mad_posted = Dropoff.query.filter_by(mad_challenge_status='Posted').count()
    mad_not_completed = Dropoff.query.filter_by(mad_challenge_status="Didn't Complete").count()
    
    # Get maintenance alerts count
    maintenance_count = MaintenanceAlert.query.filter_by(status='Pending').count()
    
    # Get service due soon count
    vehicles_service_due_soon = 0
    if total_vehicles > 0:
        vehicles_service_due_soon = Vehicle.query.filter(
            Vehicle.service_due_km.isnot(None),
            Vehicle.current_km.isnot(None),
            Vehicle.current_km >= (Vehicle.service_due_km - 1000)
        ).count()
    
    stats = {
        'total_vehicles': total_vehicles,
        'total_dropoffs': total_dropoffs,
        'completed': completed,
        'pending': pending,
        'todays_pickups': todays_pickups,
        'tomorrows_pickups': tomorrows_pickups,
        'todays_dropoffs': todays_dropoffs,
        'tomorrows_dropoffs': tomorrows_dropoffs,
        'completion_ratio': completion_ratio,
        'total_trip_km': total_trip_km,
        'vehicles_service_due_soon': vehicles_service_due_soon
    }
    
    mad_stats = {
        'total': mad_total,
        'completed': mad_completed,
        'posted': mad_posted,
        'not_completed': mad_not_completed
    }
    
    return render_template('dashboard.html', 
                          stats=stats, 
                          mad_stats=mad_stats,
                          recent_dropoffs=recent_dropoffs,
                          pending_dropoffs=pending_dropoffs,
                          maintenance_count=maintenance_count,
                          vehicle_categories=vehicle_categories)

@app.route('/dropoff', methods=['GET', 'POST'])
@login_required
def dropoff():
    if request.method == 'POST':
        try:
            # Convert empty strings to None for integer fields
            current_rucs = request.form['current_rucs']
            current_rucs = int(current_rucs) if current_rucs else 0
            
            next_hire_length = request.form['next_hire_length']
            next_hire_length = int(next_hire_length) if next_hire_length else 0
            
            # Fuel level comes as a select value now
            fuel_level = int(request.form['fuel_level'])
            
            # AdBlue level comes as a string value now
            adblue_level = request.form['adblue_level']
            
            # Create new dropoff record
            new_dropoff = Dropoff(
                rego=request.form['rego'].strip().upper(),
                name=request.form['name'].strip(),
                insurance_status=request.form['insurance_status'],
                rego_expiry=datetime.strptime(request.form['rego_expiry'], '%Y-%m-%d').date() if request.form['rego_expiry'] else None,
                cof_expiry=datetime.strptime(request.form['cof_expiry'], '%Y-%m-%d').date() if request.form['cof_expiry'] else None,
                on_road_issues=request.form['on_road_issues'],
                current_rucs=current_rucs,
                next_hire_date=datetime.strptime(request.form['next_hire_date'], '%Y-%m-%d').date() if request.form['next_hire_date'] else None,
                next_hire_length=next_hire_length,
                windscreen_condition=request.form['windscreen_condition'],
                fuel_level=fuel_level,
                adblue_level=adblue_level,
                keys_working=request.form.get('keys_working', 'No'),
                remote_working=request.form.get('remote_working', 'No'),
                safe_emptied=request.form.get('safe_emptied', 'No'),
                damage_check=request.form['damage_check'],
                review_requested=request.form.get('review_requested', 'No'),
                customer_notes=request.form['customer_notes'],
                mad_challenge_status=request.form['mad_challenge_status'],
                date_returned=datetime.now()
            )
            
            # Save to database
            db.session.add(new_dropoff)
            db.session.commit()
            
            flash('Vehicle dropoff has been successfully recorded!', 'success')
            return redirect(url_for('mad_challenge_summary'))
        except Exception as e:
            logging.error(f"Error saving dropoff: {str(e)}")
            flash(f'Error saving dropoff: {str(e)}', 'danger')
    
    return render_template('dropoff.html')

@app.route('/mad-challenge-summary')
@login_required
def mad_challenge_summary():
    # Get MAD challenge data
    mad_challenges = Dropoff.query.filter(Dropoff.mad_challenge_status.isnot(None))\
                                 .filter(Dropoff.mad_challenge_status != '')\
                                 .order_by(Dropoff.date_returned.desc()).all()
    
    # Get overall stats
    total_dropoffs = Dropoff.query.count()
    completed_challenges = Dropoff.query.filter_by(mad_challenge_status='Completed').count()
    posted_challenges = Dropoff.query.filter_by(mad_challenge_status='Posted').count()
    not_completed = Dropoff.query.filter_by(mad_challenge_status="Didn't Complete").count()
    
    stats = {
        'total': total_dropoffs,
        'completed': completed_challenges,
        'posted': posted_challenges,
        'not_completed': not_completed
    }
    
    return render_template('mad_challenge_summary.html', results=mad_challenges, stats=stats)

@app.route('/all-dropoffs')
@login_required
def all_dropoffs():
    # Get search parameters
    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'all')
    insurance_filter = request.args.get('insurance', 'all')
    
    # Build the query
    query = Dropoff.query
    
    # Add search conditions
    if search_query:
        query = query.filter(or_(
            Dropoff.rego.ilike(f"%{search_query}%"),
            Dropoff.name.ilike(f"%{search_query}%")
        ))
    
    # Filter by status
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Filter by insurance status
    if insurance_filter != 'all':
        query = query.filter_by(insurance_status=insurance_filter)
    
    # Execute query with ordering
    dropoffs = query.order_by(Dropoff.date_returned.desc()).all()
    
    # Get filter options for dropdowns
    status_options = db.session.query(Dropoff.status).distinct().order_by(Dropoff.status).all()
    status_options = [status[0] for status in status_options]
    
    insurance_options = db.session.query(Dropoff.insurance_status).distinct()\
                                .filter(Dropoff.insurance_status.isnot(None))\
                                .order_by(Dropoff.insurance_status).all()
    insurance_options = [insurance[0] for insurance in insurance_options]
    
    return render_template('all_dropoffs.html', 
                          dropoffs=dropoffs, 
                          search_query=search_query,
                          status_filter=status_filter,
                          insurance_filter=insurance_filter,
                          status_options=status_options,
                          insurance_options=insurance_options)

@app.route('/pre-dropoff', methods=['GET', 'POST'])
@login_required
def pre_dropoff():
    if request.method == 'POST':
        try:
            # Check if no_next_hire_date is in the form (checkbox is checked)
            no_next_hire_date = 'no_next_hire_date' in request.form
            
            # Convert empty strings to None for integer fields
            current_rucs = request.form.get('current_rucs', '')
            current_rucs = int(current_rucs) if current_rucs else 0
            
            next_hire_length = request.form.get('next_hire_length', '')
            next_hire_length = int(next_hire_length) if next_hire_length else 0
            
            km_pickup = request.form.get('km_pickup', '')
            km_pickup = int(km_pickup) if km_pickup else 0
            
            service_due_km = request.form.get('service_due_km', '')
            service_due_km = int(service_due_km) if service_due_km else 0
            
            # Process next_hire_date based on checkbox
            next_hire_date = None
            if not no_next_hire_date and request.form.get('next_hire_date'):
                next_hire_date = datetime.strptime(request.form['next_hire_date'], '%Y-%m-%d').date()
            
            # Process datetime fields safely
            rego_expiry = None
            if request.form.get('rego_expiry'):
                rego_expiry = datetime.strptime(request.form['rego_expiry'], '%Y-%m-%d').date()
                
            cof_expiry = None
            if request.form.get('cof_expiry'):
                cof_expiry = datetime.strptime(request.form['cof_expiry'], '%Y-%m-%d').date()
                
            dropoff_eta = None
            if request.form.get('dropoff_eta'):
                dropoff_eta = datetime.strptime(request.form['dropoff_eta'], '%Y-%m-%dT%H:%M')
            
            # Create new pre-dropoff record
            new_dropoff = Dropoff(
                rego=request.form.get('rego', '').strip().upper(),
                name=request.form.get('name', '').strip(),
                staff_name=request.form.get('staff_name', '').strip(),
                vehicle_category=request.form.get('vehicle_category', ''),
                insurance_status=request.form.get('insurance_status', ''),
                rego_expiry=rego_expiry,
                cof_expiry=cof_expiry,
                on_road_issues=request.form.get('on_road_issues', ''),
                current_rucs=current_rucs,
                next_hire_date=next_hire_date,
                next_hire_length=next_hire_length,
                km_pickup=km_pickup,
                service_due_km=service_due_km,
                date_returned=datetime.now(),
                status='To be Dropped Off',
                dropoff_eta=dropoff_eta
            )
            
            # Save to database
            db.session.add(new_dropoff)
            db.session.commit()
            
            # Update or create vehicle record
            update_vehicle_record(new_dropoff)
            
            flash('Pre-dropoff details have been successfully recorded!', 'success')
            return redirect(url_for('to_be_dropped_off'))
        except Exception as e:
            logging.error(f"Error saving pre-dropoff details: {str(e)}")
            flash(f'Error saving pre-dropoff details: {str(e)}', 'danger')
    
    return render_template('pre_dropoff.html')

@app.route('/to-be-dropped-off')
@login_required
def to_be_dropped_off():
    dropoffs = Dropoff.query.filter_by(status='To be Dropped Off').order_by(Dropoff.date_returned.desc()).all()
    return render_template('to_be_dropped_off.html', dropoffs=dropoffs)

@app.route('/priority-list')
@login_required
def priority_list():
    """View for vehicles prioritized by next hire date"""
    # Get dropoffs with next hire date (priority list)
    dropoffs_with_next_hire = Dropoff.query.filter_by(status='To be Dropped Off')\
                           .filter(Dropoff.next_hire_date.isnot(None))\
                           .order_by(Dropoff.next_hire_date, Dropoff.dropoff_eta).all()
    
    # Get ALL vehicles without next hire date (for workshop team) - including completed dropoffs
    # First, get the latest dropoff for each vehicle to avoid duplicates
    latest_dropoffs_subquery = db.session.query(
        Dropoff.rego,
        func.max(Dropoff.date_returned).label('latest_date')
    ).group_by(Dropoff.rego).subquery()
    
    # Then, get all vehicles without a next hire date
    dropoffs_without_next_hire = Dropoff.query\
        .join(
            latest_dropoffs_subquery,
            and_(
                Dropoff.rego == latest_dropoffs_subquery.c.rego,
                Dropoff.date_returned == latest_dropoffs_subquery.c.latest_date
            )
        )\
        .filter(Dropoff.next_hire_date.is_(None))\
        .order_by(Dropoff.date_returned.desc()).all()
    
    return render_template('priority_list.html', 
                          dropoffs=dropoffs_with_next_hire,
                          dropoffs_without_next_hire=dropoffs_without_next_hire)
                          
@app.route('/update-next-hire-date/<int:dropoff_id>', methods=['POST'])
@login_required
def update_next_hire_date(dropoff_id):
    """Update next hire date for a vehicle"""
    try:
        dropoff = Dropoff.query.get_or_404(dropoff_id)
        
        # Get the next hire date from the form
        next_hire_date_str = request.form.get('next_hire_date')
        next_hire_length_str = request.form.get('next_hire_length')
        
        if next_hire_date_str:
            # Convert the date string to a Python date object
            next_hire_date = datetime.strptime(next_hire_date_str, '%Y-%m-%d').date()
            
            # Update the dropoff record
            dropoff.next_hire_date = next_hire_date
            
            # Update the next hire length if provided
            if next_hire_length_str:
                try:
                    next_hire_length = int(next_hire_length_str)
                    dropoff.next_hire_length = next_hire_length
                except ValueError:
                    pass  # Ignore if not a valid integer
            
            # Save changes to the database
            db.session.commit()
            
            # Update vehicle record if it exists
            update_vehicle_record(dropoff)
            
            flash(f'Next hire date for {dropoff.rego} updated successfully!', 'success')
        else:
            flash('Please provide a valid next hire date', 'warning')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating next hire date: {str(e)}', 'danger')
        
    # Redirect back to priority list
    return redirect(url_for('priority_list'))

@app.route('/complete-dropoff/<int:dropoff_id>', methods=['GET', 'POST'])
@login_required
def complete_dropoff(dropoff_id):
    dropoff = get_dropoff(dropoff_id)
    
    if request.method == 'POST':
        try:
            # Get form data for second part of the dropoff
            fuel_level = int(request.form['fuel_level'])
            adblue_level = request.form['adblue_level']
            
            # Get kilometer readings and calculate trip km
            km_dropoff = int(request.form['km_dropoff'])
            trip_km = max(0, km_dropoff - (dropoff.km_pickup or 0))
            
            # Process damage image if provided
            damage_image_filename = None
            if 'damage_image' in request.files:
                damage_image = request.files['damage_image']
                if damage_image.filename:
                    damage_image_filename = save_uploaded_image(damage_image)
            
            # Process additional damage images if provided
            additional_damage_images = []
            if 'additional_damage_images' in request.files:
                files = request.files.getlist('additional_damage_images')
                for file in files:
                    if file.filename:
                        additional_image_filename = save_uploaded_image(file)
                        additional_damage_images.append(additional_image_filename)
            
            # Update the dropoff record
            dropoff.windscreen_condition = request.form['windscreen_condition']
            dropoff.fuel_level = fuel_level
            dropoff.adblue_level = adblue_level
            dropoff.keys_working = request.form.get('keys_working', 'No')
            dropoff.remote_working = request.form.get('remote_working', 'No')
            dropoff.safe_emptied = request.form.get('safe_emptied', 'No')
            dropoff.damage_check = request.form['damage_check']
            dropoff.review_requested = request.form.get('review_requested', 'No')
            dropoff.customer_notes = request.form['customer_notes']
            dropoff.mad_challenge_status = request.form['mad_challenge_status']
            dropoff.status = 'Drop Off Completed'
            dropoff.date_returned = datetime.now()
            dropoff.km_dropoff = km_dropoff
            dropoff.trip_km = trip_km
            
            # Calculate RUC amount for MAD EXPLORER and MAD TRACKER vehicles
            if dropoff.vehicle_category in ['MAD EXPLORER', 'MAD TRACKER']:
                ruc_amount = calculate_ruc_amount(dropoff.vehicle_category, trip_km)
                dropoff.ruc_amount = ruc_amount
                logging.info(f"Calculated RUC amount for {dropoff.rego} ({dropoff.vehicle_category}): ${ruc_amount:.2f} NZD")
            else:
                dropoff.ruc_amount = 0.0
            
            if damage_image_filename:
                dropoff.damage_image_filename = damage_image_filename
                
            if additional_damage_images:
                dropoff.additional_damage_images = additional_damage_images
                
            dropoff.urgent_assessment = request.form.get('urgent_assessment', 'No')
            
            # Save changes
            db.session.commit()
            
            # Update or create vehicle record
            update_vehicle_record(dropoff)
            
            # Generate maintenance alerts if needed (service due KM exceeded)
            if dropoff.service_due_km and dropoff.km_dropoff and dropoff.service_due_km > 0:
                if dropoff.km_dropoff >= dropoff.service_due_km:
                    # Create a maintenance alert for service due
                    service_alert = MaintenanceAlert(
                        dropoff_id=dropoff.id,
                        rego=dropoff.rego,
                        name=dropoff.name,
                        issue_type='Service',
                        details=f"Service overdue by {dropoff.km_dropoff - dropoff.service_due_km} km",
                        status='Pending',
                        date_created=datetime.now()
                    )
                    db.session.add(service_alert)
                    db.session.commit()
            
            # Create maintenance alert for urgent assessment if marked
            if dropoff.urgent_assessment == 'Yes':
                urgent_alert = MaintenanceAlert(
                    dropoff_id=dropoff.id,
                    rego=dropoff.rego,
                    name=dropoff.name,
                    issue_type='Urgent',
                    details="Vehicle needs urgent assessment",
                    status='Pending',
                    date_created=datetime.now()
                )
                db.session.add(urgent_alert)
                db.session.commit()
            
            flash('Vehicle dropoff has been successfully completed!', 'success')
            return redirect(url_for('all_dropoffs'))
        except Exception as e:
            logging.error(f"Error completing dropoff: {str(e)}")
            flash(f'Error completing dropoff: {str(e)}', 'danger')
            return render_template('complete_dropoff.html', dropoff=dropoff, error=str(e))
    
    return render_template('complete_dropoff.html', dropoff=dropoff)

# Export routes for Excel
@app.route('/export-to-excel/mad-challenge')
def export_mad_challenge_to_excel():
    try:
        # Get MAD challenge data
        records = Dropoff.query.filter(Dropoff.mad_challenge_status.isnot(None))\
                              .filter(Dropoff.mad_challenge_status != '')\
                              .order_by(Dropoff.date_returned.desc()).all()
        
        headers = ["Registration", "Customer Name", "MAD Challenge Status", "Date Returned"]
        data = []
        
        for record in records:
            date_returned = record.date_returned.strftime("%Y-%m-%d %H:%M:%S") if record.date_returned else ''
            data.append([record.rego, record.name, record.mad_challenge_status, date_returned])
        
        # Insert header row
        data.insert(0, headers)
        
        # Return excel file
        return excel.make_response_from_array(data, "xlsx", file_name="MAD_Challenge_Summary.xlsx")
    except Exception as e:
        logging.error(f"Error exporting to Excel: {str(e)}")
        flash(f'Error exporting to Excel: {str(e)}', 'danger')
        return redirect(url_for('mad_challenge_summary'))

# Export to PDF
@app.route('/export-to-pdf/mad-challenge')
def export_mad_challenge_to_pdf():
    try:
        # Get MAD challenge data
        mad_challenges = Dropoff.query.filter(Dropoff.mad_challenge_status.isnot(None))\
                                     .filter(Dropoff.mad_challenge_status != '')\
                                     .order_by(Dropoff.date_returned.desc()).all()
        
        # Get overall stats
        total_dropoffs = Dropoff.query.count()
        completed_challenges = Dropoff.query.filter_by(mad_challenge_status='Completed').count()
        posted_challenges = Dropoff.query.filter_by(mad_challenge_status='Posted').count()
        not_completed = Dropoff.query.filter_by(mad_challenge_status="Didn't Complete").count()
        
        stats = {
            'total': total_dropoffs,
            'completed': completed_challenges,
            'posted': posted_challenges,
            'not_completed': not_completed
        }
        
        # Generate HTML content for PDF
        html = render_template('pdf_mad_challenge.html', results=mad_challenges, stats=stats, now=datetime.now())
        
        # Convert HTML to PDF
        pdf = pdfkit.from_string(html, False)
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=MAD_Challenge_Summary.pdf'
        
        return response
    except Exception as e:
        logging.error(f"Error exporting to PDF: {str(e)}")
        flash(f'Error exporting to PDF: {str(e)}', 'danger')
        return redirect(url_for('mad_challenge_summary'))

# Export all dropoffs to Excel
@app.route('/export-to-excel/all-dropoffs')
def export_all_dropoffs_to_excel():
    try:
        dropoffs = get_all_dropoffs()
        
        headers = ["Registration", "Customer Name", "Insurance Status", "KM Pickup", "KM Dropoff", "Trip KM", "Windscreen", "Fuel Level", "AdBlue Level", "Damage", "MAD Challenge", "RUCs Owed", "Date Returned"]
        data = []
        
        for d in dropoffs:
            date_returned = d.date_returned.strftime("%Y-%m-%d %H:%M:%S") if d.date_returned else ''
            fuel_level_str = f"{d.fuel_level}%" if d.fuel_level is not None else "N/A"
            
            # Format RUC amount if available
            ruc_amount_formatted = "N/A"
            if hasattr(d, 'ruc_amount') and d.ruc_amount and d.ruc_amount > 0:
                ruc_amount_formatted = format_currency(d.ruc_amount)
            
            data.append([
                d.rego, 
                d.name, 
                d.insurance_status, 
                d.km_pickup or 0,
                d.km_dropoff or 0,
                d.trip_km or 0,
                d.windscreen_condition or 'N/A', 
                fuel_level_str,
                d.adblue_level or 'N/A',
                d.damage_check or 'N/A', 
                d.mad_challenge_status or 'N/A',
                ruc_amount_formatted,
                date_returned
            ])
        
        # Insert header row
        data.insert(0, headers)
        
        # Return excel file
        return excel.make_response_from_array(data, "xlsx", file_name="All_Vehicle_Dropoffs.xlsx")
    except Exception as e:
        logging.error(f"Error exporting to Excel: {str(e)}")
        flash(f'Error exporting to Excel: {str(e)}', 'danger')
        return redirect(url_for('all_dropoffs'))

# Export all dropoffs to PDF
@app.route('/export-to-pdf/all-dropoffs')
def export_all_dropoffs_to_pdf():
    try:
        dropoffs = get_all_dropoffs()
        
        # Generate HTML content for PDF
        html = render_template('pdf_all_dropoffs.html', dropoffs=dropoffs, now=datetime.now())
        
        # Convert HTML to PDF
        pdf = pdfkit.from_string(html, False)
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=All_Vehicle_Dropoffs.pdf'
        
        return response
    except Exception as e:
        logging.error(f"Error exporting to PDF: {str(e)}")
        flash(f'Error exporting to PDF: {str(e)}', 'danger')
        return redirect(url_for('all_dropoffs'))

# Maintenance alerts routes
@app.route('/maintenance-alerts')
def maintenance_alerts():
    alerts = get_maintenance_alerts()
    return render_template('maintenance_alerts.html', alerts=alerts)

# Generate new maintenance alerts
@app.route('/generate-maintenance-alerts')
def generate_maintenance_alerts():
    # First, clear any existing pending alerts
    MaintenanceAlert.query.filter_by(status='Pending').delete()
    db.session.commit()
    
    # Get all vehicles
    vehicles = Dropoff.query.all()
    
    alerts_added = 0
    now = datetime.now()
    
    for vehicle in vehicles:
        # Check if vehicle needs urgent assessment
        if vehicle.urgent_assessment == 'Yes':
            new_alert = MaintenanceAlert(
                dropoff_id=vehicle.id,
                rego=vehicle.rego,
                name=vehicle.name,
                issue_type='Urgent',
                details="Vehicle needs urgent assessment",
                status='Pending',
                date_created=now
            )
            db.session.add(new_alert)
            alerts_added += 1
            
        # Check service due KM vs current KM
        if vehicle.service_due_km and vehicle.km_dropoff and vehicle.service_due_km > 0:
            service_due = vehicle.service_due_km
            current_km = vehicle.km_dropoff or 0
            
            if current_km >= service_due:
                new_alert = MaintenanceAlert(
                    dropoff_id=vehicle.id,
                    rego=vehicle.rego,
                    name=vehicle.name,
                    issue_type='Service',
                    details=f"Service overdue by {current_km - service_due} km",
                    status='Pending',
                    date_created=now
                )
                db.session.add(new_alert)
                alerts_added += 1
            elif current_km >= (service_due - 1000):  # Approaching service
                new_alert = MaintenanceAlert(
                    dropoff_id=vehicle.id,
                    rego=vehicle.rego,
                    name=vehicle.name,
                    issue_type='Service',
                    details=f"Service due soon (in {service_due - current_km} km)",
                    status='Pending',
                    date_created=now
                )
                db.session.add(new_alert)
                alerts_added += 1
                
        # Check fuel level - alert if it's not at 100%
        if vehicle.fuel_level is not None and vehicle.fuel_level < 100:
            new_alert = MaintenanceAlert(
                dropoff_id=vehicle.id,
                rego=vehicle.rego,
                name=vehicle.name,
                issue_type='Fuel',
                details=f"Fuel level is not full ({vehicle.fuel_level}%)",
                status='Pending',
                date_created=now
            )
            db.session.add(new_alert)
            alerts_added += 1
        
        # Check AdBlue level - only alert if it needs top up, not if it's "Not applicable"
        if vehicle.adblue_level is not None and vehicle.adblue_level == "Need top up":
            new_alert = MaintenanceAlert(
                dropoff_id=vehicle.id,
                rego=vehicle.rego,
                name=vehicle.name,
                issue_type='AdBlue',
                details="AdBlue needs top up",
                status='Pending',
                date_created=now
            )
            db.session.add(new_alert)
            alerts_added += 1
        
        # Check rego expiry (if within 30 days)
        if vehicle.rego_expiry:
            days_until_expiry = (vehicle.rego_expiry - now.date()).days
            if 0 <= days_until_expiry <= 30:
                new_alert = MaintenanceAlert(
                    dropoff_id=vehicle.id,
                    rego=vehicle.rego,
                    name=vehicle.name,
                    issue_type='Rego',
                    details=f"Registration expires in {days_until_expiry} days",
                    status='Pending',
                    date_created=now
                )
                db.session.add(new_alert)
                alerts_added += 1
        
        # Check COF expiry (if within 30 days)
        if vehicle.cof_expiry:
            days_until_expiry = (vehicle.cof_expiry - now.date()).days
            if 0 <= days_until_expiry <= 30:
                new_alert = MaintenanceAlert(
                    dropoff_id=vehicle.id,
                    rego=vehicle.rego,
                    name=vehicle.name,
                    issue_type='COF',
                    details=f"COF expires in {days_until_expiry} days",
                    status='Pending',
                    date_created=now
                )
                db.session.add(new_alert)
                alerts_added += 1
        
        # Check RUCs (if current_rucs is less than or close to km_pickup or km_dropoff)
        if vehicle.current_rucs and (vehicle.km_pickup or vehicle.km_dropoff):
            current_km = max(vehicle.km_pickup or 0, vehicle.km_dropoff or 0)
            rucs = vehicle.current_rucs
            remaining_km = rucs - current_km
            
            if remaining_km <= 0:
                new_alert = MaintenanceAlert(
                    dropoff_id=vehicle.id,
                    rego=vehicle.rego,
                    name=vehicle.name,
                    issue_type='RUCs',
                    details=f"RUCs exceeded by {abs(remaining_km)} km",
                    status='Pending',
                    date_created=now
                )
                db.session.add(new_alert)
                alerts_added += 1
            elif remaining_km < 2000:
                new_alert = MaintenanceAlert(
                    dropoff_id=vehicle.id,
                    rego=vehicle.rego,
                    name=vehicle.name,
                    issue_type='RUCs',
                    details=f"RUCs low, only {remaining_km} km remaining",
                    status='Pending',
                    date_created=now
                )
                db.session.add(new_alert)
                alerts_added += 1
        
        # Check windscreen condition
        if vehicle.windscreen_condition in ['Stonechips', 'Cracked', 'Unsure']:
            new_alert = MaintenanceAlert(
                dropoff_id=vehicle.id,
                rego=vehicle.rego,
                name=vehicle.name,
                issue_type='Windscreen',
                details=f"Windscreen condition: {vehicle.windscreen_condition}",
                status='Pending',
                date_created=now
            )
            db.session.add(new_alert)
            alerts_added += 1
    
    db.session.commit()
    
    flash(f'Generated {alerts_added} maintenance alerts.', 'success')
    return redirect(url_for('maintenance_alerts'))

# Mark alert as fixed
@app.route('/mark-alert-fixed/<int:alert_id>')
def mark_alert_fixed(alert_id):
    alert = MaintenanceAlert.query.get_or_404(alert_id)
    alert.status = 'Fixed'
    alert.date_fixed = datetime.now()
    db.session.commit()
    
    flash('Alert marked as fixed.', 'success')
    return redirect(url_for('maintenance_alerts'))

# Mark alert as pending
@app.route('/mark-alert-pending/<int:alert_id>')
def mark_alert_pending(alert_id):
    alert = MaintenanceAlert.query.get_or_404(alert_id)
    alert.status = 'Pending'
    alert.date_fixed = None
    db.session.commit()
    
    flash('Alert marked as pending.', 'success')
    return redirect(url_for('maintenance_alerts'))

# Export maintenance alerts to Excel
@app.route('/export-to-excel/maintenance-alerts')
def export_maintenance_alerts_to_excel():
    try:
        alerts = get_maintenance_alerts()
        
        if not alerts:
            flash('No maintenance alerts to export', 'warning')
            return redirect(url_for('maintenance_alerts'))
            
        # Create data for Excel
        headers = ["Registration", "Customer", "Issue Type", "Details", "Status", "Date Created"]
        data = []
        
        for alert in alerts:
            date_created = alert.date_created.strftime("%Y-%m-%d %H:%M:%S") if alert.date_created else ''
            data.append([
                alert.rego,
                alert.name,
                alert.issue_type,
                alert.details,
                alert.status,
                date_created
            ])
        
        # Insert header row
        data.insert(0, headers)
        
        # Return Excel file
        return excel.make_response_from_array(data, "xlsx", file_name="Vehicle_Maintenance_Alerts.xlsx")
    except Exception as e:
        logging.error(f"Error exporting to Excel: {str(e)}")
        flash(f'Error exporting data: {str(e)}', 'danger')
        return redirect(url_for('maintenance_alerts'))

# Export maintenance alerts to PDF
@app.route('/export-to-pdf/maintenance-alerts')
def export_maintenance_alerts_to_pdf():
    try:
        alerts = get_maintenance_alerts()
        
        # Count the pending and fixed alerts
        pending_count = MaintenanceAlert.query.filter_by(status='Pending').count()
        fixed_count = MaintenanceAlert.query.filter_by(status='Fixed').count()
        
        # Generate HTML content
        html = render_template('pdf_maintenance_alerts.html', 
                              alerts=alerts, 
                              pending_count=pending_count,
                              fixed_count=fixed_count,
                              now=datetime.now())
        
        # Convert HTML to PDF
        pdf = pdfkit.from_string(html, False)
        
        # Create response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=Vehicle_Maintenance_Alerts.pdf'
        
        return response
    except Exception as e:
        logging.error(f"Error exporting to PDF: {str(e)}")
        flash(f'Error exporting to PDF: {str(e)}', 'danger')
        return redirect(url_for('maintenance_alerts'))

# API endpoint for dropoff summary
@app.route('/dropoff-summary/<int:dropoff_id>')
def dropoff_summary(dropoff_id):
    """API endpoint to get dropoff summary data in JSON format"""
    try:
        dropoff = get_dropoff(dropoff_id)
        if not dropoff:
            return jsonify({"error": "Dropoff not found"}), 404
            
        # Format dates using our British English format filter
        if dropoff.rego_expiry:
            # Check if it's today or tomorrow
            today = date.today()
            tomorrow = today + timedelta(days=1)
            
            if dropoff.rego_expiry == today:
                dropoff.rego_expiry_formatted = "Today"
            elif dropoff.rego_expiry == tomorrow:
                dropoff.rego_expiry_formatted = "Tomorrow"
            else:
                dropoff.rego_expiry_formatted = dropoff.rego_expiry.strftime('%d/%m/%Y')
        else:
            dropoff.rego_expiry_formatted = None
                
        if dropoff.cof_expiry:
            # Check if it's today or tomorrow
            today = date.today()
            tomorrow = today + timedelta(days=1)
            
            if dropoff.cof_expiry == today:
                dropoff.cof_expiry_formatted = "Today"
            elif dropoff.cof_expiry == tomorrow:
                dropoff.cof_expiry_formatted = "Tomorrow"
            else:
                dropoff.cof_expiry_formatted = dropoff.cof_expiry.strftime('%d/%m/%Y')
        else:
            dropoff.cof_expiry_formatted = None
                
        if dropoff.next_hire_date:
            # Check if it's today or tomorrow
            today = date.today()
            tomorrow = today + timedelta(days=1)
            
            if dropoff.next_hire_date == today:
                dropoff.next_hire_date_formatted = "Today"
            elif dropoff.next_hire_date == tomorrow:
                dropoff.next_hire_date_formatted = "Tomorrow"
            else:
                dropoff.next_hire_date_formatted = dropoff.next_hire_date.strftime('%d/%m/%Y')
        else:
            dropoff.next_hire_date_formatted = None
                
        if dropoff.date_returned:
            # For datetime objects, format with both date and time
            date_part = ""
            
            # Check if it's today or tomorrow
            today = date.today()
            tomorrow = today + timedelta(days=1)
            
            if dropoff.date_returned.date() == today:
                date_part = "Today"
            elif dropoff.date_returned.date() == tomorrow:
                date_part = "Tomorrow"
            else:
                date_part = dropoff.date_returned.strftime('%d/%m/%Y')
                
            # Format time in 12-hour clock
            time_part = dropoff.date_returned.strftime('%I:%M %p').lstrip('0')
            
            # Combine date and time
            dropoff.date_returned_formatted = f"{date_part} - {time_part}"
        else:
            dropoff.date_returned_formatted = None
                
        # Format RUC amount and add additional information for diesel vehicles
        ruc_info = None
        if hasattr(dropoff, 'ruc_amount') and dropoff.ruc_amount and dropoff.ruc_amount > 0:
            if dropoff.vehicle_category in ['MAD EXPLORER', 'MAD TRACKER']:
                ruc_info = {
                    'amount': dropoff.ruc_amount,
                    'formatted': format_currency(dropoff.ruc_amount),
                    'trip_km': dropoff.trip_km,
                    'is_diesel': True
                }
        
        # Get any maintenance alerts for this vehicle
        maintenance_alerts = MaintenanceAlert.query.filter_by(dropoff_id=dropoff_id).order_by(MaintenanceAlert.date_created.desc()).all()
        
        # Convert to dictionaries for JSON serialization
        dropoff_dict = dropoff.to_dict()
        dropoff_dict['rego_expiry_formatted'] = dropoff.rego_expiry_formatted
        dropoff_dict['cof_expiry_formatted'] = dropoff.cof_expiry_formatted
        dropoff_dict['next_hire_date_formatted'] = dropoff.next_hire_date_formatted
        dropoff_dict['date_returned_formatted'] = dropoff.date_returned_formatted
        dropoff_dict['ruc_info'] = ruc_info
        
        maintenance_alerts_list = []
        for alert in maintenance_alerts:
            alert_dict = {
                'id': alert.id,
                'issue_type': alert.issue_type,
                'details': alert.details,
                'status': alert.status,
                'date_created': alert.date_created.strftime('%d/%m/%Y - %I:%M %p').replace(' 0', ' ').replace('AM', 'am').replace('PM', 'pm') if alert.date_created else None
            }
            maintenance_alerts_list.append(alert_dict)
        
        return jsonify({
            "dropoff": dropoff_dict,
            "maintenance_alerts": maintenance_alerts_list
        })
        
    except Exception as e:
        logging.error(f"Error retrieving dropoff summary: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
# Search route
@app.route('/search')
def search():
    # Get search parameters
    search_query = request.args.get('q', '').strip()
    
    if not search_query:
        return render_template('search.html', results=None, query=None)
    
    # Search for vehicles by rego or name
    vehicles = Vehicle.query.filter(
        or_(
            Vehicle.rego.ilike(f"%{search_query}%"),
            Vehicle.name.ilike(f"%{search_query}%")
        )
    ).all()
    
    # Search for dropoffs
    dropoffs = Dropoff.query.filter(
        or_(
            Dropoff.rego.ilike(f"%{search_query}%"),
            Dropoff.name.ilike(f"%{search_query}%")
        )
    ).order_by(Dropoff.date_returned.desc()).all()
    
    # Search for maintenance alerts
    alerts = MaintenanceAlert.query.filter(
        or_(
            MaintenanceAlert.rego.ilike(f"%{search_query}%"),
            MaintenanceAlert.name.ilike(f"%{search_query}%")
        )
    ).order_by(MaintenanceAlert.date_created.desc()).all()
    
    return render_template('search.html', 
                           vehicles=vehicles,
                           results=dropoffs, 
                           alerts=alerts,
                           query=search_query)

# Email report routes
@app.route('/email-report')
def email_report():
    return render_template('email_report.html')

# Vehicle Management routes
@app.route('/vehicles')
def vehicles():
    """View all vehicles in the system"""
    # Get search parameters
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', 'all')
    
    # Build the query
    query = Vehicle.query
    
    # Add search conditions
    if search_query:
        query = query.filter(or_(
            Vehicle.rego.ilike(f"%{search_query}%"),
            Vehicle.name.ilike(f"%{search_query}%")
        ))
    
    # Filter by category
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    # Execute query with ordering
    vehicles = query.order_by(Vehicle.rego).all()
    
    # Get filter options for dropdowns
    category_options = db.session.query(Vehicle.category).distinct().filter(Vehicle.category.isnot(None)).order_by(Vehicle.category).all()
    category_options = [category[0] for category in category_options if category[0]]
    
    # Get current date/time for template calculations
    current_date = datetime.now().date()
    
    return render_template('vehicles.html', 
                          vehicles=vehicles, 
                          search_query=search_query,
                          category_filter=category_filter,
                          category_options=category_options,
                          current_date=current_date)

@app.route('/vehicle/<string:rego>')
def vehicle_detail(rego):
    """View detailed vehicle history"""
    vehicle = get_vehicle_by_rego(rego)
    
    if not vehicle:
        flash('Vehicle not found', 'danger')
        return redirect(url_for('vehicles'))
    
    # Get all dropoffs for this vehicle
    dropoffs = Dropoff.query.filter_by(rego=rego).order_by(Dropoff.date_returned.desc()).all()
    
    # Get maintenance history
    maintenance = MaintenanceAlert.query.filter_by(rego=rego).order_by(MaintenanceAlert.date_created.desc()).all()
    
    # Get current date for template calculations
    current_date = datetime.now().date()
    
    return render_template('vehicle_detail.html', 
                          vehicle=vehicle,
                          dropoffs=dropoffs,
                          maintenance=maintenance,
                          current_date=current_date)

@app.route('/service-calendar')
def service_calendar():
    """View for the service calendar showing upcoming service dates and next hire dates"""
    # Get all vehicles
    vehicles = get_all_vehicles()
    
    # Get all pending dropoffs
    pending_dropoffs = Dropoff.query.filter_by(status='To be Dropped Off').all()
    
    # Get all maintenance alerts
    alerts = MaintenanceAlert.query.filter_by(status='Pending').all()
    
    # Prepare calendar events
    calendar_events = []
    
    # Add next hire dates
    for dropoff in pending_dropoffs:
        if dropoff.next_hire_date:
            # Event for next hire date
            hire_event = {
                'id': f'hire_{dropoff.id}',
                'title': f'{dropoff.rego} - Next Hire',
                'start': dropoff.next_hire_date.strftime('%Y-%m-%d'),  # Keep ISO format for calendar
                'color': '#28a745',  # Green
                'url': url_for('complete_dropoff', dropoff_id=dropoff.id),
                'description': f'Vehicle: {dropoff.rego}<br>Customer: {dropoff.name}<br>Hire Length: {dropoff.next_hire_length or "N/A"} days<br>Date: {format_date(dropoff.next_hire_date)}'
            }
            calendar_events.append(hire_event)
        
        # Event for expected dropoff
        if dropoff.dropoff_eta:
            dropoff_event = {
                'id': f'dropoff_{dropoff.id}',
                'title': f'{dropoff.rego} - Dropoff',
                'start': dropoff.dropoff_eta.strftime('%Y-%m-%d %H:%M:%S'),
                'color': '#007bff',  # Blue
                'url': url_for('complete_dropoff', dropoff_id=dropoff.id),
                'description': f'Vehicle: {dropoff.rego}<br>Customer: {dropoff.name}<br>Status: Pending Dropoff<br>Expected: {format_datetime(dropoff.dropoff_eta)}'
            }
            calendar_events.append(dropoff_event)
    
    # Add service due dates
    for vehicle in vehicles:
        if vehicle.service_due_km and vehicle.current_km:
            # Calculate estimated date for service based on current KM
            # Rough estimate: If less than 1000 km to service, mark it for attention in the next month
            km_to_service = vehicle.service_due_km - vehicle.current_km
            if km_to_service < 1000:
                # We don't have an exact date, so create an event in the current month
                today = datetime.now()
                service_date = today.replace(day=min(today.day + 15, 28))  # Approximately 2 weeks from now
                
                service_event = {
                    'id': f'service_{vehicle.id}',
                    'title': f'{vehicle.rego} - Service Due',
                    'start': service_date.strftime('%Y-%m-%d'),
                    'color': '#dc3545',  # Red
                    'url': url_for('vehicle_detail', rego=vehicle.rego),
                    'description': f'Vehicle: {vehicle.rego}<br>Current KM: {vehicle.current_km}<br>Service Due: {vehicle.service_due_km}<br>KM Remaining: {km_to_service}<br>Estimated: {format_date(service_date)}'
                }
                calendar_events.append(service_event)
    
    # Add registration/COF expiry dates
    for vehicle in vehicles:
        if vehicle.rego_expiry:
            rego_event = {
                'id': f'rego_{vehicle.id}',
                'title': f'{vehicle.rego} - Rego Expiry',
                'start': vehicle.rego_expiry.strftime('%Y-%m-%d'),
                'color': '#ffc107',  # Yellow
                'url': url_for('vehicle_detail', rego=vehicle.rego),
                'description': f'Vehicle: {vehicle.rego}<br>Registration expires on: {format_date(vehicle.rego_expiry)}'
            }
            calendar_events.append(rego_event)
        
        if vehicle.cof_expiry:
            cof_event = {
                'id': f'cof_{vehicle.id}',
                'title': f'{vehicle.rego} - COF Expiry',
                'start': vehicle.cof_expiry.strftime('%Y-%m-%d'),
                'color': '#fd7e14',  # Orange
                'url': url_for('vehicle_detail', rego=vehicle.rego),
                'description': f'Vehicle: {vehicle.rego}<br>Certificate of Fitness expires on: {format_date(vehicle.cof_expiry)}'
            }
            calendar_events.append(cof_event)
    
    # Add maintenance alerts
    for alert in alerts:
        alert_event = {
            'id': f'alert_{alert.id}',
            'title': f'{alert.rego} - {alert.issue_type}',
            'start': alert.date_created.strftime('%Y-%m-%d'),
            'color': '#dc3545',  # Red
            'url': url_for('maintenance_alerts'),
            'description': f'Vehicle: {alert.rego}<br>Issue: {alert.issue_type}<br>Details: {alert.details}<br>Created: {format_date(alert.date_created)}'
        }
        calendar_events.append(alert_event)
    
    # Pass events as JSON to template
    calendar_events_json = json.dumps(calendar_events)
    
    return render_template('service_calendar.html', 
                          calendar_events=calendar_events_json,
                          vehicles=vehicles,
                          pending_dropoffs=pending_dropoffs,
                          maintenance_alerts=alerts)

# Initialize the database - using with block instead of before_first_request
with app.app_context():
    db.create_all()
    logging.debug("PostgreSQL database initialized")

if __name__ == '__main__':
    # Create the database tables
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5001, debug=True)