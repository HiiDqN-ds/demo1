from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import List, Dict
from psycopg2.extras import RealDictCursor
from dateutil import parser
from flask import session
from datetime import datetime, timedelta
from decimal import Decimal

DB_CONFIG = {
    'host': 'dpg-d20c8smuk2gs73c51nmg-a.oregon-postgres.render.com',
    'database': 'storemngm',
    'user': 'admin',
    'password': 'bq3zkOkTA5F13FaLHimwpsCnEsSFGJIs',
    'port': 5432
}

logger = logging.getLogger(__name__)


# Create DB connection
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# Fetch multiple rows
def fetch_all(query, params=None):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return cur.fetchall()

# Fetch single row
def fetch_one(query, params=None):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return cur.fetchone()

# Execute INSERT/UPDATE/DELETE
def execute_query(query, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            conn.commit()

# Load all users
def load_users():
    return fetch_all("SELECT * FROM users ORDER BY username;")
def load_all_order_items(order_id):
    query = """
        SELECT 
            p.order_date AS date,
            i.product_name,
            i.quantity,
            i.unit_price AS price,
            i.total_price
        FROM 
            purchases p
        JOIN 
            purchase_items i ON p.id = i.purchase_id
        WHERE 
            p.id = %s;
    """
    return fetch_all(query, (order_id,))


# Find user by username
def find_user(username):
    return fetch_one("SELECT * FROM users WHERE username = %s;", (username,))

# Insert user
def insert_user(user):
    query = """
        INSERT INTO users (username, password, role, profile_img, salary, activated)
        VALUES (%s, %s, %s, %s, %s, %s);
    """
    params = (
        user['username'],
        user['password'],
        user['role'],
        user.get('profile_img', ''),
        user.get('salary', 0.0),
        user.get('activated', False)
    )
    execute_query(query, params)

# Update user
def update_user(username, updates):
    query = """
        UPDATE users
        SET profile_img = %s,
            salary = %s,
            activated = %s
        WHERE username = %s
    """
    params = (
        updates.get('profile_img', ''),
        updates.get('salary', 0.0),
        updates.get('activated', False),
        username
    )
    execute_query(query, params)

# Delete user
def delete_user(username):
    execute_query("DELETE FROM users WHERE username = %s", (username,))



# Load all items from the database, ordered by name
# Used in listing all items, e.g., for display in admin dashboard
def load_items():
    return fetch_all("SELECT * FROM products ORDER BY product_name;")

# Find a single item by its ID
# Used when viewing or editing a specific item’s details
def find_item(item_id):
    return fetch_one("SELECT * FROM products WHERE id = %s;", (item_id,))

# Insert a new item into the database
# Called when an admin adds a new item via the add item form
def query_one(query, params=None):
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            result = cur.fetchone()  # fetch one record as dict
        return result
    except Exception as e:
        print("Database query error:", e)
        return None
    finally:
        if conn:
            conn.close()
# Update an existing item’s details in the database
# Used when an admin edits an existing item via the edit item form
def update_item(item_id, updates):
    query = """
        UPDATE products SET
            product_name = %s,
            barcode = %s,
            purchase_price = %s,
            selling_price = %s,
            min_selling_price = %s,
            quantity = %s,
            description = %s,
            photo_link = %s,
            date_added = NOW()
        WHERE id = %s;
    """
    params = (
        updates.get('product_name'),
        updates.get('barcode'),
        updates.get('purchase_price'),
        updates.get('selling_price'),
        updates.get('min_selling_price'),
        updates.get('quantity'),
        updates.get('description'),
        updates.get('photo_link'),
        item_id
    )
    execute_query(query, params)


# Delete an item from the database by its ID
# Called when an admin removes an item, usually via a delete action
# Assume this is your DB delete function
def db_delete_item(item_id):
    execute_query("DELETE FROM products WHERE id = %s;", (item_id,))


# Crud Sales
# Insert_sale_items
def insert_sale_items(conn, sale_id: str, items: List[Dict]):
    """
    Insert multiple sale items for a given sale_id into the sale_items table.
    
    Args:
        conn: psycopg2 connection object.
        sale_id: UUID string of the parent sale record.
        items: List of dicts, each with keys:
            'barcode', 'product_name', 'quantity', 'sale_price', 'total_price', 'purchase_price'.
    """
    try:
        with conn.cursor() as cur:
            for item in items:
                # Basic validation: ensure all required keys are present
                required_keys = ['barcode', 'product_name', 'quantity', 'sale_price', 'total_price', 'purchase_price']
                if not all(k in item for k in required_keys):
                    raise ValueError(f"Missing required keys in item: {item}")

                cur.execute("""
                    INSERT INTO sale_items 
                    (sale_id, barcode, product_name, quantity, sale_price, total_price, purchase_price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (
                    sale_id,
                    item['barcode'],
                    item['product_name'],
                    item['quantity'],
                    item['sale_price'],
                    item['total_price'],
                    item['purchase_price']
                ))
        conn.commit()
        logger.info(f"Inserted {len(items)} sale_items for sale_id {sale_id}.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting sale_items: {e}")
        raise


# insert_sale_with_items
def insert_sale_with_items(conn, sale):
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sales (sale_id, username, sale_date, total_sale_price)
                VALUES (%s, %s, %s, %s);
            """, (
                sale['sale_id'], 
                sale['user'], 
                sale['sale_date'],
                sale['total_sale_price']
            ))

            for item in sale['items']:
                cur.execute("""
                    INSERT INTO sale_items (sale_id, barcode, product_name, quantity, sale_price, total_price, purchase_price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (
                    sale['sale_id'],
                    item['barcode'],
                    item['product_name'],
                    item['quantity'],
                    item['sale_price'],
                    item['total_price'],
                    item['purchase_price']
                ))
        conn.commit()
        logger.info(f"Inserted sale {sale['sale_id']} with {len(sale['items'])} items.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to insert sale and items: {e}")
        raise


def get_sales_with_items():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    sale_id as order_id,
                    username as user,
                    sale_date as date,
                    total_sale_price as total_order_price
                FROM sales 
                ORDER BY sale_date DESC;
            """)
            sales = cur.fetchall()

            for sale in sales:
                cur.execute("""
                    SELECT product_name, barcode, quantity, sale_price, total_price, purchase_price
                    FROM sale_items 
                    WHERE sale_id = %s;
                """, (sale['order_id'],))
                sale['items'] = cur.fetchall()
        return sales
    except Exception as e:
        print(f"❌ Error fetching sales with items: {e}")
        return []
    finally:
        if conn:
            conn.close()

def load_sales():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT sale_id as order_id, username as user, sale_date as date, total_sale_price as total_order_price
                FROM sales ORDER BY sale_date DESC;
            """)
            sales = cur.fetchall()

            for sale in sales:
                cur.execute("""
                    SELECT product_name, barcode, quantity, sale_price, total_price, profit
                    FROM sale_items WHERE sale_id = %s;
                """, (sale['order_id'],))
                sale['items'] = cur.fetchall()  # fetch all sale items with profit included
        return sales
    finally:
        conn.close()



def delete_sales_order(order_id: str):
    """
    Deletes a sale and its associated items by order_id.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sale_items WHERE sale_id = %s;", (order_id,))
            cur.execute("DELETE FROM sales WHERE sale_id = %s;", (order_id,))
        conn.commit()
        logger.info(f"✅ Verkauf {order_id} und zugehörige Artikel erfolgreich gelöscht.")
        return True, f"Verkauf {order_id} gelöscht."
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"❌ Fehler beim Löschen des Verkaufs {order_id}: {e}")
        return False, f"Fehler beim Löschen des Verkaufs: {str(e)}"
    finally:
        if conn:
            conn.close()



