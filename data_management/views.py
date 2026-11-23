from __future__ import annotations

import json
from typing import Any
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .services import (
    get_available_brand_groups,
    get_all_standard_brand_groups,
    validate_brand_group_for_user,
    get_catalog_and_mappings,
    save_single_mapping,
    batch_save_mappings,
    import_excel_parsed_rows,
)
from .models import ProductCategoryMapping


@never_cache
@login_required
def product_mapping_view(request: HttpRequest) -> HttpResponse:
    """Renders the SKU & Product Category Mapping management page."""
    user_brand_groups = get_available_brand_groups(request.user)
    all_standard_bgs = get_all_standard_brand_groups()

    context: dict[str, Any] = {
        "brand_groups": user_brand_groups,
        "all_standard_brand_groups": all_standard_bgs,
        "default_brand_group": user_brand_groups[0] if user_brand_groups else "",
        "is_superuser": getattr(request.user, "is_superuser", False),
    }
    return render(request, "data_management/product_mapping.html", context)


@never_cache
@login_required
def api_mapping_data(request: HttpRequest) -> JsonResponse:
    """Returns JSON payload with paginated SKUs, KPIs, and available categories."""
    brand_group = request.GET.get("brand_group", "").lower().strip()
    status_filter = request.GET.get("status", "all").strip().lower()
    category_filter = request.GET.get("category", "ALL").strip()
    search_query = request.GET.get("search", "").strip()

    try:
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 25))
    except (ValueError, TypeError):
        page = 1
        page_size = 25

    sort_col = request.GET.get("sort_col", "sku")
    sort_asc = request.GET.get("sort_dir", "asc").lower() != "desc"

    result = get_catalog_and_mappings(
        brand_group=brand_group,
        user=request.user,
        status_filter=status_filter,
        category_filter=category_filter,
        search_query=search_query,
        page=page,
        page_size=page_size,
        sort_col=sort_col,
        sort_asc=sort_asc,
    )
    return JsonResponse(result)


from django.utils.dateparse import parse_datetime
from django.utils import timezone


def _parse_click_timestamp(ts_str: str | None):
    if not ts_str:
        return None
    try:
        parsed = parse_datetime(str(ts_str))
        if parsed:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            else:
                parsed = parsed.astimezone(timezone.get_current_timezone())
            return parsed.replace(microsecond=0)
    except Exception:
        pass
    return None


@csrf_exempt
@login_required
def api_save_mapping(request: HttpRequest) -> JsonResponse:
    """POST endpoint to save or update 1 SKU mapping."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    brand_group = data.get("brand_group", "").lower().strip()
    sku_code = data.get("sku_code", "").strip()
    product_category = data.get("product_category", "").strip()

    if not brand_group or not sku_code or not product_category:
        return JsonResponse({"status": "error", "message": "brand_group, sku_code, and product_category are required"}, status=400)

    click_dt = _parse_click_timestamp(data.get("load_timestamp"))
    try:
        mapping = save_single_mapping(brand_group, sku_code, product_category, request.user, click_time=click_dt)
    except ValueError as val_err:
        return JsonResponse({"status": "error", "message": str(val_err)}, status=400)

    return JsonResponse({
        "status": "success",
        "message": f"SKU {sku_code} successfully mapped to {product_category}",
        "data": {
            "key_id": mapping.key_id,
            "brand_group": mapping.brand_group,
            "sku_code": mapping.sku_code,
            "product_category": mapping.product_category,
            "pic": mapping.pic,
            "last_updated": timezone.localtime(mapping.last_updated).strftime("%Y-%m-%d %H:%M:%S"),
        }
    })


@csrf_exempt
@login_required
def api_batch_mapping(request: HttpRequest) -> JsonResponse:
    """POST endpoint to batch update or clear category for multiple SKUs."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    brand_group = data.get("brand_group", "").lower().strip()
    sku_codes = data.get("sku_codes", [])
    product_category = data.get("product_category", "").strip()
    clear = bool(data.get("clear", False))

    if not brand_group or not sku_codes:
        return JsonResponse({"status": "error", "message": "brand_group and sku_codes are required"}, status=400)

    click_dt = _parse_click_timestamp(data.get("load_timestamp"))
    try:
        updated_count = batch_save_mappings(
            brand_group=brand_group,
            sku_codes=sku_codes,
            product_category=product_category,
            user=request.user,
            clear=clear,
            click_time=click_dt,
        )
    except ValueError as val_err:
        return JsonResponse({"status": "error", "message": str(val_err)}, status=400)

    action_word = "dikosongkan" if clear else f"dipetakan ke {product_category}"
    return JsonResponse({
        "status": "success",
        "message": f"Berhasil {action_word} untuk {updated_count} SKU.",
        "updated_count": updated_count,
    })


