from __future__ import annotations

from typing import Any
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .services import get_filter_options, get_summary_performance_data


@never_cache
@login_required
def summary_view(request: HttpRequest) -> HttpResponse:
    """Renders the Brand Performance v2 Summary matrix page."""
    filter_options = get_filter_options(request.user)
    as_of_date = request.GET.get("as_of_date") or filter_options["latest_date"]

    context: dict[str, Any] = {
        "brand_groups": filter_options["brand_groups"],
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
    )

    return JsonResponse(data)
