# parking_app/models/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize SQLAlchemy (this will be initialized in app.py and passed here)
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user') # 'user' or 'admin'

    def __repr__(self):
        return f'<User {self.username}>'

class ParkingLot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prime_location_name = db.Column(db.String(100), nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200), nullable=False)
    pin_code = db.Column(db.String(10), nullable=False)
    maximum_number_of_spots = db.Column(db.Integer, nullable=False)
    # Relationship to ParkingSpot: 'spots' is a list of ParkingSpot objects associated with this lot
    # cascade="all, delete-orphan" means if a ParkingLot is deleted, its associated ParkingSpots are also deleted.
    spots = db.relationship('ParkingSpot', backref='parking_lot', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<ParkingLot {self.prime_location_name}>'

class ParkingSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    spot_number = db.Column(db.Integer, nullable=False) # e.g., Spot 1, Spot 2 within a lot
    status = db.Column(db.String(1), nullable=False, default='A') # 'A' for Available, 'O' for Occupied
    # Ensure uniqueness of spot_number within a given lot_id
    __table_args__ = (db.UniqueConstraint('lot_id', 'spot_number', name='_lot_spot_uc'),)

    def __repr__(self):
        return f'<ParkingSpot {self.spot_number} in Lot {self.lot_id}>'

class ReservedSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parking_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    leaving_timestamp = db.Column(db.DateTime, nullable=True)
    parking_cost = db.Column(db.Float, nullable=True)

    # Relationships to User and ParkingSpot models
    user = db.relationship('User', backref='reservations')
    spot = db.relationship('ParkingSpot', backref='current_reservation', uselist=False) # One-to-one or one-to-many

    def __repr__(self):
        return f'<ReservedSpot {self.id} by User {self.user_id} at Spot {self.spot_id}>'