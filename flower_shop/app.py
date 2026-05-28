from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from mysql.connector import pooling
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os, time, smtplib, threading, hmac, hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'flowershop_kavya_bca_2024'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

RAZORPAY_KEY_ID     = 'rzp_test_SlAA8xAaqchmRq'
RAZORPAY_KEY_SECRET = 'Mv0Rjw1j5c16CMfv5wPI4PrI'

try:
    import razorpay
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    RAZORPAY_AVAILABLE = True
    print("[RAZORPAY] ✅ Razorpay loaded successfully!")
except ImportError:
    RAZORPAY_AVAILABLE = False
    razorpay_client = None
    print("[RAZORPAY] ❌ Razorpay not installed! Run: pip install razorpay")

EMAIL_ADDRESS  = 'abhishekkabanur888@gmail.com'
EMAIL_PASSWORD = 'jowqtelabvgnmevf'
EMAIL_NAME     = 'Bloom & Petal Flower Shop'

db_pool = pooling.MySQLConnectionPool(
    pool_name="flowerPool", pool_size=10, pool_reset_session=True,
    host='localhost', user='root', password='', database='flower_shop_db'
)

def get_db():
    return db_pool.get_connection()

def allowed_file(f):
    return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    if file and file.filename != '' and allowed_file(file.filename):
        fn = f"{int(time.time())}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        return fn
    return ''

def delete_image(fn):
    if fn:
        p = os.path.join(app.config['UPLOAD_FOLDER'], fn)
        if os.path.exists(p): os.remove(p)

def send_email_async(to, subject, html):
    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = f"{EMAIL_NAME} <{EMAIL_ADDRESS}>"
            msg['To']      = to
            msg.attach(MIMEText(html, 'html'))
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                s.sendmail(EMAIL_ADDRESS, to, msg.as_string())
            print(f"[EMAIL OK] {to}")
        except Exception as e:
            print(f"[EMAIL ERR] {e}")
    threading.Thread(target=_send, daemon=True).start()

def send_confirmation(name, email, oid, items, total, address, payment):
    rows = ''.join(f"<tr><td style='padding:8px;border-bottom:1px solid #eee'>🌸 {i['name']}</td><td style='padding:8px;border-bottom:1px solid #eee;text-align:center'>x{i['qty']}</td><td style='padding:8px;border-bottom:1px solid #eee;text-align:right;color:#c9736b'>₹{float(i['price'])*i['qty']:.2f}</td></tr>" for i in items)
    pay_label = "Cash on Delivery" if payment == "cod" else "Online Payment (Razorpay)"
    html = f"""<html><body style="font-family:sans-serif;background:#faf6f1">
    <div style="max-width:600px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#7a3f3a,#c9736b);padding:32px;text-align:center;color:white">
        <h1 style="margin:0">🌸 Order Confirmed!</h1>
        <p style="margin:8px 0 0;opacity:.9">Thank you for shopping with Bloom & Petal</p>
      </div>
      <div style="padding:28px">
        <p>Hi <strong>{name}</strong>,</p>
        <p style="color:#666">Your order is being prepared with love!</p>
        <div style="background:#faf6f1;border-left:4px solid #c9736b;border-radius:8px;padding:16px;margin:16px 0">
          <b>Order:</b> #ORD-{oid:04d}<br>
          <b>Payment:</b> {pay_label}<br>
          <b>Address:</b> {address}
        </div>
        <table style="width:100%;border-collapse:collapse"><tbody>{rows}</tbody>
          <tfoot><tr><td colspan="2" style="padding:12px;font-weight:700">Total</td>
          <td style="padding:12px;font-weight:700;color:#c9736b;text-align:right">₹{total:.2f}</td></tr></tfoot>
        </table>
        <div style="background:#eaf5eb;border-left:4px solid #4caf50;border-radius:8px;padding:14px;margin-top:16px">
          🚚 <b>Estimated delivery:</b> 2-3 business days
        </div>
      </div>
      <div style="background:#faf6f1;padding:20px;text-align:center;color:#999;font-size:13px">
        Bloom &amp; Petal Flower Shop
      </div>
    </div></body></html>"""
    send_email_async(email, f"🌸 Order Confirmed #ORD-{oid:04d} – Bloom & Petal", html)

