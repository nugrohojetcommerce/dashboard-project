/**
 * Brand & Platform Logo Utilities
 * Jetcommerce Dashboard
 */
(function (window) {
  'use strict';

  const BRAND_LOGO_FILES = {
    'dove body': 'Dove Body.png',
    'dove': 'Dove.png',
    'ace kid': 'Acekid.png',
    'acekid': 'Acekid.png',
    'babyboo': 'Makuku.png',
    'baby boo': 'Makuku.png',
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
    'pilihan mamaku': 'Makuku.png',
    'pilihanmamaku': 'Makuku.png',
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
  };

  const SORTED_BRAND_KEYS = Object.keys(BRAND_LOGO_FILES).sort((a, b) => b.length - a.length);

  function escHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[c]));
  }

  function getBrandLogoUrl(brand) {
    if (!brand) return null;
    const s = String(brand).trim().toLowerCase();
    if (!s) return null;

    if (BRAND_LOGO_FILES[s]) {
      return `/static/logos/brand-logo/${encodeURIComponent(BRAND_LOGO_FILES[s])}`;
    }

    const clean = s.replace(/[^a-z0-9]/g, '');
    if (!clean) return null;

    for (let i = 0; i < SORTED_BRAND_KEYS.length; i++) {
      const k = SORTED_BRAND_KEYS[i];
      if (k.replace(/[^a-z0-9]/g, '') === clean) {
        return `/static/logos/brand-logo/${encodeURIComponent(BRAND_LOGO_FILES[k])}`;
      }
    }

    for (let i = 0; i < SORTED_BRAND_KEYS.length; i++) {
      const k = SORTED_BRAND_KEYS[i];
      if (s.includes(k) || k.includes(s)) {
        return `/static/logos/brand-logo/${encodeURIComponent(BRAND_LOGO_FILES[k])}`;
      }
    }

    return null;
  }

  function renderBrandIcon(brand, size = 24, extraClass = '') {
    const url = getBrandLogoUrl(brand);
    const cls = extraClass ? `brand-logo-icon ${extraClass}` : 'brand-logo-icon';
    const s = String(brand ?? '').trim();

    if (!url) {
      if (!s || s.toLowerCase() === 'all' || s.toLowerCase() === 'all brands' || s.toLowerCase() === 'all brand groups') {
        return `<i class="bi bi-grid-fill brand-logo-fallback" style="font-size:${Math.max(14, size - 2)}px;"></i>`;
      }
      return `<i class="bi bi-tag-fill brand-logo-fallback" style="font-size:${Math.max(14, size - 2)}px;"></i>`;
    }

    // Diameter of circle equals the width and height of the PNG side length (100% aspect ratio square)
    return `<img src="${url}" alt="${escHtml(s)}" class="${cls}" style="width:${size}px; height:${size}px; aspect-ratio: 1/1; border-radius: 50%; object-fit: cover;" loading="lazy" onerror="this.onerror=null; this.style.display='none';">`;
  }

  function getPlatformLogoUrl(platform) {
    if (!platform) return null;
    const pl = String(platform).trim().toLowerCase();
    if (pl.includes('shopee')) return '/static/logos/shopee.svg';
    if (pl.includes('tokopedia') || pl.includes('toped')) return '/static/logos/tokopedia.svg';
    if (pl.includes('tiktok')) return '/static/logos/tiktok_shop.svg';
    if (pl.includes('lazada')) return '/static/logos/lazada.svg';
    return null;
  }

  function renderPlatformIcon(platform, size = 18, extraClass = '') {
    const url = getPlatformLogoUrl(platform);
    const cls = extraClass ? `platform-logo-icon ${extraClass}` : 'platform-logo-icon';
    const pl = String(platform ?? '').trim();

    if (!url) {
      if (pl === 'All' || pl.toLowerCase() === 'all platforms' || !pl) {
        return `<i class="bi bi-grid-fill platform-logo-fallback" style="font-size:${Math.max(14, size - 2)}px;"></i>`;
      }
      return `<i class="bi bi-shop platform-logo-fallback" style="font-size:${Math.max(14, size - 2)}px;"></i>`;
    }
    return `<img src="${url}" alt="${escHtml(pl)}" class="${cls}" style="width:${size}px; height:${size}px; object-fit: contain;">`;
  }

  function formatBrandSelect2(state) {
    if (!state.id) return state.text;
    const icon = renderBrandIcon(state.text, 24);
    if (window.jQuery) {
      return window.jQuery(`<span class="brand-with-logo">${icon} <span>${escHtml(state.text)}</span></span>`);
    }
    return state.text;
  }

  function formatPlatformSelect2(state) {
    if (!state.id) return state.text;
    const icon = renderPlatformIcon(state.text, 20);
    if (window.jQuery) {
      return window.jQuery(`<span class="brand-with-logo">${icon} <span>${escHtml(state.text)}</span></span>`);
    }
    return state.text;
  }

  // Expose to window
  window.getBrandLogoUrl = getBrandLogoUrl;
  window.renderBrandIcon = renderBrandIcon;
  window.getPlatformLogoUrl = getPlatformLogoUrl;
  window.renderPlatformIcon = renderPlatformIcon;
  window.formatBrandSelect2 = formatBrandSelect2;
  window.formatPlatformSelect2 = formatPlatformSelect2;

})(window);

