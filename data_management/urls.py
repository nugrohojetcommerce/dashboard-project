from django.urls import path
from . import views

urlpatterns = [
    path("", views.product_mapping_view, name="data_management_home"),
    path("product_mapping/", views.product_mapping_view, name="product_mapping"),
    path("api/data/", views.api_mapping_data, name="api_mapping_data"),
    path("api/save/", views.api_save_mapping, name="api_save_mapping"),
    path("api/batch/", views.api_batch_mapping, name="api_batch_mapping"),
    path("api/import-excel/", views.api_import_excel, name="api_import_excel"),
    path("api/categories/", views.api_get_categories, name="api_get_categories"),
    path("api/categories/delete/", views.api_delete_category, name="api_delete_category"),
    path("api/template-catalog/", views.api_template_catalog, name="api_template_catalog"),
    path("api/download-template/", views.api_download_template_excel, name="api_download_template_excel"),
]
