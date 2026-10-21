from __future__ import annotations

from typing import Any
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .services import get_filter_options, get_summary_performance_data
from .analytics_services import (
    get_analytics_filter_options,
    get_analytics_performance_data,
)


@never_cache
@login_required
def summary_view(request: HttpRequest) -> HttpResponse:
    """Renders the Brand Performance v2 Summary matrix page."""
    dimension = request.GET.get("dimension", "brand").lower()
    if dimension not in ("brand", "brand_group"):
        dimension = "brand"

    filter_options = get_filter_options(request.user)
    as_of_date = request.GET.get("as_of_date") or filter_options["latest_date"]

    user_brand_groups = filter_options.get("brand_groups", [])
    default_brand_group = user_brand_groups[0] if user_brand_groups else "All"

    context: dict[str, Any] = {
        "dimension": dimension,
        "brand_groups": user_brand_groups,
        "brands": filter_options["brands"],
        "platforms": filter_options["platforms"],
        "latest_date": filter_options["latest_date"],
        "as_of_date": as_of_date,
        "selected_brand_group": request.GET.get("brand_group", "All"),
        "selected_brand": request.GET.get("brand", "All"),
        "selected_platform": request.GET.get("platform", "All"),
    }

    return render(request, "brand_performance_v2/summary.html", context)


@never_cache
@login_required
def summary_api(request: HttpRequest) -> JsonResponse:
    """Returns calculated summary performance data for the executive matrix."""
    dimension = request.GET.get("dimension", "brand").lower()
    if dimension not in ("brand", "brand_group"):
        dimension = "brand"

    as_of_date = request.GET.get("as_of_date")
    brand_group = request.GET.get("brand_group")
    
    # Support multiple brands (via getlist or comma-separated)
    raw_brands = request.GET.getlist("brand")
    selected_brands = []
    for b in raw_brands:
        selected_brands.extend([x.strip() for x in b.split(",") if x.strip()])

    # Support multiple platforms (via getlist or comma-separated)
    raw_platforms = request.GET.getlist("platform")
    selected_platforms = []
    for p in raw_platforms:
        selected_platforms.extend([x.strip() for x in p.split(",") if x.strip()])

    data = get_summary_performance_data(
        user=request.user,
        as_of_date_str=as_of_date,
        selected_brand_group=brand_group,
        selected_brand=selected_brands if selected_brands else None,
        selected_platform=selected_platforms if selected_platforms else None,
        dimension=dimension,
    )

    return JsonResponse(data)


@never_cache
@login_required
def analytics_view(request: HttpRequest) -> HttpResponse:
    """Renders the Brand Performance v2 Periodic Analytics page."""
    dimension = request.GET.get("dimension", "brand").lower()
    if dimension not in ("brand", "brand_group"):
        dimension = "brand"

    filter_options = get_analytics_filter_options(request.user)
    start_date = request.GET.get("start_date") or filter_options["default_start_date"]
    end_date = request.GET.get("end_date") or filter_options["default_end_date"]

    user_brand_groups = filter_options.get("brand_groups", [])
    default_brand_group = "finetoday" if "finetoday" in user_brand_groups else (user_brand_groups[0] if user_brand_groups else "All")
    selected_brand_group = request.GET.get("brand_group") or default_brand_group

    user_brands = filter_options.get("brands", [])
    default_brand = "Senka" if "Senka" in user_brands else (user_brands[0] if user_brands else "All")
    selected_brand = request.GET.get("brand") or default_brand

    context: dict[str, Any] = {
        "dimension": dimension,
        "brand_groups": user_brand_groups,
        "brands": user_brands,
        "platforms": filter_options["platforms"],
        "min_date": filter_options["min_date"],
        "latest_date": filter_options["latest_date"],
        "start_date": start_date,
        "end_date": end_date,
        "selected_brand_group": selected_brand_group,
        "selected_brand": selected_brand,
        "selected_platform": request.GET.get("platform", "All"),
    }

    return render(request, "brand_performance_v2/analytics.html", context)


@never_cache
@login_required
def analytics_api(request: HttpRequest) -> JsonResponse:
    """Returns calculated periodic analytics data (OrderMartSummary & ProductMartSummary)."""
    dimension = request.GET.get("dimension", "brand").lower()
    if dimension not in ("brand", "brand_group"):
        dimension = "brand"

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    preset = request.GET.get("preset")
    brand_group = request.GET.get("brand_group")

    filter_options = get_analytics_filter_options(request.user)
    user_brands = filter_options.get("brands", [])
    default_brand = "Senka" if "Senka" in user_brands else (user_brands[0] if user_brands else None)

    # Single-select brand: default to Senka or first brand if not specified or 'All'
    raw_brand = request.GET.get("brand")
    if not raw_brand or raw_brand.lower() == "all":
        selected_brand = default_brand
    else:
        selected_brand = raw_brand.strip()

    selected_brands = [selected_brand] if selected_brand else None

    raw_platforms = request.GET.getlist("platform")
    selected_platforms = []
    for p in raw_platforms:
        selected_platforms.extend([x.strip() for x in p.split(",") if x.strip()])

    data = get_analytics_performance_data(
        user=request.user,
        start_date_str=start_date,
        end_date_str=end_date,
        preset=preset,
        dimension=dimension,
        selected_brand_group=brand_group,
        selected_brands=selected_brands if selected_brands else None,
        selected_platforms=selected_platforms if selected_platforms else None,
    )

    return JsonResponse(data)

