from django import forms
from django.contrib import admin
from django.contrib.auth.models import User

from .models import Brand, UserBrand


# =========================================================
# FORM: BRAND ADMIN (assign users to brand)
# =========================================================
class BrandForm(forms.ModelForm):
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Assigned Users",
    )

    class Meta:
        model = Brand
        fields = ("name", "users")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # preload existing users from UserBrand (source of truth)
        if self.instance.pk:
            self.fields["users"].initial = User.objects.filter(
                userbrand__brand=self.instance
            )


# =========================================================
# BRAND ADMIN
# =========================================================
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    form = BrandForm
    list_display = ("name",)
    search_fields = ("name",)

    def save_model(self, request, obj, form, change):
        """
        Sync Brand <-> User through UserBrand table
        """
        super().save_model(request, obj, form, change)

        users = form.cleaned_data.get("users", [])

        # reset old relations
        UserBrand.objects.filter(brand=obj).delete()

        # recreate relations
        UserBrand.objects.bulk_create([
            UserBrand(user=u, brand=obj)
            for u in users
        ])


# =========================================================
# FORM: USER ADMIN (assign brands to user)
# =========================================================
class UserBrandForm(forms.ModelForm):
    assigned_brands = forms.ModelMultipleChoiceField(
        queryset=Brand.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Assigned Brands",
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "assigned_brands")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # preload from UserBrand (source of truth)
        if self.instance.pk:
            self.fields["assigned_brands"].initial = Brand.objects.filter(
                userbrand__user=self.instance
            )


# =========================================================
# USER ADMIN
# =========================================================
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    form = UserBrandForm

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Brand Access Control",
            {
                "fields": ("assigned_brands",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """
        Sync User <-> Brand through UserBrand table
        """
        super().save_model(request, obj, form, change)

        brands = form.cleaned_data.get("assigned_brands", [])

        # reset old relations
        UserBrand.objects.filter(user=obj).delete()

        # recreate relations
        UserBrand.objects.bulk_create([
            UserBrand(user=obj, brand=b)
            for b in brands
        ])


# =========================================================
# OPTIONAL: Brand admin access restriction
# =========================================================
# @admin.register(Brand)
# class BrandAdminRestricted(admin.ModelAdmin):
#     """
#     (REMOVE THIS IF YOU ALREADY USE BrandAdmin ABOVE)
#     """
#     def has_module_permission(self, request):
#         return request.user.is_superuser



# from django import forms
# from django.contrib import admin
# from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# from django.contrib.auth.models import User

# from .models import Brand, UserBrand


# class UserBrandForm(forms.ModelForm):
#     assigned_brands = forms.ModelMultipleChoiceField(
#         queryset=Brand.objects.all(),
#         widget=forms.CheckboxSelectMultiple,
#         required=False,
#         label="Assigned Brands",
#     )

#     class Meta:
#         model = User
#         fields = "__all__"

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)

#         if self.instance and self.instance.pk:
#             self.fields["assigned_brands"].initial = (
#                 UserBrand.objects.filter(user=self.instance)
#                 .values_list("brand_id", flat=True)
#             )


# admin.site.unregister(User)


# @admin.register(User)
# class CustomUserAdmin(BaseUserAdmin):
#     form = UserBrandForm

#     fieldsets = BaseUserAdmin.fieldsets + (
#         (
#             "Brand Access Control",
#             {
#                 "fields": (
#                     "assigned_brands",
#                 )
#             },
#         ),
#     )

#     # def save_model(self, request, obj, form, change):
#     #     super().save_model(request, obj, form, change)

#     #     selected_brands = form.cleaned_data.get(
#     #         "assigned_brands",
#     #         Brand.objects.none(),
#     #     )

#     #     UserBrand.objects.filter(user=obj).delete()

#     #     UserBrand.objects.bulk_create(
#     #         [
#     #             UserBrand(
#     #                 user=obj,
#     #                 brand=brand,
#     #             )
#     #             for brand in selected_brands
#     #         ]
#     #     )

#     def save_model(self, request, obj, form, change):
#         super().save_model(request, obj, form, change)

#         selected_brands = form.cleaned_data["assigned_brands"]

#         obj.brands.set(selected_brands)

#     def get_queryset(self, request):
#         qs = super().get_queryset(request)

#         if request.user.is_superuser:
#             return qs

#         return qs.filter(id=request.user.id)

#     def has_change_permission(self, request, obj=None):
#         if request.user.is_superuser:
#             return True

#         return obj is not None and obj.id == request.user.id

#     def has_delete_permission(self, request, obj=None):
#         return request.user.is_superuser


# @admin.register(Brand)
# class BrandAdmin(admin.ModelAdmin):
#     list_display = ("name",)

#     def has_module_permission(self, request):
#         return request.user.is_superuser