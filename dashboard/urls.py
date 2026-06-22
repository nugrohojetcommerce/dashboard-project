from django.urls import path
from .views import brand_performance, brand_performance_api

urlpatterns = [
    # path('', dashboard_view)
    # path('',brand_performance_view),
    # path('api/gmv', api_gmv),
    # path('api/brand_performance',api_brand_performance),
    path('',brand_performance, name="brand_performance"),
    path(
        "api/brand-performance/",
        brand_performance_api,
        name="brand_performance_api",
    ),
]