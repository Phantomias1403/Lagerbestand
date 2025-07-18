import csv
from io import StringIO
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
import os
from werkzeug.utils import secure_filename

from . import db
from .models import User, Article, Movement, Order, OrderItem, Category, EndingCategory, Message
from .utils import (
    get_setting,
    set_setting,
    user_management_enabled,
    get_categories,
    category_from_sku,
    get_category_prefixes,
    price_from_sku,
    price_from_suffix,
    csv_multiplier_from_suffix,
    get_default_price,
    get_default_minimum_stock,
    send_email,
    generate_reset_token,
    verify_reset_token,
)

from datetime import datetime



def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_app.config.get('ENABLE_USER_MANAGEMENT'):
            if not current_user.is_authenticated or not current_user.is_admin:
                flash('Adminrechte erforderlich')
                return redirect(url_for('main.index'))
        return func(*args, **kwargs)
    return wrapper

def staff_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_app.config.get('ENABLE_USER_MANAGEMENT'):
            if not current_user.is_authenticated or not current_user.has_staff_rights():
                flash('Mitarbeiterrechte erforderlich')
                return redirect(url_for('main.index'))
        return func(*args, **kwargs)
    return wrapper



def login_optional(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if user_management_enabled():
            return login_required(func)(*args, **kwargs)
        return func(*args, **kwargs)
    return wrapper


bp = Blueprint('main', __name__)

@bp.app_context_processor
def inject_config():
    return dict(enable_user_management=user_management_enabled())


@bp.route('/')
def index():
    if user_management_enabled() and not current_user.is_authenticated:
        return redirect(url_for('main.select_profile'))
    query = Article.query
    search = request.args.get('search')
    if search:
        query = query.filter((Article.name.contains(search)) | (Article.sku.contains(search)))
    category = request.args.get('category')
    if category:
        query = query.filter_by(category=category)
    understock = request.args.get('understock')
    if understock == '1':
        query = query.filter(Article.stock < Article.minimum_stock)
    no_secondary = request.args.get('no_secondary')
    if no_secondary == '1':
        query = query.filter(
            (Article.location_secondary == None) |
            (Article.location_secondary == '')
        )
    articles = query.all()
    categories = get_categories()
    return render_template('index.html', articles=articles, categories=categories, selected_category=category)

@bp.route('/profiles')
def select_profile():
    if not user_management_enabled():
        return redirect(url_for('main.index'))
    users = User.query.all()
    return render_template('profile_select.html', users=users)



@bp.route('/login', methods=['GET', 'POST'])
def login():
    if not user_management_enabled():
        return redirect(url_for('main.index'))
    preselect_id = request.args.get('user_id')    
    preselect_user = None
    if preselect_id and preselect_id.isdigit():
        preselect_user = User.query.get(int(preselect_id))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('main.index'))
        flash('Ungültige Anmeldung')
    return render_template('login.html', preselect_user=preselect_user)


@bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password_request():
    if not user_management_enabled():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if user and user.email:
            token = generate_reset_token(user.id)
            reset_link = url_for('main.reset_password_token', token=token, _external=True)
            try:
                send_email(user.email, 'Passwort zurücksetzen',
                           f'Folge diesem Link, um dein Passwort zu ändern: {reset_link}')
                flash('E-Mail zum Zurücksetzen wurde gesendet')
            except Exception:
                flash('E-Mail konnte nicht gesendet werden')
            return redirect(url_for('main.login'))
        flash('E-Mail nicht gefunden')
    return render_template('reset_password_request.html')


