from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSON
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# Define base model class
class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy with the Base model class
db = SQLAlchemy(model_class=Base)

# Define models
class Dropoff(db.Model):
    __tablename__ = 'dropoffs'
    
    id = db.Column(db.Integer, primary_key=True)
    rego = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    staff_name = db.Column(db.String(100))
    insurance_status = db.Column(db.String(50))
    rego_expiry = db.Column(db.Date)
    cof_expiry = db.Column(db.Date)
    on_road_issues = db.Column(db.Text)
    current_rucs = db.Column(db.Integer, default=0)
    next_hire_date = db.Column(db.Date)
    next_hire_length = db.Column(db.Integer, default=0)
    km_pickup = db.Column(db.Integer, default=0)
    km_dropoff = db.Column(db.Integer, default=0)
    trip_km = db.Column(db.Integer, default=0)
    service_due_km = db.Column(db.Integer, default=0)
    windscreen_condition = db.Column(db.String(50))
    fuel_level = db.Column(db.Integer, default=0)
    adblue_level = db.Column(db.String(50), default='Not applicable')
    keys_working = db.Column(db.String(5), default='No')
    remote_working = db.Column(db.String(5), default='No')
    safe_emptied = db.Column(db.String(5), default='No')
    damage_check = db.Column(db.String(50))
    damage_areas = db.Column(db.Text)
    review_requested = db.Column(db.String(5), default='No')
    customer_notes = db.Column(db.Text)
    mad_challenge_status = db.Column(db.String(50))
    date_returned = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(50), default='To be Dropped Off')
    damage_image_filename = db.Column(db.String(255))
    additional_damage_images = db.Column(JSON)
    urgent_assessment = db.Column(db.String(5), default='No')
    dropoff_eta = db.Column(db.DateTime)
    vehicle_category = db.Column(db.String(50))
    ruc_amount = db.Column(db.Float, default=0.0)  # Store calculated RUC amount in NZD
    
    # Create relationship with maintenance alerts
    maintenance_alerts = db.relationship('MaintenanceAlert', backref='vehicle', lazy=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'rego': self.rego,
            'name': self.name,
            'staff_name': self.staff_name,
            'insurance_status': self.insurance_status,
            'rego_expiry': self.rego_expiry.strftime('%Y-%m-%d') if self.rego_expiry else None,
            'cof_expiry': self.cof_expiry.strftime('%Y-%m-%d') if self.cof_expiry else None,
            'on_road_issues': self.on_road_issues,
            'current_rucs': self.current_rucs,
            'next_hire_date': self.next_hire_date.strftime('%Y-%m-%d') if self.next_hire_date else None,
            'next_hire_length': self.next_hire_length,
            'km_pickup': self.km_pickup,
            'km_dropoff': self.km_dropoff,
            'trip_km': self.trip_km,
            'service_due_km': self.service_due_km,
            'windscreen_condition': self.windscreen_condition,
            'fuel_level': self.fuel_level,
            'adblue_level': self.adblue_level,
            'keys_working': self.keys_working,
            'remote_working': self.remote_working,
            'safe_emptied': self.safe_emptied,
            'damage_check': self.damage_check,
            'damage_areas': self.damage_areas,
            'review_requested': self.review_requested,
            'customer_notes': self.customer_notes,
            'mad_challenge_status': self.mad_challenge_status,
            'date_returned': self.date_returned.strftime('%Y-%m-%d %H:%M:%S') if self.date_returned else None,
            'status': self.status,
            'damage_image_filename': self.damage_image_filename,
            'additional_damage_images': self.additional_damage_images,
            'urgent_assessment': self.urgent_assessment,
            'dropoff_eta': self.dropoff_eta.strftime('%Y-%m-%d %H:%M:%S') if self.dropoff_eta else None,
            'vehicle_category': self.vehicle_category,
            'ruc_amount': self.ruc_amount
        }


class MaintenanceAlert(db.Model):
    __tablename__ = 'maintenance_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    dropoff_id = db.Column(db.Integer, db.ForeignKey('dropoffs.id'))
    rego = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    issue_type = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    date_created = db.Column(db.DateTime, default=datetime.now)
    date_fixed = db.Column(db.DateTime)
    
