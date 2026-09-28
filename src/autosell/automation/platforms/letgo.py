"""letgo.com adaptörü."""

from __future__ import annotations

from ..driver import PageDriver
from .base import PlatformAdapter


class LetgoAdapter(PlatformAdapter):
    name = "letgo"
    post_button_texts = ["Sat", "+ Sat", "SAT", "Ücretsiz İlan Ver", "İlan Ver", "Ürün Sat", "Hemen Sat", "Satış yap"]
    logged_out_texts = ["Giriş", "Giriş Yap", "Giriş yap", "Üye Ol", "Kayıt Ol", "Giriş yap / Kayıt ol"]
    logged_in_texts = ["Çıkış Yap", "Çıkış", "Profilim", "Hesabım", "İlanlarım", "Mesajlar", "Sohbetler", "Favorilerim"]

    def next_page(self, driver: PageDriver, page_no: int) -> bool:
        """letgo sonuçları "Daha fazla yükle" düğmesi ya da sonsuz kaydırma ile gelir."""
        snap = driver.snapshot()
        btn = snap.find_clickable(["Daha fazla yükle", "Daha Fazla Göster", "Daha fazla ilan", "Load more"],
                                  threshold=0.8)
        if btn:
            driver.click(btn.id)
            driver.settle()
            driver.page.wait_for_timeout(600)
            return True
        before = driver.page.evaluate("document.body.scrollHeight")
        driver.page.mouse.wheel(0, 4000)
        driver.page.wait_for_timeout(1500)
        return driver.page.evaluate("document.body.scrollHeight") > before
