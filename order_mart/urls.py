from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="order_mart"),
    path("daily_sales_api", views.daily_sales_api, name="daily_sales_api"),
]