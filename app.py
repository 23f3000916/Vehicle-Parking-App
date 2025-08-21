# app.py
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime, timedelta
from sqlalchemy import func # Import func for database functions like count

# Import models from the models directory
from models.models import db, User, ParkingLot, ParkingSpot, ReservedSpot

# Initialize Flask app
app = Flask(__name__)

# Configuration for SQLite database
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'parking_app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_and_complex_key_for_your_app' # IMPORTANT: Change this!
app.config['SESSION_PERMANENT'] = False # Sessions are not permanent
app.config['SESSION_TYPE'] = 'filesystem' # Store sessions on the filesystem

# Initialize SQLAlchemy with the app
db.init_app(app)

# --- Authentication Decorators ---
def login_required(f):
    """
    Decorator to ensure a user is logged in.
    Redirects to login page if not authenticated.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Decorator to ensure the logged-in user is an admin.
    Requires login_required to be applied first.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('index')) # Or a specific unauthorized page
        return f(*args, **kwargs)
    return decorated_function

# --- Routes (Controllers) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: # If already logged in, redirect
        if session['user_role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_role'] = user.role
            flash(f'Logged in successfully as {user.username}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session: # If already logged in, redirect
        if session['user_role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
        else:
            new_user = User(username=username, password=hashed_password, role='user')
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    session.pop('user_role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# --- Admin Routes ---
@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    parking_lots = ParkingLot.query.all()

    # Data for Admin Charts
    total_lots = ParkingLot.query.count()
    total_spots = ParkingSpot.query.count()
    available_spots = ParkingSpot.query.filter_by(status='A').count()
    occupied_spots = ParkingSpot.query.filter_by(status='O').count()

    # Parking lot wise spot distribution
    lot_spot_data = db.session.query(
        ParkingLot.prime_location_name,
        func.count(ParkingSpot.id).label('total_spots_in_lot'),
        func.sum(db.case((ParkingSpot.status == 'O', 1), else_=0)).label('occupied_spots_in_lot')
    ).join(ParkingSpot).group_by(ParkingLot.id).all()

    lot_names = [data.prime_location_name for data in lot_spot_data]
    total_spots_per_lot = [data.total_spots_in_lot for data in lot_spot_data]
    occupied_spots_per_lot = [data.occupied_spots_in_lot for data in lot_spot_data]
    available_spots_per_lot = [t - o for t, o in zip(total_spots_per_lot, occupied_spots_per_lot)]


    return render_template('admin_dashboard.html',
                           parking_lots=parking_lots,
                           total_lots=total_lots,
                           total_spots=total_spots,
                           available_spots=available_spots,
                           occupied_spots=occupied_spots,
                           lot_names=lot_names,
                           total_spots_per_lot=total_spots_per_lot,
                           occupied_spots_per_lot=occupied_spots_per_lot,
                           available_spots_per_lot=available_spots_per_lot)

@app.route('/admin_view_users')
@admin_required
def admin_view_users():
    all_users = User.query.filter(User.role != 'admin').all() # Exclude admin user itself
    return render_template('admin_view_users.html', all_users=all_users)

@app.route('/admin_search_spot', methods=['GET', 'POST'])
@admin_required
def admin_search_spot():
    search_results = []
    search_query = None

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        search_type = request.form.get('search_type')

        if not search_query:
            flash('Please enter a search query.', 'warning')
        else:
            try:
                if search_type == 'lot_name':
                    # Search by parking lot name
                    parking_lots = ParkingLot.query.filter(
                        ParkingLot.prime_location_name.ilike(f'%{search_query}%')
                    ).all()
                    for lot in parking_lots:
                        for spot in lot.spots:
                            search_results.append({
                                'lot_name': lot.prime_location_name,
                                'spot_number': spot.spot_number,
                                'status': spot.status,
                                'lot_id': lot.id,
                                'spot_id': spot.id,
                                'reservation_details': ReservedSpot.query.filter_by(spot_id=spot.id, leaving_timestamp=None).first() if spot.status == 'O' else None
                            })
                elif search_type == 'spot_number':
                    # Search by spot number (across all lots for simplicity, or could add lot filter)
                    # Note: Spot numbers are unique per lot, not globally.
                    # This search will return all spots with that number across different lots.
                    spot_number_int = int(search_query) # Ensure it's an integer
                    parking_spots = ParkingSpot.query.filter_by(spot_number=spot_number_int).all()
                    for spot in parking_spots:
                        lot = ParkingLot.query.get(spot.lot_id)
                        if lot:
                            search_results.append({
                                'lot_name': lot.prime_location_name,
                                'spot_number': spot.spot_number,
                                'status': spot.status,
                                'lot_id': lot.id,
                                'spot_id': spot.id,
                                'reservation_details': ReservedSpot.query.filter_by(spot_id=spot.id, leaving_timestamp=None).first() if spot.status == 'O' else None
                            })
                else:
                    flash('Invalid search type selected.', 'danger')

                if not search_results and search_query:
                    flash(f'No results found for "{search_query}".', 'info')

            except ValueError:
                flash('Spot number must be a valid integer.', 'danger')
            except Exception as e:
                flash(f'An error occurred during search: {str(e)}', 'danger')

    return render_template('admin_search_spot.html', search_results=search_results, search_query=search_query)


@app.route('/add_parking_lot', methods=['GET', 'POST'])
@admin_required
def add_parking_lot():
    if request.method == 'POST':
        prime_location_name = request.form['prime_location_name']
        price_per_hour = float(request.form['price_per_hour'])
        address = request.form['address']
        pin_code = request.form['pin_code']
        maximum_number_of_spots = int(request.form['maximum_number_of_spots'])

        # Basic validation
        if not all([prime_location_name, price_per_hour, address, pin_code, maximum_number_of_spots]):
            flash('All fields are required!', 'danger')
            return render_template('add_parking_lot.html')
        if price_per_hour <= 0:
            flash('Price per hour must be positive.', 'danger')
            return render_template('add_parking_lot.html')
        if maximum_number_of_spots <= 0:
            flash('Maximum number of spots must be at least 1.', 'danger')
            return render_template('add_parking_lot.html')

        try:
            new_lot = ParkingLot(
                prime_location_name=prime_location_name,
                price_per_hour=price_per_hour,
                address=address,
                pin_code=pin_code,
                maximum_number_of_spots=maximum_number_of_spots
            )
            db.session.add(new_lot)
            db.session.commit() # Commit to get the new_lot.id

            # Create parking spots for the new lot
            for i in range(1, maximum_number_of_spots + 1):
                new_spot = ParkingSpot(lot_id=new_lot.id, spot_number=i, status='A')
                db.session.add(new_spot)
            db.session.commit()

            flash(f'Parking Lot "{prime_location_name}" and {maximum_number_of_spots} spots added successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding parking lot: {str(e)}', 'danger')

    return render_template('add_parking_lot.html')

@app.route('/edit_parking_lot/<int:lot_id>', methods=['GET', 'POST'])
@admin_required
def edit_parking_lot(lot_id):
    parking_lot = ParkingLot.query.get_or_404(lot_id)

    if request.method == 'POST':
        new_prime_location_name = request.form['prime_location_name']
        new_price_per_hour = float(request.form['price_per_hour'])
        new_address = request.form['address']
        new_pin_code = request.form['pin_code']
        new_maximum_number_of_spots = int(request.form['maximum_number_of_spots'])

        # Basic validation
        if not all([new_prime_location_name, new_price_per_hour, new_address, new_pin_code, new_maximum_number_of_spots]):
            flash('All fields are required!', 'danger')
            return render_template('edit_parking_lot.html', parking_lot=parking_lot)
        if new_price_per_hour <= 0:
            flash('Price per hour must be positive.', 'danger')
            return render_template('edit_parking_lot.html', parking_lot=parking_lot)
        if new_maximum_number_of_spots <= 0:
            flash('Maximum number of spots must be at least 1.', 'danger')
            return render_template('edit_parking_lot.html', parking_lot=parking_lot)

        try:
            # Check if decreasing spots would remove occupied spots
            current_occupied_spots = ParkingSpot.query.filter_by(lot_id=lot_id, status='O').count()
            if new_maximum_number_of_spots < current_occupied_spots:
                flash(f'Cannot reduce spots below the number of currently occupied spots ({current_occupied_spots}).', 'danger')
                return render_template('edit_parking_lot.html', parking_lot=parking_lot)

            # Update lot details
            parking_lot.prime_location_name = new_prime_location_name
            parking_lot.price_per_hour = new_price_per_hour
            parking_lot.address = new_address
            parking_lot.pin_code = new_pin_code

            # Handle spot changes
            if new_maximum_number_of_spots > parking_lot.maximum_number_of_spots:
                # Add new spots
                for i in range(parking_lot.maximum_number_of_spots + 1, new_maximum_number_of_spots + 1):
                    new_spot = ParkingSpot(lot_id=parking_lot.id, spot_number=i, status='A')
                    db.session.add(new_spot)
            elif new_maximum_number_of_spots < parking_lot.maximum_number_of_spots:
                # Delete excess spots (only if not occupied)
                spots_to_delete = ParkingSpot.query.filter(
                    ParkingSpot.lot_id == lot_id,
                    ParkingSpot.spot_number > new_maximum_number_of_spots,
                    ParkingSpot.status == 'A' # Only delete available spots
                ).all()
                for spot in spots_to_delete:
                    db.session.delete(spot)

            parking_lot.maximum_number_of_spots = new_maximum_number_of_spots
            db.session.commit()
            flash(f'Parking Lot "{parking_lot.prime_location_name}" updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating parking lot: {str(e)}', 'danger')

    return render_template('edit_parking_lot.html', parking_lot=parking_lot)

@app.route('/delete_parking_lot/<int:lot_id>', methods=['POST'])
@admin_required
def delete_parking_lot(lot_id):
    parking_lot = ParkingLot.query.get_or_404(lot_id)

    # Check if any spots in the lot are occupied
    occupied_spots_count = ParkingSpot.query.filter_by(lot_id=lot_id, status='O').count()
    if occupied_spots_count > 0:
        flash(f'Cannot delete parking lot "{parking_lot.prime_location_name}" because there are {occupied_spots_count} occupied spots.', 'danger')
    else:
        try:
            db.session.delete(parking_lot)
            db.session.commit()
            flash(f'Parking Lot "{parking_lot.prime_location_name}" and all its spots deleted successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting parking lot: {str(e)}', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/view_parking_lot_details/<int:lot_id>')
@admin_required
def view_parking_lot_details(lot_id):
    parking_lot = ParkingLot.query.get_or_404(lot_id)
    parking_spots = ParkingSpot.query.filter_by(lot_id=lot_id).order_by(ParkingSpot.spot_number).all()

    for spot in parking_spots:
        if spot.status == 'O':
            spot.reservation_details = ReservedSpot.query.filter_by(spot_id=spot.id, leaving_timestamp=None).first()
            if spot.reservation_details:
                spot.reserved_by_user = User.query.get(spot.reservation_details.user_id)
            else:
                spot.reserved_by_user = None
        else:
            spot.reservation_details = None
            spot.reserved_by_user = None

    return render_template('view_parking_lot_details.html', parking_lot=parking_lot, parking_spots=parking_spots)

# --- User Routes ---
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    # Get all parking lots with available spots
    parking_lots = ParkingLot.query.all()
    
    # Check if the user has an active reservation
    user_id = session['user_id']
    active_reservation = ReservedSpot.query.filter_by(user_id=user_id, leaving_timestamp=None).first()

    return render_template('user_dashboard.html', parking_lots=parking_lots, active_reservation=active_reservation)

@app.route('/book_spot/<int:lot_id>')
@login_required
def book_spot(lot_id):
    user_id = session['user_id']
    
    # Check if user already has an active reservation
    existing_reservation = ReservedSpot.query.filter_by(user_id=user_id, leaving_timestamp=None).first()
    if existing_reservation:
        flash('You already have an active parking reservation. Please release it first.', 'warning')
        return redirect(url_for('user_dashboard'))

    # Find the first available spot in the selected lot
    available_spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='A').order_by(ParkingSpot.spot_number).first()

    if available_spot:
        try:
            # Mark spot as occupied
            available_spot.status = 'O'
            db.session.add(available_spot)

            # Create a new reservation
            new_reservation = ReservedSpot(
                spot_id=available_spot.id,
                user_id=user_id,
                parking_timestamp=datetime.utcnow()
            )
            db.session.add(new_reservation)
            db.session.commit()

            flash(f'Spot {available_spot.spot_number} in {available_spot.parking_lot.prime_location_name} booked successfully!', 'success')
            return redirect(url_for('my_reservations'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error booking spot: {str(e)}', 'danger')
    else:
        flash('No available spots in this parking lot.', 'danger')
    
    return redirect(url_for('user_dashboard'))

@app.route('/my_reservations')
@login_required
def my_reservations():
    user_id = session['user_id']
    # Fetch all reservations for the current user, ordered by parking timestamp (newest first)
    reservations = ReservedSpot.query.filter_by(user_id=user_id).order_by(ReservedSpot.parking_timestamp.desc()).all()

    # Calculate current cost for active reservation
    active_reservation = None
    total_past_cost = 0
    past_reservation_counts = {} # To store counts for chart

    for res in reservations:
        if res.leaving_timestamp is None:
            active_reservation = res
            # Calculate current duration and cost for active reservation
            duration = datetime.utcnow() - res.parking_timestamp
            hours = duration.total_seconds() / 3600.0
            lot_price_per_hour = res.spot.parking_lot.price_per_hour
            res.current_cost = hours * lot_price_per_hour
            res.current_duration = str(timedelta(seconds=int(duration.total_seconds()))) # Format as H:MM:SS
        else:
            total_past_cost += res.parking_cost if res.parking_cost is not None else 0
            # For past reservation counts by month/year
            month_year = res.parking_timestamp.strftime('%Y-%m')
            past_reservation_counts[month_year] = past_reservation_counts.get(month_year, 0) + 1
            
    # Sort past_reservation_counts by date
    sorted_past_reservation_counts = sorted(past_reservation_counts.items())
    chart_labels = [item[0] for item in sorted_past_reservation_counts]
    chart_data = [item[1] for item in sorted_past_reservation_counts]


    return render_template('my_reservations.html',
                           reservations=reservations,
                           active_reservation=active_reservation,
                           total_past_cost=total_past_cost,
                           user_chart_labels=chart_labels,
                           user_chart_data=chart_data)

@app.route('/release_spot/<int:reservation_id>', methods=['POST'])
@login_required
def release_spot(reservation_id):
    user_id = session['user_id']
    reservation = ReservedSpot.query.filter_by(id=reservation_id, user_id=user_id, leaving_timestamp=None).first()

    if not reservation:
        flash('No active reservation found to release.', 'danger')
        return redirect(url_for('my_reservations'))

    try:
        # Update leaving timestamp
        reservation.leaving_timestamp = datetime.utcnow()

        # Calculate parking duration and cost
        duration = reservation.leaving_timestamp - reservation.parking_timestamp
        hours = duration.total_seconds() / 3600.0
        
        lot_price_per_hour = reservation.spot.parking_lot.price_per_hour
        parking_cost = hours * lot_price_per_hour
        reservation.parking_cost = round(parking_cost, 2) # Round to 2 decimal places

        # Mark parking spot as available
        parking_spot = ParkingSpot.query.get(reservation.spot_id)
        if parking_spot:
            parking_spot.status = 'A'
            db.session.add(parking_spot)
        
        db.session.add(reservation)
        db.session.commit()

        flash(f'Spot released! Total cost: ${reservation.parking_cost:.2f}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error releasing spot: {str(e)}', 'danger')

    return redirect(url_for('my_reservations'))

# --- API Resources ---
@app.route('/api/lots', methods=['GET'])
def api_lots():
    """
    API endpoint to get a list of all parking lots.
    Returns JSON with lot details and spot counts.
    """
    lots = ParkingLot.query.all()
    lot_list = []
    for lot in lots:
        total_spots = len(lot.spots)
        occupied_spots = len([spot for spot in lot.spots if spot.status == 'O'])
        available_spots = total_spots - occupied_spots
        lot_list.append({
            'id': lot.id,
            'prime_location_name': lot.prime_location_name,
            'price_per_hour': lot.price_per_hour,
            'address': lot.address,
            'pin_code': lot.pin_code,
            'total_spots': total_spots,
            'occupied_spots': occupied_spots,
            'available_spots': available_spots
        })
    return jsonify({'parking_lots': lot_list})

@app.route('/api/lots/<int:lot_id>', methods=['GET'])
def api_lot_details(lot_id):
    """
    API endpoint to get details of a single parking lot.
    Returns JSON with lot details and a list of all its spots.
    """
    lot = ParkingLot.query.get_or_404(lot_id)
    spot_list = []
    for spot in lot.spots:
        spot_details = {
            'id': spot.id,
            'spot_number': spot.spot_number,
            'status': 'Available' if spot.status == 'A' else 'Occupied'
        }
        if spot.status == 'O':
            # Add reservation details for occupied spots
            reservation = ReservedSpot.query.filter_by(spot_id=spot.id, leaving_timestamp=None).first()
            if reservation:
                spot_details['occupied_by_user_id'] = reservation.user_id
                spot_details['parking_timestamp'] = reservation.parking_timestamp.isoformat()
        spot_list.append(spot_details)

    lot_details = {
        'id': lot.id,
        'prime_location_name': lot.prime_location_name,
        'price_per_hour': lot.price_per_hour,
        'address': lot.address,
        'pin_code': lot.pin_code,
        'total_spots': len(lot.spots),
        'parking_spots': spot_list
    }
    return jsonify(lot_details)

@app.route('/api/spots', methods=['GET'])
def api_spots():
    """
    API endpoint to get a list of all parking spots.
    Returns JSON with basic spot details.
    """
    spots = ParkingSpot.query.all()
    spot_list = []
    for spot in spots:
        spot_list.append({
            'id': spot.id,
            'lot_id': spot.lot_id,
            'spot_number': spot.spot_number,
            'status': 'Available' if spot.status == 'A' else 'Occupied'
        })
    return jsonify({'parking_spots': spot_list})

@app.route('/api/spots/<int:spot_id>', methods=['GET'])
def api_spot_details(spot_id):
    """
    API endpoint to get details of a single parking spot.
    Returns JSON with spot details and reservation info if occupied.
    """
    spot = ParkingSpot.query.get_or_404(spot_id)
    spot_details = {
        'id': spot.id,
        'lot_id': spot.lot_id,
        'lot_name': spot.parking_lot.prime_location_name,
        'spot_number': spot.spot_number,
        'status': 'Available' if spot.status == 'A' else 'Occupied'
    }
    if spot.status == 'O':
        reservation = ReservedSpot.query.filter_by(spot_id=spot.id, leaving_timestamp=None).first()
        if reservation:
            spot_details['reservation'] = {
                'reservation_id': reservation.id,
                'user_id': reservation.user_id,
                'user_name': reservation.user.username,
                'parking_timestamp': reservation.parking_timestamp.isoformat()
            }
    return jsonify(spot_details)


# --- Database Initialization ---
with app.app_context():
    db.create_all()
    # Create admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin_password = generate_password_hash('adminpass', method='pbkdf2:sha256') # Default admin password
        admin_user = User(username='admin', password=admin_password, role='admin')
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created: username='admin', password='adminpass'")
    else:
        print("Admin user already exists.")


if __name__ == '__main__':
    app.run(debug=True)