def barcode_or_order_exists(value):
    query = """
    SELECT 1 FROM products WHERE barcode = %s
    UNION
    SELECT 1 FROM sales WHERE sale_id = %s
    LIMIT 1;
    """
    result = fetch_one(query, (value, value))
    return result is not None

def get_item_by_product_name(product_name):
    query = "SELECT * FROM products WHERE product_name = %s ORDER BY date_added DESC ;"
    return fetch_one(query, (product_name,))

def update_item_quantity_and_prices(product_name, quantity, purchase_price, selling_price, min_selling_price, description):
    query = """
    UPDATE products SET 
        quantity = %s,
        purchase_price = %s,
        selling_price = %s,
        min_selling_price = %s,
        description = %s,
        date_added = NOW()
    WHERE product_name = %s;
    """
    execute_query(query, (quantity, purchase_price, selling_price, min_selling_price, description, product_name))


# Crud Orders

def get_product_id_by_name_or_barcode(product_name, barcode=None):
    conn = get_connection()
    cur = conn.cursor()
    if barcode:
        cur.execute("SELECT id FROM products WHERE product_name = %s AND barcode = %s ORDER BY date_added DESC ", (product_name, barcode))
    else:
        cur.execute("SELECT id FROM products WHERE product_name = %s ORDER BY date_added DESC ", (product_name,))
    
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def get_orders(role, username, filter_user, filter_date):
    conn = get_connection()
    try:
        # Use DictCursor to get dict-like rows (keyed by column name)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Base query
        query = """
            SELECT
                order_number,
                product_name,
                price,
                selling_price,
                min_selling_price,
                quantity,
                description,
                total_price,
                date,
                "user",
                ref_number
            FROM orders
            WHERE 1=1
        """

        params = []

        # Role-based filtering:
        if role == 'seller':
            # Seller only sees own orders
            query += ' AND "user" = %s'
            params.append(username)

        # Filter by user if provided and allowed (admin only)
        if filter_user:
            if role == 'admin':
                query += ' AND "user" = %s'
                params.append(filter_user)
            else:
                # ignore filter_user for sellers, or you can return empty or error
                pass

        # Filter by date if provided (assuming date is stored as a date or datetime)
        if filter_date:
            query += ' AND date::text LIKE %s'
            params.append(f"{filter_date}%")  # for partial date filtering, e.g. YYYY-MM-DD

        # Order by date descending (newest first)
        query += ' ORDER BY date DESC'

        cur.execute(query, params)
        rows = cur.fetchall()

        orders = []
        for row in rows:
            # row is a DictRow, access by column name
            # Safely handle the date formatting
            raw_date = row['date']
            if isinstance(raw_date, (datetime, date)):
                date_str = raw_date.strftime("%Y-%m-%d")
            else:
                # If the date field is None or string, handle accordingly
                date_str = str(raw_date) if raw_date else ''

            orders.append({
                "order_number": row['order_number'],
                "product_name": row['product_name'],
                "price": float(row['price']) if row['price'] is not None else 0,
                "selling_price": float(row['selling_price']) if row['selling_price'] is not None else 0,
                "min_selling_price": float(row['min_selling_price']) if row['min_selling_price'] is not None else 0,
                "quantity": row['quantity'],
                "description": row['description'],
                "total_price": float(row['total_price']) if row['total_price'] is not None else 0,
                "date": date_str,
                "user": row['user'],
                "ref_number": row['ref_number'],
            })

        cur.close()
        return orders

    finally:
        conn.close()




