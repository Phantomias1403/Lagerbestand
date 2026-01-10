from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from decimal import Decimal

from django import forms as django_forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import FormView
from django.views.generic.base import RedirectView
from django.db import transaction
from django.db.models import Q, F, Sum, DecimalField, ExpressionWrapper

from amazon.importer import AmazonOrderImporter
from amazon.models import AmazonMarketplace, AmazonOrder
from amazon.sp_api import AmazonSpApiError

from . import forms, models, utils

User = get_user_model()


def login_optional(view_func):
    if utils.user_management_enabled():
        return login_required(view_func)
    return view_func


def log_activity(request: HttpRequest, action: str) -> None:
    if request.user.is_authenticated:
        models.ActivityLog.objects.create(user=request.user, action=action)


class OptionalLoginRequiredMixin(View):
    """Mixin that only requires login when user management is enabled."""

    @method_decorator(login_optional)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DashboardView(View):
    template_name = 'core/dashboard.html'

    @method_decorator(login_optional)
    def get(self, request: HttpRequest) -> HttpResponse:
        articles = models.Article.objects.select_related('category').all()
        search = request.GET.get('search', '').strip()
        if search:
            articles = articles.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        category = request.GET.get('category', '').strip()
        if category:
            articles = articles.filter(category__name=category)
        if request.GET.get('understock') == '1':
            articles = articles.filter(stock__lt=F('minimum_stock'))
        if request.GET.get('no_secondary') == '1':
            articles = articles.filter(Q(location_secondary='') | Q(location_secondary__isnull=True))
        categories = utils.get_categories()
        return render(request, self.template_name, {
            'articles': articles,
            'categories': categories,
            'selected_category': category,
        })


class ProfileSelectView(TemplateView):
    template_name = 'core/profile_select.html'

    @method_decorator(login_optional)
    def dispatch(self, request, *args, **kwargs):
        if not utils.user_management_enabled():
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all()
        return context


class LoginView(FormView):
    form_class = forms.LoginForm
    template_name = 'core/login.html'

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not utils.user_management_enabled():
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        preselect = self.request.GET.get('user_id')
        if preselect:
            try:
                user = User.objects.get(pk=int(preselect))
                initial['username'] = user.username
            except (ValueError, User.DoesNotExist):
                pass
        return initial

    def form_valid(self, form):
        user = authenticate(self.request, username=form.cleaned_data['username'], password=form.cleaned_data['password'])
        if user is not None:
            login(self.request, user)
            return redirect('dashboard')
        messages.error(self.request, 'Ungültige Anmeldedaten')
        return self.form_invalid(form)


class LogoutView(RedirectView):
    url = reverse_lazy('dashboard')

    @method_decorator(login_optional)
    def get(self, request, *args, **kwargs):
        logout(request)
        return super().get(request, *args, **kwargs)


class ProfileView(FormView):
    template_name = 'core/profile.html'
    form_class = forms.ProfileForm

    @method_decorator(login_optional)
    def dispatch(self, request, *args, **kwargs):
        if not utils.user_management_enabled():
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        log_activity(self.request, 'Profil aktualisiert')
        messages.success(self.request, 'Profil aktualisiert')
        return redirect('profile')


class ArticleListView(OptionalLoginRequiredMixin, ListView):
    model = models.Article
    template_name = 'core/article_list.html'
    context_object_name = 'articles'

    def get_queryset(self):
        return models.Article.objects.select_related('category').all()


class ArticleCreateView(OptionalLoginRequiredMixin, FormView):
    template_name = 'core/article_form.html'
    form_class = forms.ArticleForm

    def form_valid(self, form):
        article = form.save(commit=False)
        if not article.minimum_stock:
            article.minimum_stock = utils.get_default_minimum_stock(article.category)
        if not article.price:
            price = utils.price_from_suffix(article.sku, article.category)
            if price is None:
                price = utils.price_from_sku(article.sku)
            if price is None:
                price = utils.get_default_price(article.category)
            article.price = price or 0
        article.save()
        log_activity(self.request, f'Artikel {article.sku} erstellt')
        messages.success(self.request, 'Artikel erstellt')
        return redirect('dashboard')


