from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any
import time

from django.db.models import Max, Min, Q, Sum
from dashboard.models import User
from .models import OrderMartSummary, ProductMartSummary
from .services import apply_brand_access_filter, get_user_brands, get_filter_options


def parse_date(date_str: str | None, default: date) -> date:
    """Parse YYYY-MM-DD or return default."""
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def get_analytics_filter_options(user: User) -> dict[str, Any]:
    """Retrieve distinct dropdown options for analytics filters and default periodic date range."""
    summary_opts = get_filter_options(user)
    latest_date_str = summary_opts.get("latest_date") or (date.today() - timedelta(days=1)).isoformat()
    latest_date = date.fromisoformat(latest_date_str)

    min_date = date(2025, 1, 1)
    default_end_date = latest_date
    default_start_date = max(min_date, latest_date - timedelta(days=29))

    return {
        "brand_groups": summary_opts.get("brand_groups", []),
        "brands": summary_opts.get("brands", []),
        "platforms": summary_opts.get("platforms", []),
        "min_date": min_date.isoformat(),
        "latest_date": latest_date.isoformat(),
        "default_start_date": default_start_date.isoformat(),
        "default_end_date": default_end_date.isoformat(),
    }


def split_date_range_by_month(start_d: date, end_d: date) -> list[dict[str, Any]]:
    """
    Split arbitrary date range [start_d, end_d] into calendar month slices.
    e.g., 2026-01-15 to 2026-02-15 returns:
    [
      { "year": 2026, "month": 1, "start": 2026-01-15, "end": 2026-01-31, "label": "Jan 2026 (15-31 Jan)" },
      { "year": 2026, "month": 2, "start": 2026-02-01, "end": 2026-02-15, "label": "Feb 2026 (1-15 Feb)" },
    ]
    """
    slices: list[dict[str, Any]] = []
    curr = start_d
    while curr <= end_d:
        _, last_day_of_month = calendar.monthrange(curr.year, curr.month)
        m_end = min(end_d, date(curr.year, curr.month, last_day_of_month))
        m_name = calendar.month_abbr[curr.month]

        if curr.day == 1 and m_end.day == last_day_of_month:
            label = f"Full {m_name} {curr.year}"
        else:
            label = f"{m_name} {curr.year} ({curr.day}-{m_end.day} {m_name})"

        slices.append({
            "year": curr.year,
            "month": curr.month,
            "start": curr,
            "end": m_end,
            "label": label,
        })
        # Advance to 1st of next month
        if curr.month == 12:
            curr = date(curr.year + 1, 1, 1)
        else:
            curr = date(curr.year, curr.month + 1, 1)
    return slices


def calc_growth(curr: float | int | None, prev: float | int | None) -> dict[str, Any]:
    c = float(curr or 0)
    p = float(prev or 0)
    if p > 0:
        pct = round(((c - p) / p) * 100, 2)
    elif c > 0 and p == 0:
        pct = 100.0
    elif c == 0 and p == 0:
        pct = 0.0
    else:
        pct = -100.0

    return {
        "value": pct,
        "is_positive": pct >= 0,
        "formatted": f"{'+' if pct > 0 else ''}{pct:,.2f}%",
    }


