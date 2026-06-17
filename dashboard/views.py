from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from dashboard.services.dashboard_performance import get_cards
from .services.gmv_services import get_gmv
from .services.dashboard_performance import get_nmv_line

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
    brands = list(
        request.user.userbrand_set.values_list("brand__name", flat=True)
    )

    return render(request, "brand_performance.html", {"brands": brands})

@login_required
def api_brand_performance(request):
    # 1. Ambil semua list brand yang di-assign ke user ini
    user_brands = list(
        request.user.userbrand_set.values_list("brand__name", flat=True)
    )

    # 2. Tangkap parameter filter dari AJAX request GET
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    selected_brand = request.GET.get("brand", "all")

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
    cards_data = get_cards(start_date, end_date, brands_to_query)
    trend_data = get_nmv_line(start_date, end_date, brands_to_query)

    # 5. Gabungkan hasilnya ke dalam satu response object sesuai ekspektasi AJAX HTML
    context_response = {
        "cards": cards_data,
        "trend": trend_data
    }

    return JsonResponse(context_response)