@csrf_exempt
@login_required
def api_import_excel(request: HttpRequest) -> JsonResponse:
    """POST endpoint to import parsed rows from Excel using bulk create."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid JSON body"}, status=400)

    rows = data.get("rows", [])
    if not rows:
        return JsonResponse({"status": "error", "message": "Tidak ada baris data untuk diimport"}, status=400)

    click_dt = _parse_click_timestamp(data.get("load_timestamp"))
    try:
        res = import_excel_parsed_rows(rows, request.user, click_time=click_dt)
    except ValueError as val_err:
        return JsonResponse({"status": "error", "message": str(val_err)}, status=400)

    dup_msg = ""
    if res.get("duplicates_collapsed", 0) > 0:
        dup_msg = f" ({res['duplicates_collapsed']} baris duplikat SKU disatukan)"

    return JsonResponse({
        "status": "success",
        "message": f"Berhasil menyimpan {res['updated']} SKU ke database{dup_msg}.",
        "imported_count": res["updated"],
        "total_rows": res.get("total_rows", res["updated"]),
        "duplicates_collapsed": res.get("duplicates_collapsed", 0),
    })


@never_cache
@login_required
def api_get_categories(request: HttpRequest) -> JsonResponse:
    """Returns list of distinct categories and SKU count for a brand_group."""
    brand_group = request.GET.get("brand_group", "").lower().strip()
    if not brand_group:
        return JsonResponse({"categories": []})

    qs = ProductCategoryMapping.objects.filter(brand_group=brand_group).exclude(
        product_category__isnull=True
    ).exclude(product_category="")
    cats = list(qs.values_list("product_category", flat=True).distinct().order_by("product_category"))

    cat_counts = []
    for c in cats:
        count = qs.filter(product_category=c).count()
        cat_counts.append({"name": c, "count": count})

    return JsonResponse({
        "brand_group": brand_group,
        "categories": cat_counts,
    })


@csrf_exempt
@login_required
def api_delete_category(request: HttpRequest) -> JsonResponse:
    """Unlinks a category from all SKUs in a brand_group by setting product_category to NULL."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST

    brand_group = data.get("brand_group", "").lower().strip()
    category = data.get("category", "").strip()

    if not brand_group or not category:
        return JsonResponse({"status": "error", "message": "brand_group and category required"}, status=400)

    try:
        canonical_bg = validate_brand_group_for_user(brand_group, request.user)
    except ValueError as val_err:
        return JsonResponse({"status": "error", "message": str(val_err)}, status=400)

    pic_name = request.user.username if request.user.is_authenticated else "system"
    click_dt = _parse_click_timestamp(data.get("load_timestamp"))
    now_sec = (click_dt or timezone.now()).replace(microsecond=0)

    updated_count = ProductCategoryMapping.objects.filter(
        brand_group=canonical_bg,
        product_category=category,
    ).update(
        product_category=None,
        pic=pic_name,
        last_updated=now_sec,
    )

    return JsonResponse({
        "status": "success",
        "message": f"Category '{category}' unlinked from {updated_count} SKUs.",
        "updated_count": updated_count,
        "deleted_count": updated_count,
    })


