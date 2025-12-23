from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from . import models
from . import utils

User = get_user_model()



class StyledFormMixin:
    """Apply consistent form-control classes across widgets."""

    text_like_inputs = {
        'text',
        'email',
        'number',
        'password',
        'search',
        'tel',
        'url',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            self._apply_widget_classes(widget)
            self._apply_placeholder(widget, field)

    def _apply_widget_classes(self, widget: forms.Widget) -> None:
        existing_classes = widget.attrs.get('class', '').split()

        def ensure_class(css_class: str) -> None:
            if css_class and css_class not in existing_classes:
                existing_classes.append(css_class)

        if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
            ensure_class('form-check-input')
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            ensure_class('form-select')
        else:
            ensure_class('form-control')

        widget.attrs['class'] = ' '.join(existing_classes).strip()

    def _apply_placeholder(self, widget: forms.Widget, field: forms.Field) -> None:
        has_placeholder = widget.attrs.get('placeholder')
        input_type = getattr(widget, 'input_type', None)
        is_text_like = (
            isinstance(widget, (forms.TextInput, forms.Textarea))
            or input_type in self.text_like_inputs
        )
        if not has_placeholder and is_text_like and field.label:
            widget.attrs['placeholder'] = field.label


class LoginForm(StyledFormMixin, forms.Form):
    username = forms.CharField(label=_('Benutzername'))
    password = forms.CharField(label=_('Passwort'), widget=forms.PasswordInput)


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'display_name', 'gender', 'bio', 'profile_image']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
        }


class ArticleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.Article
        fields = [
            'name', 'sku', 'category', 'stock', 'minimum_stock',
            'price', 'location_primary', 'location_secondary', 'image'
        ]

    def clean(self):
        cleaned = super().clean()
        sku = cleaned.get('sku')
        category = cleaned.get('category')
        if not category and sku:
            category_guess = utils.category_from_sku(sku)
            if category_guess:
                cleaned['category'] = category_guess
                self.cleaned_data['category'] = category_guess
        return cleaned


class MovementForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.Movement
        fields = ['quantity', 'movement_type', 'note', 'invoice_number']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }


class CSVImportForm(forms.Form):
    file = forms.FileField(
        label="Datei auswählen",
        widget=forms.ClearableFileInput(attrs={"class": "form-control form-control-lg"})
    )


class OrderForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.Order
        fields = ['customer_name', 'customer_address', 'status', 'user', 'order_number']
        widgets = {
            'customer_address': forms.Textarea(attrs={'rows': 3}),
        }


class OrderItemForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.OrderItem
        fields = ['article', 'quantity', 'unit_price']


OrderItemFormSet = inlineformset_factory(
    models.Order,
    models.OrderItem,
    form=OrderItemForm,
    extra=1,
    can_delete=True,
)


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.Category
        fields = ['name', 'prefix', 'default_price', 'default_min_stock']


class EndingCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.EndingCategory
        fields = ['category', 'suffix', 'price', 'csv_multiplier']


class EndingComponentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.EndingComponent
        fields = ['component_sku', 'component_quantity']


EndingComponentFormSet = inlineformset_factory(
    models.EndingCategory,
    models.EndingComponent,
    form=EndingComponentForm,
    extra=1,
    can_delete=True,
)



class BackupImportForm(StyledFormMixin, forms.Form):
    file = forms.FileField(label='Backup-ZIP-Datei')
    include_articles = forms.BooleanField(required=False, initial=True)
    include_orders = forms.BooleanField(required=False, initial=True)


class MessageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = models.Message
        fields = ['receiver', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
        }


class UserAdminForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'is_active', 'is_staff', 'is_superuser']
