from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.database import db, User, Product, bcrypt, Cart, CartItem, get_user_data
from functools import wraps
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from forms import LoginForm, RegistrationForm
import time
from controllers.user_controller import user_dashboard

app = Flask(__name__,
            template_folder='views/templates',
            static_folder='views/static')
app.config['SECRET_KEY'] = 'rahasia123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///toko_komputer.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'views/static/uploads'

# Tambahkan decorator untuk membatasi akses admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Anda tidak memiliki akses ke halaman ini!', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login terlebih dahulu!'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)

# Pastikan folder upload ada
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def home():
    # Ambil 4 produk terbaru
    latest_products = Product.query.order_by(Product.created_at.desc()).limit(4).all()
    
    # Ambil 4 produk terlaris (misalnya berdasarkan stok terendah)
    best_sellers = Product.query.order_by(Product.stock.asc()).limit(4).all()
    
    # Ambil kategori dengan jumlah produknya
    categories_data = db.session.query(
        Product.category,
        db.func.count(Product.id).label('count')
    ).group_by(Product.category).all()
    
    # Definisikan icon dan warna untuk setiap kategori
    category_icons = {
        'Laptop': {'icon': 'laptop', 'color': 'primary'},
        'Desktop': {'icon': 'desktop', 'color': 'success'},
        'Komponen': {'icon': 'microchip', 'color': 'info'},
        'Aksesoris': {'icon': 'keyboard', 'color': 'warning'},
    }
    
    # Format data kategori
    categories = []
    for cat_name, count in categories_data:
        icon_data = category_icons.get(cat_name, {'icon': 'box', 'color': 'secondary'})
        categories.append({
            'name': cat_name,
            'count': count,
            'icon': icon_data['icon'],
            'color': icon_data['color']
        })
    
    return render_template('home.html',
                         latest_products=latest_products,
                         best_sellers=best_sellers,
                         categories=categories)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash(f'Selamat datang kembali, {user.name}!', 'success')
            # Redirect ke home untuk semua user
            return redirect(url_for('home'))
        flash('Username atau password salah!', 'error')
    
    # Render home content untuk background
    home_content = render_template('_home_content.html',
                                latest_products=Product.query.order_by(Product.created_at.desc()).limit(4).all(),
                                best_sellers=Product.query.order_by(Product.stock.asc()).limit(4).all())
    
    return render_template('login.html', form=form, home_content=home_content)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('login'))

