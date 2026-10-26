from __future__ import annotations

from datetime import date, timedelta, datetime
from typing import Any
from django.db.models import Max, Q
from django.contrib.auth import get_user_model
from django.utils import timezone

from brand_performance_v2.models import ProductMartSummary, OrderMartSummary
from brand_performance_v2.services import apply_brand_access_filter, get_user_brands
from .models import ProductCategoryMapping

User = get_user_model()


def get_available_brand_groups(user: User) -> list[str]:
    """
    Returns sorted list of brand_groups the user has access to.
    Superusers can access all brand_groups.
    """
    if not user.is_authenticated:
        return []

    base_qs = apply_brand_access_filter(OrderMartSummary.objects.all(), user)
    brand_groups = sorted(
        list(
            base_qs.exclude(brand_group__isnull=True)
            .exclude(brand_group="")
            .values_list("brand_group", flat=True)
            .distinct()
        )
    )
    return brand_groups


def get_catalog_and_mappings(
    brand_group: str,
    user: User,
    status_filter: str = "all",
    category_filter: str = "ALL",
    search_query: str = "",
    page: int = 1,
    page_size: int = 25,
    sort_col: str = "sku",
    sort_asc: bool = True,
    days_lookback: int = 365,
) -> dict[str, Any]:
    """
    Retrieves distinct SKUs for a brand_group from ProductMartSummary (auto-synced)
    and LEFT JOINs with ProductCategoryMapping table in PostgreSQL.
    """
    brand_group = (brand_group or "").strip()
    if not brand_group or brand_group == "ALL":
        available = get_available_brand_groups(user)
        if not available:
            return {
                "items": [],
                "total_items": 0,
                "total_pages": 1,
                "current_page": 1,
                "page_size": page_size,
                "kpis": {"total": 0, "mapped": 0, "unmapped": 0, "categories_count": 0},
                "categories": [],
            }
        brand_group = available[0]

    # 1. Fetch SKUs from ProductMartSummary within lookback window
    min_date = date.today() - timedelta(days=days_lookback)
    catalog_qs = (
        ProductMartSummary.objects.filter(
            brand_group=brand_group,
            date__gte=min_date,
        )
        .values("sku_code")
        .annotate(product_name=Max("product_name"))
    )

    catalog_dict: dict[str, str] = {
        row["sku_code"]: (row["product_name"] or "")
        for row in catalog_qs
        if row.get("sku_code")
    }

    # 2. Fetch existing mappings in PostgreSQL
    mappings_qs = ProductCategoryMapping.objects.filter(brand_group=brand_group)
    mapping_dict: dict[str, ProductCategoryMapping] = {
        m.sku_code: m for m in mappings_qs
    }

    # Also include any SKU in mapping table that might not have orders in last 365 days
    for sku, m in mapping_dict.items():
        if sku not in catalog_dict:
            catalog_dict[sku] = f"[Catalog Item] {sku}"

    # 3. Combine / LEFT JOIN
    all_combined: list[dict[str, Any]] = []
    distinct_categories = set()

    for sku, product_name in catalog_dict.items():
        m = mapping_dict.get(sku)
        is_mapped = m is not None and bool(m.product_category)
        cat = m.product_category if is_mapped else None
        if cat:
            distinct_categories.add(cat)

        all_combined.append({
            "key_id": m.key_id if m else None,
            "sku": sku,
            "name": product_name,
            "brand_group": brand_group,
            "category": cat,
            "pic": m.pic if is_mapped else "System",
            "last_updated": timezone.localtime(m.last_updated).strftime("%Y-%m-%d %H:%M") if is_mapped else "-",
            "is_mapped": is_mapped,
        })

    # 4. Calculate KPIs
    total_count = len(all_combined)
    mapped_count = sum(1 for item in all_combined if item["is_mapped"])
    unmapped_count = total_count - mapped_count
    categories_list = sorted(list(distinct_categories))

    # 5. Apply Status filter
    filtered = all_combined
    if status_filter == "mapped":
        filtered = [i for i in filtered if i["is_mapped"]]
    elif status_filter == "unmapped":
        filtered = [i for i in filtered if not i["is_mapped"]]

    # 6. Apply Category filter
    if category_filter and category_filter != "ALL":
        filtered = [i for i in filtered if i.get("category") == category_filter]

    # 7. Apply Search query
    if search_query:
        q = search_query.strip().lower()
        filtered = [
            i for i in filtered
            if q in i["sku"].lower()
            or q in i["name"].lower()
            or (i.get("category") and q in i["category"].lower())
        ]

    # 8. Sort
    col_map = {
        "sku": lambda x: x["sku"].lower(),
        "name": lambda x: x["name"].lower(),
        "category": lambda x: (x["category"] or "").lower(),
        "last_updated": lambda x: x["last_updated"],
    }
    key_func = col_map.get(sort_col, lambda x: x["sku"].lower())
    filtered.sort(key=key_func, reverse=not sort_asc)

    # 9. Paginate
    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = filtered[start_idx:end_idx]

    return {
        "items": page_items,
        "total_items": total_items,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "brand_group": brand_group,
        "kpis": {
            "total": total_count,
            "mapped": mapped_count,
            "unmapped": unmapped_count,
            "categories_count": len(categories_list),
        },
        "categories": categories_list,
    }