def get_analytics_performance_data(
    user: User,
    start_date_str: str | None,
    end_date_str: str | None,
    selected_brand_group: str | None = None,
    selected_brands: list[str] | None = None,
    selected_platforms: list[str] | None = None,
) -> dict[str, Any]:
    """
    Main computational service for the Executive Analytics Dashboard.
    Uses periodic date range filtering on OrderMartSummary and ProductMartSummary.
    """
    filter_opts = get_analytics_filter_options(user)
    def_start = date.fromisoformat(filter_opts["default_start_date"])
    def_end = date.fromisoformat(filter_opts["default_end_date"])

    start_d = parse_date(start_date_str, def_start)
    end_d = parse_date(end_date_str, def_end)
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    # Calculate M-1 (Previous Period) of exact same length
    num_days = (end_d - start_d).days + 1
    prev_end_d = start_d - timedelta(days=1)
    prev_start_d = start_d - timedelta(days=num_days)

    # Base Querysets with Brand Access & Date Range (Current + Compare Period)
    base_order_qs = apply_brand_access_filter(
        OrderMartSummary.objects.filter(create_order_date_time_date__range=(prev_start_d, end_d)),
        user,
    )
    base_prod_qs = apply_brand_access_filter(
        ProductMartSummary.objects.filter(date__range=(prev_start_d, end_d)),
        user,
    )

    # Apply Optional Filters
    if selected_brand_group and selected_brand_group.lower() != "all":
        base_order_qs = base_order_qs.filter(brand_group__iexact=selected_brand_group)
        base_prod_qs = base_prod_qs.filter(brand_group__iexact=selected_brand_group)

    if not selected_brands:
        avail_brands = filter_opts.get("brands") or []
        if avail_brands:
            selected_brands = [avail_brands[0]]

    if selected_brands:
        clean_brands = [b for b in selected_brands if b and b.lower() != "all"]
        if clean_brands:
            base_order_qs = base_order_qs.filter(brand__in=clean_brands)
            base_prod_qs = base_prod_qs.filter(brand__in=clean_brands)

    if selected_platforms:
        clean_plats = [p for p in selected_platforms if p and p.lower() != "all"]
        if clean_plats:
            base_order_qs = base_order_qs.filter(platform__in=clean_plats)
            base_prod_qs = base_prod_qs.filter(platform__in=clean_plats)

    # -------------------------------------------------------------
    # 1. Comprehensive Metrics Performance & Growth vs M-1
    # -------------------------------------------------------------
    order_curr_qs = base_order_qs.filter(create_order_date_time_date__range=(start_d, end_d))
    order_prev_qs = base_order_qs.filter(create_order_date_time_date__range=(prev_start_d, prev_end_d))
    prod_curr_qs = base_prod_qs.filter(date__range=(start_d, end_d))
    prod_prev_qs = base_prod_qs.filter(date__range=(prev_start_d, prev_end_d))

    curr_agg = order_curr_qs.aggregate(
        gmv=Sum("total_gmv"),
        nmv=Sum("total_nmv"),
        gross_orders=Sum("gross_orders"),
        net_orders=Sum("net_orders"),
        gross_qty=Sum("gross_quantity"),
        net_qty=Sum("net_quantity"),
        platform_voucher=Sum("total_platform_voucher"),
        seller_voucher=Sum("total_seller_voucher"),
        platform_discount=Sum("platform_discount"),
        seller_discount=Sum("seller_discount"),
        pageviews=Sum("page_view"),
        visitors=Sum("visitors"),
        target=Sum("target"),
    )

    prev_agg = order_prev_qs.aggregate(
        gmv=Sum("total_gmv"),
        nmv=Sum("total_nmv"),
        gross_orders=Sum("gross_orders"),
        net_orders=Sum("net_orders"),
        gross_qty=Sum("gross_quantity"),
        net_qty=Sum("net_quantity"),
        platform_voucher=Sum("total_platform_voucher"),
        seller_voucher=Sum("total_seller_voucher"),
        platform_discount=Sum("platform_discount"),
        seller_discount=Sum("seller_discount"),
        pageviews=Sum("page_view"),
        visitors=Sum("visitors"),
        target=Sum("target"),
    )

    def extract_metrics(agg: dict[str, Any]) -> dict[str, float]:
        gmv = float(agg.get("gmv") or 0)
        nmv = float(agg.get("nmv") or 0)
        gross_orders = float(agg.get("gross_orders") or 0)
        net_orders = float(agg.get("net_orders") or 0)
        gross_qty = float(agg.get("gross_qty") or 0)
        net_qty = float(agg.get("net_qty") or 0)
        platform_voucher = float(agg.get("platform_voucher") or 0)
        seller_voucher = float(agg.get("seller_voucher") or 0)
        platform_discount = float(agg.get("platform_discount") or 0)
        seller_discount = float(agg.get("seller_discount") or 0)
        pageviews = float(agg.get("pageviews") or 0)
        visitors = float(agg.get("visitors") or 0)
        target = float(agg.get("target") or 0)

        aov = (nmv / net_orders) if net_orders > 0 else 0.0
        asp = (nmv / net_qty) if net_qty > 0 else 0.0
        abs_val = (net_qty / net_orders) if net_orders > 0 else 0.0
        cvr = (net_orders / visitors * 100) if visitors > 0 else 0.0
        cr = ((gross_orders - net_orders) / gross_orders * 100) if gross_orders > 0 else 0.0

        return {
            "gmv": gmv,
            "nmv": nmv,
            "gross_orders": gross_orders,
            "net_orders": net_orders,
            "gross_qty": gross_qty,
            "net_qty": net_qty,
            "platform_voucher": platform_voucher,
            "seller_voucher": seller_voucher,
            "platform_discount": platform_discount,
            "seller_discount": seller_discount,
            "pageviews": pageviews,
            "visitors": visitors,
            "target": target,
            "aov": aov,
            "asp": asp,
            "abs": abs_val,
            "cvr": cvr,
            "cr": cr,
        }

    curr_metrics = extract_metrics(curr_agg)
    prev_metrics = extract_metrics(prev_agg)

    metric_definitions = [
        ("GMV", "gmv", "currency"),
        ("NMV", "nmv", "currency"),
        ("Gross Order", "gross_orders", "number"),
        ("Net Order", "net_orders", "number"),
        ("Gross Qty", "gross_qty", "number"),
        ("Net Qty", "net_qty", "number"),
        ("Platform Voucher", "platform_voucher", "currency"),
        ("Seller Voucher", "seller_voucher", "currency"),
        ("Platform Discount", "platform_discount", "currency"),
        ("Seller Discount", "seller_discount", "currency"),
        ("Pageviews", "pageviews", "number"),
        ("Visitors", "visitors", "number"),
        ("AOV (Average Order Value)", "aov", "currency"),
        ("ASP (Average Selling Price)", "asp", "currency"),
        ("ABS (Average Basket Size)", "abs", "decimal"),
        ("Conversion Rate (CVR)", "cvr", "percent"),
        ("Cancellation Rate (CR)", "cr", "percent"),
    ]

    curr_target_val = curr_metrics.get("target", 0.0)
    comprehensive_table: list[dict[str, Any]] = []
    for name, key, fmt in metric_definitions:
        c_val = curr_metrics.get(key, 0.0)
        p_val = prev_metrics.get(key, 0.0)
        growth = calc_growth(c_val, p_val)
        m_target = curr_target_val if key == "nmv" else None
        m_ach = round((c_val / curr_target_val * 100), 1) if (key == "nmv" and curr_target_val > 0) else None
        comprehensive_table.append({
            "name": name,
            "key": key,
            "format": fmt,
            "current_value": c_val,
            "previous_value": p_val,
            "target": m_target,
            "achievement_pct": m_ach,
            "growth": growth,
        })

    # -------------------------------------------------------------
    # 2. Monthly Breakdown Per Platform
    # -------------------------------------------------------------
    month_slices = split_date_range_by_month(start_d, end_d)
    monthly_platform_breakdown: list[dict[str, Any]] = []

    for m_slice in month_slices:
        slice_qs = base_order_qs.filter(
            create_order_date_time_date__range=(m_slice["start"], m_slice["end"])
        ).values("platform").annotate(
            gmv=Sum("total_gmv"),
            nmv=Sum("total_nmv"),
            gross_orders=Sum("gross_orders"),
            net_orders=Sum("net_orders"),
            gross_qty=Sum("gross_quantity"),
            net_qty=Sum("net_quantity"),
            platform_voucher=Sum("total_platform_voucher"),
            seller_voucher=Sum("total_seller_voucher"),
            platform_discount=Sum("platform_discount"),
            seller_discount=Sum("seller_discount"),
            pageviews=Sum("page_view"),
            visitors=Sum("visitors"),
        ).order_by("-nmv")

        plat_rows = []
        m_tot_gmv = m_tot_nmv = m_tot_go = m_tot_no = m_tot_gq = m_tot_nq = 0.0
        m_tot_pv = m_tot_sv = m_tot_pd = m_tot_sd = m_tot_views = m_tot_vis = 0.0

        for r in slice_qs:
            p_gmv = float(r.get("gmv") or 0)
            p_nmv = float(r.get("nmv") or 0)
            p_go = float(r.get("gross_orders") or 0)
            p_no = float(r.get("net_orders") or 0)
            p_gq = float(r.get("gross_qty") or 0)
            p_nq = float(r.get("net_qty") or 0)
            p_pv = float(r.get("platform_voucher") or 0)
            p_sv = float(r.get("seller_voucher") or 0)
            p_pd = float(r.get("platform_discount") or 0)
            p_sd = float(r.get("seller_discount") or 0)
            p_views = float(r.get("pageviews") or 0)
            p_vis = float(r.get("visitors") or 0)

            p_aov = (p_nmv / p_no) if p_no > 0 else 0.0
            p_asp = (p_nmv / p_nq) if p_nq > 0 else 0.0

            plat_rows.append({
                "platform": r["platform"] or "Unknown",
                "gmv": p_gmv,
                "nmv": p_nmv,
                "gross_orders": p_go,
                "net_orders": p_no,
                "gross_qty": p_gq,
                "net_qty": p_nq,
                "platform_voucher": p_pv,
                "seller_voucher": p_sv,
                "platform_discount": p_pd,
                "seller_discount": p_sd,
                "pageviews": p_views,
                "visitors": p_vis,
                "aov": p_aov,
                "asp": p_asp,
            })

            m_tot_gmv += p_gmv
            m_tot_nmv += p_nmv
            m_tot_go += p_go
            m_tot_no += p_no
            m_tot_gq += p_gq
            m_tot_nq += p_nq
            m_tot_pv += p_pv
            m_tot_sv += p_sv
            m_tot_pd += p_pd
            m_tot_sd += p_sd
            m_tot_views += p_views
            m_tot_vis += p_vis

        subtotal = {
            "gmv": m_tot_gmv,
            "nmv": m_tot_nmv,
            "gross_orders": m_tot_go,
            "net_orders": m_tot_no,
            "gross_qty": m_tot_gq,
            "net_qty": m_tot_nq,
            "platform_voucher": m_tot_pv,
            "seller_voucher": m_tot_sv,
            "platform_discount": m_tot_pd,
            "seller_discount": m_tot_sd,
            "pageviews": m_tot_views,
            "visitors": m_tot_vis,
            "aov": (m_tot_nmv / m_tot_no) if m_tot_no > 0 else 0.0,
            "asp": (m_tot_nmv / m_tot_nq) if m_tot_nq > 0 else 0.0,
        }

        monthly_platform_breakdown.append({
            "month_label": m_slice["label"],
            "start": m_slice["start"].isoformat(),
            "end": m_slice["end"].isoformat(),
            "platforms": plat_rows,
            "subtotal": subtotal,
        })

    # -------------------------------------------------------------
    # 3. Daily Trend (Selected vs M-1) Line Chart
    # -------------------------------------------------------------
    curr_daily_qs = order_curr_qs.values("create_order_date_time_date").annotate(
        gmv=Sum("total_gmv"),
        nmv=Sum("total_nmv"),
        target=Sum("target"),
        net_orders=Sum("net_orders"),
        pageviews=Sum("page_view"),
        visitors=Sum("visitors"),
    ).order_by("create_order_date_time_date")

    prev_daily_qs = order_prev_qs.values("create_order_date_time_date").annotate(
        gmv=Sum("total_gmv"),
        nmv=Sum("total_nmv"),
        target=Sum("target"),
        net_orders=Sum("net_orders"),
        pageviews=Sum("page_view"),
        visitors=Sum("visitors"),
    ).order_by("create_order_date_time_date")

    curr_daily_map = {
        r["create_order_date_time_date"]: r for r in curr_daily_qs
    }
    prev_daily_map = {
        r["create_order_date_time_date"]: r for r in prev_daily_qs
    }

    trend_days = []
    trend_labels = []
    curr_nmv_series = []
    prev_nmv_series = []
    curr_target_series = []
    prev_target_series = []
    curr_gmv_series = []
    prev_gmv_series = []
    curr_orders_series = []
    prev_orders_series = []
    curr_views_series = []
    prev_views_series = []
    curr_visitors_series = []
    prev_visitors_series = []

    for i in range(num_days):
        c_date = start_d + timedelta(days=i)
        p_date = prev_start_d + timedelta(days=i)

        c_data = curr_daily_map.get(c_date, {})
        p_data = prev_daily_map.get(p_date, {})

        c_nmv = float(c_data.get("nmv") or 0)
        p_nmv = float(p_data.get("nmv") or 0)
        c_tgt = float(c_data.get("target") or 0)
        p_tgt = float(p_data.get("target") or 0)
        c_gmv = float(c_data.get("gmv") or 0)
        p_gmv = float(p_data.get("gmv") or 0)
        c_ord = float(c_data.get("net_orders") or 0)
        p_ord = float(p_data.get("net_orders") or 0)
        c_view = float(c_data.get("pageviews") or 0)
        p_view = float(p_data.get("pageviews") or 0)
        c_vis = float(c_data.get("visitors") or 0)
        p_vis = float(p_data.get("visitors") or 0)

        trend_labels.append(c_date.strftime("%d %b"))
        trend_days.append({
            "day_index": i + 1,
            "curr_date": c_date.isoformat(),
            "prev_date": p_date.isoformat(),
            "curr_label": c_date.strftime("%d %b %Y"),
            "prev_label": p_date.strftime("%d %b %Y"),
        })

        curr_nmv_series.append(c_nmv)
        prev_nmv_series.append(p_nmv)
        curr_target_series.append(c_tgt)
        prev_target_series.append(p_tgt)
        curr_gmv_series.append(c_gmv)
        prev_gmv_series.append(p_gmv)
        curr_orders_series.append(c_ord)
        prev_orders_series.append(p_ord)
        curr_views_series.append(c_view)
        prev_views_series.append(p_view)
        curr_visitors_series.append(c_vis)
        prev_visitors_series.append(p_vis)

    trend_chart_data = {
        "labels": trend_labels,
        "days": trend_days,
        "series": {
            "nmv": {"current": curr_nmv_series, "previous": prev_nmv_series},
            "target": {"current": curr_target_series, "previous": prev_target_series},
            "gmv": {"current": curr_gmv_series, "previous": prev_gmv_series},
            "net_order": {"current": curr_orders_series, "previous": prev_orders_series},
            "pageviews": {"current": curr_views_series, "previous": prev_views_series},
            "visitors": {"current": curr_visitors_series, "previous": prev_visitors_series},
        },
    }

    # -------------------------------------------------------------
    # 4. Platform NMV Share Target Achievement
    # -------------------------------------------------------------
    plat_target_qs = order_curr_qs.values("platform").annotate(
        actual_nmv=Sum("total_nmv"),
        target_val=Sum("target"),
    ).order_by("-actual_nmv")

    total_nmv_all = curr_metrics["nmv"]
    total_target_all = sum(float(r.get("target_val") or 0) for r in plat_target_qs)

    platform_targets: list[dict[str, Any]] = []
    for r in plat_target_qs:
        p_name = r["platform"] or "Unknown"
        p_nmv = float(r.get("actual_nmv") or 0)
        p_target = float(r.get("target_val") or 0)

        act_share = round((p_nmv / total_nmv_all * 100), 1) if total_nmv_all > 0 else 0.0
        target_share = round((p_target / total_target_all * 100), 1) if total_target_all > 0 else 0.0

        if p_target > 0:
            achieved = round((p_nmv / p_target * 100), 1)
        elif target_share > 0:
            achieved = round((act_share / target_share * 100), 1)
        else:
            achieved = 100.0 if p_nmv > 0 else 0.0

        platform_targets.append({
            "platform": p_name,
            "actual_nmv": p_nmv,
            "target_val": p_target,
            "actual_share": act_share,
            "target_share": target_share,
            "achieved_pct": achieved,
        })

    # -------------------------------------------------------------
    # 5. Donut Charts (Platform Share, Top SKUs, Dummy Product Groups)
    # -------------------------------------------------------------
    # A. Platform Share (NMV)
    platform_donut = [
        {
            "name": pt["platform"],
            "value": pt["actual_nmv"],
            "share_pct": pt["actual_share"],
        }
        for pt in platform_targets
    ]

    # B. Top SKUs (NMV Share) from ProductMartSummary (Top 20, positive NMV only, remainder as Others)
    all_positive_skus = list(
        prod_curr_qs.values("sku_code")
        .annotate(
            product_name=Max("product_name"),
            nmv=Sum("nmv"),
            gmv=Sum("gmv"),
            net_qty=Sum("net_quantity"),
        )
        .filter(nmv__gt=0)
        .order_by("-nmv")
    )

    total_sku_nmv = sum(float(r.get("nmv") or 0) for r in all_positive_skus)
    top_20_skus = all_positive_skus[:20]
    remaining_skus = all_positive_skus[20:]

    sku_donut = []
    accum_sku_nmv = 0.0
    for r in top_20_skus:
        n = float(r.get("nmv") or 0)
        accum_sku_nmv += n
        share = round((n / total_sku_nmv * 100), 1) if total_sku_nmv > 0 else 0.0
        label = r["sku_code"]
        prod_name = r.get("product_name") or "-"
        if not label or label == "nan":
            label = prod_name[:24]
        sku_donut.append({
            "sku_code": label,
            "product_name": prod_name,
            "name": label,
            "full_name": prod_name if prod_name != "-" else label,
            "value": n,
            "share_pct": share,
        })

    remaining_nmv = total_sku_nmv - accum_sku_nmv
    if remaining_nmv > 0:
        sku_donut.append({
            "sku_code": "Others",
            "product_name": f"Remaining {len(remaining_skus)} SKUs",
            "name": "Others",
            "full_name": f"Remaining {len(remaining_skus)} SKUs",
            "value": round(remaining_nmv, 2),
            "share_pct": round((remaining_nmv / total_sku_nmv * 100), 1) if total_sku_nmv > 0 else 0.0,
        })

    # C. Product Groups (Dummy / Placeholder as requested by user)
    # User note: "untuk product group bisa dibuat dummy / placeholder dulu karena itu perlu join data lagi dan datanya belum ready dari stakeholder"
    # We create realistic dummy category breakdown matching total NMV:
    dummy_ratios = [
        ("Core / Best Sellers", 0.38),
        ("New Launches", 0.24),
        ("Multipacks & Bundles", 0.18),
        ("Travel / Minis", 0.12),
        ("Seasonal / Limited", 0.08),
    ]
    group_donut = []
    for cat_name, ratio in dummy_ratios:
        cat_val = round(curr_metrics["nmv"] * ratio)
        group_donut.append({
            "name": f"{cat_name} *",
            "value": cat_val,
            "share_pct": round(ratio * 100, 1),
            "is_placeholder": True,
        })

    # -------------------------------------------------------------
    # 6. Product Price Analytics (from ProductMartSummary)
    # -------------------------------------------------------------
    price_analytics_qs = prod_curr_qs.values(
        "sku_code", "brand", "platform"
    ).annotate(
        product_name=Max("product_name"),
        max_rsp=Max("max_rsp"),
        min_rsp=Min("min_rsp"),
        max_selling_price=Max("max_selling_price"),
        min_selling_price=Min("min_selling_price"),
        max_platform_discount=Max("max_platform_discount"),
        min_platform_discount=Min("min_platform_discount"),
        max_seller_discount=Max("max_seller_discount"),
        min_seller_discount=Min("min_seller_discount"),
        total_platform_discount=Sum("total_platform_discount"),
        total_seller_discount=Sum("total_seller_discount"),
        total_nmv=Sum("nmv"),
    ).order_by("brand", "sku_code")

    product_price_analytics: list[dict[str, Any]] = []
    for r in price_analytics_qs:
        sku = r.get("sku_code")
        if not sku or sku == "nan":
            sku = (r.get("product_name") or "-")[:20]

        product_price_analytics.append({
            "sku_code": sku,
            "product_name": r.get("product_name") or "-",
            "brand": r.get("brand") or "-",
            "platform": r.get("platform") or "-",
            "max_rsp": float(r.get("max_rsp") or 0),
            "min_rsp": float(r.get("min_rsp") or 0),
            "max_selling_price": float(r.get("max_selling_price") or 0),
            "min_selling_price": float(r.get("min_selling_price") or 0),
            "max_platform_discount": float(r.get("max_platform_discount") or 0),
            "min_platform_discount": float(r.get("min_platform_discount") or 0),
            "max_seller_discount": float(r.get("max_seller_discount") or 0),
            "min_seller_discount": float(r.get("min_seller_discount") or 0),
            "total_platform_discount": float(r.get("total_platform_discount") or 0),
            "total_seller_discount": float(r.get("total_seller_discount") or 0),
            "total_nmv": float(r.get("total_nmv") or 0),
        })

    # -------------------------------------------------------------
    # 7. Product Performance Monthly Breakdown (with Month split & Total toggle)
    # -------------------------------------------------------------
    # A. Monthly breakdown view
    prod_monthly_breakdown: list[dict[str, Any]] = []
    for m_slice in month_slices:
        m_prod_qs = base_prod_qs.filter(
            date__range=(m_slice["start"], m_slice["end"])
        ).values(
            "sku_code", "brand", "platform"
        ).annotate(
            product_name=Max("product_name"),
            net_qty=Sum("net_quantity"),
            nmv=Sum("nmv"),
            gmv=Sum("gmv"),
            gross_orders=Sum("gross_order"),
            net_orders=Sum("net_order"),
            platform_discount=Sum("total_platform_discount"),
            seller_discount=Sum("total_seller_discount"),
        ).order_by("brand", "platform", "-nmv")

        m_prods = []
        for r in m_prod_qs:
            sku = r.get("sku_code")
            if not sku or sku == "nan":
                sku = (r.get("product_name") or "-")[:20]
            gross_ord = float(r.get("gross_orders") or 0)
            net_ord = float(r.get("net_orders") or 0)
            cr = ((gross_ord - net_ord) / gross_ord * 100) if gross_ord > 0 else 0.0
            m_prods.append({
                "month_label": m_slice["label"],
                "sku_code": sku,
                "product_name": r.get("product_name") or "-",
                "brand": r.get("brand") or "-",
                "platform": r.get("platform") or "-",
                "net_qty": float(r.get("net_qty") or 0),
                "nmv": float(r.get("nmv") or 0),
                "gmv": float(r.get("gmv") or 0),
                "gross_orders": gross_ord,
                "net_orders": net_ord,
                "cr": round(cr, 1),
                "platform_discount": float(r.get("platform_discount") or 0),
                "seller_discount": float(r.get("seller_discount") or 0),
            })

        prod_monthly_breakdown.append({
            "month_label": m_slice["label"],
            "year": m_slice["year"],
            "month": m_slice["month"],
            "start": m_slice["start"].isoformat(),
            "end": m_slice["end"].isoformat(),
            "products": m_prods,
        })

    # B. Total Period view (Toggle Total)
    prod_total_qs = prod_curr_qs.values(
        "sku_code", "brand", "platform"
    ).annotate(
        product_name=Max("product_name"),
        net_qty=Sum("net_quantity"),
        nmv=Sum("nmv"),
        gmv=Sum("gmv"),
        gross_orders=Sum("gross_order"),
        net_orders=Sum("net_order"),
        platform_discount=Sum("total_platform_discount"),
        seller_discount=Sum("total_seller_discount"),
    ).order_by("brand", "platform", "-nmv")

    prod_total_period: list[dict[str, Any]] = []
    total_period_label = f"Total Period ({start_d.strftime('%d %b')} - {end_d.strftime('%d %b %Y')})"
    for r in prod_total_qs:
        sku = r.get("sku_code")
        if not sku or sku == "nan":
            sku = (r.get("product_name") or "-")[:20]
        gross_ord = float(r.get("gross_orders") or 0)
        net_ord = float(r.get("net_orders") or 0)
        cr = ((gross_ord - net_ord) / gross_ord * 100) if gross_ord > 0 else 0.0
        prod_total_period.append({
            "period_label": total_period_label,
            "sku_code": sku,
            "product_name": r.get("product_name") or "-",
            "brand": r.get("brand") or "-",
            "platform": r.get("platform") or "-",
            "net_qty": float(r.get("net_qty") or 0),
            "nmv": float(r.get("nmv") or 0),
            "gmv": float(r.get("gmv") or 0),
            "gross_orders": gross_ord,
            "net_orders": net_ord,
            "cr": round(cr, 1),
            "platform_discount": float(r.get("platform_discount") or 0),
            "seller_discount": float(r.get("seller_discount") or 0),
        })

    # -------------------------------------------------------------
    # 8. Raw Data Export: Daily All Metrics Level (from OrderMartSummary)
    # -------------------------------------------------------------
    raw_daily_qs = order_curr_qs.values(
        "create_order_date_time_date",
        "brand",
        "brand_group",
        "platform",
        "total_nmv",
        "total_gmv",
        "net_orders",
        "gross_orders",
        "net_quantity",
        "gross_quantity",
        "total_platform_voucher",
        "total_seller_voucher",
        "platform_discount",
        "seller_discount",
        "page_view",
        "visitors",
    ).order_by("-create_order_date_time_date", "brand", "platform")[:500]

    daily_raw_rows: list[dict[str, Any]] = []
    for r in raw_daily_qs:
        d_val = r["create_order_date_time_date"].isoformat() if r["create_order_date_time_date"] else ""
        nmv = float(r.get("total_nmv") or 0)
        gmv = float(r.get("total_gmv") or 0)
        no = float(r.get("net_orders") or 0)
        go = float(r.get("gross_orders") or 0)
        nq = float(r.get("net_quantity") or 0)
        gq = float(r.get("gross_quantity") or 0)
        pv = float(r.get("total_platform_voucher") or 0)
        sv = float(r.get("total_seller_voucher") or 0)
        pd = float(r.get("platform_discount") or 0)
        sd = float(r.get("seller_discount") or 0)
        views = float(r.get("page_view") or 0)
        vis = float(r.get("visitors") or 0)

        aov = (nmv / no) if no > 0 else 0.0
        asp = (nmv / nq) if nq > 0 else 0.0
        abs_val = (nq / no) if no > 0 else 0.0
        cvr = (no / vis * 100) if vis > 0 else 0.0
        cr = ((go - no) / go * 100) if go > 0 else 0.0

        daily_raw_rows.append({
            "date": d_val,
            "brand": r.get("brand") or "",
            "brand_group": r.get("brand_group") or "",
            "platform": r.get("platform") or "",
            "nmv": nmv,
            "net_order": no,
            "net_quantity": nq,
            "abs": round(abs_val, 2),
            "aov": round(aov),
            "asp": round(asp),
            "gmv": gmv,
            "gross_order": go,
            "gross_quantity": gq,
            "page_views": views,
            "visitors": vis,
            "cvr": round(cvr, 2),
            "cr": round(cr, 2),
            "voucher_paid_by_platform": pv,
            "voucher_paid_by_seller": sv,
            "discount_from_platform": pd,
            "discount_from_seller": sd,
        })

    # Return full package
    return {
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "prev_start_date": prev_start_d.isoformat(),
        "prev_end_date": prev_end_d.isoformat(),
        "period_label": f"{start_d.strftime('%d %b %Y')} – {end_d.strftime('%d %b %Y')}",
        "prev_period_label": f"M-1 ({prev_start_d.strftime('%d %b %Y')} – {prev_end_d.strftime('%d %b %Y')})",
        "num_days": num_days,
        "target": curr_target_val,
        "target_achievement": round((curr_metrics["nmv"] / curr_target_val * 100), 1) if curr_target_val > 0 else 0.0,
        "comprehensive_metrics": comprehensive_table,
        "monthly_platform_breakdown": monthly_platform_breakdown,
        "trend_chart": trend_chart_data,
        "platform_targets": platform_targets,
        "donut_charts": {
            "platform_share": platform_donut,
            "sku_share": sku_donut,
            "group_share": group_donut,
        },
        "price_analytics": product_price_analytics,
        "product_performance": {
            "monthly_breakdown": prod_monthly_breakdown,
            "total_period": prod_total_period,
            "total_period_label": total_period_label,
        },
        "raw_daily_metrics": daily_raw_rows,
    }
