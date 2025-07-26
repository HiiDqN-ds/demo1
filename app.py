from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
import json, uuid, io, os, random, barcode
from datetime import datetime, timedelta
from barcode.writer import ImageWriter
from flask import jsonify,send_file
from functools import wraps
from db import *
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user, LoginManager, current_user
from flask import Response
import barcode

from barcode.writer import ImageWriter
import io
from db import fetch_one, execute_query
from flask import request, flash, redirect, url_for
from db import fetch_one, execute_query
from flask import render_template
from flask_login import login_required
from sqlalchemy import func
from flask import render_template, request, redirect, url_for, flash
from db import fetch_all, execute_query
from datetime import datetime, date
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # required for sessions


# ✅ Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # route name of your login page

# ✅ User class compatible with Flask-Login
class User(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict['username']  # required by Flask-Login
        self.username = user_dict['username']
        self.role = user_dict.get('role', 'user')
        self.activated = user_dict.get('activated', True)

    def is_active(self):
        return self.activated

# ✅ User loader callback
@login_manager.user_loader
def load_user(user_id):
    user_data = find_user(user_id)
    print("DEBUG load_user user_data:", user_data)
    if user_data:
        return User(user_data)
    return None

# ✅ Custom role_required decorator
def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Bitte einloggen.", "warning")
                return redirect(url_for("login"))
            if getattr(current_user, "role", None) != role_name:
                flash("Keine Berechtigung.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapped
    return decorator








# Login_required
def login_required(roles=None):
    if not isinstance(roles, (list, tuple)):
        roles = [roles] if roles else []

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Please login first', 'warning')
                return redirect(url_for('login'))
            if roles and session.get('role') not in roles:
                flash('Unauthorized access', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ROUTES
@app.route('/')
def index():
    role = session.get('role')
    if role == 'admin':
        # redirect to seller_dashboard temporarily or show message
        return redirect(url_for('admin_dashboard'))
    elif role == 'seller':
        return redirect(url_for('seller_dashboard'))
    else:
        return redirect(url_for('login'))


# Login
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = find_user(username)
        if user and check_password_hash(user['password'], password):
            if not user['activated']:
                flash('Your account is not activated yet.', 'warning')
                return redirect(url_for('login'))
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Welcome {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')


# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'success')
    return redirect(url_for('login'))


# Date Time Format 
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime(format)
    except Exception:
        return value

# calculate_all_time_profit
def calculate_all_time_profit(sales, items):
    barcode_map = {item['barcode']: item.get('purchase_price', 0) for item in items}
    profit = 0.0
    for s in sales:
        barcode = s.get('barcode')
        purchase_price = barcode_map.get(barcode, 0)
        sale_price = s.get('sale_price', 0)
        quantity = s.get('quantity', 0)
        profit += (sale_price - purchase_price) * quantity
    return round(profit, 2)

from datetime import datetime

@app.route('/admin')
@login_required('admin')
def admin_dashboard():
    now = datetime.now()
    today = now.date()

    # Load data
    sales = load_sales()       # includes items with 'profit'
    purchases = load_orders()
    items = load_items()
    kasse_balance = load_kasse_balance()

    dismissed = set(session.get('dismissed_notifications', []))

    heutiger_gewinn = calculate_today_profit()
    monatliche_einnahmen = calculate_monthly_sales()

    # Calculate daily income from sales
    taegliche_einnahmen = 0
    for sale in sales:
        sale_date = sale.get('date')
        if isinstance(sale_date, str):
            try:
                sale_date = datetime.fromisoformat(sale_date)
            except Exception:
                continue
        if isinstance(sale_date, datetime) and sale_date.date() == today:
            for item in sale.get('items', []):
                taegliche_einnahmen += float(item.get('total_price', 0))
    taegliche_einnahmen = round(taegliche_einnahmen, 2)

    # Calculate purchases totals (daily & monthly)
    daily_purchases_total = 0
    monthly_purchases_total = 0
    for p in purchases:
        p_date = p.get('order_date') or p.get('date')
        if isinstance(p_date, str):
            try:
                p_date = datetime.fromisoformat(p_date)
            except Exception:
                p_date = datetime.min
        if isinstance(p_date, datetime):
            total_price = float(p.get('total_price', 0))
            if p_date.date() == today:
                daily_purchases_total += total_price
            if p_date.year == now.year and p_date.month == now.month:
                monthly_purchases_total += total_price
    daily_purchases_total = round(daily_purchases_total, 2)
    monthly_purchases_total = round(monthly_purchases_total, 2)

    # Calculate cash balance after sales & purchases today
    berechneter_kassenstand = round(kasse_balance + taegliche_einnahmen - daily_purchases_total, 2)

    # Notifications filtering dismissed ones
    low_stock_notes = get_low_stock_notifications(items, threshold=5)
    old_stock_notes = get_old_stock_notifications(items, days_old=21)
    warehouse_notifications = [
        note for note in (low_stock_notes + old_stock_notes)
        if note.get('barcode') not in dismissed
    ]
    mailbox_notifications = [
        {
            'date': now.strftime("%Y-%m-%d"),
            'message': note.get('message', 'Keine Nachricht'),
            'type': note.get('type', 'info'),
            'barcode': note.get('barcode')
        }
        for note in warehouse_notifications
    ]

    # Sort sales and purchases by date descending
    sales_sorted = sorted(sales, key=lambda x: x.get('date', datetime.min), reverse=True)
    purchases_sorted = sorted(purchases, key=lambda x: x.get('order_date', datetime.min), reverse=True)

    total_order_sum = round(sum(float(p.get('total_price', 0)) for p in purchases), 2)

    return render_template(
        "admin_dashboard.html",
        heutiger_gewinn=heutiger_gewinn,
        taegliche_einnahmen=taegliche_einnahmen,
        monatliche_einnahmen=monatliche_einnahmen,
        wallet_balance=kasse_balance,
        daily_purchases_total=daily_purchases_total,
        monthly_purchases_total=monthly_purchases_total,
        berechneter_kassenstand=berechneter_kassenstand,
        sales=sales_sorted,
        purchases=purchases_sorted,
        mailbox_notifications=mailbox_notifications,
        warehouse_notifications=warehouse_notifications,
        total_order_sum=total_order_sum,
    )




@app.template_filter('to_float')
def to_float_filter(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# Format_currency_de
def format_currency_de(amount):
    return f"€{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

#Saving Everyday History
def save_dashboard_snapshot(date, daily_profit, monthly_profit, wallet_balance, all_time_profit):
    history_file = os.path.join('data', 'dashboard_history.json')
    
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []
    else:
        history = []

    # Avoid duplicate entry for the same day
    if any(entry.get("date") == date.isoformat() for entry in history):
        return

    history.append({
        "date": date.isoformat(),
        "daily_profit": round(daily_profit, 2),
        "monthly_profit": round(monthly_profit, 2),
        "wallet_balance": round(wallet_balance, 2),
        "all_time_profit": round(all_time_profit, 2)
    })

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

#log_wallet_change
def log_wallet_change(amount, change_type="manual"):
    wallet_file = os.path.join('data', 'wallet_log.json')

    # Load old log
    if os.path.exists(wallet_file):
        with open(wallet_file, 'r', encoding='utf-8') as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []
    else:
        log = []

    # Get the username from session
    username = session.get('username', 'unknown')

    # Append new entry
    log.append({
        "date": datetime.now().isoformat(),
        "change_type": change_type,
        "amount": round(amount, 2),
        "user": username
    })

    # Save updated log
    with open(wallet_file, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)




 # Generate CSV
#Log generate_csv
def generate_csv(data, fieldnames):
    """Generate CSV response from list of dicts."""
    def generate():
        yield ",".join(fieldnames) + "\n"
        for row in data:
            yield ",".join(str(row.get(f, "")) for f in fieldnames) + "\n"
    return Response(generate(), mimetype='text/csv')

@app.route('/download/sales.csv')
@login_required(['admin', 'seller'])
def download_sales_csv():
    current_user = session.get('username')
    sales = load_sales()

    # Filter sales for current user
    user_sales = [sale for sale in sales if sale.get('user') == current_user]

    rows = []
    for sale in user_sales:
        sale_date = sale.get('date')
        for item in sale.get('items', []):
            rows.append({
                'date': sale_date,
                'product_name': item.get('product_name'),
                'quantity': item.get('quantity'),
                'price': item.get('sale_price'),
                'total_price': item.get('total_price'),
            })

    fieldnames = ['date', 'product_name', 'quantity', 'price', 'total_price']
    return generate_csv(rows, fieldnames)


@app.route('/download/purchases.csv')
@login_required(['admin', 'seller'])
def download_purchases_csv():
    current_user = session.get('username')

    # Use the same function you use in the dashboard
    user_purchases = get_purchases_for_user(current_user)

    rows = []
    for purchase in user_purchases:
        purchase_date = purchase.get('date') or purchase.get('order_date')
        rows.append({
            'date': purchase_date,
            'product_name': purchase.get('product_name', 'Unbekannt'),
            'quantity': purchase.get('quantity', 0),
            'price': purchase.get('purchase_price') or purchase.get('price', 0),
            'total_price': (purchase.get('purchase_price') or purchase.get('price', 0)) * purchase.get('quantity', 0),
        })

    fieldnames = ['date', 'product_name', 'quantity', 'price', 'total_price']
    return generate_csv(rows, fieldnames)


# Admin: List Sellers
@app.route('/admin/sellers')
@login_required('admin')
def list_sellers():
    sellers = load_users()
    for seller in sellers:
        seller.setdefault('salary', 0.0)
        seller.setdefault('profile_img', '')
        seller.setdefault('activated', False)
    return render_template('sellers.html', sellers=sellers)

# Add  user
from werkzeug.security import generate_password_hash

@app.route('/admin/sellers/add', methods=['GET', 'POST'])
@login_required('admin')
def add_seller():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        profile_img = request.form.get('profile_img', '').strip()
        salary_str = request.form.get('salary', '').strip()
        activated = 'activated' in request.form

        if not username:
            flash('Benutzername darf nicht leer sein.', 'danger')
            return redirect(url_for('add_seller'))

        if not password:
            flash('Passwort darf nicht leer sein.', 'danger')
            return redirect(url_for('add_seller'))

        try:
            salary = float(salary_str) if salary_str else 0.0
            if salary < 0:
                raise ValueError("Gehalt darf nicht negativ sein.")
        except ValueError as e:
            flash(f'Ungültiges Gehalt: {e}', 'danger')
            return redirect(url_for('add_seller'))

        if find_user(username):
            flash('Benutzername existiert bereits.', 'danger')
            return redirect(url_for('add_seller'))

        # Hash the password before storing
        hashed_password = generate_password_hash(password)

        new_seller = {
            'username': username,
            'password': hashed_password,  # store hashed password here
            'role': 'seller',
            'profile_img': profile_img,
            'salary': salary,
            'activated': activated
        }

        insert_user(new_seller)

        flash('Verkäufer erfolgreich hinzugefügt!', 'success')
        return redirect(url_for('list_sellers'))

    return render_template('add_seller.html')



# Admin: Edit Seller
@app.route('/admin/sellers/edit/<username>', methods=['GET', 'POST'])
@login_required('admin')
def edit_seller(username):
    sellers = load_users()
    seller = next((s for s in sellers if s['username'] == username), None)
    if not seller:
        flash('Seller not found', 'danger')
        return redirect(url_for('list_sellers'))

    if request.method == 'POST':
        seller['profile_img'] = request.form.get('profile_img', seller.get('profile_img', ''))
        seller['salary'] = float(request.form.get('salary', seller.get('salary', 0.0)))
        seller['activated'] = 'activated' in request.form

        update_user(username, {
            'profile_img': request.form.get('profile_img', ''),
            'salary': float(request.form.get('salary', 0.0)),
            'activated': 'activated' in request.form
        })

        flash('Seller updated successfully', 'success')
        return redirect(url_for('list_sellers'))

    return render_template('edit_seller.html', seller=seller)

# Admin: Delete Seller
@app.route('/admin/sellers/delete/<username>', methods=['POST'])
@login_required('admin')
def delete_seller(username):
    delete_user(username)
    flash('Seller deleted successfully', 'success')
    return redirect(url_for('list_sellers'))


@app.route('/admin/items')
@login_required('admin')
def list_items():
    # Step 1: Load items from the DB using your existing function
    items = load_items()

    # Step 2: Reverse the list if you want newest items first
    items = items[::-1]

    # Step 3: Normalize fields for display (optional but recommended)
    for item in items:
        product_name = item.get('product_name', '').strip()
        if not product_name:
            product_name = "Unnamed product"
        item['product_name'] = product_name

        item['barcode'] = item.get('barcode', '')

        item['purchase_price'] = float(item.get('purchase_price', 0) or 0)
        item['selling_price'] = float(item.get('selling_price', 0) or 0)  # fix key here
        item['min_selling_price'] = float(item.get('min_selling_price', 0) or 0)

        item['quantity'] = int(item.get('quantity', 0) or 0)

        item['description'] = item.get('description', '')
        item['photo_link'] = item.get('photo_link', '')

    # Step 4: Render the template with items list
    return render_template('items.html', items=items)


from flask import send_file, abort
import io
import barcode
from barcode.writer import ImageWriter

@app.route('/admin/items/barcode_print/<barcode_value>')
@login_required('admin')
def barcode_print(barcode_value):
    try:
        CODE128 = barcode.get_barcode_class('code128')
        img_io = io.BytesIO()

        code = CODE128(barcode_value, writer=ImageWriter())
        code.write(img_io)
        img_io.seek(0)

        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=False
        )
    except Exception as e:
        # Log error here if you want
        abort(404, description="Invalid barcode")




from flask_login import login_required
# Add Item
@app.route('/admin/add_item', methods=['GET', 'POST'])

def add_item():
    if request.method == 'POST':
        form_data = request.form
        barcode = form_data['barcode']

        items = load_items()

        # ✅ Check for duplicate barcode
        if any(item.get('barcode') == barcode for item in items):
            flash(f'⚠️ Ein Artikel mit dem Barcode "{barcode}" existiert bereits!', 'danger')
            return redirect(url_for('add_item'))

        # ✅ Create new item with added_date
        new_item = {
        "name": form_data['name'],  # rename key here
        "barcode": barcode,
        "purchase_price": float(form_data['purchase_price']),
        "selling_price": float(form_data['selling_price']),
        "min_selling_price": float(form_data['min_selling_price']),
        "quantity": int(form_data['quantity']),
        "description": form_data.get('description', ''),
        "seller": current_user.id,
        "added_date": datetime.now().strftime('%Y-%m-%d')
    }

        insert_item(form_data, current_user)
        flash('✅ Neuer Artikel hinzugefügt.', 'success')
        return redirect(url_for('list_items'))

    return render_template('add_item.html', item=None)

# Update Item
@app.route('/edit_item/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    # Fetch the item from DB by id
    item = find_item(item_id)  # You need to implement this

    if request.method == 'POST':
        # Determine if barcode is being edited or not
        edit_barcode = request.form.get('edit_barcode') == 'on'

        # If not editing barcode, keep old barcode
        barcode = request.form.get('barcode') if edit_barcode else request.form.get('old_barcode')

        updates = {
            'product_name': request.form.get('product_name'),
            'barcode': barcode,
            'purchase_price': float(request.form.get('purchase_price', 0)),
            'selling_price': float(request.form.get('selling_price', 0)),
            'min_selling_price': float(request.form.get('min_selling_price', 0)),
            'quantity': int(request.form.get('quantity', 0)),
            'description': request.form.get('description'),
            'photo_link': request.form.get('photo_link'),
        }

        # Basic validation
        if not updates['product_name'] or not updates['barcode']:
            flash('Produktname und Barcode dürfen nicht leer sein.', 'danger')
            return render_template('edit_item.html', item=item)

        # Update in DB
        update_item(item_id, updates)

        flash('Artikel erfolgreich aktualisiert.', 'success')
        return redirect(url_for('list_items'))

    return render_template('edit_item.html', item=item)


 # Delete Item
# Route handler
@app.route('/admin/items/delete/<int:item_id>', methods=['POST'])
@login_required('admin')
def delete_item_route(item_id):
    db_delete_item(item_id)  # call the DB function renamed here
    flash("Item deleted successfully", "success")
    items = load_items()
    return render_template('items.html', items=items)


# Helper function to find product by barcode (if needed)
def find_item_by_barcode(barcode):
    return fetch_one("SELECT * FROM products WHERE barcode = %s;", (barcode,))



from flask import request, session, redirect, url_for, flash, render_template
from datetime import datetime
import uuid
from db import load_items, execute_query, get_connection  # your db helper functions

@app.route('/sell', methods=['GET', 'POST'])
def sell_item():
    # Access control: only admin or seller can sell
    if 'username' not in session or session.get('role') not in ('admin', 'seller'):
        flash("❌ Zugriff verweigert. Bitte einloggen.", 'danger')
        return redirect(url_for('login'))

    items = load_items()  # Load all products from DB

    if request.method == 'POST':
        # Collect all indices from form keys like items[0][barcode], etc.
        indices = {
            key.split('[')[1].split(']')[0]
            for key in request.form if key.startswith('items[')
        }
        indices = sorted(indices, key=int)

        sale_items = []
        total_sale_price = 0.0

        # We'll modify quantities locally first to validate stock before DB update
        updated_quantities = {}

        for idx in indices:
            barcode = request.form.get(f'items[{idx}][barcode]', '').strip()
            quantity_raw = request.form.get(f'items[{idx}][quantity]', '').strip()
            discount_active = request.form.get(f'items[{idx}][discount_active]')
            price_input = request.form.get(f'items[{idx}][price]', '').strip()

            # Validate barcode
            if not barcode:
                flash(f"❌ Bitte wählen Sie für Produkt {int(idx)+1} ein Produkt aus.", 'danger')
                return redirect(url_for('sell_item'))

            # Find the item in stock by barcode
            item = next((i for i in items if i['barcode'] == barcode), None)
            if not item:
                flash(f"❌ Produkt mit Barcode {barcode} nicht gefunden.", 'danger')
                return redirect(url_for('sell_item'))

            # Validate quantity
            try:
                quantity = int(quantity_raw)
                if quantity <= 0:
                    raise ValueError()
            except ValueError:
                flash(f"❌ Ungültige Menge für Produkt {item.get('product_name', 'Produkt')}.", 'danger')
                return redirect(url_for('sell_item'))

            if quantity > item['quantity']:
                flash(f"❌ Nicht genug Bestand für Produkt {item.get('product_name', 'Produkt')}. Nur noch {item['quantity']} verfügbar.", 'danger')
                return redirect(url_for('sell_item'))

            # Determine sale price
            if discount_active:
                try:
                    sale_price = float(price_input)
                    if sale_price <= 0:
                        raise ValueError()
                except ValueError:
                    flash(f"❌ Ungültiger Preis für Produkt {item.get('product_name', 'Produkt')}.", 'danger')
                    return redirect(url_for('sell_item'))
            else:
                try:
                    sale_price = float(item.get('selling_price', 0))
                    if sale_price <= 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    flash(f"❌ Das Produkt {item.get('product_name', 'Produkt')} hat einen ungültigen Preis.", 'danger')
                    return redirect(url_for('sell_item'))

            # Calculate total price for this item
            total_price = round(sale_price * quantity, 2)
            total_sale_price += total_price

            # Prepare sale item record
            sale_items.append({
                'barcode': barcode,
                'product_name': item.get('product_name') or 'Unbenannt',
                'quantity': quantity,
                'sale_price': sale_price,
                'total_price': total_price,
                'purchase_price': item.get('purchase_price', 0)
            })

            # Track updated stock quantity (for batch DB update later)
            updated_quantities[barcode] = item['quantity'] - quantity

            # Flash success per item
            product_name = item.get("product_name") or "Produkt"
            flash(f'✅ Verkauf von {quantity} × {product_name} erfolgreich.', 'success')

            # Low stock warning
            if updated_quantities[barcode] <= 5:
                flash(f'⚠️ Achtung: Nur noch {updated_quantities[barcode]} Stück von {product_name} auf Lager!', 'warning')

        # At this point, all validation passed and sale_items prepared

        sale_id = str(uuid.uuid4())
        sale_date = datetime.now()

        # Insert sale and sale items into DB and update stocks in a transaction
        try:
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    # Insert sale record
                    cur.execute("""
                        INSERT INTO sales (sale_id, username, sale_date, total_sale_price)
                        VALUES (%s, %s, %s, %s)
                    """, (sale_id, session['username'], sale_date, total_sale_price))

                    # Insert each sale item
                    for item in sale_items:
                        cur.execute("""
                            INSERT INTO sale_items (sale_id, barcode, product_name, quantity, sale_price, total_price, purchase_price)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            sale_id,
                            item['barcode'],
                            item['product_name'],
                            item['quantity'],
                            item['sale_price'],
                            item['total_price'],
                            item['purchase_price']
                        ))

                    # Update stock quantities in products table
                    for barcode, new_qty in updated_quantities.items():
                        cur.execute("""
                            UPDATE products SET quantity = %s WHERE barcode = %s
                        """, (new_qty, barcode))

            conn.close()

        except Exception as e:
            flash(f"❌ Fehler beim Speichern des Verkaufs: {e}", 'danger')
            return redirect(url_for('sell_item'))

        # Redirect based on user role
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('seller_dashboard'))

    # GET request renders sell form with items
    return render_template('sell_item.html', items=items)




# Admin: admin_sales
@app.route('/admin/sales')
@login_required('admin')
def admin_sales():
    all_orders = load_sales()
    flattened_sales = []

    for order in all_orders:
        order_id = order.get('order_id')
        user = order.get('user')
        date = order.get('date')
        items = order.get('items', [])
        for item in items:
            flattened_sales.append({
                'order_id': order_id,
                'seller': user,
                'date': date,
                'barcode': item.get('barcode'),
                'product_name': item.get('product_name'),
                'quantity': item.get('quantity'),
                'sale_price': float(item.get('sale_price', 0)),
                'total_price': float(item.get('total_price', item.get('quantity', 0) * item.get('sale_price', 0)))
            })

    # Then pass flattened_sales to template, but your template must handle that structure
    all_orders = load_sales()  # Each order is a dict with an 'items' list inside
    return render_template('admin_sales.html', sales=all_orders[::-1])


@app.route('/admin/sales/delete_sales_order/<order_id>', methods=['POST'])
@login_required('admin')
def delete_sales_order(order_id):
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Delete sale items associated with this order
            cur.execute("DELETE FROM sale_items WHERE sale_id = %s;", (order_id,))
            # Delete the sale itself
            cur.execute("DELETE FROM sales WHERE sale_id = %s;", (order_id,))
        conn.commit()
        flash("✅ Bestellung erfolgreich gelöscht.", "success")
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"❌ Fehler beim Löschen der Bestellung: {e}", "danger")
    finally:
        if conn:
            conn.close()
    return redirect(url_for('admin_sales'))


@app.route('/admin/pay-salary', methods=['GET', 'POST'])
@login_required('admin')
def pay_salary():
    users = load_users()  # list of user objects with .username

    if request.method == 'POST':
        try:
            employee = request.form['employee_name']
            amount = float(request.form['salary_amount'])
            source = request.form['payment_source']
            note = request.form.get('note', '')

            record = {
                'employee': employee,
                'amount': amount,
                'source': source,
                'note': note,
                'payment_date': datetime.now()  # direct datetime object
            }

            insert_salary_payment(record)

            flash(f'✅ {amount:.2f} € an {employee} aus {source} bezahlt.', 'success')
            return redirect(url_for('pay_salary'))

        except Exception as e:
            flash(f'Fehler bei der Zahlung: {str(e)}', 'danger')

    return render_template('pay_salary.html', users=users)




@app.route('/order', methods=['GET', 'POST'])
def order():
    # Check user role
    if session.get('role') not in ['admin', 'seller']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            product_name = request.form['product_name'].strip()
            ref_number = request.form.get('ref_number', '').strip()
            description = request.form.get('description', '').strip()
            price = float(request.form['price'])
            selling_price = float(request.form['selling_price'])
            min_selling_price = float(request.form['min_selling_price'])
            quantity = int(request.form['quantity'])

            if price < 0 or selling_price < 0 or min_selling_price < 0 or quantity < 1:
                raise ValueError("Preise und Menge müssen positiv sein.")
            
            # Barcode validation/generation
            if ref_number:
                if not ref_number.isdigit() or len(ref_number) not in [12, 13]:
                    flash("❌ Der manuell eingegebene Barcode muss genau 12 oder 13 Ziffern lang sein.", "danger")
                    return redirect(url_for('order'))
                barcode_number = ref_number
            else:
                # Generate unique 12-digit barcode (simple example)
                barcode_number = ''.join(str(random.randint(0, 9)) for _ in range(12))

            # Save barcode image
            barcode_dir = os.path.join(app.static_folder, 'barcodes')
            os.makedirs(barcode_dir, exist_ok=True)
            barcode_filename_no_ext = f'code_barres_{barcode_number}'
            barcode_path = os.path.join(barcode_dir, barcode_filename_no_ext)

            ean = barcode.get_barcode_class('ean13')
            code = ean(barcode_number, writer=ImageWriter())
            code.save(barcode_path)

            total_price = round(price * quantity, 2)
            today = datetime.now().strftime('%Y-%m-%d')
            username = session.get('username', 'unbekannt')

            new_order = {
                "order_number": barcode_number,
                "product_name": product_name,
                "ref_number": ref_number if ref_number else None,
                "description": description,
                "price": price,
                "selling_price": selling_price,
                "min_selling_price": min_selling_price,
                "quantity": quantity,
                "total_price": total_price,
                "date": today,
                "user": username,
                "barcode": f"barcodes/{barcode_filename_no_ext}.png"
            }

            add_order(new_order)  # Your DB insert function

            flash('✅ Bestellung erfolgreich gespeichert!', 'success')
            return redirect(url_for('list_orders'))

        except (ValueError, KeyError) as e:
            flash(f'Ungültige Eingabe: {e}', 'danger')
            return redirect(url_for('order'))

        except Exception as e:
            flash(f'Fehler beim Speichern der Bestellung: {e}', 'danger')
            return redirect(url_for('order'))

    # GET request - render form
    return render_template('order_item.html')








# Update_Item_quantity
@app.route('/update_quantity', methods=['POST'])
@login_required('admin')
def update_quantity():
    product_identifier = request.form.get('product_identifier', '').strip()
    add_quantity_str = request.form.get('add_quantity', '0').strip()

    # Validate quantity
    try:
        add_quantity = int(add_quantity_str)
        if add_quantity < 1:
            flash("Menge muss mindestens 1 sein.", "danger")
            return redirect(url_for('list_items'))
    except ValueError:
        flash("Ungültige Menge angegeben.", "danger")
        return redirect(url_for('list_items'))

    if not product_identifier:
        flash("Bitte Produktname oder Barcode eingeben.", "warning")
        return redirect(url_for('list_items'))

    # First try to find by barcode (exact match)
    item = fetch_one("SELECT * FROM products WHERE barcode = %s;", (product_identifier,))

    # If not found, try by product name (case insensitive)
    if not item:
        item = fetch_one("SELECT * FROM products WHERE LOWER(product_name) = LOWER(%s);", (product_identifier,))

    if not item:
        flash("Produkt nicht gefunden. Bitte Produktname oder Barcode prüfen.", "warning")
        return redirect(url_for('list_items'))

    new_quantity = item['quantity'] + add_quantity
    update_query = "UPDATE products SET quantity = %s WHERE id = %s;"
    execute_query(update_query, (new_quantity, item['id']))

    flash(f"Menge von '{item['product_name']}' von {item['quantity']} auf {new_quantity} erhöht.", "success")
    return redirect(url_for('list_items'))








# Load normalize_items
def normalize_items(items):
    for item in items:
        item['name'] = item.get('name') or item.get('product_name') or 'Unbenannt'
        item['product_name'] = item.get('product_name') or item.get('name') or 'Unbenannt'
        item['barcode'] = item.get('barcode', '')
        item['quantity'] = int(item.get('quantity', 0))
        item['purchase_price'] = float(item.get('purchase_price', 0))
        item['selling_price'] = float(item.get('selling_price', 0))
        item['min_selling_price'] = float(item.get('min_selling_price', 0))
        item['price'] = float(item.get('price', item.get('selling_price', 0)))
        item['description'] = item.get('description', '')
        item['photo_link'] = item.get('photo_link') or item.get('image_url', '')
    return items


@app.route('/orders')
@login_required(['admin', 'seller'])
def list_orders():
    role = session.get('role')
    username = session.get('username')
    
    # Get filters from query params
    filter_user = request.args.get('user', '').strip()
    filter_date = request.args.get('date', '').strip()
    
    # Fetch orders with filter and access control
    orders = get_orders(role=role, username=username, filter_user=filter_user, filter_date=filter_date)
    
    # Fetch distinct users for filtering dropdown (exclude system user 'postgres')
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT "user" FROM orders WHERE "user" != %s ORDER BY "user";', ('postgres',))
            users = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()
    
    return render_template(
        "list_orders.html",
        orders=orders,
        users=users,
        filter_user=filter_user,
        filter_date=filter_date
    )

@app.route('/orders/<order_number>/edit', methods=['GET', 'POST'])
@login_required(['admin'])
def edit_order(order_number):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == 'POST':
        try:
            selling_price = float(request.form['selling_price'])
            quantity = int(request.form['quantity'])
            total_price = selling_price * quantity

            order_data = {
                'product_name': request.form['product_name'],
                'ref_number': request.form.get('ref_number'),
                'description': request.form.get('description'),
                'price': float(request.form.get('price')),
                'selling_price': selling_price,
                'min_selling_price': float(request.form['min_selling_price']),
                'quantity': quantity,
                'total_price': total_price,
                'date': datetime.now().strftime('%Y-%m-%d'),  # system date in 'YYYY-MM-DD' format
                'user': session.get('username'),  # get logged-in username from session
                'barcode': request.form.get('barcode')
            }

            update_order(order_number, order_data)
            flash('Bestellung erfolgreich aktualisiert.', 'success')
            return redirect(url_for('list_orders'))

        except KeyError as e:
            flash(f'Missing form field: {e.args[0]}', 'danger')
        except ValueError:
            flash('Please enter valid numeric values.', 'danger')

    # GET request: load existing order for editing
    cur.execute("SELECT * FROM orders WHERE order_number = %s;", (order_number,))
    order = cur.fetchone()
    cur.close()
    conn.close()

    if not order:
        flash('Bestellung nicht gefunden.', 'danger')
        return redirect(url_for('list_orders'))

    return render_template('edit_order.html', order=order)


@app.route('/orders/<order_number>/delete', methods=['POST'])
@login_required(['admin', 'seller'])
def delete_order_route(order_number):
    delete_order(order_number)
    flash('Bestellung wurde gelöscht.', 'success')
    return redirect(url_for('list_orders'))


# save_salary_payment
def save_salary_payment(payment_record):
    # Load existing payments
    try:
        with open('data/salary_payments.json', 'r', encoding='utf-8') as f:
            payments = json.load(f)
    except FileNotFoundError:
        payments = []

    # Append new payment
    payments.append(payment_record)

    # Save back
    with open('data/salary_payments.json', 'w', encoding='utf-8') as f:
        json.dump(payments, f, ensure_ascii=False, indent=2)

# save_salary_payment
@app.route('/pay_salary', methods=['POST'], endpoint='pay_salary_post')
def pay_salary():
    record = request.get_json()  # JSON-Daten vom Client erhalten
    
    # Hier könntest du Validierungen machen, z.B. Felder prüfen
    if not record or 'employee_name' not in record or 'salary_amount' not in record or 'payment_source' not in record:
        return jsonify({'error': 'Ungültige Daten'}), 400
    
    # Speichern
    save_salary_payment(record)

    return jsonify({'message': 'Gehaltszahlung gespeichert!'}), 200


@app.route('/list_salary_payments')
@login_required('admin')  # optional but secure
def list_salary_payments():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT employee, amount, source, note, payment_date
        FROM salaries
        ORDER BY payment_date DESC
    """)
    payments = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('list_salary_payments.html', payments=payments)



# Kasse
@app.route('/kasse', methods=['GET', 'POST'])
def kasse():
    role = 'admin'  # Replace with session logic

    if request.method == 'POST':
        typ = request.form.get('typ')  # 'einzahlung' or 'auszahlung'
        betrag = request.form.get('betrag')
        beschreibung = request.form.get('beschreibung')
        username = 'current_username'  # Replace with actual user from session

        if typ not in ('einzahlung', 'auszahlung'):
            flash('Ungültiger Typ')
            return redirect(url_for('kasse'))

        try:
            amount = float(betrag)
            if amount <= 0:
                flash('Betrag muss größer als 0 sein')
                return redirect(url_for('kasse'))
        except Exception:
            flash('Ungültiger Betrag')
            return redirect(url_for('kasse'))

        if typ == 'auszahlung':
            amount = -amount

        query = """
            INSERT INTO cash_transactions (date, amount, type, description, username)
            VALUES (%s, %s, %s, %s, %s);
        """
        params = (datetime.now(), abs(amount), typ, beschreibung, username)
        execute_query(query, params)
        flash('Transaktion erfolgreich gespeichert')
        return redirect(url_for('kasse'))

    # Fetch transactions
    transactions = fetch_all("SELECT * FROM cash_transactions ORDER BY date DESC;")

    # Calculate current balance
    current_balance = sum(
        t['amount'] if t['type'] == 'einzahlung' else -t['amount'] for t in transactions
    )

    # Get today's date
    today = date.today()

    # 🔹 Fetch total sales from 'sales' table for today
    sales_query = "SELECT SUM(total_sale_price) AS total FROM sales WHERE DATE(sale_date) = %s;"
    sales_result = fetch_one(sales_query, (today,))
    total_sold_today = sales_result['total'] if sales_result['total'] is not None else 0

    # 🔹 Fetch total orders from 'orders' table for today
    orders_query = "SELECT SUM(total_price) AS total FROM orders WHERE DATE(date) = %s;"
    orders_result = fetch_one(orders_query, (today,))
    total_orders_today = orders_result['total'] if orders_result['total'] is not None else 0

    # Optional: Calculate theoretical cash balance
    total_balance = current_balance + total_sold_today - total_orders_today

    return render_template(
        'kasse.html',
        transactions=transactions,
        current_balance=current_balance,
        total_sold_today=total_sold_today,
        total_orders_today=total_orders_today,
        total_balance=total_balance,
        role=role
    )


# Delete_cash_transaction
@app.route('/admin/kasse/delete/<int:transaction_id>', methods=['POST'])
@login_required('admin')
def delete_cash_transaction(transaction_id):
    try:
        execute_query("DELETE FROM cash_transactions WHERE id = %s", (transaction_id,))
        flash('Transaktion gelöscht.', 'success')
    except Exception as e:
        flash('Fehler beim Löschen: ' + str(e), 'danger')
    return redirect(url_for('kasse'))



from flask import Flask, jsonify
import os
import barcode
from barcode.writer import ImageWriter

@app.route("/generate_barcode/<order_number>")
def generate_barcode(order_number):
    try:
        # Create directory if not exists
        barcode_dir = os.path.join("static", "barcodes")
        os.makedirs(barcode_dir, exist_ok=True)

        # Define the filename
        filename = f"code_barres_{order_number}.png"
        filepath = os.path.join(barcode_dir, filename)

        # Generate barcode if it doesn't already exist
        if not os.path.exists(filepath):
            EAN = barcode.get_barcode_class('code128')
            ean = EAN(order_number, writer=ImageWriter())
            ean.save(filepath[:-4])  # Remove ".png" as `.save` adds it automatically

        return jsonify({"status": "ok", "filename": f"/static/barcodes/{filename}"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})



from datetime import datetime
from decimal import Decimal, InvalidOperation

# Helper to parse date safely
def parse_date(date_val):
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, str):
        try:
            return datetime.fromisoformat(date_val)
        except ValueError:
            return None
    return None

def to_decimal(value, default=Decimal('0')):
    """Convert value to Decimal safely."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default

@app.template_filter('format_date_str')
def format_date_str(value):
    # Assume value is a string like "2023-07-24T15:32:10.123Z" or similar
    if not isinstance(value, str):
        return value
    return value.replace("T", " ")[:19]

# Seller Dashboard Route
from decimal import Decimal
from datetime import datetime


from datetime import date, datetime

@app.route('/seller')
@login_required('seller')
def seller_dashboard():
    username = session['username']

    # Existing sales and purchases fetching logic (if you still need those)
    user_sales = get_sales_for_user(username)
    user_purchases = get_purchases_for_user(username)

    # Calculate today's sales and purchases using your helper functions
    daily_sales_total = calculate_today_sales()
    daily_purchases_total = calculate_today_purchases()

    # Calculate daily net difference
    daily_net_difference = daily_sales_total - daily_purchases_total

    # You can keep your existing profit, monthly totals, etc. calculations here or adjust as needed
    # For example, let's just keep the previous monthly calculations based on user_sales
    flat_sales = []
    for sale in user_sales:
        sale_date = sale.get('sale_date')
        if isinstance(sale_date, str):
            sale_date = datetime.fromisoformat(sale_date)
        elif not sale_date:
            sale_date = datetime.now()

        quantity = Decimal(str(sale.get('quantity', 0)))
        sale_price = Decimal(str(sale.get('sale_price', '0')))
        purchase_price = Decimal(str(sale.get('purchase_price', '0')))
        total_price = sale_price * quantity
        profit = (sale_price - purchase_price) * quantity

        flat_sales.append({
            'date': sale_date,
            'product_name': sale.get('product_name', 'Unbekannt'),
            'quantity': quantity,
            'sale_price': sale_price,
            'purchase_price': purchase_price,
            'total_price': total_price,
            'profit': profit,
        })

    today = datetime.now().date()
    daily_profit = sum(sale['profit'] for sale in flat_sales if sale['date'].date() == today)
    monthly_profit = sum(sale['profit'] for sale in flat_sales if sale['date'].year == today.year and sale['date'].month == today.month)
    total_profit = sum(sale['profit'] for sale in flat_sales)
    monthly_total_order_price = sum(sale['total_price'] for sale in flat_sales if sale['date'].year == today.year and sale['date'].month == today.month)
    total_purchase_cost = sum(
        Decimal(str(p.get('purchase_price', '0'))) * Decimal(str(p.get('quantity', 0)))
        for p in user_purchases
    )
    total_balance = daily_sales_total - daily_purchases_total

    return render_template(
        'seller_dashboard.html',
        sales=flat_sales,
        purchases=user_purchases,
        daily_profit=float(daily_profit),
        monthly_profit=float(monthly_profit),
        total_profit=float(total_profit),
        total_purchase_cost=float(total_purchase_cost),
        total_balance=float(total_balance),
        monthly_total_order_price=float(monthly_total_order_price),
        daily_sales_total=float(daily_sales_total),
        daily_purchases_total=float(daily_purchases_total),
        daily_net_difference=float(daily_net_difference),
    )



# Seller: Seller History
@app.route('/seller/sales')
@login_required('seller')
def seller_sales():
    username = session.get('username', '').lower()
    
    # Load all sales (replace with your actual function)
    sales = load_sales()  # returns a list of sale dicts
    
    # Filter sales by matching user/seller - using .get() to avoid KeyError
    user_sales = [s for s in sales if s.get('user', '').lower() == username]
    
    # Optional: sort by date descending (if your sales have a 'date' field)
    user_sales.sort(key=lambda s: s.get('date', ''), reverse=True)
    
    return render_template('seller_sales.html', sales=user_sales)


# Load Items for User/Seller
def load_items_for_seller(username):
    all_items = load_items()
    filtered_items = []
    for item in all_items:
        seller = item.get('seller', 'admin')  # Default to admin if missing
        if seller in ('admin', username):
            filtered_items.append(item)
    return filtered_items

# List all the items for the seller
@app.route('/seller/items')
@login_required('seller')
def seller_items():
    username = session['username']
    items = load_items_for_seller(username)
    items = normalize_items(items)  # Ensure all items have 'name'
    items = items[::-1]
    return render_template('seller_items.html', items=items)




if __name__ == '__main__':
    
    # Ensure initial admin user exists
    users = load_users()
   
    app.run(debug=True)