def find_order_by_barcode(barcode):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE barcode = %s;", (barcode,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order


def get_order_by_number(order_number):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE order_number = %s;", (order_number,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

def add_order(order):
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Determine the barcode to use:
        barcode = order.get('ref_number')
        if not barcode or barcode.strip() == "":
            # Generate barcode if not provided (example: use product_name + timestamp or UUID)
            import uuid
            barcode = str(uuid.uuid4()).replace('-', '')[:12]  # 12-char random string
        
        # Construct photo_link based on barcode:
        photo_link = f"barcodes/code_barres_{barcode}.png"

        # Insert order into orders table - store barcode string in order_number
        query_insert_order = """
            INSERT INTO orders 
            (order_number, product_name, ref_number, description, price, selling_price, min_selling_price,
             quantity, total_price, date, "user", barcode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        cur.execute(query_insert_order, (
            barcode,                   # order_number = barcode string
            order['product_name'],
            barcode,                   # ref_number = same barcode string
            order.get('description'),
            order['price'],
            order['selling_price'],
            order['min_selling_price'],
            order['quantity'],
            order['total_price'],
            order['date'],
            order['user'],
            barcode                    # barcode column in orders also stores barcode string
        ))

        # Insert or update product in products table
        query_upsert_product = """
            INSERT INTO products 
            (product_name, barcode, purchase_price, selling_price, min_selling_price, quantity, description, seller, date_added, photo_link)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (barcode) DO UPDATE SET
                quantity = products.quantity + EXCLUDED.quantity,
                selling_price = EXCLUDED.selling_price,
                min_selling_price = EXCLUDED.min_selling_price,
                purchase_price = EXCLUDED.purchase_price,
                description = COALESCE(EXCLUDED.description, products.description),
                seller = COALESCE(EXCLUDED.seller, products.seller),
                date_added = COALESCE(EXCLUDED.date_added, products.date_added),
                photo_link = COALESCE(EXCLUDED.photo_link, products.photo_link);
        """
        cur.execute(query_upsert_product, (
            order['product_name'],
            barcode,                 # barcode string here
            order['price'],          # purchase_price
            order['selling_price'],
            order['min_selling_price'],
            order['quantity'],
            order.get('description'),
            order.get('user'),       # seller
            order.get('date'),
            photo_link               # photo link with barcode path
        ))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Error saving order and product: {e}")

    finally:
        cur.close()
        conn.close()





def update_order(order_number, order_data):
    conn = get_connection()
    cur = conn.cursor()
    query = """
        UPDATE orders SET
            product_name=%s,
            ref_number=%s,
            description=%s,
            price=%s,
            selling_price=%s,
            min_selling_price=%s,
            quantity=%s,
            total_price=%s,
            date=%s,
            "user"=%s,
            barcode=%s
        WHERE order_number=%s;
    """
    cur.execute(query, (
        order_data['product_name'], order_data.get('ref_number'), order_data.get('description'),
        order_data['price'], order_data['selling_price'], order_data['min_selling_price'],
        order_data['quantity'], order_data['total_price'], order_data['date'],
        order_data['user'], order_data.get('barcode'), order_number
    ))
    conn.commit()
    cur.close()
    conn.close()

def delete_order(order_number):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE order_number = %s;", (order_number,))
    conn.commit()
    cur.close()
    conn.close()


def insert_salary_payment(record):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO salaries (employee, amount, source, note, payment_date)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        record['employee'],
        record['amount'],
        record['source'],
        record['note'],
        record['payment_date']
    ))
    conn.commit()
    cur.close()
    conn.close()


def load_orders():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT
            date,
            product_name,
            quantity,
            price,
            total_price
        FROM orders
        ORDER BY date DESC
    """)
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return orders
from datetime import datetime, timedelta