def send_delivery(name, email, oid, address):
    html = f"""<html><body style="font-family:sans-serif;background:#faf6f1">
    <div style="max-width:600px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#2e7d32,#66bb6a);padding:32px;text-align:center;color:white">
        <h1 style="margin:0">🚚 Order Delivered!</h1>
        <p style="margin:8px 0 0;opacity:.9">Your flowers have arrived!</p>
      </div>
      <div style="padding:28px">
        <p>Hi <strong>{name}</strong>,</p>
        <p>Your order <strong>#ORD-{oid:04d}</strong> has been delivered to <strong>{address}</strong></p>
        <p style="color:#666;margin-top:16px">Thank you for choosing Bloom &amp; Petal! 🌸</p>
      </div>
      <div style="background:#faf6f1;padding:20px;text-align:center;color:#999;font-size:13px">
        Bloom &amp; Petal Flower Shop
      </div>
    </div></body></html>"""
    send_email_async(email, f"✅ Delivered! Order #ORD-{oid:04d} – Bloom & Petal", html)

def login_required(f):
    @wraps(f)
    def d(*a, **k):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login_page'))
        return f(*a, **k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **k):
        if 'admin' not in session:
            return redirect(url_for('login_page') + '?tab=admin')
        return f(*a, **k)
    return d

# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.route('/login-page')
def login_page():
    return render_template('login_page.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET': return redirect(url_for('login_page'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE email=%s", (request.form['email'],))
    user = cur.fetchone(); cur.close(); db.close()
    if user and check_password_hash(user['password'], request.form['password']):
        session['user_id'] = user['id']; session['user_name'] = user['name']; session['user_email'] = user['email']
        flash(f"Welcome back, {user['name']}! 🌸", 'success')
        return redirect(url_for('index'))
    flash('Invalid email or password.', 'danger')
    return redirect(url_for('login_page'))

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if 'admin' in session: return redirect(url_for('admin_dashboard'))
    if request.method == 'GET': return redirect(url_for('login_page') + '?tab=admin')
    if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
        session['admin'] = True; flash('Welcome Admin! 👑', 'success')
        return redirect(url_for('admin_dashboard'))
    flash('Wrong credentials!', 'danger')
    return redirect(url_for('login_page') + '?tab=admin')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login_page'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None); flash('Logged out.', 'info')
    return redirect(url_for('login_page') + '?tab=admin')

# ── CUSTOMER ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM flowers WHERE stock > 0 LIMIT 8"); flowers = cur.fetchall()
    cur.execute("SELECT * FROM categories"); categories = cur.fetchall()
    cur.close(); db.close()
    return render_template('index.html', flowers=flowers, categories=categories)

@app.route('/shop')
def shop():
    db = get_db(); cur = db.cursor(dictionary=True)
    cat = request.args.get('category',''); srch = request.args.get('search','')
    q = "SELECT f.*, c.name as category_name FROM flowers f JOIN categories c ON f.category_id=c.id WHERE f.stock>0"
    p = []
    if cat:  q += " AND c.name=%s"; p.append(cat)
    if srch: q += " AND f.name LIKE %s"; p.append(f'%{srch}%')
    cur.execute(q, p); flowers = cur.fetchall()
    cur.execute("SELECT * FROM categories"); categories = cur.fetchall()
    cur.close(); db.close()
    return render_template('shop.html', flowers=flowers, categories=categories)

@app.route('/flower/<int:fid>')
def flower_detail(fid):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT f.*, c.name as category_name FROM flowers f JOIN categories c ON f.category_id=c.id WHERE f.id=%s", (fid,))
    flower = cur.fetchone(); cur.close(); db.close()
    if not flower: flash('Not found.','danger'); return redirect(url_for('shop'))
    return render_template('flower_detail.html', flower=flower)

@app.route('/cart')
def cart():
    c = session.get('cart',{}); items = []; total = 0
    if c:
        db = get_db(); cur = db.cursor(dictionary=True)
        ids = list(c.keys())
        cur.execute(f"SELECT * FROM flowers WHERE id IN ({','.join(['%s']*len(ids))})", ids)
        for f in cur.fetchall():
            qty = c[str(f['id'])]; f['qty'] = qty; f['subtotal'] = float(f['price'])*qty
            total += f['subtotal']; items.append(f)
        cur.close(); db.close()
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add/<int:fid>', methods=['POST'])
def add_to_cart(fid):
    qty = int(request.form.get('qty',1)); c = session.get('cart',{})
    c[str(fid)] = c.get(str(fid),0) + qty; session['cart'] = c
    flash('Added to cart! 🌸','success')
    return redirect(request.referrer or url_for('shop'))

@app.route('/cart/remove/<int:fid>')
def remove_from_cart(fid):
    c = session.get('cart',{}); c.pop(str(fid),None); session['cart'] = c
    return redirect(url_for('cart'))

# ── CHECKOUT ──────────────────────────────────────────────────────────────────
@app.route('/checkout', methods=['GET','POST'])
@login_required
def checkout():
    c = session.get('cart',{})
    if not c: return redirect(url_for('cart'))
    db = get_db(); cur = db.cursor(dictionary=True)
    ids = list(c.keys())
    cur.execute(f"SELECT * FROM flowers WHERE id IN ({','.join(['%s']*len(ids))})", ids)
    fd = {str(f['id']): f for f in cur.fetchall()}
    cart_items = []; total = 0
    for fid, qty in c.items():
        if fid in fd:
            f = fd[fid]; sub = float(f['price'])*qty; total += sub
            cart_items.append({'name':f['name'],'price':f['price'],'qty':qty,'subtotal':sub})
    if request.method == 'POST':
        address = request.form['address']; pm = request.form.get('payment_method','cod')
        if pm == 'cod':
            cur.execute("INSERT INTO orders (user_id,total,address,status,payment_method) VALUES (%s,%s,%s,'Pending','cod')",
                        (session['user_id'], total, address))
            oid = cur.lastrowid; ei = []
            for fid, qty in c.items():
                if fid in fd:
                    f = fd[fid]
                    cur.execute("INSERT INTO order_items (order_id,flower_id,qty,price) VALUES (%s,%s,%s,%s)", (oid,fid,qty,f['price']))
                    cur.execute("UPDATE flowers SET stock=stock-%s WHERE id=%s", (qty,fid))
                    ei.append({'name':f['name'],'price':f['price'],'qty':qty})
            db.commit(); cur.close(); db.close(); session['cart'] = {}
            send_confirmation(session['user_name'], session.get('user_email',''), oid, ei, total, address, 'cod')
            flash(f'Order #ORD-{oid:04d} placed! 🌺 Check your email!','success')
            return redirect(url_for('orders'))
    cur.close(); db.close()
    return render_template('checkout.html', cart_items=cart_items, total=total,
                           customer_name=session['user_name'],
                           customer_email=session.get('user_email',''),
                           razorpay_key_id=RAZORPAY_KEY_ID)

# ── RAZORPAY ORDER CREATE (AJAX) ──────────────────────────────────────────────
@app.route('/create-razorpay-order', methods=['POST'])
@login_required
def create_razorpay_order():
    if not RAZORPAY_AVAILABLE:
        return jsonify({'error': 'Razorpay not installed. Run: pip install razorpay'}), 500
    try:
        data    = request.get_json()
        address = data.get('address','')
        c       = session.get('cart',{})
        if not c: return jsonify({'error': 'Cart is empty'}), 400
        db = get_db(); cur = db.cursor(dictionary=True)
        ids = list(c.keys())
        cur.execute(f"SELECT * FROM flowers WHERE id IN ({','.join(['%s']*len(ids))})", ids)
        fd = {str(f['id']): f for f in cur.fetchall()}
        cur.close(); db.close()
        total = sum(float(fd[fid]['price']) * qty for fid, qty in c.items() if fid in fd)
        amount_paise = int(total * 100)
        rzp_order = razorpay_client.order.create({'amount': amount_paise, 'currency': 'INR', 'payment_capture': 1})
        session['pending_order'] = {'address': address, 'total': total, 'cart': c, 'rzp_order_id': rzp_order['id']}
        return jsonify({'order_id': rzp_order['id'], 'amount': amount_paise, 'total': total})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── RAZORPAY VERIFY ───────────────────────────────────────────────────────────
@app.route('/payment/verify', methods=['POST'])
@login_required
def payment_verify():
    rzp_oid = request.form.get('razorpay_order_id')
    rzp_pid = request.form.get('razorpay_payment_id')
    rzp_sig = request.form.get('razorpay_signature')
    address = request.form.get('delivery_address','')
    msg = f"{rzp_oid}|{rzp_pid}".encode()
    gen = hmac.new(RAZORPAY_KEY_SECRET.encode(), msg, hashlib.sha256).hexdigest()
    # Debug: uncomment below to test signature matching
    # print(f"Generated: {gen}\nReceived:  {rzp_sig}")
    if gen == rzp_sig:
        pending = session.get('pending_order',{})
        if not address: address = pending.get('address','')
        total = pending.get('total', 0); c = pending.get('cart', session.get('cart',{}))
        db = get_db(); cur = db.cursor(dictionary=True)
        ids = list(c.keys())
        cur.execute(f"SELECT * FROM flowers WHERE id IN ({','.join(['%s']*len(ids))})", ids)
        fd = {str(f['id']): f for f in cur.fetchall()}
        cur.execute("INSERT INTO orders (user_id,total,address,status,payment_method) VALUES (%s,%s,%s,'Processing','online')",
                    (session['user_id'], total, address))
        oid = cur.lastrowid; ei = []
        for fid, qty in c.items():
            if fid in fd:
                f = fd[fid]
                cur.execute("INSERT INTO order_items (order_id,flower_id,qty,price) VALUES (%s,%s,%s,%s)", (oid,fid,int(qty),f['price']))
                cur.execute("UPDATE flowers SET stock=stock-%s WHERE id=%s", (int(qty),fid))
                ei.append({'name':f['name'],'price':f['price'],'qty':int(qty)})
        db.commit(); cur.close(); db.close()
        session['cart'] = {}; session.pop('pending_order', None)
        send_confirmation(session['user_name'], session.get('user_email',''), oid, ei, total, address, 'online')
        flash(f'Payment successful! 🎉 Order #ORD-{oid:04d} placed!','success')
        return redirect(url_for('orders'))
    flash('Payment verification failed.','danger')
    return redirect(url_for('checkout'))

@app.route('/orders')
@login_required
def orders():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC", (session['user_id'],))
    orders = cur.fetchall(); cur.close(); db.close()
    return render_template('orders.html', orders=orders)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        db = get_db(); cur = db.cursor()
        try:
            cur.execute("INSERT INTO users (name,email,password) VALUES (%s,%s,%s)",
                        (request.form['name'], request.form['email'], generate_password_hash(request.form['password'])))
            db.commit(); flash('Registered! Please login.','success')
            return redirect(url_for('login_page'))
        except: flash('Email already exists.','danger')
        finally: cur.close(); db.close()
    return render_template('register.html')

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) as cnt FROM orders"); orders_count = cur.fetchone()['cnt']
    cur.execute("SELECT IFNULL(SUM(total),0) as rev FROM orders"); revenue = cur.fetchone()['rev']
    cur.execute("SELECT COUNT(*) as cnt FROM users"); customers = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM flowers WHERE stock < 5"); low_stock = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM flowers"); total_flowers = cur.fetchone()['cnt']
    cur.execute("SELECT o.*, u.name as customer_name FROM orders o JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC LIMIT 8")
    recent = cur.fetchall()
    cur.execute("SELECT status, COUNT(*) as cnt FROM orders GROUP BY status")
    status_counts = {r['status']: r['cnt'] for r in cur.fetchall()}
    cur.execute("SELECT f.name, SUM(oi.qty) as sold FROM order_items oi JOIN flowers f ON oi.flower_id=f.id GROUP BY f.id ORDER BY sold DESC LIMIT 5")
    bestsellers = cur.fetchall(); cur.close(); db.close()
    return render_template('admin/dashboard.html', orders_count=orders_count, revenue=revenue,
        customers=customers, low_stock=low_stock, total_flowers=total_flowers,
        recent=recent, status_counts=status_counts, bestsellers=bestsellers)

@app.route('/admin/flowers')
@admin_required
def admin_flowers():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT f.*, c.name as cat FROM flowers f JOIN categories c ON f.category_id=c.id ORDER BY f.id DESC")
    flowers = cur.fetchall()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall()
    cur.close(); db.close()
    return render_template('admin/flowers.html', flowers=flowers, categories=cats)

@app.route('/admin/flowers/add', methods=['POST'])
@admin_required
def admin_add_flower():
    db = get_db(); cur = db.cursor()
    img = save_image(request.files['image']) if 'image' in request.files else ''
    cur.execute("INSERT INTO flowers (name,description,price,stock,category_id,image) VALUES (%s,%s,%s,%s,%s,%s)",
        (request.form['name'],request.form['description'],request.form['price'],request.form['stock'],request.form['category_id'],img))
    db.commit(); cur.close(); db.close(); flash('Flower added! 🌸','success')
    return redirect(url_for('admin_flowers'))

@app.route('/admin/flowers/edit/<int:fid>', methods=['GET','POST'])
@admin_required
def admin_edit_flower(fid):
    db = get_db(); cur = db.cursor(dictionary=True)
    if request.method == 'POST':
        cur.execute("SELECT image FROM flowers WHERE id=%s", (fid,)); row = cur.fetchone()
        existing = row['image'] if row else ''; img = existing
        if 'image' in request.files and request.files['image'].filename != '':
            new = save_image(request.files['image'])
            if new: delete_image(existing); img = new
        cur.execute("UPDATE flowers SET name=%s,description=%s,price=%s,stock=%s,category_id=%s,image=%s WHERE id=%s",
            (request.form['name'],request.form['description'],request.form['price'],request.form['stock'],request.form['category_id'],img,fid))
        db.commit(); cur.close(); db.close(); flash('Flower updated! 🌸','success')
        return redirect(url_for('admin_flowers'))
    cur.execute("SELECT * FROM flowers WHERE id=%s",(fid,)); flower = cur.fetchone()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall()
    cur.close(); db.close()
    return render_template('admin/edit_flower.html', flower=flower, categories=cats)

@app.route('/admin/flowers/delete/<int:fid>')
@admin_required
def admin_delete_flower(fid):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT image FROM flowers WHERE id=%s",(fid,)); row = cur.fetchone()
    if row: delete_image(row['image'])
    cur.execute("DELETE FROM flowers WHERE id=%s",(fid,))
    db.commit(); cur.close(); db.close(); flash('Deleted.','info')
    return redirect(url_for('admin_flowers'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    db = get_db(); cur = db.cursor(dictionary=True)
    sf = request.args.get('status','')
    q = "SELECT o.*, u.name as customer_name, u.email as customer_email FROM orders o JOIN users u ON o.user_id=u.id"
    p = []
    if sf: q += " WHERE o.status=%s"; p.append(sf)
    q += " ORDER BY o.created_at DESC"
    cur.execute(q, p); orders = cur.fetchall(); cur.close(); db.close()
    return render_template('admin/orders.html', orders=orders, status_filter=sf)

@app.route('/admin/orders/<int:oid>')
@admin_required
def admin_order_detail(oid):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT o.*, u.name as customer_name, u.email as customer_email FROM orders o JOIN users u ON o.user_id=u.id WHERE o.id=%s",(oid,))
    order = cur.fetchone()
    cur.execute("SELECT oi.*, f.name as flower_name, f.image FROM order_items oi JOIN flowers f ON oi.flower_id=f.id WHERE oi.order_id=%s",(oid,))
    items = cur.fetchall(); cur.close(); db.close()
    return render_template('admin/order_detail.html', order=order, items=items)

@app.route('/admin/orders/update/<int:oid>', methods=['POST'])
@admin_required
def admin_update_order(oid):
    ns = request.form['status']
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT o.*, u.name as customer_name, u.email as customer_email FROM orders o JOIN users u ON o.user_id=u.id WHERE o.id=%s",(oid,))
    order = cur.fetchone()
    cur.execute("UPDATE orders SET status=%s WHERE id=%s",(ns,oid))
    db.commit(); cur.close(); db.close()
    if ns == 'Delivered' and order:
        send_delivery(order['customer_name'], order['customer_email'], oid, order['address'])
        flash(f'Marked Delivered! Email sent to {order["customer_email"]}','success')
    else:
        flash('Status updated!','success')
    return redirect(request.referrer or url_for('admin_orders'))

@app.route('/admin/create-order', methods=['GET','POST'])
@admin_required
def admin_create_order():
    db = get_db(); cur = db.cursor(dictionary=True)
    if request.method == 'POST':
        uid = request.form['user_id']; addr = request.form['address']
        fids = request.form.getlist('flower_id[]'); qtys = request.form.getlist('qty[]')
        total = 0; fd = {}
        for fid, qty in zip(fids, qtys):
            qty = int(qty)
            if qty <= 0: continue
            cur.execute("SELECT * FROM flowers WHERE id=%s",(fid,)); f = cur.fetchone()
            if f: fd[fid] = {'flower':f,'qty':qty}; total += float(f['price'])*qty
        cur.execute("INSERT INTO orders (user_id,total,address,status,payment_method) VALUES (%s,%s,%s,'Processing','cod')",(uid,total,addr))
        oid = cur.lastrowid; ei = []
        for fid, d in fd.items():
            cur.execute("INSERT INTO order_items (order_id,flower_id,qty,price) VALUES (%s,%s,%s,%s)",(oid,fid,d['qty'],d['flower']['price']))
            cur.execute("UPDATE flowers SET stock=stock-%s WHERE id=%s",(d['qty'],fid))
            ei.append({'name':d['flower']['name'],'price':d['flower']['price'],'qty':d['qty']})
        cur.execute("SELECT name,email FROM users WHERE id=%s",(uid,)); cust = cur.fetchone()
        db.commit(); cur.close(); db.close()
        if cust: send_confirmation(cust['name'],cust['email'],oid,ei,total,addr,'cod')
        flash(f'Order #{oid} created!','success')
        return redirect(url_for('admin_orders'))
    cur.execute("SELECT id,name,email FROM users ORDER BY name"); users = cur.fetchall()
    cur.execute("SELECT f.*,c.name as cat FROM flowers f JOIN categories c ON f.category_id=c.id WHERE f.stock>0")
    flowers = cur.fetchall(); cur.close(); db.close()
    return render_template('admin/create_order.html', users=users, flowers=flowers)

@app.route('/admin/customers')
@admin_required
def admin_customers():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT u.*, COUNT(o.id) as total_orders, IFNULL(SUM(o.total),0) as total_spent FROM users u LEFT JOIN orders o ON u.id=o.user_id GROUP BY u.id ORDER BY total_spent DESC")
    customers = cur.fetchall(); cur.close(); db.close()
    return render_template('admin/customers.html', customers=customers)

@app.route('/admin/customers/<int:uid>')
@admin_required
def admin_customer_detail(uid):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE id=%s",(uid,)); user = cur.fetchone()
    cur.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC",(uid,)); orders = cur.fetchall()
    cur.close(); db.close()
    return render_template('admin/customer_detail.html', user=user, orders=orders)

@app.route('/admin/sales')
@admin_required
def admin_sales():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT IFNULL(SUM(total),0) as rev FROM orders WHERE status!='Cancelled'"); total_revenue = cur.fetchone()['rev']
    cur.execute("SELECT IFNULL(SUM(total),0) as rev FROM orders WHERE status='Delivered'"); delivered_revenue = cur.fetchone()['rev']
    cur.execute("SELECT COUNT(*) as cnt FROM orders WHERE status!='Cancelled'"); total_orders = cur.fetchone()['cnt']
    cur.execute("SELECT f.name,f.price,SUM(oi.qty) as units_sold,SUM(oi.qty*oi.price) as earnings FROM order_items oi JOIN flowers f ON oi.flower_id=f.id GROUP BY f.id ORDER BY earnings DESC")
    flower_sales = cur.fetchall()
    cur.execute("SELECT DATE_FORMAT(created_at,'%b %Y') as month,COUNT(*) as orders,SUM(total) as revenue FROM orders WHERE status!='Cancelled' GROUP BY DATE_FORMAT(created_at,'%Y-%m') ORDER BY MIN(created_at) DESC LIMIT 6")
    monthly = cur.fetchall()
    cur.execute("SELECT u.name,u.email,IFNULL(SUM(o.total),0) as spent,COUNT(o.id) as orders FROM users u JOIN orders o ON u.id=o.user_id WHERE o.status!='Cancelled' GROUP BY u.id ORDER BY spent DESC LIMIT 5")
    top_customers = cur.fetchall(); cur.close(); db.close()
    return render_template('admin/sales.html', total_revenue=total_revenue,
        delivered_revenue=delivered_revenue, total_orders=total_orders,
        flower_sales=flower_sales, monthly=monthly, top_customers=top_customers)

if __name__ == '__main__':
    app.run(debug=True)
