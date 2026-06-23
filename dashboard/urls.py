from django.urls import path
from .views import (
    brand_performance_api_new,
    brand_performance_new,
    brand_performance,
    brand_performance_api
)

urlpatterns = [
    # =============== contoh
    path('', brand_performance_new, name="brand_performance_new"),
    path('brand_performance_api_new', brand_performance_api_new, name="brand_performance_api_new"),
    # path('',brand_performance_view),

    # =============== dev imam
    path('brand_performance/',brand_performance, name="brand_performance"),
    path('brand_performance_api/',brand_performance_api, name="brand_performance_api")
]