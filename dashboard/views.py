from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .services.gmv_services import get_gmv

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