@never_cache
@login_required
def api_template_catalog(request: HttpRequest) -> JsonResponse:
    """Returns catalog of SKUs for a brand_group to pre-fill in the Excel template."""
    brand_group = request.GET.get("brand_group", "").lower().strip()
    if not brand_group:
        return JsonResponse({"status": "error", "message": "brand_group is required"}, status=400)

    try:
        canonical_bg = validate_brand_group_for_user(brand_group, request.user)
    except ValueError as val_err:
        return JsonResponse({"status": "error", "message": str(val_err)}, status=400)

    data = get_catalog_and_mappings(canonical_bg, request.user, page=1, page_size=10000, status_filter="all")

    rows = []
    for item in data.get("items", []):
        rows.append({
            "sku_code": item["sku"],
            "product_name": item["name"] or "",
            "brand_group": item["brand_group"],
            "product_category": item["category"] or "",
            "is_mapped": item["is_mapped"],
        })

    return JsonResponse({
        "status": "success",
        "brand_group": canonical_bg,
        "rows": rows,
        "total": len(rows),
    })


@never_cache
@login_required
def api_download_template_excel(request: HttpRequest) -> HttpResponse:
    """
    Generates and downloads a lightweight Excel (.xlsx) template
    where entire Column A, B, and C natively have Text format ('@') down to row 1,048,576.
    """
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    raw_bg = request.GET.get("brand_group", "").strip() or "mars"
    try:
        brand_group = validate_brand_group_for_user(raw_bg, request.user)
    except ValueError:
        user_bgs = get_available_brand_groups(request.user)
        brand_group = user_bgs[0] if user_bgs else raw_bg

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Product_Category_Template"

    # Set whole column dimensions to TEXT format ('@')
    # In Excel OpenXML specification, this writes <col min="1" max="1" style="1" /> where style 1 has numFmtId 49 (@)
    # This guarantees the ENTIRE Column A, B, and C down to row 1,048,576 natively has Text data type in Excel!
    ws.column_dimensions["A"].number_format = "@"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].number_format = "@"
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].number_format = "@"
    ws.column_dimensions["C"].width = 28

    # Headers
    headers = ["sku_code", "brand_group", "product_category"]
    ws.append(headers)

    # Style header row
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    for col_idx in range(1, 4):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.number_format = "@"

    # Sample rows (pure string values)
    sample_rows = [
        ["1729384538798392851", brand_group, "Contoh Kategori A"],
        ["WHIS-DRY-1.2KG", brand_group, "Cat Dry Food"],
        ["PEDI-WET-130G", brand_group, "Dog Wet Food"],
        ["111617-24", brand_group, "Dog Care & Treat"],
    ]

    for row_data in sample_rows:
        ws.append(row_data)

    # Ensure sample data cells also have explicit '@' text format
    for row in ws.iter_rows(min_row=2, max_row=len(sample_rows) + 1, min_col=1, max_col=3):
        for cell in row:
            cell.number_format = "@"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"template_sku_product_category_{brand_group}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@never_cache
@login_required
def target_management_view(request: HttpRequest) -> HttpResponse:
    """Renders the Daily & Monthly Target Data Ingestion and Planning management page."""
    from brand_performance_v2.services import get_user_brands
    from brand_performance_v2.models import OrderMartSummary

    user_brands = get_user_brands(request.user)

    platforms = ["Shopee", "Tokopedia", "Tiktok", "Lazada"]

    context: dict[str, Any] = {
        "brands": user_brands,
        "platforms": platforms,
        "default_brand": user_brands[0] if user_brands else "Senka",
        "default_platform": "Shopee",
        "current_year": 2026,
        "current_month": "11",
        "years": [2026, 2025, 2024],
        "is_superuser": getattr(request.user, "is_superuser", False),
    }
    return render(request, "data_management/target_management.html", context)