class Vehicle(db.Model):
    """Vehicle model for tracking complete vehicle history."""
    __tablename__ = 'vehicles'

    id = db.Column(db.Integer, primary_key=True)
    rego = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(100))
    category = db.Column(db.String(50))
    current_km = db.Column(db.Integer, default=0)
    service_due_km = db.Column(db.Integer, default=0)
    rego_expiry = db.Column(db.Date)
    cof_expiry = db.Column(db.Date)
    last_dropoff_date = db.Column(db.DateTime)
    total_dropoffs = db.Column(db.Integer, default=0)
    total_trip_km = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    dropoffs = db.relationship('Dropoff', backref='vehicle_info', lazy=True,
                            primaryjoin="Vehicle.rego == foreign(Dropoff.rego)")
    maintenance_alerts = db.relationship('MaintenanceAlert', backref='vehicle_info', lazy=True,
                                      primaryjoin="Vehicle.rego == foreign(MaintenanceAlert.rego)")

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'rego': self.rego,
            'name': self.name,
            'category': self.category,
            'current_km': self.current_km,
            'service_due_km': self.service_due_km,
            'rego_expiry': self.rego_expiry.strftime('%Y-%m-%d') if self.rego_expiry else None,
            'cof_expiry': self.cof_expiry.strftime('%Y-%m-%d') if self.cof_expiry else None,
            'last_dropoff_date': self.last_dropoff_date.strftime('%Y-%m-%d %H:%M:%S') if self.last_dropoff_date else None,
            'total_dropoffs': self.total_dropoffs,
            'total_trip_km': self.total_trip_km,
            'notes': self.notes,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }


class SentEmailReport(db.Model):
    __tablename__ = 'sent_email_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    recipient_email = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    report_type = db.Column(db.String(50), nullable=False)
    additional_message = db.Column(db.Text)
    include_pdf = db.Column(db.Boolean, default=False)
    date_sent = db.Column(db.DateTime, default=datetime.now)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'recipient_email': self.recipient_email,
            'subject': self.subject,
            'report_type': self.report_type,
            'additional_message': self.additional_message,
            'include_pdf': self.include_pdf,
            'date_sent': self.date_sent.strftime('%Y-%m-%d %H:%M:%S') if self.date_sent else None
        }


class User(UserMixin, db.Model):
    """User model for authentication and session tracking"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='staff')  # 'staff' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)
    
    # Granular permission fields
    dashboard_access = db.Column(db.Boolean, default=True)
    dropoff_access = db.Column(db.Boolean, default=True)
    ta_checklist_access = db.Column(db.Boolean, default=True)
    maintenance_alerts_access = db.Column(db.Boolean, default=True)
    vehicle_management_access = db.Column(db.Boolean, default=True)
    reports_access = db.Column(db.Boolean, default=True)
    
    # Relationships
    session_logs = db.relationship('SessionLog', backref='user', lazy=True)
    
    def set_password(self, password):
        """Set the password for the user"""
        # For now, using plain text as requested
        # Later will implement: self.password = generate_password_hash(password)
        self.password = password
    
    def check_password(self, password):
        """Check if the password is correct"""
        # For now, direct comparison as requested
        # Later will implement: return check_password_hash(self.password, password)
        return self.password == password
    
    def is_admin(self):
        """Check if the user is an admin"""
        return self.role == 'admin'
    
    def has_permission(self, permission):
        """Check if the user has a specific permission"""
        if self.is_admin():
            return True  # Admins have all permissions
            
        if permission == 'dashboard':
            return self.dashboard_access
        elif permission == 'dropoff':
            return self.dropoff_access
        elif permission == 'ta_checklist':
            return self.ta_checklist_access
        elif permission == 'maintenance_alerts':
            return self.maintenance_alerts_access
        elif permission == 'vehicle_management':
            return self.vehicle_management_access
        elif permission == 'reports':
            return self.reports_access
        else:
            return False
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'dashboard_access': self.dashboard_access,
            'dropoff_access': self.dropoff_access,
            'ta_checklist_access': self.ta_checklist_access,
            'maintenance_alerts_access': self.maintenance_alerts_access,
            'vehicle_management_access': self.vehicle_management_access,
            'reports_access': self.reports_access,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else None
        }


class SessionLog(db.Model):
    """Session tracking for user activity"""
    __tablename__ = 'session_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))
    device_type = db.Column(db.String(20))  # 'mobile', 'tablet', 'desktop'
    page_url = db.Column(db.String(255))
    action_type = db.Column(db.String(50))  # 'page_view', 'form_submit', 'file_upload', 'error', etc.
    action_details = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'device_type': self.device_type,
            'page_url': self.page_url,
            'action_type': self.action_type,
            'action_details': self.action_details,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None
        }