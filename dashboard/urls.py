from django.urls import path
from .views import brand_performance_api_new,brand_performance,api_gmv,brand_performance_new,api_brand_performance

urlpatterns = [
    path('', brand_performance_new, name="brand_performance_new"),
    path('brand_performance_api_new', brand_performance_api_new, name="brand_performance_api_new"),
    # path('',brand_performance_view),
    path('api/gmv', api_gmv),
    path('api/brand_performance',api_brand_performance),
    path('brand_performance/',brand_performance, name="brand_performance")
]