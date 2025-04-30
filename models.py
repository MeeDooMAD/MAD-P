from datetime import datetime
from main import db
from sqlalchemy.dialects.postgresql import JSON

class Dropoff(db.Model):
    __tablename__ = 'dropoffs'
    
    id = db.Column(db.Integer, primary_key=True)
    rego = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
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
    adblue_level = db.Column(db.Integer, default=0)
    keys_working = db.Column(db.String(5), default='No')
    remote_working = db.Column(db.String(5), default='No')
    safe_emptied = db.Column(db.String(5), default='No')
    damage_check = db.Column(db.String(50))
    review_requested = db.Column(db.String(5), default='No')
    customer_notes = db.Column(db.Text)
    mad_challenge_status = db.Column(db.String(50))
    date_returned = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(50), default='To be Dropped Off')
    damage_image_filename = db.Column(db.String(255))
    additional_damage_images = db.Column(JSON)
    urgent_assessment = db.Column(db.String(5), default='No')
    dropoff_eta = db.Column(db.DateTime)
    
    # Create relationship with maintenance alerts
    maintenance_alerts = db.relationship('MaintenanceAlert', backref='vehicle', lazy=True)
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            'id': self.id,
            'rego': self.rego,
            'name': self.name,
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
            'review_requested': self.review_requested,
            'customer_notes': self.customer_notes,
            'mad_challenge_status': self.mad_challenge_status,
            'date_returned': self.date_returned.strftime('%Y-%m-%d %H:%M:%S') if self.date_returned else None,
            'status': self.status,
            'damage_image_filename': self.damage_image_filename,
            'additional_damage_images': self.additional_damage_images,
            'urgent_assessment': self.urgent_assessment,
            'dropoff_eta': self.dropoff_eta.strftime('%Y-%m-%d %H:%M:%S') if self.dropoff_eta else None
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
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            'id': self.id,
            'dropoff_id': self.dropoff_id,
            'rego': self.rego,
            'name': self.name,
            'issue_type': self.issue_type,
            'details': self.details,
            'status': self.status,
            'date_created': self.date_created.strftime('%Y-%m-%d %H:%M:%S') if self.date_created else None,
            'date_fixed': self.date_fixed.strftime('%Y-%m-%d %H:%M:%S') if self.date_fixed else None
        }