# ==============================================================================
# TARGET MANAGEMENT BACKEND API (postgre_daily_target_mart + order_mart_summary)
# ==============================================================================

_BOSS_STORE_ALIASES: dict[str, str] = {
    "makuku": "makuku official",
    "makuku babyboo": "babyboo",
    "hotwheels": "hot wheels",
    "popokmamaku": "pilihan mamaku",
    "thomas": "thomas & friends",
    "whiskas pedigree": "whiskas",
    "ace kid": "acekid",
    "gaabor official": "gaabor",
}


def _clean_alnum(val: str) -> str:
    return "".join(ch for ch in str(val or "").lower() if ch.isalnum())


def _normalize_store_name_for_db(raw_brand_or_store: str, existing_store_map: dict[str, str]) -> str:
    """
    Converts a display brand name (e.g. 'Ace Kid', 'Senka', 'Makuku Official')
    to the exact lowercase `store_name` convention used in `postgre_daily_target_mart`.
    """
    s = str(raw_brand_or_store or "").strip().lower()
    if not s:
        return ""
    if s in _BOSS_STORE_ALIASES:
        s = _BOSS_STORE_ALIASES[s]
    if s in existing_store_map:
        return existing_store_map[s]
    alnum = _clean_alnum(s)
    if alnum in existing_store_map:
        return existing_store_map[alnum]
    return s


def _build_target_reference_maps(user) -> dict[str, Any]:
    """
    Builds lookup maps from `postgre_daily_target_mart` and `order_mart_summary`
    so brand_group, store_name, display brand, and Store PIC stay 100% consistent.
    """
    from brand_performance_v2.services import get_user_brands
    from brand_performance_v2.models import OrderMartSummary
    from double_date.models import DailyTargetMart

    user_brands = get_user_brands(user)
    if not user_brands and getattr(user, "is_superuser", False):
        user_brands = sorted(
            list(
                OrderMartSummary.objects.order_by()
                .exclude(brand__isnull=True)
                .exclude(brand="")
                .values_list("brand", flat=True)
                .distinct()
            )
        )

    # Map clean alphanumeric key -> canonical display brand name
    display_brand_by_key: dict[str, str] = {}
    for b in user_brands:
        b_str = str(b).strip()
        display_brand_by_key[b_str.lower()] = b_str
        display_brand_by_key[_clean_alnum(b_str)] = b_str

    # Special aliases between DailyTargetMart.store_name and OrderMartSummary.brand
    if "gaabor official" in display_brand_by_key:
        display_brand_by_key.setdefault("gaabor", display_brand_by_key["gaabor official"])
        display_brand_by_key.setdefault("gaabor store", display_brand_by_key["gaabor official"])

    # Inspect distinct metadata in postgre_daily_target_mart
    existing_store_map: dict[str, str] = {}
    brand_group_by_store: dict[str, str] = {}
    pic_by_store_plat: dict[tuple[str, str], str] = {}
    pic_by_store: dict[str, str] = {}

    dtm_meta = (
        DailyTargetMart.objects.order_by()
        .values("store_name", "brand_group", "platform", "store_pic")
        .distinct()
    )
    for r in dtm_meta:
        sn = str(r.get("store_name") or "").strip().lower()
        if not sn:
            continue
        existing_store_map[sn] = sn
        existing_store_map[_clean_alnum(sn)] = sn

        bg = str(r.get("brand_group") or "").strip()
        if bg and sn not in brand_group_by_store:
            brand_group_by_store[sn] = bg

        pl = str(r.get("platform") or "").strip().lower()
        pic = str(r.get("store_pic") or "").strip()
        if pic:
            if pl and (sn, pl) not in pic_by_store_plat:
                pic_by_store_plat[(sn, pl)] = pic
            if sn not in pic_by_store:
                pic_by_store[sn] = pic

    # Fallback brand_group from OrderMartSummary for brands not yet in DailyTargetMart
    oms_bg = (
        OrderMartSummary.objects.order_by()
        .exclude(brand__isnull=True)
        .exclude(brand_group__isnull=True)
        .values("brand", "brand_group")
        .distinct()
    )
    for r in oms_bg:
        b_low = str(r.get("brand") or "").strip().lower()
        bg_up = str(r.get("brand_group") or "").strip().upper()
        if b_low and bg_up:
            sn = _normalize_store_name_for_db(b_low, existing_store_map)
            brand_group_by_store.setdefault(sn, bg_up)
            brand_group_by_store.setdefault(b_low, bg_up)

    return {
        "user_brands": user_brands,
        "display_brand_by_key": display_brand_by_key,
        "existing_store_map": existing_store_map,
        "brand_group_by_store": brand_group_by_store,
        "pic_by_store_plat": pic_by_store_plat,
        "pic_by_store": pic_by_store,
    }