@app.route('/products')
def products():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'name')  # Default sort by name
    
    query = Product.query
    
    # Search functionality
    if search:
        search_terms = search.split()
        conditions = []
        for term in search_terms:
            conditions.append(
                db.or_(
                    Product.name.ilike(f'%{term}%'),
                    Product.description.ilike(f'%{term}%'),
                    Product.category.ilike(f'%{term}%')
                )
            )
        query = query.filter(db.or_(*conditions))
    
    # Category filter
    if category:
        query = query.filter_by(category=category)
    
    # Sorting
    if sort == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort == 'newest':
        query = query.order_by(Product.created_at.desc())
    else:  # default sort by name
        query = query.order_by(Product.name.asc())
    
    products = query.all()
    categories = db.session.query(Product.category).distinct().all()
    
    return render_template('products.html',
                         products=products,
                         categories=categories,
                         search=search,
                         selected_category=category,
                         selected_sort=sort)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    # Hanya admin yang bisa menambah produk
    if request.method == 'POST':
        try:
            # Handle image upload
            image_url = None
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Tambahkan timestamp untuk menghindari nama file yang sama
                    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_url = f'uploads/{filename}'

            product = Product(
                name=request.form['name'],
                description=request.form['description'],
                price=float(request.form['price']),
                stock=int(request.form['stock']),
                category=request.form['category'],
                supplier=request.form['supplier'],
                image_url=image_url
            )
            db.session.add(product)
            db.session.commit()
            flash('Produk berhasil ditambahkan!', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            flash(f'Terjadi kesalahan: {str(e)}', 'error')
            db.session.rollback()
            
    return render_template('product_form.html', mode='add')

@app.route('/product/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    try:
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.stock = int(request.form['stock'])
        product.category = request.form['category']
        product.supplier = request.form['supplier']
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                # Delete old image if exists
                if product.image_url:
                    old_file = os.path.join(app.config['UPLOAD_FOLDER'], 
                                          product.image_url.split('/')[-1])
                    if os.path.exists(old_file):
                        os.remove(old_file)
                
                # Save new image
                filename = secure_filename(file.filename)
                filename = f"{int(time.time())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                product.image_url = f'uploads/{filename}'
        
        db.session.commit()
        flash('Produk berhasil diupdate!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/product/delete/<int:id>')
@login_required
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    try:
        # Delete product image if exists
        if product.image_url:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                   product.image_url.split('/')[-1])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(product)
        db.session.commit()
        flash('Produk berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('admin_dashboard'))

# API Endpoints
@app.route('/api/products')
@login_required
def api_products():
    products = Product.query.all()
    return jsonify([product.to_dict() for product in products])

@app.route('/api/products/<int:id>')
@login_required
def api_product(id):
    product = Product.query('/api/products/<int:id>')
    return jsonify(product.to_dict())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user = User(
                username=form.username.data,
                name=form.name.data,
                role='customer'
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Terjadi kesalahan: {str(e)}', 'error')
            db.session.rollback()
    return render_template('register.html', form=form)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    # Get page number from query parameter, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 5  # Mengubah dari 10 menjadi 5 items per halaman
    
    # Get products with pagination
    products = Product.query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    
    # Get total counts
    total_products = Product.query.count()
    total_users = User.query.count()
    total_customers = User.query.filter_by(role='customer').count()
    
    return render_template('admin/dashboard.html',
                         products=products,
                         total_products=total_products,
                         total_users=total_users,
                         total_customers=total_customers)

@app.route('/admin/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

# User Management Routes
@app.route('/admin/user/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    try:
        user = User(
            username=request.form['username'],
            name=request.form['name'],
            role=request.form['role']
        )
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        flash('User berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('manage_users'))

@app.route('/admin/user/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    try:
        user.username = request.form['username']
        user.name = request.form['name']
        user.role = request.form['role']
        if request.form['password']:
            user.set_password(request.form['password'])
        db.session.commit()
        flash('User berhasil diupdate!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('manage_users'))

@app.route('/admin/user/delete/<int:id>')
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.is_admin() and User.query.filter_by(role='admin').count() == 1:
        flash('Tidak dapat menghapus admin terakhir!', 'error')
        return redirect(url_for('manage_users'))
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        db.session.rollback()
    return redirect(url_for('manage_users'))

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        # Update informasi dasar
        current_user.username = request.form['username']
        current_user.name = request.form['name']
        
        # Update password jika diisi
        if request.form['password']:
            current_user.set_password(request.form['password'])
        
        # Handle upload foto profil
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                # Hapus foto lama jika ada
                if current_user.profile_image:
                    old_file = os.path.join(app.config['UPLOAD_FOLDER'], 
                                          current_user.profile_image.split('/')[-1])
                    if os.path.exists(old_file):
                        os.remove(old_file)
                
                # Simpan foto baru
                filename = secure_filename(file.filename)
                filename = f"profile_{current_user.id}_{int(time.time())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.profile_image = f'uploads/{filename}'
        
        db.session.commit()
        flash('Profil berhasil diupdate!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('profile'))

@app.route('/product/<int:id>')
def product_detail(id):
    product = Product.query.get_or_404(id)
    return render_template('product_detail.html', product=product)

@app.route('/cart')
@login_required
def view_cart():
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.session.add(cart)
        db.session.commit()
    return render_template('cart.html', cart=cart)

@app.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    if not cart:
        cart = Cart(user_id=current_user.id)
        db.session.add(cart)
        db.session.commit()
    
    product = Product.query.get_or_404(product_id)
    
    # Cek stok tersedia
    if product.stock <= 0:
        flash('Maaf, stok produk habis', 'error')
        return redirect(url_for('product_detail', id=product_id))
        
    try:
        cart_item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()
        
        if cart_item:
            # Jika item sudah ada di keranjang, tambah quantity
            if product.stock > 0:
                cart_item.quantity += 1
                product.stock -= 1
            else:
                flash('Maaf, stok tidak mencukupi', 'error')
                return redirect(url_for('product_detail', id=product_id))
        else:
            # Jika item belum ada di keranjang
            if product.stock > 0:
                cart_item = CartItem(cart_id=cart.id, product_id=product_id)
                product.stock -= 1
                db.session.add(cart_item)
            else:
                flash('Maaf, stok tidak mencukupi', 'error')
                return redirect(url_for('product_detail', id=product_id))
        
        db.session.commit()
        flash('Produk berhasil ditambahkan ke keranjang!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Terjadi kesalahan saat menambahkan ke keranjang', 'error')
        
    return redirect(url_for('view_cart'))

@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart_item(item_id):
    data = request.get_json()
    cart_item = CartItem.query.get_or_404(item_id)
    
    if cart_item.cart.user_id != current_user.id:
        return jsonify({'success': False}), 403
    
    try:
        product = Product.query.get(cart_item.product_id)
        
        if data['action'] == 'increase':
            # Cek stok tersedia
            if product.stock > 0:
                cart_item.quantity += 1
                product.stock -= 1
            else:
                return jsonify({'success': False, 'message': 'Stok tidak mencukupi'})
                
        elif data['action'] == 'decrease':
            if cart_item.quantity > 0:
                cart_item.quantity = max(0, cart_item.quantity - 1)
                product.stock += 1
                
            if cart_item.quantity == 0:
                db.session.delete(cart_item)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'new_quantity': cart_item.quantity if cart_item.quantity > 0 else 0,
            'new_stock': product.stock
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_cart_item(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    
    if cart_item.cart.user_id != current_user.id:
        return jsonify({'success': False}), 403
    
    try:
        # Kembalikan stok
        product = Product.query.get(cart_item.product_id)
        product.stock += cart_item.quantity
        
        db.session.delete(cart_item)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cart/clear', methods=['POST'])
@login_required
def clear_cart():
    try:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
        if cart:
            # Kembalikan semua stok
            for item in cart.items:
                product = Product.query.get(item.product_id)
                product.stock += item.quantity
                
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/user/dashboard')
def user_dashboard_route():
    return user_dashboard()

if __name__ == '__main__':
    with app.app_context():
        # Buat tabel jika belum ada
        db.create_all()
        
        # Cek apakah user admin sudah ada
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            # Buat user admin default
            admin = User(
                username='admin',
                name='Administrator',
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            try:
                db.session.commit()
                print('User admin berhasil dibuat!')
            except Exception as e:
                print(f'Terjadi kesalahan: {str(e)}')
                db.session.rollback()
        else:
            print('User admin sudah ada')
            
    app.run(debug=True) 