def save_single_mapping(
    brand_group: str,
    sku_code: str,
    product_category: str,
    user: User,
    click_time: datetime | None = None,
) -> ProductCategoryMapping:
    """Upserts a single SKU mapping to ProductCategoryMapping in database."""
    now_sec = (click_time or timezone.now()).replace(microsecond=0)
    mapping, _ = ProductCategoryMapping.objects.update_or_create(
        brand_group=brand_group.strip(),
        sku_code=sku_code.strip(),
        defaults={
            "product_category": product_category.strip(),
            "pic": user.username if user.is_authenticated else "system",
            "last_updated": now_sec,
        },
    )
    return mapping


def batch_save_mappings(
    brand_group: str,
    sku_codes: list[str],
    product_category: str | None,
    user: User,
    clear: bool = False,
    click_time: datetime | None = None,
) -> int:
    """Batch updates or clears product_category for multiple SKUs."""
    brand_group = brand_group.strip()
    clean_skus = [s.strip() for s in sku_codes if s.strip()]

    if clear:
        # Clear/delete mapping from table
        deleted_count, _ = ProductCategoryMapping.objects.filter(
            brand_group=brand_group,
            sku_code__in=clean_skus,
        ).delete()
        return deleted_count

    if not product_category:
        return 0

    pic_name = user.username if user.is_authenticated else "system"
    cat = product_category.strip()
    now_sec = (click_time or timezone.now()).replace(microsecond=0)

    objs = [
        ProductCategoryMapping(
            brand_group=brand_group,
            sku_code=sku,
            product_category=cat,
            pic=pic_name,
            last_updated=now_sec,
        )
        for sku in clean_skus
    ]

    if objs:
        ProductCategoryMapping.objects.bulk_create(
            objs,
            batch_size=1000,
            update_conflicts=True,
            unique_fields=["brand_group", "sku_code"],
            update_fields=["product_category", "pic", "last_updated"],
        )

    return len(objs)


def import_excel_parsed_rows(
    rows: list[dict[str, str]],
    user: User,
    click_time: datetime | None = None,
) -> dict[str, int]:
    """
    Upserts multiple mappings parsed from Excel using fast bulk_create.
    Deduplicates rows by (brand_group, sku_code) taking the last occurrence.
    All rows receive the exact click_time timestamp truncated to seconds.
    """
    pic_name = user.username if user.is_authenticated else "excel-import"
    now_sec = (click_time or timezone.now()).replace(microsecond=0)
    known_bgs = {bg.lower(): bg for bg in get_available_brand_groups(user)}

    deduped: dict[tuple[str, str], str] = {}
    for r in rows:
        sku = str(r.get("sku_code", "")).strip()
        bg_raw = str(r.get("brand_group", "")).strip()
        cat = str(r.get("product_category", "")).strip()

        # Match to exact case in DB if known
        bg = known_bgs.get(bg_raw.lower(), bg_raw.lower())

        if sku and bg and cat:
            deduped[(bg, sku)] = cat

    objs = [
        ProductCategoryMapping(
            brand_group=bg,
            sku_code=sku,
            product_category=cat,
            pic=pic_name,
            last_updated=now_sec,
        )
        for (bg, sku), cat in deduped.items()
    ]

    if objs:
        ProductCategoryMapping.objects.bulk_create(
            objs,
            batch_size=1000,
            update_conflicts=True,
            unique_fields=["brand_group", "sku_code"],
            update_fields=["product_category", "pic", "last_updated"],
        )

    total_valid = len(rows)
    unique_count = len(objs)
    duplicates = max(0, total_valid - unique_count)

    return {
        "updated": unique_count,
        "total_rows": total_valid,
        "duplicates_collapsed": duplicates,
    }

