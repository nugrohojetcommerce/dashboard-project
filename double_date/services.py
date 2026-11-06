from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

from django.db.models import Sum
from django.utils import timezone

from dashboard.models import User, UserBrand
from .models import OrderMartDDSummary, TrafficMartDD


@lru_cache(maxsize=256)
def get_user_brands_cached(user_id: int) -> tuple[str, ...]:
    return tuple(
        UserBrand.objects.filter(user_id=user_id)
        .values_list("brand__name", flat=True)
    )


@lru_cache(maxsize=1)
def get_all_order_brands() -> list[str]:
    return list(
        OrderMartDDSummary.objects.exclude(brand__isnull=True)
        .exclude(brand="")
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )


def get_user_brands(user: User) -> list[str]:
    """Returns list of brand names accessible by user based on UserBrand relationship."""
    if not user.is_authenticated:
        return []
    all_brands = get_all_order_brands()
    if user.is_superuser:
        return sorted(all_brands)
    user_brands = get_user_brands_cached(user.id)
    if not user_brands:
        return []
    return sorted(
        [
            brand
            for brand in all_brands
            if any(brand.lower().startswith(ub.lower()) or ub.lower() in brand.lower() for ub in user_brands)
        ]
    )


def get_available_campaign_dates(user: User) -> list[dict[str, Any]]:
    """Returns available campaign dates with formatted labels, sorted descending."""
    authorized_brands = get_user_brands(user)
    if not authorized_brands:
        return []

    qs = OrderMartDDSummary.objects.filter(brand__in=authorized_brands).exclude(date__isnull=True)
    raw_dates = (
        qs.values_list("date", flat=True)
        .distinct()
        .order_by("-date")
    )

    campaign_dates = []
    for d in raw_dates:
        if not d:
            continue
        day = d.day
        month = d.month
        year = d.year
        date_str = d.strftime("%Y-%m-%d")

        # Determine campaign type badge & name
        if day == month:
            label = f"{day}.{month} Mega Sale ({d.strftime('%d %b %Y')})"
            tag = f"{day}.{month}"
        elif day in (24, 25, 26, 27, 28, 29, 30, 31):
            label = f"Payday Festival ({d.strftime('%d %b %Y')})"
            tag = "Payday"
        else:
            label = f"Campaign ({d.strftime('%d %b %Y')})"
            tag = "Campaign"

        campaign_dates.append({
            "date": date_str,
            "label": label,
            "tag": tag,
            "year": year,
            "month": month,
            "day": day,
        })

    return campaign_dates


