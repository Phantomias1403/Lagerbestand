from datetime import datetime

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)


from . import db
from .models import Article, Movement, Order, OrderItem
from .routes import login_optional, admin_required
from .utils import get_setting


bp = Blueprint('orders', __name__, url_prefix='/orders')


@bp.route('/dashboard')
@login_optional
def dashboard():
    """Show overview of all orders."""
    query = Order.query
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)
    orders = query.order_by(Order.created_at.desc()).all()
    statuses = ['offen', 'bezahlt', 'versendet']
    return render_template(
        'orders/dashboard.html',
        orders=orders,
        statuses=statuses,
        selected_status=status,
    )


@bp.route('/<int:order_id>')
@login_optional
def detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('orders/detail.html', order=order)


@bp.route('/<int:order_id>/label')
@login_optional
def label(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status not in ['bezahlt', 'versendet']:
        flash('Versandetikett erst ab Status bezahlt verfügbar')
        return redirect(url_for('orders.detail', order_id=order.id))

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

    pdf.ln(3)

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

    return Response(
        pdf.output(dest='S').encode('latin-1'),
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment;filename=order_{order.id}_label.pdf'
        },
    )


@bp.route('/new', methods=['GET', 'POST'])
@login_optional
@admin_required
def new():
    statuses = ['offen', 'bezahlt', 'versendet']
    articles = Article.query.all()
    if request.method == 'POST':
        street = request.form.get('customer_street', '')
        city_zip = request.form.get('customer_city_zip', '')
        address = f"{street}\n{city_zip}" if street or city_zip else None
        order = Order(
            customer_name=request.form['customer_name'],
            customer_address=address,
            status=request.form['status'],
        )
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
                    return redirect(url_for('orders.new'))
                item = OrderItem(
                    order_id=order.id,
                    article_id=article.id,
                    quantity=qty,
                    unit_price=price,
                )
                db.session.add(item)
                if order.status in ['offen', 'bezahlt']:
                    article.stock -= qty
                    movements.append(
                        Movement(
                            article_id=article.id,
                            quantity=-qty,
                            note=f'Bestellung #{order.id}',
                            order_id=order.id,
                            type='Warenausgang',
                        )
                    )
        for m in movements:
            db.session.add(m)
        db.session.commit()
        flash('Bestellung angelegt')
        return redirect(url_for('orders.detail', order_id=order.id))
    return render_template(
        'orders/form.html',
        articles=articles,
        statuses=statuses,
        addr_street='',
        addr_city_zip='',
    )


@bp.route('/<int:order_id>/edit', methods=['GET', 'POST'])
@login_optional
@admin_required
def edit(order_id):
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
        return redirect(url_for('orders.detail', order_id=order.id))
    street = ''
    city_zip = ''
    if order.customer_address:
        lines = order.customer_address.splitlines()
        if len(lines) > 0:
            street = lines[0]
        if len(lines) > 1:
            city_zip = lines[1]
    return render_template(
        'orders/form.html',
        order=order,
        statuses=statuses,
        articles=None,
        addr_street=street,
        addr_city_zip=city_zip,
    )

