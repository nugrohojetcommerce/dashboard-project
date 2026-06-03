from django.urls import path
from .views import dashboard_view, api_gmv

urlpatterns = [
    path('', dashboard_view),
    path('api/gmv', api_gmv),
]