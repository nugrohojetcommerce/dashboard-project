from django.urls import path
from . import views

urlpatterns = [
    path("", views.summary_view, name="brand_performance_v2"),
    path("summary/", views.summary_view, name="brand_performance_v2_summary"),
    path("api/summary/", views.summary_api, name="brand_performance_v2_summary_api"),
]