def get_old_stock_notifications(items, days_old=21):
    notifications = []
    threshold_date = datetime.now().date() - timedelta(days=days_old)
    for item in items:
        try:
            date_str = item.get('date_added') or item.get('added_date')
            barcode = item.get('barcode')
            product_name = item.get('product_name') or item.get('name') or "Unbekannt"
            if not date_str:
                continue
            date_obj = datetime.fromisoformat(date_str).date() if isinstance(date_str, str) else date_str
            if date_obj < threshold_date:
                notifications.append({
                    'message': f"⏳ Old stock: {product_name} added on {date_obj} (> {days_old} days)",
                    'type': 'old_stock',
                    'barcode': barcode
                })
        except Exception:
            continue
    return notifications

def get_low_stock_notifications(items, threshold=5):
    notifications = []
    dismissed = session.get('dismissed_notifications', [])

    for item in items:
        try:
            quantity = int(item.get('quantity', 0))
            barcode = item.get('barcode', '')
            name = item.get('product_name', 'Unknown')

            if quantity < threshold and barcode not in dismissed:
                notifications.append({
                    'type': 'low_stock',
                    'barcode': barcode,
                    'message': f"❗ Low stock: {name} (Quantity: {quantity})"
                })
        except Exception:
            continue

    return notifications


from datetime import date

def calculate_today_profit_and_sales():
    today = date.today()
    query = """
        SELECT 
            SUM((sale_price - purchase_price) * quantity) AS profit,
            SUM(sale_price * quantity) AS revenue
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE DATE(s.sale_date) = %s;
    """
    result = fetch_one(query, (today,))
    return {
        'today_profit': round(result['profit'] or 0, 2),
        'today_sales': round(result['revenue'] or 0, 2)
    }

def calculate_kassenstand(kasse_balance, einnahmen_heute, ausgaben_heute):
    """
    Calculate the current cash balance including today's sales and purchases.
    
    Args:
        kasse_balance (float): Aktueller Kassenstand (cash register balance).
        einnahmen_heute (float): Einnahmen aus Verkäufen heute (today's sales).
        ausgaben_heute (float): Ausgaben aus Bestellungen heute (today's purchases).
        
    Returns:
        float: Berechneter Kassenstand (calculated cash balance).
    """
    return round(kasse_balance + einnahmen_heute - ausgaben_heute, 2)


def calculate_revenue(start_date, end_date):
    """
    Calculate total revenue from sale_items between start_date and end_date.
    
    Args:
        start_date (date or datetime): Start date of period.
        end_date (date or datetime): End date of period.
        
    Returns:
        float: Total revenue (sum of sale_price * quantity).
    """
    query = """
        SELECT SUM(sale_price * quantity) AS revenue
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE s.sale_date >= %s AND s.sale_date <= %s;
    """
    result = fetch_one(query, (start_date, end_date))
    return round(result['revenue'] or 0, 2)