def get_available_platforms() -> list[str]:
    return ["Shopee", "TikTok", "Tokopedia", "Lazada"]


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _to_int(val: Any) -> int:
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def get_campaign_war_room_data(
    date_str: str,
    selected_platforms: Optional[list[str]],
    selected_brands: Optional[list[str]],
    user: User,
) -> dict[str, Any]:
    """
    Main aggregator for the Double Date War Room & Leaderboard.
    Aggregates orders (OrderMartDDSummary) and traffic (TrafficMartDD)
    by brand, platform, and hour.
    """
    authorized_brands = get_user_brands(user)
    if not authorized_brands:
        return {"error": "No authorized brands found for current user"}

    # Filter brands to subset of authorized brands
    if selected_brands:
        target_brands = [b for b in selected_brands if b in authorized_brands]
        if not target_brands:
            target_brands = authorized_brands
    else:
        target_brands = authorized_brands

    # Filter platforms
    available_plats = get_available_platforms()
    if selected_platforms:
        target_platforms = [p for p in selected_platforms if p in available_plats]
        if not target_platforms:
            target_platforms = available_plats
    else:
        target_platforms = available_plats

    # Parse date
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        target_date = OrderMartDDSummary.objects.filter(brand__in=target_brands).values_list("date", flat=True).order_by("-date").first()
        if not target_date:
            return {"error": "No campaign data available"}
        date_str = target_date.strftime("%Y-%m-%d")

    traffic_date_str = target_date.strftime("%Y%m%d")

    # 1. Query Orders aggregated by (brand, platform, hour)
    order_qs = (
        OrderMartDDSummary.objects.filter(
            date=target_date,
            brand__in=target_brands,
            platform__in=target_platforms,
        )
        .values("brand", "platform", "hour")
        .annotate(
            gmv=Sum("total_gmv"),
            nmv=Sum("total_nmv"),
            orders=Sum("net_orders"),
            gross_orders=Sum("gross_orders"),
            units=Sum("net_quantity"),
            gross_units=Sum("gross_quantity"),
            platform_discount=Sum("platform_discount"),
            seller_discount=Sum("seller_discount"),
            total_platform_voucher=Sum("total_platform_voucher"),
            total_seller_voucher=Sum("total_seller_voucher"),
        )
    )

    # 2. Query Traffic aggregated by (brand, platform, hour)
    traffic_qs = (
        TrafficMartDD.objects.filter(
            date=traffic_date_str,
            platform__in=target_platforms,
        )
        .values("brand", "platform", "hour")
        .annotate(
            uv=Sum("uv"),
            pv=Sum("pv"),
        )
    )

    # Index traffic by (brand_lower, platform_lower, hour_int)
    traffic_map = defaultdict(lambda: {"uv": 0, "pv": 0})
    for t in traffic_qs:
        b_name = (t["brand"] or "").strip().lower()
        p_name = (t["platform"] or "").strip().lower()
        h_val = _to_int(t["hour"])
        traffic_map[(b_name, p_name, h_val)]["uv"] += _to_int(t["uv"])
        traffic_map[(b_name, p_name, h_val)]["pv"] += _to_int(t["pv"])

    # Build joined dataset by (brand, hour) and (brand, platform)
    # brand_summary: { brand: { gmv, nmv, orders, units, uv, pv, discounts, platform_gmv: {}, hourly_gmv: [24], hourly_orders: [24], hourly_uv: [24] } }
    brand_summary: dict[str, dict[str, Any]] = {}
    for b in target_brands:
        brand_summary[b] = {
            "brand": b,
            "gmv": 0.0,
            "nmv": 0.0,
            "orders": 0,
            "gross_orders": 0,
            "units": 0.0,
            "gross_units": 0.0,
            "uv": 0,
            "pv": 0,
            "discounts": 0.0,
            "platform_gmv": defaultdict(float),
            "platform_orders": defaultdict(int),
            "platform_uv": defaultdict(int),
            "hourly_gmv": [0.0] * 24,
            "hourly_nmv": [0.0] * 24,
            "hourly_orders": [0] * 24,
            "hourly_uv": [0] * 24,
            "hourly_pv": [0] * 24,
        }

    # Hourly campaign totals across all brands
    hourly_totals = [
        {
            "hour": h,
            "hour_label": f"{h:02d}:00",
            "gmv": 0.0,
            "nmv": 0.0,
            "orders": 0,
            "units": 0.0,
            "uv": 0,
            "pv": 0,
        }
        for h in range(24)
    ]

    platform_totals = {
        p: {"platform": p, "gmv": 0.0, "nmv": 0.0, "orders": 0, "uv": 0, "pv": 0}
        for p in target_platforms
    }

    # Populate orders data
    for o in order_qs:
        b = o["brand"]
        p = o["platform"]
        h = o["hour"] if (o["hour"] is not None and 0 <= o["hour"] <= 23) else 0

        gmv = _to_float(o["gmv"])
        nmv = _to_float(o["nmv"])
        orders = _to_int(o["orders"])
        gross_orders = _to_int(o["gross_orders"])
        units = _to_float(o["units"])
        gross_units = _to_float(o["gross_units"])
        discounts = (
            _to_float(o["platform_discount"])
            + _to_float(o["seller_discount"])
            + _to_float(o["total_platform_voucher"])
            + _to_float(o["total_seller_voucher"])
        )

        b_entry = brand_summary[b]
        b_entry["gmv"] += gmv
        b_entry["nmv"] += nmv
        b_entry["orders"] += orders
        b_entry["gross_orders"] += gross_orders
        b_entry["units"] += units
        b_entry["gross_units"] += gross_units
        b_entry["discounts"] += discounts
        b_entry["platform_gmv"][p] += gmv
        b_entry["platform_orders"][p] += orders
        b_entry["hourly_gmv"][h] += gmv
        b_entry["hourly_nmv"][h] += nmv
        b_entry["hourly_orders"][h] += orders

        hourly_totals[h]["gmv"] += gmv
        hourly_totals[h]["nmv"] += nmv
        hourly_totals[h]["orders"] += orders
        hourly_totals[h]["units"] += units

        if p in platform_totals:
            platform_totals[p]["gmv"] += gmv
            platform_totals[p]["nmv"] += nmv
            platform_totals[p]["orders"] += orders

    # Populate traffic data into matching brands and platforms
    # We match target brands
    for b in target_brands:
        b_lower = b.strip().lower()
        b_entry = brand_summary[b]
        for p in target_platforms:
            p_lower = p.strip().lower()
            for h in range(24):
                t_info = traffic_map.get((b_lower, p_lower, h))
                if t_info and (t_info["uv"] > 0 or t_info["pv"] > 0):
                    uv = t_info["uv"]
                    pv = t_info["pv"]
                    b_entry["uv"] += uv
                    b_entry["pv"] += pv
                    b_entry["platform_uv"][p] += uv
                    b_entry["hourly_uv"][h] += uv
                    b_entry["hourly_pv"][h] += pv

                    hourly_totals[h]["uv"] += uv
                    hourly_totals[h]["pv"] += pv

                    if p in platform_totals:
                        platform_totals[p]["uv"] += uv
                        platform_totals[p]["pv"] += pv

    # Determine latest hour with active data (for live war room pacing)
    latest_active_hour = 0
    for h in range(23, -1, -1):
        if hourly_totals[h]["gmv"] > 0 or hourly_totals[h]["uv"] > 0 or hourly_totals[h]["orders"] > 0:
            latest_active_hour = h
            break

    # Macro KPIs
    total_gmv = sum(h["gmv"] for h in hourly_totals)
    total_nmv = sum(h["nmv"] for h in hourly_totals)
    total_orders = sum(h["orders"] for h in hourly_totals)
    total_units = sum(h["units"] for h in hourly_totals)
    total_uv = sum(h["uv"] for h in hourly_totals)
    total_pv = sum(h["pv"] for h in hourly_totals)
    total_discounts = sum(b_entry["discounts"] for b_entry in brand_summary.values())

    blended_cvr = (total_orders / total_uv * 100.0) if total_uv > 0 else 0.0
    overall_aov = (total_gmv / total_orders) if total_orders > 0 else 0.0
    overall_rpv = (total_gmv / total_uv) if total_uv > 0 else 0.0

    # Hourly CVR calculation
    for h in range(24):
        h_uv = hourly_totals[h]["uv"]
        h_orders = hourly_totals[h]["orders"]
        hourly_totals[h]["cvr"] = (h_orders / h_uv * 100.0) if h_uv > 0 else 0.0

    # Find peak hour
    peak_hour_entry = max(hourly_totals, key=lambda x: x["gmv"], default=hourly_totals[0])
    peak_hour = peak_hour_entry["hour"]
    peak_hour_gmv = peak_hour_entry["gmv"]

    # Filter active brands that have GMV > 0 or UV > 0 or Orders > 0
    active_brands = [
        b_entry for b_entry in brand_summary.values()
        if b_entry["gmv"] > 0 or b_entry["uv"] > 0 or b_entry["orders"] > 0
    ]
    # Sort brands by total GMV descending
    active_brands.sort(key=lambda x: x["gmv"], reverse=True)

    # Build Leaderboard items with ranks, CVR, momentum, platform split
    leaderboard = []
    for rank, b in enumerate(active_brands, start=1):
        b_gmv = b["gmv"]
        b_orders = b["orders"]
        b_uv = b["uv"]
        b_cvr = (b_orders / b_uv * 100.0) if b_uv > 0 else 0.0
        b_aov = (b_gmv / b_orders) if b_orders > 0 else 0.0
        b_rpv = (b_gmv / b_uv) if b_uv > 0 else 0.0
        share_pct = (b_gmv / total_gmv * 100.0) if total_gmv > 0 else 0.0

        # Hourly momentum (growth of latest hour vs previous hour)
        prev_hour = max(0, latest_active_hour - 1)
        latest_gmv = b["hourly_gmv"][latest_active_hour]
        prev_gmv = b["hourly_gmv"][prev_hour]
        if prev_gmv > 0:
            momentum = ((latest_gmv - prev_gmv) / prev_gmv) * 100.0
        elif latest_gmv > 0:
            momentum = 100.0
        else:
            momentum = 0.0

        # Platform breakdown
        p_breakdown = []
        for p in target_platforms:
            p_val = b["platform_gmv"].get(p, 0.0)
            p_pct = (p_val / b_gmv * 100.0) if b_gmv > 0 else 0.0
            p_breakdown.append({
                "platform": p,
                "gmv": p_val,
                "pct": round(p_pct, 1),
            })

        leaderboard.append({
            "rank": rank,
            "brand": b["brand"],
            "total_gmv": b_gmv,
            "total_nmv": b["nmv"],
            "total_orders": b_orders,
            "total_units": b["units"],
            "total_uv": b_uv,
            "total_pv": b["pv"],
            "cvr": round(b_cvr, 2),
            "aov": round(b_aov, 0),
            "rpv": round(b_rpv, 0),
            "share_pct": round(share_pct, 1),
            "discounts": b["discounts"],
            "platforms": p_breakdown,
            "hourly_gmv": b["hourly_gmv"],
            "hourly_nmv": b["hourly_nmv"],
            "hourly_uv": b["hourly_uv"],
            "momentum": round(momentum, 1),
        })

    # Podium: Top 3 Brands
    podium = leaderboard[:3]

    # Dynamic Bar Race Data (for hours 0..latest_active_hour)
    # ECharts timeline dynamic race format
    race_hours = list(range(latest_active_hour + 1))
    race_timeline = []

    # Calculate cumulative GMV for each brand hour by hour
    top_race_brands = [b["brand"] for b in active_brands[:15]]  # Top 15 brands in race
    brand_cumulative_map = {b: 0.0 for b in top_race_brands}

    for h in race_hours:
        hour_entries = []
        for b_name in top_race_brands:
            b_item = brand_summary[b_name]
            brand_cumulative_map[b_name] += b_item["hourly_gmv"][h]
            hour_entries.append({
                "brand": b_name,
                "value": brand_cumulative_map[b_name],
                "hourly_value": b_item["hourly_gmv"][h],
                "hourly_orders": b_item["hourly_orders"][h],
            })
        # Sort descending for the hour
        hour_entries.sort(key=lambda x: x["value"], reverse=True)
        race_timeline.append({
            "hour": h,
            "hour_label": f"{h:02d}:00",
            "data": hour_entries,
        })

    # Hourly Velocity Chart Series (Top 8 brands + Total)
    def _make_cumulative(arr):
        res = []
        c = 0.0
        for x in arr:
            c += float(x or 0.0)
            res.append(round(c, 2))
        return res

    velocity_top_brands = leaderboard[:8]
    velocity_brand_series = [
        {
            "name": b["brand"],
            "data_gmv": b["hourly_gmv"][: latest_active_hour + 1],
            "data_nmv": b["hourly_nmv"][: latest_active_hour + 1],
            "cum_gmv": _make_cumulative(b["hourly_gmv"][: latest_active_hour + 1]),
            "cum_nmv": _make_cumulative(b["hourly_nmv"][: latest_active_hour + 1]),
            "data": b["hourly_nmv"][: latest_active_hour + 1],
        }
        for b in velocity_top_brands
    ]

    # Traffic vs GMV Scatter Matrix Data
    # Points: [uv, gmv, orders, cvr, brand_name, aov]
    scatter_data = []
    for b in leaderboard:
        if b["total_uv"] > 0 or b["total_gmv"] > 0:
            scatter_data.append({
                "brand": b["brand"],
                "uv": b["total_uv"],
                "gmv": b["total_gmv"],
                "orders": b["total_orders"],
                "cvr": b["cvr"],
                "aov": b["aov"],
                "rank": b["rank"],
            })

    # Platform Shares
    platform_data = []
    for p, p_info in platform_totals.items():
        p_gmv = p_info["gmv"]
        p_uv = p_info["uv"]
        p_orders = p_info["orders"]
        p_cvr = (p_orders / p_uv * 100.0) if p_uv > 0 else 0.0
        platform_data.append({
            "platform": p,
            "gmv": p_gmv,
            "nmv": p_info["nmv"],
            "orders": p_orders,
            "uv": p_uv,
            "pv": p_info["pv"],
            "cvr": round(p_cvr, 2),
            "gmv_share": round((p_gmv / total_gmv * 100.0) if total_gmv > 0 else 0.0, 1),
            "uv_share": round((p_uv / total_uv * 100.0) if total_uv > 0 else 0.0, 1),
        })

    return {
        "date": date_str,
        "traffic_date": traffic_date_str,
        "latest_active_hour": latest_active_hour,
        "latest_active_hour_label": f"{latest_active_hour:02d}:00",
        "summary": {
            "total_gmv": total_gmv,
            "total_nmv": total_nmv,
            "total_orders": total_orders,
            "total_units": total_units,
            "total_uv": total_uv,
            "total_pv": total_pv,
            "blended_cvr": round(blended_cvr, 2),
            "overall_aov": round(overall_aov, 0),
            "overall_rpv": round(overall_rpv, 0),
            "total_discounts": total_discounts,
            "peak_hour": peak_hour,
            "peak_hour_label": f"{peak_hour:02d}:00",
            "peak_hour_gmv": peak_hour_gmv,
            "active_brands_count": len(leaderboard),
        },
        "podium": podium,
        "leaderboard": leaderboard,
        "bar_race": {
            "hours": race_hours,
            "timeline": race_timeline,
        },
        "hourly_velocity": {
            "hours": [f"{h:02d}:00" for h in range(latest_active_hour + 1)],
            "total_series": [h["gmv"] for h in hourly_totals[: latest_active_hour + 1]],
            "total_series_nmv": [h["nmv"] for h in hourly_totals[: latest_active_hour + 1]],
            "total_cum_gmv": _make_cumulative([h["gmv"] for h in hourly_totals[: latest_active_hour + 1]]),
            "total_cum_nmv": _make_cumulative([h["nmv"] for h in hourly_totals[: latest_active_hour + 1]]),
            "brand_series": velocity_brand_series,
        },
        "scatter_matrix": {
            "points": scatter_data,
            "avg_uv": (total_uv / len(leaderboard)) if leaderboard else 0,
            "avg_gmv": (total_gmv / len(leaderboard)) if leaderboard else 0,
        },
        "platform_breakdown": platform_data,
        "hourly_totals": hourly_totals[: latest_active_hour + 1],
    }

