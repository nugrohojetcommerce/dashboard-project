from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .services import (
    get_available_campaign_dates,
    get_available_platforms,
    get_campaign_war_room_data,
    get_user_brands,
    standardize_brand_name,
)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


@never_cache
@login_required
def index_view(request: HttpRequest) -> HttpResponse:
    """Renders the Double Date / Payday Campaign War Room & Leaderboard page."""
    user = request.user
    available_dates = get_available_campaign_dates(user)
    available_platforms = get_available_platforms()
    user_brands = get_user_brands(user)

    # Determine selected date (strictly Double Date or Payday)
    valid_date_strings = {d["date"] for d in available_dates}
    selected_date = request.GET.get("date")
    if not selected_date or selected_date not in valid_date_strings:
        # Default to the most recent double date or payday
        selected_date = available_dates[0]["date"] if available_dates else ""

    # Parse platform filters
    raw_platforms = request.GET.getlist("platform")
    selected_platforms = []
    for p in raw_platforms:
        selected_platforms.extend([x.strip() for x in p.split(",") if x.strip()])
    if not selected_platforms:
        selected_platforms = []  # Empty means all platforms

    # Parse brand filters
    raw_brands = request.GET.getlist("brand")
    selected_brands = []
    for b in raw_brands:
        selected_brands.extend([standardize_brand_name(x) for x in b.split(",") if x.strip()])
    # Remove duplicates preserving order
    selected_brands = list(dict.fromkeys(selected_brands))

    # Fetch initial payload so SSR renders initial charts & tables immediately
    initial_data = {}
    if selected_date:
        initial_data = get_campaign_war_room_data(
            date_str=selected_date,
            selected_platforms=selected_platforms or None,
            selected_brands=selected_brands or None,
            user=user,
        )

    context: dict[str, Any] = {
        "campaign_dates": available_dates,
        "selected_date": selected_date,
        "available_platforms": available_platforms,
        "selected_platforms": selected_platforms,
        "user_brands": user_brands,
        "selected_brands": selected_brands,
        "initial_data_json": json.dumps(initial_data, cls=DecimalEncoder),
    }

    return render(request, "double_date/index.html", context)


@never_cache
@login_required
def api_campaign_data(request: HttpRequest) -> JsonResponse:
    """JSON API endpoint for polling or asynchronous filter updates."""
    user = request.user
    date_str = request.GET.get("date", "").strip()

    raw_platforms = request.GET.getlist("platform")
    selected_platforms = []
    for p in raw_platforms:
        selected_platforms.extend([x.strip() for x in p.split(",") if x.strip()])

    raw_brands = request.GET.getlist("brand")
    selected_brands = []
    for b in raw_brands:
        selected_brands.extend([standardize_brand_name(x) for x in b.split(",") if x.strip()])
    selected_brands = list(dict.fromkeys(selected_brands))

    data = get_campaign_war_room_data(
        date_str=date_str,
        selected_platforms=selected_platforms or None,
        selected_brands=selected_brands or None,
        user=user,
    )

    return JsonResponse(data, encoder=DecimalEncoder, safe=False)

