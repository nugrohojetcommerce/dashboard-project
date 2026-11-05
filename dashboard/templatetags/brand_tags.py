import re
from django import template
from django.templatetags.static import static
from django.utils.html import escape, mark_safe

register = template.Library()

# Exact & Alias Mapping to static file names in dashboard/static/logos/brand-logo/
BRAND_LOGO_FILES = {
    'dove body': 'Dove Body.png',
    'dove': 'Dove.png',
    'ace kid': 'Acekid.png',
    'acekid': 'Acekid.png',
    'barbie': 'Barbie.png',
    'bayer': 'Bayer.png',
    'biolage': 'Biolage.png',
    'lp-bio': 'Biolage.png',
    'lp bio': 'Biolage.png',
    'clear': 'Clear.png',
    'colgate': 'Colgate.png',
    'comfee': 'Comfee.png',
    'finetoday': 'Finetoday.png',
    'fine today': 'Finetoday.png',
    'fino': 'Fino.png',
    'fisher price': 'Fisher Price.png',
    'fisher-price': 'Fisher Price.png',
    'fisherprice': 'Fisher Price.png',
    'gaabor': 'Gaabor.png',
    'gaabor official': 'Gaabor.png',
    'gaabor socmed': 'Gaabor.png',
    'hot wheels': 'Hot Wheels.png',
    'hotwheels': 'Hot Wheels.png',
    'ladis': 'Ladis.png',
    'loreal': 'Loreal.png',
    "l'oreal": 'Loreal.png',
    "l'oréal": 'Loreal.png',
    'makuku': 'Makuku.png',
    'makuku official': 'Makuku.png',
    'makuku family': 'Makuku.png',
    'makuku semarang': 'Makuku.png',
    'makukoe': 'Makuku.png',
    'mars wrigley': 'Mars Wrigley.png',
    'mars': 'Mars Wrigley.png',
    'maers': 'Mars Wrigley.png',
    'mares': 'Mars Wrigley.png',
    'mattel': 'Mattel.png',
    'midea': 'Midea_1.png',
    'midea 1': 'Midea_1.png',
    'midea_1': 'Midea_1.png',
    'oppo': 'Oppo.png',
    'parenty': 'Parenty.png',
    'pedigree': 'Pedigree.png',
    'philips': 'Philips.png',
    'ponds': 'Ponds.png',
    "pond's": 'Ponds.png',
    'rexona': 'Rexona.png',
    'royal canin': 'Royal Canin.png',
    'royalcanin': 'Royal Canin.png',
    'senka': 'Senka.png',
    'sunsilk': 'Sunsilk.png',
    'super mild': 'Supermild.png',
    'supermild': 'Supermild.png',
    'thomas & friends': 'Thomas & Friends.png',
    'thomas and friends': 'Thomas & Friends.png',
    'thomas': 'Thomas & Friends.png',
    'tresemme': 'Tresemme.png',
    'tresemmé': 'Tresemme.png',
    'tsubaki': 'Tsubaki.png',
    'uhbs': 'UHBS.png',
    'unilever': 'UHBS.png',
    'vaseline': 'Vaseline.png',
    'walls': 'Walls.png',
    "wall's": 'Walls.png',
    'whiskas': 'Whiskas.png',
    'wilson': 'WIlson.png',
    'zwitsal': 'Zwitsal.png',
}

_SORTED_KEYS = sorted(BRAND_LOGO_FILES.keys(), key=lambda k: -len(k))


def resolve_brand_logo_file(name: str | None) -> str | None:
    if not name:
        return None
    s = str(name).strip().lower()
    if s in BRAND_LOGO_FILES:
        return BRAND_LOGO_FILES[s]

    clean = re.sub(r'[^a-z0-9]', '', s)
    if not clean:
        return None

    # Check alphanumeric normalization
    for k, v in BRAND_LOGO_FILES.items():
        if re.sub(r'[^a-z0-9]', '', k) == clean:
            return v

    # Check substring match (longest keys checked first)
    for k in _SORTED_KEYS:
        if k in s or s in k:
            return BRAND_LOGO_FILES[k]

    return None


@register.filter(name='brand_logo_url')
def brand_logo_url(brand_name) -> str:
    """Return static URL for brand logo, or empty string."""
    fname = resolve_brand_logo_file(brand_name)
    if not fname:
        return ""
    return static(f"logos/brand-logo/{fname}")


@register.simple_tag(name='render_brand_logo')
def render_brand_logo(brand_name, size: int = 24, extra_class: str = ""):
    """Render circular brand logo <img> or fallback icon."""
    url = brand_logo_url(brand_name)
    b_str = str(brand_name or '').strip()
    cls_parts = ["brand-logo-icon"]
    if extra_class:
        cls_parts.append(extra_class)
    cls = " ".join(cls_parts)

    if not url:
        if not b_str or b_str.lower() in ('all', 'all brands', 'all brand groups'):
            return mark_safe(f'<i class="bi bi-grid-fill brand-logo-fallback" style="font-size:{max(14, size - 2)}px;"></i>')
        return mark_safe(f'<i class="bi bi-tag-fill brand-logo-fallback" style="font-size:{max(14, size - 2)}px;"></i>')

    escaped_name = escape(b_str)
    # Circle diameter equals size (side of the PNG aspect square), inscribed circle
    return mark_safe(
        f'<img src="{url}" alt="{escaped_name}" class="{cls}" '
        f'style="width:{size}px; height:{size}px; aspect-ratio: 1/1; border-radius: 50%; object-fit: cover;" '
        f'loading="lazy" onerror="this.onerror=null; this.style.display=\'none\';">'
    )


@register.filter(name='platform_logo_url')
def platform_logo_url(platform_name) -> str:
    if not platform_name:
        return ""
    pl = str(platform_name).strip().lower()
    if 'shopee' in pl:
        return static('logos/shopee.svg')
    if 'tokopedia' in pl or 'toped' in pl:
        return static('logos/tokopedia.svg')
    if 'tiktok' in pl:
        return static('logos/tiktok_shop.svg')
    if 'lazada' in pl:
        return static('logos/lazada.svg')
    return ""


@register.simple_tag(name='render_platform_logo')
def render_platform_logo(platform_name, size: int = 15, extra_class: str = ""):
    url = platform_logo_url(platform_name)
    p_str = str(platform_name or '').strip()
    cls_parts = ["platform-logo-icon"]
    if extra_class:
        cls_parts.append(extra_class)
    cls = " ".join(cls_parts)

    if not url:
        if not p_str or p_str.lower() in ('all', 'all platforms'):
            return mark_safe(f'<i class="bi bi-grid-fill platform-logo-fallback" style="font-size:{max(10, size - 2)}px;"></i>')
        return mark_safe(f'<i class="bi bi-shop platform-logo-fallback" style="font-size:{max(10, size - 2)}px;"></i>')

    escaped_name = escape(p_str)
    return mark_safe(
        f'<img src="{url}" alt="{escaped_name}" class="{cls}" '
        f'style="width:{size}px; height:{size}px; object-fit: contain;">'
    )