class ArticleUpdateView(OptionalLoginRequiredMixin, FormView):
    template_name = 'core/article_form.html'
    form_class = forms.ArticleForm

    def dispatch(self, request, *args, **kwargs):
        self.article = get_object_or_404(models.Article, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.article
        return kwargs

    def form_valid(self, form):
        article = form.save()
        log_activity(self.request, f'Artikel {article.sku} aktualisiert')
        messages.success(self.request, 'Artikel aktualisiert')
        return redirect('dashboard')


class ArticleDeleteView(OptionalLoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        article = get_object_or_404(models.Article, pk=pk)
        sku = article.sku
        article.delete()
        log_activity(request, f'Artikel {sku} gelöscht')
        messages.success(request, 'Artikel gelöscht')
        return redirect('dashboard')


class ArticleHistoryView(OptionalLoginRequiredMixin, DetailView):
    model = models.Article
    template_name = 'core/article_history.html'
    context_object_name = 'article'


class MovementCreateView(OptionalLoginRequiredMixin, FormView):
    template_name = 'core/movement_form.html'
    form_class = forms.MovementForm

    def dispatch(self, request, *args, **kwargs):
        self.article = get_object_or_404(models.Article, pk=kwargs['article_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['article'] = self.article
        return context

    def form_valid(self, form):
        movement = form.save(commit=False)
        movement.article = self.article
        qty = movement.quantity
        if movement.movement_type == 'Warenausgang' and qty > 0:
            qty = -qty
        if movement.movement_type in {'Wareneingang', 'Inventur'} and qty < 0:
            qty = abs(qty)
        movement.quantity = qty
        movement.save()
        self.article.stock += movement.quantity
        self.article.save(update_fields=['stock'])
        log_activity(self.request, f'Bewegung {movement.movement_type} {movement.quantity} für {self.article.sku}')
        if self.article.stock < self.article.minimum_stock:
            messages.warning(self.request, 'Bestand unter Mindestbestand!')
        messages.success(self.request, 'Bewegung erfasst')
        return redirect('article_history', pk=self.article.pk)


class CSVImportView(OptionalLoginRequiredMixin, FormView):
    template_name = 'core/import.html'
    form_class = forms.CSVImportForm

    def form_valid(self, form):
        uploaded = form.cleaned_data['file']
        content = uploaded.read()
        text = None
        for encoding in ('utf-8-sig', 'latin1'):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            messages.error(self.request, 'Datei konnte nicht gelesen werden.')
            return redirect('import_csv')
        stream = io.StringIO(text)
        reader = csv.DictReader(stream)
        required = {'name', 'sku', 'stock'}

        def normalised_headers(fieldnames):
            return {
                utils.normalise_import_header(name)
                for name in (fieldnames or [])
                if utils.normalise_import_header(name)
            }

        normalised = normalised_headers(reader.fieldnames)
        if not required.issubset(normalised):
            stream.seek(0)
            reader = csv.DictReader(stream, delimiter=';')
            normalised = normalised_headers(reader.fieldnames)

        if not required.issubset(normalised):
            missing = ', '.join(sorted(required - normalised))
            messages.error(self.request, f'Die Datei enthält nicht alle benötigten Spalten ({missing}).')
            return redirect('import_csv')

        try:
            with transaction.atomic():
                created, updated = utils.import_articles(reader)
        except Exception as exc:  # pragma: no cover - defensive
            messages.error(self.request, f'Import fehlgeschlagen: {exc}')
            return redirect('import_csv')

        log_activity(self.request, 'CSV-Import durchgeführt')
        if created or updated:
            messages.success(self.request, f'Import abgeschlossen: {created} neu, {updated} aktualisiert.')
        else:
            messages.info(self.request, 'Die Datei enthielt keine neuen Artikel.')
        return redirect('dashboard')


@login_optional
def export_articles(request: HttpRequest) -> HttpResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'sku', 'stock', 'minimum_stock', 'category', 'location_primary', 'location_secondary'])
    for article in models.Article.objects.select_related('category').all():
        writer.writerow([
            article.name,
            article.sku,
            article.stock,
            article.minimum_stock,
            article.category.name if article.category else '',
            article.location_primary,
            article.location_secondary,
        ])
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="articles.csv"'
    return response


class OrderListView(OptionalLoginRequiredMixin, ListView):
    model = models.Order
    template_name = 'core/order_list.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return models.Order.objects.select_related('user').prefetch_related('items__article').all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['amazon_orders'] = AmazonOrder.objects.select_related('marketplace').prefetch_related('items')
        context['latest_order'] = (
            models.Order.objects.select_related('user')
            .prefetch_related('items__article')
            .order_by('-created_at')
            .first()
        )
        return context


class OrderAnalysisView(OptionalLoginRequiredMixin, TemplateView):
    template_name = 'core/order_analysis.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = forms.OrderAnalysisForm(self.request.GET or None)
        orders = models.Order.objects.select_related('user').prefetch_related('items__article').all()
        if form.is_valid():
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            marketplace = form.cleaned_data.get('marketplace') or forms.OrderAnalysisForm.ALL_MARKETPLACES
            sort = form.cleaned_data.get('sort') or 'desc'
            if start_date:
                orders = orders.filter(created_at__date__gte=start_date)
            if end_date:
                orders = orders.filter(created_at__date__lte=end_date)
            if marketplace != forms.OrderAnalysisForm.ALL_MARKETPLACES:
                orders = orders.filter(marketplace=marketplace)
        else:
            sort = 'desc'
        ordering = 'created_at' if sort == 'asc' else '-created_at'
        orders = orders.order_by(ordering)
        revenue_expression = ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        item_queryset = models.OrderItem.objects.filter(order__in=orders.values('pk'))
        total_revenue = item_queryset.aggregate(total=Sum(revenue_expression))['total'] or Decimal("0")
        marketplace_rows = (
            item_queryset
            .values('order__marketplace')
            .annotate(total=Sum(revenue_expression))
            .order_by('order__marketplace')
        )
        totals_by_marketplace = {row['order__marketplace']: row['total'] or Decimal("0") for row in marketplace_rows}
        marketplace_totals = [
            {
                'code': code,
                'label': label,
                'total': totals_by_marketplace.get(code, Decimal("0")),
            }
            for code, label in models.Order.MARKETPLACE_CHOICES
        ]
        context.update({
            'form': form,
            'orders': orders,
            'total_revenue': total_revenue,
            'total_orders': orders.count(),
            'marketplace_totals': marketplace_totals,
        })
        return context


class OrderDetailView(OptionalLoginRequiredMixin, DetailView):
    model = models.Order
    template_name = 'core/order_detail.html'
    context_object_name = 'order'


class OrderEditView(OptionalLoginRequiredMixin, View):
    template_name = 'core/order_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.order = None
        if 'pk' in kwargs:
            self.order = get_object_or_404(models.Order, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = forms.OrderForm(instance=self.order)
        formset = forms.OrderItemFormSet(instance=self.order)
        return render(request, self.template_name, {'form': form, 'formset': formset, 'order': self.order})

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = forms.OrderForm(request.POST, instance=self.order)
        formset = forms.OrderItemFormSet(request.POST, instance=self.order)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                order = form.save()
                if self.order:
                    for movement in models.Movement.objects.filter(order=order):
                        if movement.article:
                            movement.article.stock += abs(movement.quantity)
                            movement.article.save(update_fields=['stock'])
                    models.Movement.objects.filter(order=order).delete()
                formset.instance = order
                formset.save()
                total_qty = sum(item.quantity for item in order.items.all())
                order.order_quantity = total_qty
                order.save(update_fields=['order_quantity'])
                utils.allocate_stock_for_order(order)
                action = 'Bestellung aktualisiert' if self.order else 'Bestellung erstellt'
                log_activity(request, action)
                messages.success(request, 'Bestellung gespeichert')
                return redirect('order_detail', pk=order.pk)
        messages.error(request, 'Bitte Formular prüfen')
        return render(request, self.template_name, {'form': form, 'formset': formset, 'order': self.order})


class OrderDeleteView(OptionalLoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = get_object_or_404(models.Order, pk=pk)
        for movement in models.Movement.objects.filter(order=order):
            if movement.article:
                movement.article.stock += abs(movement.quantity)
                movement.article.save(update_fields=['stock'])
        models.Movement.objects.filter(order=order).delete()
        order.delete()
        log_activity(request, 'Bestellung gelöscht')
        messages.success(request, 'Bestellung gelöscht')
        return redirect('order_list')


class CategorySettingsView(OptionalLoginRequiredMixin, View):
    template_name = 'core/settings_categories.html'

    def get(self, request: HttpRequest) -> HttpResponse:
        categories = models.Category.objects.all()
        category_id = request.GET.get('pk')
        instance = None
        if category_id:
            instance = get_object_or_404(models.Category, pk=category_id)
        form = forms.CategoryForm(instance=instance)
        return render(request, self.template_name, {'categories': categories, 'form': form})

    def post(self, request: HttpRequest) -> HttpResponse:
        category_id = request.POST.get('pk')
        action = request.POST.get('action')
        instance = None
        if category_id:
            instance = get_object_or_404(models.Category, pk=category_id)

        if action == 'apply' and instance:
            if not instance.prefix:
                messages.error(request, 'Kategorie besitzt keinen Prefix und kann nicht angewendet werden.')
            else:
                updated = utils.apply_category_defaults(instance)
                if updated:
                    messages.success(request, f'{updated} Artikel aktualisiert.')
                else:
                    messages.info(request, 'Keine Artikel mit diesem Prefix gefunden.')
            return redirect('settings_categories')

        form = forms.CategoryForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kategorie gespeichert')
            return redirect('settings_categories')
        categories = models.Category.objects.all()
        return render(request, self.template_name, {'categories': categories, 'form': form})


class EndingSettingsView(OptionalLoginRequiredMixin, View):
    template_name = 'core/settings_endings.html'

    def dispatch(self, request, *args, **kwargs):
        self.ending = None
        if 'pk' in kwargs:
            self.ending = get_object_or_404(models.EndingCategory, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = forms.EndingCategoryForm(instance=self.ending)
        formset = forms.EndingComponentFormSet(instance=self.ending)
        endings = models.EndingCategory.objects.select_related('category').all()
        return render(request, self.template_name, {'form': form, 'formset': formset, 'endings': endings, 'ending': self.ending})

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = forms.EndingCategoryForm(request.POST, instance=self.ending)
        formset = forms.EndingComponentFormSet(request.POST, instance=self.ending)
        if form.is_valid() and formset.is_valid():
            ending = form.save()
            formset.instance = ending
            formset.save()
            messages.success(request, 'Suffix gespeichert')
            return redirect('settings_endings')
        endings = models.EndingCategory.objects.select_related('category').all()
        return render(request, self.template_name, {'form': form, 'formset': formset, 'endings': endings, 'ending': self.ending})

class ApiImportView(OptionalLoginRequiredMixin, View):
    template_name = 'core/settings_api_imports.html'

    def _amazon_missing_env_vars(self) -> list[str]:
        required = (
            'AMAZON_CLIENT_ID',
            'AMAZON_CLIENT_SECRET',
            'AMAZON_REFRESH_TOKEN',
        )
        return [name for name in required if not os.environ.get(name)]

    def get(self, request: HttpRequest) -> HttpResponse:
        marketplaces = AmazonMarketplace.objects.all()
        return render(request, self.template_name, {
            'marketplaces': marketplaces,
            'amazon_missing_env_vars': self._amazon_missing_env_vars(),
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        action = request.POST.get('action')
        if action == 'test_amazon':
            try:
                importer = AmazonOrderImporter()
                importer.client._ensure_access_token()
                messages.success(request, 'Amazon API Verbindung erfolgreich getestet.')
                log_activity(request, 'Amazon API Verbindung getestet')
            except KeyError as exc:
                messages.error(request, f'Amazon API Verbindung fehlgeschlagen: Fehlende Umgebungsvariable {exc}.')
            except AmazonSpApiError as exc:
                messages.error(request, f'Amazon API Verbindung fehlgeschlagen: {exc}.')
            return redirect('settings_api_imports')
        if action == 'run_amazon_import':
            try:
                importer = AmazonOrderImporter()
                created = importer.import_orders()
                if importer.errors:
                    messages.error(request, f"Amazon Import fehlgeschlagen: {', '.join(importer.errors)}.")
                else:
                    messages.success(request, f'Amazon Bestellungen importiert. Erstellt: {created}.')
                    log_activity(request, 'Amazon letzte Bestellung importiert')
            except KeyError as exc:
                messages.error(request, f'Amazon Import fehlgeschlagen: Fehlende Umgebungsvariable {exc}.')
            except AmazonSpApiError as exc:
                messages.error(request, f'Amazon Import fehlgeschlagen: {exc}.')
            return redirect('settings_api_imports')
        if action == 'run_amazon_latest_order':
            try:
                importer = AmazonOrderImporter()
                updated = importer.import_latest_orders()
                messages.success(request, f'Amazon letzte Bestellung importiert. Aktualisiert: {updated}.')
                log_activity(request, 'Amazon letzte Bestellung importiert')
            except KeyError as exc:
                messages.error(request, f'Amazon Import fehlgeschlagen: Fehlende Umgebungsvariable {exc}.')
            except AmazonSpApiError as exc:
                messages.error(request, f'Amazon Import fehlgeschlagen: {exc}.')
            return redirect('settings_api_imports')
        messages.error(request, 'Unbekannte Aktion.')
        return redirect('settings_api_imports')


class BackupExportView(OptionalLoginRequiredMixin, View):
    def post(self, request: HttpRequest) -> HttpResponse:
        zip_buffer = io.BytesIO()
        import zipfile

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['sku', 'name', 'category', 'stock', 'minimum_stock', 'location_primary', 'location_secondary', 'image', 'price'])
            for article in models.Article.objects.select_related('category'):
                writer.writerow([
                    article.sku,
                    article.name,
                    article.category.name if article.category else '',
                    article.stock,
                    article.minimum_stock,
                    article.location_primary,
                    article.location_secondary,
                    article.image,
                    f"{article.price:.2f}",
                ])
            archive.writestr('articles.csv', output.getvalue())

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['id', 'customer_name', 'customer_address', 'status', 'marketplace', 'created_at', 'user_id'])
            for order in models.Order.objects.all():
                writer.writerow([
                    order.pk,
                    order.customer_name,
                    order.customer_address,
                    order.status,
                    order.marketplace,
                    order.created_at.isoformat(),
                    order.user.id if order.user else '',
                ])
            archive.writestr('orders.csv', output.getvalue())

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['order_id', 'article_sku', 'quantity', 'unit_price'])
            for item in models.OrderItem.objects.select_related('article', 'order'):
                writer.writerow([
                    item.order_id,
                    item.article.sku if item.article else '',
                    item.quantity,
                    f"{item.unit_price:.2f}",
                ])
            archive.writestr('order_items.csv', output.getvalue())

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['article_sku', 'quantity', 'type', 'note', 'timestamp', 'invoice_number', 'order_id'])
            for movement in models.Movement.objects.select_related('article', 'order'):
                writer.writerow([
                    movement.article.sku if movement.article else '',
                    movement.quantity,
                    movement.movement_type,
                    movement.note,
                    movement.created_at.isoformat(),
                    movement.invoice_number,
                    movement.order_id or '',
                ])
            archive.writestr('movements.csv', output.getvalue())

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="backup.zip"'
        log_activity(request, 'Backup exportiert')
        return response


class BackupImportView(OptionalLoginRequiredMixin, FormView):
    template_name = 'core/settings_backup.html'
    form_class = forms.BackupImportForm

    def form_valid(self, form):
        file = form.cleaned_data['file']
        import zipfile
        data = file.read()
        if not zipfile.is_zipfile(io.BytesIO(data)):
            messages.error(self.request, 'Ungültiges Archiv')
            return redirect('settings_backup')

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if form.cleaned_data.get('include_articles'):
                try:
                    text = archive.read('articles.csv').decode('utf-8')
                    utils.import_articles(csv.DictReader(io.StringIO(text)))
                except KeyError:
                    pass
            if form.cleaned_data.get('include_orders'):
                try:
                    text = archive.read('orders.csv').decode('utf-8')
                    order_rows = list(csv.DictReader(io.StringIO(text)))
                    order_map: dict[int, models.Order] = {}
                    for row in order_rows:
                        try:
                            oid = int(row.get('id', 0))
                        except ValueError:
                            continue
                        order, _ = models.Order.objects.update_or_create(
                            pk=oid,
                            defaults={
                                'customer_name': row.get('customer_name', ''),
                                'customer_address': row.get('customer_address', ''),
                                'status': row.get('status', 'offen'),
                                'marketplace': row.get('marketplace', 'unbekannt'),
                            }
                        )
                        order_map[oid] = order
                    try:
                        item_text = archive.read('order_items.csv').decode('utf-8')
                        items = list(csv.DictReader(io.StringIO(item_text)))
                        for order in order_map.values():
                            order.items.all().delete()
                        for row in items:
                            try:
                                oid = int(row.get('order_id', 0))
                                quantity = int(row.get('quantity', 0))
                                price = float(row.get('unit_price', 0))
                            except ValueError:
                                continue
                            article = models.Article.objects.filter(sku=row.get('article_sku', '')).first()
                            order = order_map.get(oid)
                            if not article or not order:
                                continue
                            models.OrderItem.objects.create(
                                order=order,
                                article=article,
                                quantity=quantity,
                                unit_price=price,
                            )
                        for order in order_map.values():
                            order.order_quantity = sum(item.quantity for item in order.items.all())
                            order.save(update_fields=['order_quantity'])
                    except KeyError:
                        pass
                    try:
                        movement_text = archive.read('movements.csv').decode('utf-8')
                        models.Movement.objects.all().delete()
                        for row in csv.DictReader(io.StringIO(movement_text)):
                            article = models.Article.objects.filter(sku=row.get('article_sku', '')).first()
                            if not article:
                                continue
                            try:
                                qty = int(row.get('quantity', 0))
                            except ValueError:
                                qty = 0
                            movement = models.Movement.objects.create(
                                article=article,
                                quantity=qty,
                                movement_type=row.get('type', 'Warenausgang'),
                                note=row.get('note', ''),
                                invoice_number=row.get('invoice_number', ''),
                            )
                            try:
                                oid = int(row.get('order_id', 0))
                                movement.order_id = oid if oid else None
                                timestamp = row.get('timestamp')
                                if timestamp:
                                    try:
                                        movement.created_at = datetime.fromisoformat(timestamp)
                                    except ValueError:
                                        pass
                                movement.save(update_fields=['order', 'created_at'])
                            except ValueError:
                                pass
                    except KeyError:
                        pass
                except KeyError:
                    pass

        messages.success(self.request, 'Backup importiert')
        log_activity(self.request, 'Backup importiert')
        return redirect('settings_backup')


class MessageListView(OptionalLoginRequiredMixin, ListView):
    model = models.Message
    template_name = 'core/messages.html'

    def get_queryset(self):
        qs = super().get_queryset().select_related('sender', 'receiver')
        if self.request.user.is_authenticated:
            return qs.filter(Q(sender=self.request.user) | Q(receiver=self.request.user))
        return qs.none()


class MessageCreateView(OptionalLoginRequiredMixin, FormView):
    template_name = 'core/message_form.html'
    form_class = forms.MessageForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.setdefault('initial', {})
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        receiver_field = form.fields.get('receiver')
        if isinstance(receiver_field, django_forms.ModelChoiceField):
            receiver_field.queryset = User.objects.exclude(pk=self.request.user.pk)
        return form

    def form_valid(self, form):
        message = form.save(commit=False)
        message.sender = self.request.user
        message.save()
        messages.success(self.request, 'Nachricht gesendet')
        return redirect('messages')


class ActivityLogListView(OptionalLoginRequiredMixin, ListView):
    model = models.ActivityLog
    template_name = 'core/activity_logs.html'
    paginate_by = 50

    def get_queryset(self):
        return models.ActivityLog.objects.select_related('user').order_by('-created_at')


class StaticTemplateView(OptionalLoginRequiredMixin, TemplateView):
    template_name = 'core/static_page.html'

    def get_template_names(self):
        slug = self.kwargs.get('slug', 'info')
        return [f'core/static/{slug}.html', self.template_name]
