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

from . import db
from .models import User, Article, Movement, Order, OrderItem


MINDESTBESTAND = {
    'sticker': 1000,
    'schal': 100,
    'shirt':10
}

def get_default_minimum_stock(category: str) -> int:
    return MINDESTBESTAND.get(category.lower(), 0)


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


def login_optional(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_app.config.get('ENABLE_USER_MANAGEMENT'):
            return login_required(func)(*args, **kwargs)
        return func(*args, **kwargs)
    return wrapper


bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    query = Article.query
    search = request.args.get('search')
    if search:
        query = query.filter((Article.name.contains(search)) | (Article.sku.contains(search)))
    category = request.args.get('category')
    if category:
        query = query.filter_by(category=category)
    articles = query.all()
    categories = ['Sticker', 'Schal', 'Shirt']
    return render_template('index.html', articles=articles, categories=categories, selected_category=category)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if not current_app.config.get('ENABLE_USER_MANAGEMENT'):
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('main.index'))
        flash('Ungültige Anmeldung')
    return render_template('login.html')


@bp.route('/logout')
@login_optional
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@bp.route('/article/new', methods=['GET', 'POST'])
@login_optional
@admin_required
def new_article():
    if request.method == 'POST':
        if Article.query.filter_by(sku=request.form['sku']).first():
            flash('Artikel mit dieser SKU existiert bereits.')
            return redirect(url_for('main.new_article'))

        category = request.form['category']
        default_min = get_default_minimum_stock(category)

        article = Article(
            name=request.form['name'],
            sku=request.form['sku'],
            category=category,
            stock=int(request.form['stock']),
            location_primary=request.form['location_primary'],
            location_secondary=request.form['location_secondary'],
            image=request.form.get('image'),
            minimum_stock=default_min
        )
        db.session.add(article)
        db.session.commit()
        flash('Artikel erstellt')
        return redirect(url_for('main.index'))

    categories = ['Sticker', 'Schal', 'Shirt']
    return render_template('article_form.html', categories=categories)



@bp.route('/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_optional
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    if current_app.config.get('ENABLE_USER_MANAGEMENT') and (not current_user.is_authenticated or not current_user.is_admin):
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
        article.image = request.form.get('image')
        db.session.commit()
        flash('Artikel aktualisiert')
        return redirect(url_for('main.index'))
    categories = ['Sticker', 'Schal', 'Shirt']
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
@admin_required
def import_csv():
    if request.method == 'POST':
        file = request.files['file']
        content = file.stream.read().decode('utf-8-sig')
        stream = StringIO(content)
        reader = csv.DictReader(stream)

        expected_fields = ['name', 'sku', 'stock', 'category', 'location_primary', 'location_secondary']
        if reader.fieldnames != expected_fields:
            flash(f'CSV-Spalten stimmen nicht. Erwartet: {expected_fields}, gefunden: {reader.fieldnames}')
            return redirect(url_for('main.import_csv'))

        for row in reader:
            article = Article.query.filter_by(sku=row['sku']).first()
            if not article:
                article = Article(sku=row['sku'])
                db.session.add(article)

            article.name = row['name']
            article.stock = int(row['stock'])
            article.category = row['category']
            article.location_primary = row.get('location_primary')
            article.location_secondary = row.get('location_secondary')

            try:
                article.minimum_stock = int(row.get('minimum_stock', get_default_minimum_stock(article.category)))
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


@bp.route('/export/movements')
@login_optional
def export_movements():
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['article_sku','article_name', 'quantity', 'type', 'note', 'timestamp'])
    for m in Movement.query.all():
        writer.writerow([m.article.sku,m.article.name, m.quantity, m.type, m.note, m.timestamp])
    output = si.getvalue()
    return Response(output, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=movements.csv'})

@bp.route('/inventory', methods=['GET', 'POST'])
@login_optional
@admin_required
def inventory():
    query = Article.query
    search = request.args.get('search')
    if search:
        query = query.filter((Article.name.contains(search)) | (Article.sku.contains(search)))
    category = request.args.get('category')
    if category:
        query = query.filter_by(category=category)
    articles = query.all()
    categories = ['Sticker', 'Schal', 'Shirt']

    if request.method == 'POST' and 'search' not in request.form:
        adjusted = 0
        for article in articles:
            val = request.form.get(f'count_{article.id}')
            if val is not None and val != '':
                counted = int(val)
                diff = counted - article.stock
                if diff != 0:
                    movement = Movement(article_id=article.id, quantity=diff, type='Inventur', note='Inventur')
                    article.stock = counted
                    db.session.add(movement)
                    adjusted += 1
        if adjusted:
            db.session.commit()
        flash(f'Inventur erfolgreich gespeichert – {adjusted} Artikel angepasst.')
        return redirect(url_for('main.inventory'))

    return render_template('inventory.html', articles=articles, categories=categories, selected_category=category)


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

    pdf = FPDF(unit='mm', format=(100, 50))
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
@admin_required
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
@admin_required
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
