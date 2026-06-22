from __future__ import annotations
from django.shortcuts import render
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
# from rest_framework.request import Request
from django.http import HttpRequest, HttpResponse
from dashboard.models import User
from datetime import date

from dashboard.services.dashboard_performance import get_cards
from .services.gmv_services import get_gmv
from .services.dashboard_performance import *


from collections import defaultdict
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.db.models import Sum

# replace with your actual model
from dashboard.models import OrderMartDashboardBrandDF as OrderMart

@login_required
def dashboard_view(request):
    brands = list(
        request.user.userbrand_set.values_list("brand__name", flat=True)
    )

    return render(request, "dashboard.html", {"brands": brands})


@login_required
def api_gmv(request):
    brands = list(
        request.user.userbrand_set.values_list("brand__name", flat=True)
    )

    data = get_gmv(
        request.GET.get("start_date"),
        request.GET.get("end_date"),
        brands
    )

    return JsonResponse(data, safe=False)

@login_required
def brand_performance_view(request):
    brands: list[str] = list(
        request.user.userbrand_set
        .select_related("brand")
        .values_list("brand__name", flat=True)
        .order_by("brand__name")
        .distinct()
    )

    return render(request, "brand_performance.html", {"brands": brands})

@login_required
def brand_performance(request):

    user_brands = list(
        request.user.userbrand_set
        .values_list("brand__name", flat=True)
        .order_by("brand__name")
        .distinct()
    )

    start_date = request.GET.get(
        "start_date",
        date.today().replace(day=1).isoformat()
    )

    end_date = request.GET.get(
        "end_date",
        date.today().isoformat()
    )

    base_queryset = (
        OrderMart.objects
        .filter(
            date__range=[start_date, end_date],
            brand__in=user_brands
        )
    )

    # ==========================================
    # AVAILABLE FILTER VALUES
    # ==========================================

    all_brands = list(
        base_queryset
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )

    all_platforms = list(
        base_queryset
        .values_list("platform", flat=True)
        .distinct()
        .order_by("platform")
    )

    # ==========================================
    # CURRENT SELECTION
    # ==========================================

    selected_brands = request.GET.getlist("brand")
    selected_platforms = request.GET.getlist("platform")

    # First page load = everything selected

    if not selected_brands:
        selected_brands = all_brands

    if not selected_platforms:
        selected_platforms = all_platforms

    # ==========================================
    # CASCADING BRANDS
    # ==========================================

    brands = list(
        base_queryset
        .filter(
            platform__in=selected_platforms
        )
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )

    # ==========================================
    # CASCADING PLATFORMS
    # ==========================================

    platforms = list(
        base_queryset
        .filter(
            brand__in=selected_brands
        )
        .values_list("platform", flat=True)
        .distinct()
        .order_by("platform")
    )

    # ==========================================
    # FINAL DATASET
    # ==========================================

    queryset = (
        base_queryset
        .filter(
            brand__in=selected_brands,
            platform__in=selected_platforms
        )
    )

    # ==========================================
    # KPI
    # ==========================================

    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
    )

    cards["total_nmv"] = float(
        cards["total_nmv"] or 0
    )

    cards["total_gmv"] = float(
        cards["total_gmv"] or 0
    )

    # ==========================================
    # TREND
    # ==========================================

    trend = [
        {
            "date": row["date"].isoformat(),
            "nmv": float(row["nmv"] or 0),
        }
        for row in (
            queryset
            .values("date")
            .annotate(
                nmv=Sum("nmv")
            )
            .order_by("date")
        )
    ]
    context = {
            "brands": brands,
            "platforms": platforms,
            "selected_brands": selected_brands,
            "selected_platforms": selected_platforms,
            "start_date": start_date,
            "end_date": end_date,
            "cards": cards,
            "trend_json": trend,
        }

    return render(
        request,
        "brand_performance_view.html",
        context
        
    )


@login_required
def api_brand_performance(request,order_data=None):
    # 1. Ambil semua list brand yang di-assign ke user ini
    user_brands = list(
        request.user.userbrand_set.values_list("brand__name", flat=True)
    )

    # 2. Tangkap parameter filter dari AJAX request GET
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    selected_brand = request.GET.get("brand", "all")
    selected_platform = request.GET.get("platform","all")

    # start_date = "2026-01-01"
    # end_date = "2026-01-31"
    # selected_brand = "Loreal"

    # 3. Logika penentuan brand yang akan di-query
    # Jika user memilih brand spesifik dan brand tersebut ada di dalam hak aksesnya
    if selected_brand != "all":
        if selected_brand in user_brands:
            brands_to_query = [selected_brand]
        else:
            # Antisipasi jika user nembak brand yang bukan hak miliknya lewat API
            return JsonResponse({"error": "Unauthorized brand access"}, status=403)
    else:
        # Jika milih 'all', query semua brand milik user tersebut
        brands_to_query = user_brands

    # 4. Panggil kedua fungsi service layer lu
    # filtered_data = request.get("filtered_data")
    # if star
    # filtered_data = filtered_data or get_data(start_date,end_date,brands_to_query,selected_platform)
    # order_data = request.GET.get("order_data")
    order_data = order_data or get_order_mart_dashboard_brand(user_brands)
    filtered_data = filter_data(order_data, start_date, end_date, brands_to_query, selected_platform)
    cards_data = get_cards(filtered_data)
    trend_data = get_nmv_line(filtered_data)

    # 5. Gabungkan hasilnya ke dalam satu response object sesuai ekspektasi AJAX HTML
    context_response = {
        "cards": cards_data,
        "trend": trend_data,
        "order_data": order_data,
    }

    return JsonResponse(context_response)