@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    if not user_management_enabled():
        return redirect(url_for('main.index'))

    user_id = verify_reset_token(token)
    if not user_id:
        flash('Link ist ungültig oder abgelaufen')
        return redirect(url_for('main.reset_password_request'))

    user = User.query.get(user_id)
    if not user:
        flash('Benutzer nicht gefunden')
        return redirect(url_for('main.reset_password_request'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        if password:
            user.set_password(password)
            db.session.commit()
            flash('Passwort wurde zurückgesetzt')
            return redirect(url_for('main.login'))
        flash('Ungültige Daten')
    return render_template('reset_password_form.html')

@bp.route('/logout')
@login_optional
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/profile', methods=['GET', 'POST'])
@login_optional
def profile():
    if not user_management_enabled():
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        gender = request.form.get('gender', '').strip()
        bio = request.form.get('bio', '').strip()
        file = request.files.get('profile_image')

        if username and username != current_user.username:
            if User.query.filter_by(username=username).first():
                flash('Benutzername existiert bereits.')
                return redirect(url_for('main.profile'))
            current_user.username = username

        if email and email != current_user.email:
            if User.query.filter_by(email=email).first():
                flash('E-Mail existiert bereits.')
                return redirect(url_for('main.profile'))
            current_user.email = email

        if password:
            current_user.set_password(password)

        if name:
            current_user.name = name
        if gender:
            current_user.gender = gender
        current_user.bio = bio
        if file and file.filename:
            filename = secure_filename(file.filename)
            folder = current_app.config['PROFILE_IMAGE_FOLDER']
            base, ext = os.path.splitext(filename)
            counter = 1
            path = os.path.join(folder, filename)
            while os.path.exists(path):
                filename = f"{base}_{counter}{ext}"
                path = os.path.join(folder, filename)
                counter += 1
            file.save(path)
            current_user.profile_image = f"profile_pics/{filename}"


        db.session.commit()
        flash('Profil aktualisiert')
        return redirect(url_for('main.profile'))

    return render_template('profile.html')

@bp.route('/nils')
@login_optional
def nils():
    return render_template('nils.html')

@bp.route('/worker')
@login_optional
def worker():
    return render_template('worker.html')

@bp.route('/dick')
@login_optional
def frauen_tab():
    """Simple page shown only to the user named 'Frauen'."""
    return render_template('dick.html')


@bp.route('/article/new', methods=['GET', 'POST'])
@login_optional
@staff_required
def new_article():
    if request.method == 'POST':
        if Article.query.filter_by(sku=request.form['sku']).first():
            flash('Artikel mit dieser SKU existiert bereits.')
            return redirect(url_for('main.new_article'))

        # Kategorie aus Formular oder anhand der SKU ableiten
        category = request.form.get('category', '').strip()
        if not category:
            guess = category_from_sku(request.form['sku'])
            category = guess or 'Sticker'

        default_min = get_default_minimum_stock(category)

        article = Article(
            name=request.form['name'],
            sku=request.form['sku'],
            category=category,
            stock=int(request.form['stock']),
            price=0.0,
            location_primary=request.form['location_primary'],
            location_secondary=request.form['location_secondary'],
            image=request.form.get('image'),
            minimum_stock=default_min
        )

        price_raw = request.form.get('price', '').strip()
        if price_raw:
            try:
                article.price = float(price_raw.replace(',', '.'))  # Dezimal-Komma erlauben
            except ValueError:
                flash('Ungültiger Preis. Bitte Zahl mit Punkt oder Komma eingeben.')
                return redirect(url_for('main.new_article'))
        else:
            # Nur wenn das Feld leer ist, Standardpreis berechnen
            p = price_from_suffix(article.sku, article.category)
            if p is None:
                p = price_from_sku(article.sku)
            if p is None:
                p = get_default_price(article.category)
            article.price = p or 0.0
        db.session.add(article)
        db.session.commit()
        flash('Artikel erstellt')
        return redirect(url_for('main.index'))

    categories = get_categories()
    return render_template('article_form.html', categories=categories)




@bp.route('/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_optional
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    if user_management_enabled() and (not current_user.is_authenticated or not current_user.has_staff_rights()):
        flash('Keine Rechte zum Bearbeiten')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        article.name = request.form['name']
        article.sku = request.form['sku']
        article.category = request.form['category']
        article.stock = int(request.form['stock'])
        article.minimum_stock = int(request.form.get('minimum_stock', 0))
        article.location_primary = request.form['location_primary']
        article.location_secondary = request.form['location_secondary']
        price_raw = request.form.get('price', '').strip()
        if price_raw:
            try:
                article.price = float(price_raw)
            except ValueError:
                pass
        article.image = request.form.get('image')
        db.session.commit()
        flash('Artikel aktualisiert')
        return redirect(url_for('main.index'))
    categories = get_categories()
    return render_template('article_form.html', article=article, categories=categories)


@bp.route('/article/<int:article_id>/delete')
@login_optional
@admin_required
def delete_article(article_id):
    article = Article.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    flash('Artikel gelöscht')
    return redirect(url_for('main.index'))


@bp.route('/article/<int:article_id>/history')
@login_optional
def article_history(article_id):
    article = Article.query.get_or_404(article_id)
    return render_template('history.html', article=article)


@bp.route('/movement/<int:article_id>/new', methods=['GET', 'POST'])
@login_optional
@staff_required
def new_movement(article_id):
    article = Article.query.get_or_404(article_id)
    if request.method == 'POST':
        qty = int(request.form['quantity'])
        note = request.form.get('note')
        mtype = request.form.get('type', 'Wareneingang')
        movement = Movement(article_id=article.id, quantity=qty, note=note, type=mtype)
        article.stock += qty
        db.session.add(movement)
        db.session.commit()
        if article.stock < article.minimum_stock:
            flash('Bestand unter Mindestbestand!')
        flash('Bewegung erfasst')
        return redirect(url_for('main.article_history', article_id=article.id))
    return render_template('movement_form.html', article=article)



@bp.route('/import', methods=['GET', 'POST'])
@login_optional
@staff_required
def import_csv():
    if request.method == 'POST':
        file = request.files['file']
        raw = file.read()
        try:
            content = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content = raw.decode('latin1')
            except UnicodeDecodeError:
                flash('Datei konnte nicht gelesen werden. Bitte UTF-8 oder Latin1 codierte CSV verwenden.')
                return redirect(url_for('main.import_csv'))

        stream = StringIO(content)

        # Erst versuchen wir, das Standardformat zu lesen
        reader = csv.DictReader(stream)
        expected_fields = ['name', 'sku', 'stock', 'category', 'location_primary', 'location_secondary']

        if reader.fieldnames == expected_fields:
            mode = 'standard'
        else:
            stream.seek(0)
            reader = csv.DictReader(stream, delimiter=';')
            if 'Produktname' in (reader.fieldnames or []):
                mode = 'lagerverwaltung'
            else:
                flash('Dateiformat nicht erkannt oder Spalten fehlen')
                return redirect(url_for('main.import_csv'))

        for row in reader:
            if mode == 'lagerverwaltung':
                sku = row.get('SKU')
                name = row.get('Produktname')
                stock = row.get('Lagerbestand (neu)')
                minimum = row.get('Mindestbestand')
                location_primary = row.get('Lagerplatz')
                category = category_from_sku(sku) or 'Sonstiges'
                location_secondary = ''
            else:
                sku = row['sku']
                name = row['name']
                stock = row['stock']
                minimum = row.get('minimum_stock')
                category = row['category']
                location_primary = row.get('location_primary')
                location_secondary = row.get('location_secondary')

            article = Article.query.filter_by(sku=sku).first()
            if not article:
                article = Article(sku=sku)
                db.session.add(article)

            article.name = name
            article.stock = int(stock) if stock not in (None, '') else 0
            category = (category or '').strip()
            if not category:
                category = category_from_sku(sku) or 'Sticker'
            article.category = category
            article.location_primary = location_primary
            article.location_secondary = location_secondary

            price_raw = row.get('price', '').strip()
            if price_raw:
                try:
                    article.price = float(price_raw.replace(',', '.'))
                except ValueError:
                    article.price = article.price  # Beibehalten, falls fehlerhaft
            elif not article.price or article.price == 0:
                # Nur wenn Preis nicht gesetzt, versuche Default
                p = price_from_suffix(sku, article.category)
                if p is None:
                    p = price_from_sku(sku)
                if p is None:
                    p = get_default_price(article.category)
                article.price = p or 0.0


            try:
                if minimum is not None and minimum != '':
                    article.minimum_stock = int(minimum)
                else:
                    article.minimum_stock = get_default_minimum_stock(article.category)
            except (ValueError, TypeError):
                article.minimum_stock = get_default_minimum_stock(article.category)

        db.session.commit()
        flash('Import abgeschlossen')
        return redirect(url_for('main.index'))

    return render_template('import.html')





@bp.route('/export/articles')
@login_optional
def export_articles():
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['name', 'sku', 'stock', 'minimum_stock', 'category', 'location_primary', 'location_secondary'])
    for a in Article.query.all():
        writer.writerow([a.name, a.sku, a.stock, a.minimum_stock, a.category, a.location_primary, a.location_secondary])
    output = si.getvalue()
    return Response(output, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=articles.csv'})


@bp.route('/backup/export')
@login_optional
def backup_export():
    
    """Export all articles and orders as a ZIP archive."""
    import zipfile
    from io import BytesIO

    # Articles -------------------------------------------------------------
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow([
        'sku', 'name', 'category', 'stock', 'minimum_stock',
        'location_primary', 'location_secondary', 'image', 'price'
    ])
    for a in Article.query.all():
        writer.writerow([
            a.sku or '',
            a.name or '',
            a.category or '',
            a.stock if a.stock is not None else 0,
            a.minimum_stock if a.minimum_stock is not None else 0,
            a.location_primary or '',
            a.location_secondary or '',
            a.image or '',
            f"{a.price:.2f}" if a.price is not None else ''
        ])
    articles_csv = si.getvalue().encode('utf-8')

    # Orders ---------------------------------------------------------------
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['id', 'customer_name', 'customer_address', 'status', 'created_at'])
    for o in Order.query.all():
        writer.writerow([
            o.id,
            o.customer_name or '',
            o.customer_address or '',
            o.status or '',
            o.created_at.isoformat() if o.created_at else ''
        ])
    orders_csv = si.getvalue().encode('utf-8')

    # Order items ----------------------------------------------------------
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['order_id', 'article_sku', 'quantity', 'unit_price'])
    for item in OrderItem.query.all():
        writer.writerow([
            item.order_id,
            item.article.sku if item.article else '',
            item.quantity,
            f"{item.unit_price:.2f}"
        ])
    items_csv = si.getvalue().encode('utf-8')

    
    # Invoice movements ----------------------------------------------------
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow([
        'article_sku', 'article_name', 'quantity',
        'type', 'note', 'timestamp', 'invoice_number'
    ])
    for m in Movement.query.filter(Movement.invoice_number != None).all():
        writer.writerow([
            m.article.sku if m.article else '',
            m.article.name if m.article else '',
            m.quantity,
            m.type,
            m.note or '',
            m.timestamp.isoformat() if m.timestamp else '',
            m.invoice_number or ''
        ])
    invoices_csv = si.getvalue().encode('utf-8')


    # Build ZIP ------------------------------------------------------------
    mem = BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('articles.csv', articles_csv)
        zf.writestr('orders.csv', orders_csv)
        zf.writestr('order_items.csv', items_csv)
        zf.writestr('invoice_movements.csv', invoices_csv)
    mem.seek(0)
    return Response(
        mem.read(),
        mimetype='application/zip',
        headers={'Content-Disposition': 'attachment;filename=backup.zip'}
    )



@bp.route('/export/movements')
@login_optional
def export_movements():
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['article_sku','article_name', 'quantity', 'type', 'note', 'timestamp', 'invoice_number'])
    for m in Movement.query.all():
        writer.writerow([m.article.sku, m.article.name, m.quantity, m.type, m.note, m.timestamp, m.invoice_number or ''])
    output = si.getvalue()
    return Response(output, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=movements.csv'})

@bp.route('/backup/import', methods=['GET', 'POST'])
@login_optional
@admin_required
def backup_import():
    """Restore articles and orders from a backup ZIP or CSV file."""
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            flash('Keine Datei ausgewählt')
            return redirect(url_for('main.backup_import'))
        
        import zipfile
        from io import BytesIO
        raw = file.read()
        def decode_bytes(data: bytes) -> str | None:
            for enc in ('utf-8-sig', 'latin1'):
                try:
                    return data.decode(enc)
                except UnicodeDecodeError:
                    continue
            return None

        articles_text = None
        orders_text = None
        items_text = None
        invoices_text = None

        if zipfile.is_zipfile(BytesIO(raw)):
            with zipfile.ZipFile(BytesIO(raw)) as zf:
                try:
                    articles_text = decode_bytes(zf.read('articles.csv'))
                    orders_text = decode_bytes(zf.read('orders.csv'))
                    items_text = decode_bytes(zf.read('order_items.csv'))
                    try:
                        invoices_text = decode_bytes(
                            zf.read('invoice_movements.csv')
                        )
                    except KeyError:
                        invoices_text = None
                except KeyError:
                    flash('Backup-Datei unvollständig')
                    return redirect(url_for('main.backup_import'))
        else:
            articles_text = decode_bytes(raw)

        if articles_text is None:
            flash('Datei konnte nicht gelesen werden.')
            return redirect(url_for('main.backup_import'))

        reader = csv.DictReader(StringIO(articles_text))
        required = {
            'sku', 'name', 'category', 'stock', 'minimum_stock',
            'location_primary', 'location_secondary', 'image', 'price'
        }
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            flash('Ungültiges Format der Backup-Datei')
            return redirect(url_for('main.backup_import'))

        for row in reader:
            sku = (row.get('sku') or '').strip()
            if not sku:
                continue
            article = Article.query.filter_by(sku=sku).first()
            if not article:
                article = Article(sku=sku)
                db.session.add(article)

            article.name = row.get('name') or ''
            article.category = (row.get('category') or 'Sticker').strip() or 'Sticker'

            try:
                article.stock = int(row.get('stock') or 0)
            except ValueError:
                article.stock = 0

            try:
                article.minimum_stock = int(row.get('minimum_stock') or 0)
            except ValueError:
                article.minimum_stock = 0

            article.location_primary = row.get('location_primary') or ''
            article.location_secondary = row.get('location_secondary') or ''
            article.image = row.get('image') or ''

            price_raw = row.get('price', '').strip()
            if price_raw:
                try:
                    article.price = float(price_raw.replace(',', '.'))
                except ValueError:
                    article.price = article.price  # Behalte alten Preis
            elif not article.price or article.price == 0:
                p = price_from_suffix(sku, article.category)
                if p is None:
                    p = price_from_sku(sku)
                if p is None:
                    p = get_default_price(article.category)
                article.price = p or 0.0


         # Orders -----------------------------------------------------------
        from datetime import datetime
        orders_mapping = {}
        if orders_text:
            r = csv.DictReader(StringIO(orders_text))
            fields = {'id', 'customer_name', 'customer_address', 'status', 'created_at'}
            if not r.fieldnames or not fields.issubset(set(r.fieldnames)):
                flash('Ungültiges Format der Orders-Datei')
                return redirect(url_for('main.backup_import'))
            for row in r:
                try:
                    oid = int(row.get('id') or 0)
                except ValueError:
                    continue
                if oid <= 0:
                    continue
                order = Order.query.get(oid)
                if not order:
                    order = Order(id=oid)
                    db.session.add(order)
                else:
                    # remove existing items
                    for it in order.items:
                        db.session.delete(it)
                order.customer_name = row.get('customer_name') or ''
                order.customer_address = row.get('customer_address') or ''
                order.status = row.get('status') or 'offen'
                ts = row.get('created_at')
                try:
                    order.created_at = datetime.fromisoformat(ts) if ts else datetime.utcnow()
                except ValueError:
                    order.created_at = datetime.utcnow()
                orders_mapping[oid] = order

        # Order items ------------------------------------------------------
        if items_text:
            r = csv.DictReader(StringIO(items_text))
            fields = {'order_id', 'article_sku', 'quantity', 'unit_price'}
            if not r.fieldnames or not fields.issubset(set(r.fieldnames)):
                flash('Ungültiges Format der Order-Items-Datei')
                return redirect(url_for('main.backup_import'))
            for row in r:
                try:
                    oid = int(row.get('order_id') or 0)
                    qty = int(row.get('quantity') or 0)
                    price = float(row.get('unit_price') or 0)
                except ValueError:
                    continue
                sku = (row.get('article_sku') or '').strip()
                if oid not in orders_mapping:
                    continue
                article = Article.query.filter_by(sku=sku).first()
                if not article:
                    continue
                item = OrderItem(order_id=oid, article_id=article.id,
                                 quantity=qty, unit_price=price)
                db.session.add(item)


        # Invoice movements -------------------------------------------------
        if invoices_text:
            r = csv.DictReader(StringIO(invoices_text))
            fields = {
                'article_sku', 'quantity', 'type',
                'note', 'timestamp', 'invoice_number'
            }
            if not r.fieldnames or not fields.issubset(set(r.fieldnames)):
                flash('Ungültiges Format der Invoice-Movements-Datei')
                return redirect(url_for('main.backup_import'))
            from datetime import datetime
            for row in r:
                sku = (row.get('article_sku') or '').strip()
                if not sku:
                    continue
                article = Article.query.filter_by(sku=sku).first()
                if not article:
                    continue
                try:
                    qty = int(row.get('quantity') or 0)
                except ValueError:
                    qty = 0
                t = row.get('timestamp') or ''
                try:
                    ts = datetime.fromisoformat(t) if t else datetime.utcnow()
                except ValueError:
                    ts = datetime.utcnow()
                m = Movement(
                    article_id=article.id,
                    quantity=qty,
                    type=row.get('type') or 'Warenausgang',
                    note=row.get('note') or '',
                    timestamp=ts,
                    invoice_number=(row.get('invoice_number') or None),
                )
                db.session.add(m)


        db.session.commit()
        flash('Backup importiert')
        return redirect(url_for('main.index'))

    return render_template('backup_import.html')



@bp.route('/invoices')
@login_optional
@admin_required
def invoices():
    movements = Movement.query.filter(Movement.invoice_number != None).order_by(Movement.timestamp.desc()).all()
    return render_template('invoices.html', movements=movements)

@bp.route('/analysis')
@login_optional
@admin_required
def analysis():
    sort = request.args.get('sort', 'revenue')
    results = (
        db.session.query(
            Article.name.label('name'),
            func.sum(OrderItem.quantity).label('quantity'),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label('revenue'),
        )
        .join(OrderItem, Article.id == OrderItem.article_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status.in_(['bezahlt', 'versendet']))
        .group_by(Article.id)
        .all()
    )
    if sort == 'quantity':
        results.sort(key=lambda r: r.quantity or 0, reverse=True)
    else:
        results.sort(key=lambda r: r.revenue or 0, reverse=True)
    return render_template('analysis.html', data=results, sort=sort)

@bp.route('/analysis/invoices')
@login_optional
@admin_required
def invoice_analysis():
    """Show statistics for all invoiced movements grouped by article SKU."""
    sort = request.args.get('sort', 'sku')

    query_results = (
        db.session.query(
            Article.id.label('id'),
            Article.name.label('name'),
            Article.sku.label('sku'),
            Article.category.label('category'),
            Article.price.label('price'),
            func.sum(func.abs(Movement.quantity)).label('quantity'),
        )
        .join(Article, Movement.article_id == Article.id)
        .filter(Movement.invoice_number != None)
        .group_by(Article.id)
        .all()
    )

    data = []
    for r in query_results:
        multiplier = csv_multiplier_from_suffix(r.sku, r.category)
        # Fallback für Sticker-Kategorie
        if multiplier is None and r.category and r.category.strip().lower() == 'sticker':
            multiplier = int(get_setting('sticker_csv_multiplier', '100') or '100')
        # Absicherung gegen fehlerhafte Werte
        if not multiplier or multiplier < 1:
            multiplier = 1
        quantity = r.quantity/multiplier
        revenue = r.price * quantity
        data.append(
            dict(name=r.name, sku=r.sku, quantity=r.quantity, revenue=revenue)
        )
    if sort == 'quantity':
        data.sort(key=lambda x: x['quantity'] or 0, reverse=True)
    elif sort == 'revenue':
        data.sort(key=lambda x: x['revenue'] or 0, reverse=True)
    else:  # 'sku'
        data.sort(key=lambda x: x['sku'] or '')

    return render_template('invoice_analysis.html', data=data, sort=sort)



@bp.route('/inventory', methods=['GET', 'POST'])
@login_optional
@staff_required
def inventory():
    query = Article.query

    # Suche verarbeiten
    search = request.args.get('search')
    if search:
        query = query.filter(
            (Article.name.contains(search)) | (Article.sku.contains(search))
        )

    # Kategorie-Filter mit Trim aus URL + DB
    category = request.args.get('category')
    if category:
        query = query.filter(func.trim(Article.category) == category.strip())

    categories = get_categories()

    # CSV-Import bei POST
    if request.method == 'POST' and 'search' not in request.form:
        file = request.files.get('file')
        if file and file.filename:
            adjusted = 0
            data = file.read()

            # Encoding prüfen und Text dekodieren
            text = None
            for enc in ('utf-8-sig', 'latin1'):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue

            if text is None:
                flash('Datei konnte nicht verarbeitet werden (Encoding).')
                return redirect(url_for('main.inventory'))

            reader = csv.DictReader(StringIO(text), delimiter=';')
            invoice_field = None
            for f in ('Rechnung', 'Rechennummer', 'Dokument: Dokumentnummer'):
                if f in reader.fieldnames:
                    invoice_field = f
                    break

            date_field = None
            for f in reader.fieldnames:
                lf = f.lower()
                if 'datum' in lf or 'date' in lf:
                    date_field = f
                    if 'bestell' in lf or 'dokument' in lf or lf == 'datum' or lf == 'date':
                        break

            if 'Posten: Artikelnummer' not in reader.fieldnames or 'Posten: Anzahl' not in reader.fieldnames:
                flash('Erforderliche Spalten fehlen.')
                return redirect(url_for('main.inventory'))

            try:
                for row in reader:
                    sku = row.get('Posten: Artikelnummer', '').strip()
                    qty = row.get('Posten: Anzahl', '').strip()
                    invoice = row.get(invoice_field, '').strip() if invoice_field else None
                    date_str = row.get(date_field, '').strip() if date_field else ''
                    ts = None
                    if date_str:
                        for fmt in ('%d.%m.%Y %H:%M:%S', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                            try:
                                ts = datetime.strptime(date_str, fmt)
                                break
                            except ValueError:
                                continue
                        if ts is None:
                            try:
                                ts = datetime.fromisoformat(date_str)
                            except ValueError:
                                ts = None
                    if not sku or not qty:
                        continue
                    try:
                        qty = int(qty)
                    except ValueError:
                        continue

                    article = Article.query.filter_by(sku=sku).first()
                    if not article:
                        continue

                    multiplier = csv_multiplier_from_suffix(article.sku, article.category)
                    if multiplier is None and article.category and article.category.strip().lower() == 'sticker':
                        multiplier = int(get_setting('sticker_csv_multiplier', '100') or '100')
                    if multiplier and multiplier != 1:
                        current_app.logger.info(f"[IMPORT] Multiplier f\u00fcr Sticker/Endung: {multiplier}")
                        qty *= multiplier

                    article.stock -= qty
                    db.session.add(Movement(
                        article_id=article.id,
                        quantity=-qty,
                        type='Warenausgang',
                        invoice_number=invoice if invoice else None,
                        note='Import Export-Datei',
                        timestamp=ts if ts else datetime.utcnow()
                    ))
                    adjusted += 1
            except Exception as e:
                flash('Fehler beim Verarbeiten der Datei.')
                return redirect(url_for('main.inventory'))

            if adjusted:
                db.session.commit()
                flash(f'CSV-Import abgeschlossen – {adjusted} Artikel angepasst.')
            else:
                flash('CSV-Import abgeschlossen – Keine passenden Artikel gefunden.')

            return redirect(url_for('main.inventory'))

    # WICHTIG: articles immer definieren, wenn kein Redirect/Return vorher ausgeführt wurde
    articles = query.all()

    return render_template(
        'inventory.html',
        articles=articles,
        categories=categories,
        selected_category=category
    )




# Bestellungen
@bp.route('/orders')
@login_optional
def order_list():
    from datetime import datetime
    query = Order.query
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)
    customer = request.args.get('customer')
    if customer:
        query = query.filter(Order.customer_name.contains(customer))
    start = request.args.get('start')
    if start:
        try:
            start_dt = datetime.strptime(start, '%Y-%m-%d')
            query = query.filter(Order.created_at >= start_dt)
        except ValueError:
            pass
    end = request.args.get('end')
    if end:
        try:
            end_dt = datetime.strptime(end, '%Y-%m-%d')
            query = query.filter(Order.created_at <= end_dt)
        except ValueError:
            pass
    orders = query.order_by(Order.created_at.desc()).all()
    statuses = ['offen', 'bezahlt', 'versendet']
    return render_template('orders_list.html', orders=orders, statuses=statuses, selected_status=status)


@bp.route('/orders/<int:order_id>')
@login_optional
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('order_detail.html', order=order)


@bp.route('/orders/<int:order_id>/label')
@bp.route('/order/<int:order_id>/label')
@login_optional
def order_label(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status not in ['bezahlt', 'versendet']:
        flash('Versandetikett erst ab Status bezahlt verfügbar')
        return redirect(url_for('main.order_detail', order_id=order.id))

    from fpdf import FPDF

    fmt = get_setting('etikett_format', '100x50')
    try:
        w, h = [float(x) for x in fmt.lower().split('x')]
    except Exception:
        w, h = 100, 50
    pdf = FPDF(unit='mm', format=(w, h))
    pdf.set_auto_page_break(False)
    pdf.add_page()

    left = 5
    top = 5
    line_height = 5

    # Absender
    pdf.set_xy(left, top)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, line_height, 'Absender:', ln=True)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_x(left)
    pdf.cell(0, line_height, 'Fan-Kultur Xperience GmbH', ln=True)
    pdf.set_x(left)
    pdf.cell(0, line_height, 'Hauptstr. 20', ln=True)
    pdf.set_x(left)
    pdf.cell(0, line_height, '55288 Armsheim', ln=True)

    # Abstand nach Absender
    pdf.ln(3)

    # Empfänger
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_x(left)
    pdf.cell(0, line_height, 'Empfänger:', ln=True)

    pdf.set_font('Helvetica', '', 12)
    pdf.set_x(left)
    pdf.cell(0, line_height, order.customer_name, ln=True)

    if order.customer_address:
        for line in order.customer_address.splitlines():
            pdf.set_x(left)
            pdf.cell(0, line_height, line, ln=True)

    # Webadresse separat unten platzieren
    #pdf.set_y(50 - 8)
    #pdf.set_font('Helvetica', 'B', 11)
    #pdf.set_x(left)
    #pdf.cell(0, 6, 'www.fan-kultur.de', ln=True)




    return Response(pdf.output(dest='S').encode('latin-1'), mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment;filename=order_{order.id}_label.pdf'})




@bp.route('/orders/new', methods=['GET', 'POST'])
@login_optional
@staff_required
def new_order():
    statuses = ['offen', 'bezahlt', 'versendet']
    articles = Article.query.all()
    if request.method == 'POST':
        street = request.form.get('customer_street', '')
        city_zip = request.form.get('customer_city_zip', '')
        address = f"{street}\n{city_zip}" if street or city_zip else None
        order = Order(customer_name=request.form['customer_name'],
                      customer_address=address,
                      status=request.form['status'])
        db.session.add(order)
        db.session.flush()
        movements = []
        for article in articles:
            qty = int(request.form.get(f'qty_{article.id}', 0))
            price = float(request.form.get(f'price_{article.id}', 0) or 0)
            if qty > 0:
                if order.status in ['offen', 'bezahlt'] and article.stock - qty < 0:
                    db.session.rollback()
                    flash(f'Nicht genug Bestand für {article.name}')
                    return redirect(url_for('main.new_order'))
                item = OrderItem(order_id=order.id, article_id=article.id, quantity=qty, unit_price=price)
                db.session.add(item)
                if order.status in ['offen', 'bezahlt']:
                    article.stock -= qty
                    movements.append(Movement(article_id=article.id, quantity=-qty, note=f'Bestellung #{order.id}', order_id=order.id, type='Warenausgang'))
        for m in movements:
            db.session.add(m)
        db.session.commit()
        flash('Bestellung angelegt')
        return redirect(url_for('main.order_detail', order_id=order.id))
    return render_template('order_form.html', articles=articles, statuses=statuses,
                           addr_street='', addr_city_zip='')


@bp.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_optional
@staff_required
def edit_order(order_id):
    statuses = ['offen', 'bezahlt', 'versendet']
    order = Order.query.get_or_404(order_id)
    if request.method == 'POST':
        order.customer_name = request.form['customer_name']
        street = request.form.get('customer_street', '')
        city_zip = request.form.get('customer_city_zip', '')
        order.customer_address = f"{street}\n{city_zip}" if street or city_zip else None
        order.status = request.form['status']
        db.session.commit()
        flash('Bestellung aktualisiert')
        return redirect(url_for('main.order_detail', order_id=order.id))
    street = ''
    city_zip = ''
    if order.customer_address:
        lines = order.customer_address.splitlines()
        if len(lines) > 0:
            street = lines[0]
        if len(lines) > 1:
            city_zip = lines[1]
    return render_template('order_form.html', order=order, statuses=statuses, articles=None,
                           addr_street=street, addr_city_zip=city_zip)

@bp.route('/settings')
@login_optional
@admin_required
def settings_index():
    """Redirect to the first settings tab."""
    return redirect(url_for('main.settings_categories'))



@bp.route('/settings/general', methods=['GET', 'POST'])
@login_optional
@admin_required
def settings_general():

    keys = [
        'enable_user_management',
        'etikett_format',
        'sticker_csv_multiplier',
    ]
    if request.method == 'POST':
        for key in keys:
            val = request.form.get(key, '')
            set_setting(key, val)
        flash('Einstellungen gespeichert.')
        return redirect(url_for('main.settings_general'))

    values = {key: get_setting(key, '') for key in keys}
    return render_template('settings_general.html', settings=values)


@bp.route('/settings/cleanup', methods=['POST'])
@login_optional
@admin_required
def settings_cleanup():
    """Delete selected parts of the database after password confirmation."""
    option = request.form.get('delete_option', '')
    password = request.form.get('password', '')

    if not current_user.check_password(password):
        flash('Falsches Passwort.')
        return redirect(url_for('main.settings_general'))

    if option == 'orders':
        Movement.query.delete()
        OrderItem.query.delete()
        Order.query.delete()
        db.session.commit()
        flash('Alle Bestellungen gelöscht.')
    elif option == 'articles':
        Movement.query.delete()
        OrderItem.query.delete()
        Article.query.delete()
        db.session.commit()
        flash('Alle Artikel gelöscht.')
    elif option == 'all':
        Movement.query.delete()
        OrderItem.query.delete()
        Order.query.delete()
        Article.query.delete()
        Category.query.delete()
        db.session.commit()
        flash('Datenbank bereinigt.')
    else:
        flash('Keine gültige Option ausgewählt.')
    return redirect(url_for('main.settings_general'))



@bp.route('/settings/categories')
@login_optional
@admin_required
def settings_categories():
    categories = Category.query.order_by(Category.name).all()
    return render_template('settings_categories.html', categories=categories)


@bp.route('/settings/categories/add', methods=['POST'])
@login_optional
@admin_required
def add_category():
    name = request.form.get('name', '').strip()
    if name:
        if not Category.query.filter(func.lower(Category.name) == name.lower()).first():
            prefix = request.form.get('prefix', '').strip() or None
            price_raw = request.form.get('price', '').replace(',', '.').strip()
            try:
                price = float(price_raw) if price_raw else 0.0
            except ValueError:
                price = 0.0
            minimum = request.form.get('minimum', '').strip()
            try:
                minimum = int(minimum) if minimum else 0
            except ValueError:
                minimum = 0
            db.session.add(Category(
                name=name,
                prefix=prefix,
                default_price=price,
                default_min_stock=minimum,
            ))
            db.session.commit()
            flash('Kategorie hinzugefügt')
    return redirect(url_for('main.settings_categories'))


@bp.route('/settings/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_optional
@admin_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        prefix = request.form.get('prefix', '').strip() or None
        price_raw = request.form.get('price', '').replace(',', '.').strip()
        minimum = request.form.get('minimum', '').strip()
        if name:
            old_name = category.name
            category.name = name
            # Update articles using old category name
            Article.query.filter_by(category=old_name).update({'category': name})
        category.prefix = prefix
        try:
            category.default_price = float(price_raw) if price_raw else 0.0
        except ValueError:
            pass
        try:
            category.default_min_stock = int(minimum) if minimum else 0
        except ValueError:
            pass
        db.session.commit()
        flash('Kategorie aktualisiert')
        return redirect(url_for('main.settings_categories'))
    return render_template('category_form.html', category=category)

@bp.route('/settings/categories/<int:category_id>/apply', methods=['POST'])
@login_optional
@admin_required
def apply_category_defaults(category_id):
    """Apply default price and minimum stock of a category to all its articles."""
    category = Category.query.get_or_404(category_id)
    Article.query.filter_by(category=category.name).update({
        'price': category.default_price,
        'minimum_stock': category.default_min_stock,
    })
    db.session.commit()
    flash('Standardwerte auf Artikel angewendet')
    return redirect(url_for('main.settings_categories'))




@bp.route('/settings/categories/<int:category_id>/delete', methods=['POST'])
@login_optional
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    # Only allow deletion if no article uses this category
    in_use = Article.query.filter_by(category=category.name).first()
    if in_use:
        flash('Kategorie wird von Artikeln verwendet und kann nicht gelöscht werden.')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('Kategorie gelöscht')
    return redirect(url_for('main.settings_categories'))

@bp.route('/settings/endings')
@login_optional
@admin_required
def settings_endings():
    endings = EndingCategory.query.order_by(EndingCategory.suffix).all()
    categories = get_categories()
    return render_template('settings_endings.html', endings=endings, categories=categories)


@bp.route('/settings/endings/add', methods=['POST'])
@login_optional
@admin_required
def add_ending():
    suffix = request.form.get('suffix', '').strip()
    category = request.form.get('category', '').strip()
    if suffix and category and not EndingCategory.query.filter_by(suffix=suffix, category=category).first():
        price_raw = request.form.get('price', '').replace(',', '.').strip()
        multiplier_raw = request.form.get('multiplier', '').strip()
        try:
            price = float(price_raw) if price_raw else 0.0
        except ValueError:
            price = 0.0
        try:
            multiplier = int(multiplier_raw) if multiplier_raw else 1
        except ValueError:
            multiplier = 1
        db.session.add(EndingCategory(suffix=suffix, category=category, price=price, csv_multiplier=multiplier))
        db.session.commit()
        flash('Endung hinzugefügt')
    return redirect(url_for('main.settings_endings'))


@bp.route('/settings/endings/<int:ending_id>/edit', methods=['GET', 'POST'])
@login_optional
@admin_required
def edit_ending(ending_id):
    ending = EndingCategory.query.get_or_404(ending_id)
    if request.method == 'POST':
        suffix = request.form.get('suffix', '').strip()
        category = request.form.get('category', '').strip()        
        price_raw = request.form.get('price', '').replace(',', '.').strip()
        multiplier_raw = request.form.get('multiplier', '').strip()
        if suffix:
            ending.suffix = suffix
        if category:
            ending.category = category
        try:
            ending.price = float(price_raw) if price_raw else 0.0
        except ValueError:
            pass
        try:
            ending.csv_multiplier = int(multiplier_raw) if multiplier_raw else 1
        except ValueError:
            pass
        db.session.commit()
        flash('Endung aktualisiert')
        return redirect(url_for('main.settings_endings'))
    categories = get_categories()
    return render_template('ending_form.html', ending=ending, categories=categories)

@bp.route('/settings/endings/<int:ending_id>/apply', methods=['POST'])
@login_optional
@admin_required
def apply_ending_price(ending_id):
    """Apply the price of an ending category to all matching articles."""
    ending = EndingCategory.query.get_or_404(ending_id)
    if ending.suffix:
        price = ending.price
        if ending.csv_multiplier and ending.csv_multiplier > 1:
            price = price 
        Article.query.filter(
            Article.category == ending.category,
            Article.sku.like(f"%{ending.suffix}")
        ).update({'price': price})
        db.session.commit()
        flash('Preis auf Artikel angewendet')
    return redirect(url_for('main.settings_endings'))



@bp.route('/settings/endings/<int:ending_id>/delete', methods=['POST'])
@login_optional
@admin_required
def delete_ending(ending_id):
    ending = EndingCategory.query.get_or_404(ending_id)
    db.session.delete(ending)
    db.session.commit()
    flash('Endung gelöscht')
    return redirect(url_for('main.settings_endings'))


# Benutzerverwaltung ---------------------------------------------------------

@bp.route('/settings/users')
@login_optional
@admin_required
def settings_users():
    users = User.query.all()
    return render_template('settings_users.html', users=users)


@bp.route('/settings/users/new', methods=['GET', 'POST'])
@login_optional
@admin_required
def new_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        gender = request.form.get('gender', '').strip()
        bio = request.form.get('bio', '').strip()
        file = request.files.get('profile_image')
        is_admin = bool(request.form.get('is_admin'))
        is_staff = bool(request.form.get('is_staff'))

        if not username or not password:
            flash('Benutzername und Passwort sind erforderlich.')
            return redirect(url_for('main.new_user'))

        if User.query.filter_by(username=username).first():
            flash('Benutzername existiert bereits.')
            return redirect(url_for('main.new_user'))
        
        if email and User.query.filter_by(email=email).first():
            flash('E-Mail existiert bereits.')
            return redirect(url_for('main.new_user'))

        user = User(
            username=username,
            is_admin=is_admin,
            is_staff=is_staff or is_admin,
            name=name,
            gender=gender,
            bio=bio,
            email=email,
        )
        if file and file.filename:
            filename = secure_filename(file.filename)
            folder = current_app.config['PROFILE_IMAGE_FOLDER']
            base, ext = os.path.splitext(filename)
            counter = 1
            path = os.path.join(folder, filename)
            while os.path.exists(path):
                filename = f"{base}_{counter}{ext}"
                path = os.path.join(folder, filename)
                counter += 1
            file.save(path)
            user.profile_image = f"profile_pics/{filename}"
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Benutzer angelegt')
        return redirect(url_for('main.settings_users'))

    return render_template('user_form.html', user=None)


@bp.route('/settings/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_optional
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        gender = request.form.get('gender', '').strip()
        bio = request.form.get('bio', '').strip()
        file = request.files.get('profile_image')
        is_admin = bool(request.form.get('is_admin'))
        user.is_staff = bool(request.form.get('is_staff')) or is_admin

        if not is_admin and user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
            flash('Mindestens ein Admin-Benutzer muss bestehen bleiben.')
            return redirect(url_for('main.settings_users'))

        user.is_admin = is_admin
        if password:
            user.set_password(password)
        if email and email != user.email:
            if User.query.filter_by(email=email).first():
                flash('E-Mail existiert bereits.')
                return redirect(url_for('main.edit_user', user_id=user.id))
            user.email = email
        if name:
            user.name = name
        if gender:
            user.gender = gender
        user.bio = bio
        if file and file.filename:
            filename = secure_filename(file.filename)
            folder = current_app.config['PROFILE_IMAGE_FOLDER']
            base, ext = os.path.splitext(filename)
            counter = 1
            path = os.path.join(folder, filename)
            while os.path.exists(path):
                filename = f"{base}_{counter}{ext}"
                path = os.path.join(folder, filename)
                counter += 1
            file.save(path)
            user.profile_image = f"profile_pics/{filename}"
        db.session.commit()
        flash('Benutzer aktualisiert')
        return redirect(url_for('main.settings_users'))

    return render_template('user_form.html', user=user)


@bp.route('/settings/users/<int:user_id>/delete')
@login_optional
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash('Mindestens ein Admin-Benutzer muss bestehen bleiben.')
        return redirect(url_for('main.settings_users'))
    db.session.delete(user)
    db.session.commit()
    flash('Benutzer gelöscht')
    return redirect(url_for('main.settings_users'))


@bp.route('/social')
@login_optional
def social():
    if not user_management_enabled():
        return redirect(url_for('main.index'))
    users = User.query.all()
    return render_template('social.html', users=users)


@bp.route('/social/<int:user_id>', methods=['GET', 'POST'])
@login_optional
def chat(user_id):
    if not user_management_enabled():
        return redirect(url_for('main.index'))
    other = User.query.get_or_404(user_id)
    if request.method == 'POST' and current_user.is_authenticated:
        content = request.form.get('message', '').strip()
        if content:
            msg = Message(sender_id=current_user.id, receiver_id=other.id, content=content)
            db.session.add(msg)
            db.session.commit()
            return redirect(url_for('main.chat', user_id=other.id))
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other.id)) |
        ((Message.sender_id == other.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    return render_template('chat.html', other=other, messages=messages)
