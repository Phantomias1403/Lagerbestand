from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from . import models
from . import utils

User = get_user_model()


class LoginForm(forms.Form):
    username = forms.CharField(label=_('Benutzername'))
    password = forms.CharField(label=_('Passwort'), widget=forms.PasswordInput)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'display_name', 'gender', 'bio', 'profile_image']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
        }


class ArticleForm(forms.ModelForm):
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


class MovementForm(forms.ModelForm):
    class Meta:
        model = models.Movement
        fields = ['quantity', 'movement_type', 'note', 'invoice_number']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }


class CSVImportForm(forms.Form):
    file = forms.FileField(label='CSV-Datei')


class OrderForm(forms.ModelForm):
    class Meta:
        model = models.Order
        fields = ['customer_name', 'customer_address', 'status', 'user', 'order_number']
        widgets = {
            'customer_address': forms.Textarea(attrs={'rows': 3}),
        }


class OrderItemForm(forms.ModelForm):
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


class CategoryForm(forms.ModelForm):
    class Meta:
        model = models.Category
        fields = ['name', 'prefix', 'default_price', 'default_min_stock']


class EndingCategoryForm(forms.ModelForm):
    class Meta:
        model = models.EndingCategory
        fields = ['category', 'suffix', 'price', 'csv_multiplier']


EndingComponentFormSet = inlineformset_factory(
    models.EndingCategory,
    models.EndingComponent,
    fields=['component_sku', 'component_quantity'],
    extra=1,
    can_delete=True,
)


class SettingForm(forms.Form):
    company_name = forms.CharField(label='Unternehmen', required=False)
    company_address = forms.CharField(label='Adresse', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    category_prefixes = forms.CharField(
        label='SKU-Prefixe',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'ST-:Sticker:0:1000'}),
    )


class BackupImportForm(forms.Form):
    file = forms.FileField(label='Backup-ZIP-Datei')
    include_articles = forms.BooleanField(required=False, initial=True)
    include_orders = forms.BooleanField(required=False, initial=True)
    include_settings = forms.BooleanField(required=False, initial=True)


class MessageForm(forms.ModelForm):
    class Meta:
        model = models.Message
        fields = ['receiver', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
        }


class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'is_active', 'is_staff', 'is_superuser']
