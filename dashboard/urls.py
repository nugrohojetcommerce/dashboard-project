from django.urls import path
from .views import dashboard_view, api_gmv, api_brand_performance, brand_performance_view

urlpatterns = [
    path('', dashboard_view),
    path('api/gmv', api_gmv),
    path('api/brand_performance',api_brand_performance),
    path('brand_performance/', brand_performance_view)
]