def calculate_today_profit():
    """
    Calculate today's profit as the sum of (sale_price - purchase_price) * quantity for all items sold today.
    
    Returns:
        float: Total profit for today.
    """
    from datetime import datetime, date

    now = datetime.now()
    today = now.date()
    
    query = """
        SELECT SUM((sale_price - purchase_price) * quantity) AS profit
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE s.sale_date >= %s AND s.sale_date <= %s;
    """
    
    # Use today's date from midnight to 23:59:59 to include all sales of the day
    start_datetime = datetime.combine(today, datetime.min.time())
    end_datetime = datetime.combine(today, datetime.max.time())
    
    result = fetch_one(query, (start_datetime, end_datetime))
    return round(result['profit'] or 0, 2)

def calculate_monthly_sales():
    """
    Calculate total sales (sum of sale_price * quantity) for the current month.
    """
    now = datetime.now()
    today = now.date()
    first_day_of_month = today.replace(day=1)
    start_datetime = datetime.combine(first_day_of_month, datetime.min.time())
    end_datetime = datetime.combine(today, datetime.max.time())

    query = """
        SELECT SUM(sale_price * quantity) AS revenue
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE s.sale_date >= %s AND s.sale_date <= %s;
    """
    result = fetch_one(query, (start_datetime, end_datetime))
    return round(result['revenue'] or 0, 2)


def get_kasse_cash():
    """Fetch current cash value from Kasse table."""
    result = fetch_one("SELECT balance FROM kasse ORDER BY id DESC LIMIT 1")
    return round(result['balance'] or 0, 2)

def calculate_today_sales():
    """Calculate today's total sales revenue (brutto)."""
    today = date.today()
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())

    query = """
        SELECT SUM(sale_price * quantity) AS revenue
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE s.sale_date BETWEEN %s AND %s;
    """
    result = fetch_one(query, (start_dt, end_dt))
    return round(result['revenue'] or 0, 2)

def calculate_today_purchases():
    """Calculate today's total purchase expenses."""
    today = date.today()
    query = """
        SELECT SUM(total_price) AS expenses
        FROM orders
        WHERE date = %s;
    """
    result = fetch_one(query, (today,))
    return round(result['expenses'] or 0, 2)



def load_kasse_balance():
    query = "SELECT amount FROM cash_transactions ORDER BY id DESC LIMIT 1;"
    result = fetch_one(query)
    return float(result['amount']) if result and result['amount'] is not None else 0.0


def calculate_kassenstand():
    """Compute: Kasse + Einnahmen - Ausgaben"""
    cash = get_kasse_cash()
    sales_today = calculate_today_sales()
    purchases_today = calculate_today_purchases()
    return {
        "kasse_cash": cash,
        "taegliche_einnahmen": sales_today,
        "taegliche_ausgaben": purchases_today,
        "berechneter_kassenstand": round(cash + sales_today - purchases_today, 2)
    }

def calculate_total_orders():
    query = "SELECT SUM(total_price) AS total_orders FROM orders;"
    result = fetch_one(query)
    return float(result['total_orders']) if result and result['total_orders'] is not None else 0.0



def get_sales_for_user(username):
    query = """
        SELECT 
            si.sale_id,
            si.sale_id,
            si.product_name,
            si.quantity,
            si.sale_price,
            si.purchase_price,
            si.total_price,
            si.profit,
            s.sale_date
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.sale_id
        WHERE s.username = %s
        ORDER BY s.sale_date DESC
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (username,))
            rows = cur.fetchall()
            # Parse sale_date strings to datetime objects
            for row in rows:
                if isinstance(row['sale_date'], str):
                    row['sale_date'] = parser.parse(row['sale_date'])
            return rows
    finally:
        conn.close()



def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
    

from psycopg2.extras import RealDictCursor
from dateutil import parser

def get_purchases_for_user(username):
    query = """
        SELECT
            order_number,
            product_name,
            quantity,
            price,
            total_price,
            date,
            "user"
        FROM orders
        WHERE "user" = %s
        ORDER BY date DESC
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (username,))
            purchases = cur.fetchall()
            # parse dates if needed
            for p in purchases:
                if isinstance(p['date'], str):
                    p['date'] = parser.parse(p['date'])
            return purchases
    finally:
        conn.close()


def execute_query(query, params):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        conn.commit()   # <-- Make sure this is here!
    except Exception as e:
        print("Query failed:", e)
    finally:
        cur.close()
        conn.close()