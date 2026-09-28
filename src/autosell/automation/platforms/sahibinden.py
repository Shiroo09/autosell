"""sahibinden.com adaptörü."""

from __future__ import annotations

import re

from ..driver import PageDriver
from .base import PlatformAdapter, page_number_param


class SahibindenAdapter(PlatformAdapter):
    name = "sahibinden"
    post_button_texts = ["Ücretsiz* İlan Ver", "Ücretsiz İlan Ver", "İlan Ver"]
    logged_out_texts = ["Giriş Yap", "Hesap Aç", "Üye Ol"]
    logged_in_texts = ["Çıkış", "Çıkış Yap", "Bana Özel", "Hesabım", "İlanlarım", "Mesajlarım"]
    page_size = 20

    def price_params(self, url: str, price_min: float | None, price_max: float | None) -> list[str]:
        params = []
        if price_min is not None and "price_min=" not in url:
            params.append(f"price_min={int(price_min)}")
        if price_max is not None and "price_max=" not in url:
            params.append(f"price_max={int(price_max)}")
        return params

    def next_page(self, driver: PageDriver, page_no: int) -> bool:
        """Sonuç sayfaları pagingOffset parametresiyle ilerler (varsayılan 20 ilan/sayfa)."""
        url = driver.page.url
        size = self.page_size
        m = re.search(r"pagingSize=(\d+)", url)
        if m:
            size = int(m.group(1))
        target = page_no * size
        snap = driver.snapshot()
        offsets = [
            int(found.group(1))
            for c in snap.clickables
            if (found := re.search(r"pagingOffset=(\d+)", c.href or ""))
        ]
        if offsets:
            if max(offsets) < target:
                return False
        elif not snap.find_clickable(["Sonraki", "›", "»"], threshold=0.9):
            return False
        driver.goto(page_number_param(url, "pagingOffset", target))
        return True