def _display_platform(raw_plat: str) -> str:
    p = str(raw_plat or "").strip().lower()
    mapping = {
        "shopee": "Shopee",
        "tokopedia": "Tokopedia",
        "toped": "Tokopedia",
        "tiktok": "Tiktok",
        "tiktok shop": "Tiktok",
        "lazada": "Lazada",
        "blibli": "Blibli",
        "akulaku": "Akulaku",
    }
    return mapping.get(p, str(raw_plat or "").strip().title())


@never_cache
@login_required
@require_GET
def api_target_data(request: HttpRequest) -> JsonResponse:
    """
    Returns daily target records from `postgre_daily_target_mart` along with
    existing brand_group & Store PIC mappings for the authenticated user.
    """
    from double_date.models import DailyTargetMart

    ref = _build_target_reference_maps(request.user)
    user_brands = ref["user_brands"]
    display_brand_by_key = ref["display_brand_by_key"]
    existing_store_map = ref["existing_store_map"]
    brand_group_by_store = ref["brand_group_by_store"]
    pic_by_store = ref["pic_by_store"]
    pic_by_store_plat = ref["pic_by_store_plat"]

    allowed_alnum = {_clean_alnum(b) for b in user_brands}
    for b in user_brands:
        sn = _normalize_store_name_for_db(b, existing_store_map)
        if sn:
            allowed_alnum.add(_clean_alnum(sn))

    qs = DailyTargetMart.objects.exclude(date__isnull=True).order_by("date", "store_name", "platform", "key_id")

    records: list[dict[str, Any]] = []
    months_set: set[str] = set()

    for row in qs.values("key_id", "date", "brand_group", "store_name", "platform", "target", "store_pic"):
        sn_raw = str(row["store_name"] or "").strip()
        sn_low = sn_raw.lower()
        sn_alnum = _clean_alnum(sn_low)

        if not getattr(request.user, "is_superuser", False):
            if sn_alnum not in allowed_alnum:
                continue

        disp_brand = (
            display_brand_by_key.get(sn_low)
            or display_brand_by_key.get(sn_alnum)
            or sn_raw.title()
        )
        disp_plat = _display_platform(row["platform"])
        d_iso = row["date"].isoformat()
        ym = d_iso[:7]
        months_set.add(ym)

        records.append({
            "id": row["key_id"],
            "brand": disp_brand,
            "store_name": sn_low,
            "brand_group": row["brand_group"] or brand_group_by_store.get(sn_low, ""),
            "platform": disp_plat,
            "date": d_iso,
            "year_month": ym,
            "target": int(row["target"] or 0),
            "store_pic": row["store_pic"] or "",
            "status": "Active",
        })

    # Build brand metadata for frontend auto-lookup of brand_group & Store PIC
    brand_meta: dict[str, dict[str, Any]] = {}
    for b in user_brands:
        sn = _normalize_store_name_for_db(b, existing_store_map)
        plat_pics = {
            _display_platform(pl): pic
            for (s_key, pl), pic in pic_by_store_plat.items()
            if s_key == sn and pic
        }
        brand_meta[b] = {
            "store_name": sn,
            "brand_group": brand_group_by_store.get(sn, b.upper()),
            "default_pic": pic_by_store.get(sn, ""),
            "platform_pics": plat_pics,
        }

    sorted_months = sorted(months_set, reverse=True)
    return JsonResponse({
        "status": "success",
        "records": records,
        "brand_meta": brand_meta,
        "available_months": sorted_months,
        "latest_month": sorted_months[0] if sorted_months else "2026-11",
    })


