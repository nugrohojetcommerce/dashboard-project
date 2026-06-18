from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Brand, UserBrand


class UserBrandForm(forms.ModelForm):
    assigned_brands = forms.ModelMultipleChoiceField(
        queryset=Brand.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Assigned Brands",
    )

    class Meta:
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["assigned_brands"].initial = (
                UserBrand.objects.filter(user=self.instance)
                .values_list("brand_id", flat=True)
            )


admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    form = UserBrandForm

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Brand Access Control",
            {
                "fields": (
                    "assigned_brands",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        selected_brands = form.cleaned_data.get(
            "assigned_brands",
            Brand.objects.none(),
        )

        UserBrand.objects.filter(user=obj).delete()

        UserBrand.objects.bulk_create(
            [
                UserBrand(
                    user=obj,
                    brand=brand,
                )
                for brand in selected_brands
            ]
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        return qs.filter(id=request.user.id)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        return obj is not None and obj.id == request.user.id

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name",)

    def has_module_permission(self, request):
        return request.user.is_superuser