@never_cache
@login_required
@require_POST
def api_target_save(request: HttpRequest) -> JsonResponse:
    """
    Atomically upserts daily target records into `postgre_daily_target_mart`
    AND propagates updated `target` & `store_pic` to `order_mart_summary` in real-time.
    Guarantees zero duplicate rows and zero primary key sequence collisions.
    """
    from datetime import date as date_cls

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"status": "error", "message": "Format JSON tidak valid."}, status=400)

    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or len(raw_records) == 0:
        return JsonResponse({"status": "error", "message": "Data target kosong."}, status=400)

    ref = _build_target_reference_maps(request.user)
    user_brands = ref["user_brands"]
    display_brand_by_key = ref["display_brand_by_key"]
    existing_store_map = ref["existing_store_map"]
    brand_group_by_store = ref["brand_group_by_store"]
    pic_by_store_plat = ref["pic_by_store_plat"]
    pic_by_store = ref["pic_by_store"]

    allowed_alnum = {_clean_alnum(b) for b in user_brands}
    for b in user_brands:
        sn = _normalize_store_name_for_db(b, existing_store_map)
        if sn:
            allowed_alnum.add(_clean_alnum(sn))

    # Deduplicate incoming records by (date, store_name, platform) keeping last
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for idx, item in enumerate(raw_records):
        raw_brand = str(item.get("brand") or item.get("store_name") or "").strip()
        raw_plat = str(item.get("platform") or "").strip().lower()
        raw_date = str(item.get("date") or "").strip()[:10]
        raw_target = item.get("target", 0)
        raw_pic = str(item.get("store_pic") or "").strip()
        raw_bg = str(item.get("brand_group") or "").strip()

        if not raw_brand or not raw_plat or not raw_date:
            continue

        try:
            date_cls.fromisoformat(raw_date)
        except ValueError:
            return JsonResponse({"status": "error", "message": f"Tanggal tidak valid pada baris {idx + 1}: {raw_date}"}, status=400)

        try:
            target_int = max(0, int(round(float(raw_target or 0))))
        except (ValueError, TypeError):
            return JsonResponse({"status": "error", "message": f"Nominal target tidak valid pada baris {idx + 1}"}, status=400)

        store_name = _normalize_store_name_for_db(raw_brand, existing_store_map)
        sn_alnum = _clean_alnum(store_name)

        if not getattr(request.user, "is_superuser", False):
            if sn_alnum not in allowed_alnum and _clean_alnum(raw_brand) not in allowed_alnum:
                return JsonResponse({"status": "error", "message": f"Anda tidak memiliki akses untuk brand '{raw_brand}'."}, status=403)

        # Auto-resolve brand_group from existing mapping if not explicitly provided
        resolved_bg = (
            raw_bg
            or brand_group_by_store.get(store_name)
            or brand_group_by_store.get(raw_brand.lower())
            or raw_brand.upper()
        )

        # Auto-resolve Store PIC: use user input if provided, else fallback to existing DB mapping
        resolved_pic = (
            raw_pic
            or pic_by_store_plat.get((store_name, raw_plat))
            or pic_by_store.get(store_name)
            or None
        )

        disp_brand = (
            display_brand_by_key.get(store_name)
            or display_brand_by_key.get(sn_alnum)
            or raw_brand
        )

        deduped[(raw_date, store_name, raw_plat)] = {
            "date": raw_date,
            "store_name": store_name,
            "display_brand": disp_brand,
            "platform": raw_plat,
            "target": target_int,
            "brand_group": resolved_bg,
            "store_pic": resolved_pic,
        }

    if not deduped:
        return JsonResponse({"status": "error", "message": "Tidak ada baris target valid untuk disimpan."}, status=400)

    clean_list = list(deduped.values())
    affected_dates = sorted({r["date"] for r in clean_list})
    affected_stores = sorted({r["store_name"] for r in clean_list})

    inserted_count = 0
    updated_count = 0
    oms_synced_count = 0

    with transaction.atomic():
        with connection.cursor() as cur:
            # 1. Ensure primary key sequence is strictly aligned with MAX(key_id) so INSERT never collides
            cur.execute(
                "SELECT setval('postgre_daily_target_mart_key_id_seq', "
                "COALESCE((SELECT MAX(key_id) FROM postgre_daily_target_mart), 1), true)"
            )

            # 2. Fetch existing key_ids for affected (date, store_name, platform)
            cur.execute(
                """
                SELECT key_id, date::text, LOWER(TRIM(store_name)), LOWER(TRIM(platform))
                FROM postgre_daily_target_mart
                WHERE date = ANY(%s::date[])
                  AND LOWER(TRIM(store_name)) = ANY(%s)
                ORDER BY key_id ASC
                """,
                [affected_dates, affected_stores],
            )
            existing_rows: dict[tuple[str, str, str], list[int]] = {}
            for kid, d_str, s_low, p_low in cur.fetchall():
                existing_rows.setdefault((d_str, s_low, p_low), []).append(kid)

            duplicate_kids_to_remove: list[int] = []

            for rec in clean_list:
                triple = (rec["date"], rec["store_name"], rec["platform"])
                kids = existing_rows.get(triple)

                if kids:
                    keep_kid = kids[-1]
                    if len(kids) > 1:
                        duplicate_kids_to_remove.extend(kids[:-1])
                    cur.execute(
                        """
                        UPDATE postgre_daily_target_mart
                        SET target = %s,
                            brand_group = COALESCE(%s, brand_group),
                            "Store PIC" = COALESCE(%s, "Store PIC")
                        WHERE key_id = %s
                        """,
                        [rec["target"], rec["brand_group"], rec["store_pic"], keep_kid],
                    )
                    updated_count += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO postgre_daily_target_mart (date, brand_group, store_name, platform, target, "Store PIC")
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        [
                            rec["date"],
                            rec["brand_group"],
                            rec["store_name"],
                            rec["platform"],
                            rec["target"],
                            rec["store_pic"],
                        ],
                    )
                    inserted_count += 1

                # 3. Real-time sync to order_mart_summary for matching (date, brand, platform)
                cur.execute(
                    """
                    UPDATE order_mart_summary
                    SET target = %s,
                        store_pic = COALESCE(%s, store_pic)
                    WHERE create_order_date_time_date = %s::date
                      AND LOWER(TRIM(platform)) = %s
                      AND (
                        LOWER(TRIM(brand)) = %s
                        OR LOWER(TRIM(brand)) = %s
                        OR REGEXP_REPLACE(LOWER(brand), '[^a-z0-9]', '', 'g') = %s
                      )
                    """,
                    [
                        rec["target"],
                        rec["store_pic"],
                        rec["date"],
                        rec["platform"],
                        rec["store_name"],
                        rec["display_brand"].lower(),
                        _clean_alnum(rec["store_name"]),
                    ],
                )
                oms_synced_count += cur.rowcount

            if duplicate_kids_to_remove:
                cur.execute(
                    "DELETE FROM postgre_daily_target_mart WHERE key_id = ANY(%s)",
                    [duplicate_kids_to_remove],
                )

    return JsonResponse({
        "status": "success",
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "total_saved": inserted_count + updated_count,
        "oms_synced_count": oms_synced_count,
    })


