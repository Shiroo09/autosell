"""Komut satırı arayüzü.

Örnekler:
    autosell panel                      # web panelini aç (http://127.0.0.1:8000)
    autosell panel --demo               # API anahtarı olmadan örnek verilerle dene
    autosell giris sahibinden           # tarayıcıda bir kez giriş yap (oturum saklanır)
    autosell olustur ./urunler/iphone --fiyat 32500
    autosell yayinla <taslak-id> --platform sahibinden
    autosell toplu ./urunler --platform sahibinden,letgo
    autosell tara --izle                # takip listelerini sürekli tara
    autosell arastir "iPhone 13 128 GB" --platform sahibinden
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

from . import __version__
from .automation.interaction import ConsoleInteraction
from .automation.platforms import PublishError, get_adapter
from .config import PLATFORM_NAMES, PLATFORMS
from .images import ALLOWED_SUFFIXES
from .listing import ListingGenerator
from .market.scanner import MarketScanner
from .service import AutoSell
from .textutil import format_price


def _platforms(value: str) -> list[str]:
    items = [p.strip().lower() for p in value.split(",") if p.strip()]
    bad = [p for p in items if p not in PLATFORMS]
    if bad:
        raise argparse.ArgumentTypeError(f"Bilinmeyen platform: {', '.join(bad)} (sahibinden, letgo)")
    return items


def _photos_from(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in ALLOWED_SUFFIXES)
        elif p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES:
            files.append(p)
    return files


def _read_folder_notes(folder: Path) -> tuple[str, float | None]:
    """Klasördeki notlar.txt (ilk satırlarda 'fiyat: 25000' olabilir) dosyasını okur."""
    notes_file = next((folder / n for n in ("notlar.txt", "not.txt", "aciklama.txt", "bilgi.txt")
                       if (folder / n).exists()), None)
    if not notes_file:
        return "", None
    text = notes_file.read_text(encoding="utf-8")
    price = None
    m = re.search(r"(?im)^\s*fiyat\s*[:=]\s*([\d.,]+)", text)
    if m:
        raw = m.group(1).replace(".", "").replace(",", ".")
        try:
            price = float(raw)
        except ValueError:
            price = None
        text = text.replace(m.group(0), "").strip()
    return text, price


def _print_draft(draft) -> None:  # type: ignore[no-untyped-def]
    print(f"\nTaslak: {draft.id}")
    if draft.product.name:
        print(f"Ürün: {draft.product.name} ({draft.product.condition})")
    for platform, listing in draft.listings.items():
        print(f"\n── {PLATFORM_NAMES.get(platform, platform)} ──")
        print(f"Kategori : {' > '.join(listing.category_path)}")
        for i, cand in enumerate(listing.title_candidates[:5]):
            mark = "★" if i == 0 else " "
            print(f" {mark} [{cand.score:5.1f}] {cand.text}")
        print("Özellikler: " + "; ".join(f"{a.name}: {a.value}" for a in listing.attributes))
        print("Açıklama:\n" + listing.description)
    if draft.product.missing_info:
        print("\nİlanı güçlendirmek için eklenebilecek bilgiler: " + ", ".join(draft.product.missing_info))
    if draft.product.warnings:
        print("⚠ Uyarılar: " + "; ".join(draft.product.warnings))


def cmd_panel(app: AutoSell, args: argparse.Namespace) -> int:
    import uvicorn

    from .web import create_app

    if args.demo:
        from .demo import DemoProvider, seed_demo

        app.provider_override = DemoProvider()
        seed_demo(app)
        print("Demo modu: yapay zekâ yanıtları örnektir, gerçek API çağrısı yapılmaz.")
    local = args.host in ("127.0.0.1", "localhost", "::1")
    if not local and not app.settings.panel_password() and not args.sifresiz:
        print("Güvenlik: panel ağa açılırken şifre gerekir. Ayarlar > Panel bölümünden şifre belirleyin ya da "
              "AUTOSELL_PANEL_PASSWORD ortam değişkenini tanımlayın (riski kabul ediyorsanız --sifresiz).")
        return 2
    if not args.demo:  # demo verisi gerçek siteleri taramasın
        app.scheduler.start()
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    print(f"AutoSell paneli: {url}  (veri: {app.paths.root})")
    if not local:
        print("Telefonunuzdan erişmek için bilgisayarınızın yerel IP adresini kullanın, ör. http://192.168.1.20:"
              f"{args.port}")
    uvicorn.run(create_app(app), host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_giris(app: AutoSell, args: argparse.Namespace) -> int:
    ui = ConsoleInteraction()
    adapter = get_adapter(args.platform, app.settings, None, ui, app.paths.shots_dir)
    app.pool.worker(args.platform).run(adapter.login, label="giriş")
    return 0


def _generate(app: AutoSell, draft_id: str) -> None:
    draft = app.draft_or_404(draft_id)
    provider = app.provider()
    assert provider is not None
    ListingGenerator(provider, app.settings).generate(draft, app.photo_paths(draft), print)
    app.db.save_draft(draft)


def cmd_olustur(app: AutoSell, args: argparse.Namespace) -> int:
    photos = _photos_from(args.fotograflar)
    notes, price = args.not_ or "", args.fiyat
    for raw in args.fotograflar:
        folder = Path(raw).expanduser()
        if folder.is_dir():
            folder_notes, folder_price = _read_folder_notes(folder)
            notes = notes or folder_notes
            price = price if price is not None else folder_price
    if not photos and not notes:
        print("En az bir fotoğraf ya da --not gerekli.")
        return 2
    draft = app.create_draft(notes=notes, price=price, platforms=args.platform,
                             photos=[(p.name, p.read_bytes()) for p in photos])
    _generate(app, draft.id)
    _print_draft(app.draft_or_404(draft.id))
    print(f"\nYayınlamak için: autosell yayinla {draft.id}")
    return 0


def _publish(app: AutoSell, draft_id: str, platform: str, auto: bool) -> bool:
    ui = ConsoleInteraction(auto_yes=auto)
    draft = app.draft_or_404(draft_id)
    adapter = get_adapter(platform, app.settings, app.provider(required=False), ui, app.paths.shots_dir)
    if auto:
        adapter.ps.auto_publish = True
    try:
        result = app.pool.worker(platform).run(
            lambda session: adapter.publish(session, draft, app.photo_paths(draft)), label="yayın"
        )
    except PublishError as exc:
        app._set_publication(draft_id, platform, "hata", message=str(exc))
        print(f"✖ {PLATFORM_NAMES[platform]}: {exc}")
        return False
    app._set_publication(draft_id, platform, "yayinda", url=result.url, listing_no=result.listing_no,
                         message=result.message)
    print(f"✔ {PLATFORM_NAMES[platform]}: {result.message} {result.url}")
    return True


def cmd_yayinla(app: AutoSell, args: argparse.Namespace) -> int:
    draft = app.draft_or_404(args.taslak)
    ok = True
    for platform in args.platform or draft.platforms:
        ok = _publish(app, draft.id, platform, args.otomatik) and ok
    return 0 if ok else 1


def cmd_toplu(app: AutoSell, args: argparse.Namespace) -> int:
    root = Path(args.klasor).expanduser()
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    if not folders:
        print("Alt klasör bulunamadı. Her ürün için fotoğrafları ve notlar.txt dosyasını ayrı bir klasöre koyun.")
        return 2
    for folder in folders:
        photos = _photos_from([str(folder)])
        notes, price = _read_folder_notes(folder)
        if not photos and not notes:
            continue
        print(f"\n=== {folder.name} ===")
        draft = app.create_draft(notes=notes, price=price, platforms=args.platform,
                                 photos=[(p.name, p.read_bytes()) for p in photos])
        _generate(app, draft.id)
        draft = app.draft_or_404(draft.id)
        _print_draft(draft)
        if args.sadece_olustur:
            continue
        if draft.price is None:
            print("Fiyat yok (notlar.txt içine 'fiyat: 25000' yazın); yayınlama atlandı.")
            continue
        for platform in draft.platforms:
            _publish(app, draft.id, platform, args.otomatik)
            time.sleep(5)
    return 0


def cmd_tara(app: AutoSell, args: argparse.Namespace) -> int:
    ui = ConsoleInteraction()

    def run_once() -> None:
        watches = app.db.list_watches(active_only=True)
        if not watches:
            print("Aktif takip listesi yok. Panelden ya da 'autosell panel' ile ekleyin.")
        for watch in watches:
            scanner = MarketScanner(app.db, app.settings, app.provider(required=False), ui, app.paths.shots_dir)
            summary = app.pool.worker(watch.platform).run(lambda s, w=watch: scanner.scan_watch(s, w), label="tarama")
            print(f"• {watch.name}: {summary.message}")

    if not args.izle:
        run_once()
        return 0
    print("Takip listeleri ayarlanan aralıklarla taranıyor (durdurmak için Ctrl+C)...")
    app.scheduler.start()
    reported: set[str] = set()
    try:
        while True:
            time.sleep(10)
            for job in app.jobs.list(limit=20):
                if job.kind == "scan" and not job.active and job.id not in reported:
                    reported.add(job.id)
                    detail = (job.result or {}).get("message", "") if job.status == "done" else job.error
                    print(f"[{job.finished_at}] {job.title}: {detail}")
    except KeyboardInterrupt:
        return 0


def cmd_arastir(app: AutoSell, args: argparse.Namespace) -> int:
    ui = ConsoleInteraction()
    scanner = MarketScanner(app.db, app.settings, None, ui, app.paths.shots_dir)
    result = app.pool.worker(args.platform).run(
        lambda s: scanner.research(s, args.platform, query=args.kelime or "", url=args.url or ""), label="araştırma"
    )
    est = result["estimate"]
    print(f"\n{result['matched']} benzer ilan (taranan {result['scanned']}):")
    print(f"  Medyan : {format_price(est['median'])}")
    print(f"  Aralık : {format_price(est['p25'])} – {format_price(est['p75'])}")
    sugg = result["suggestions"]
    print(f"  Öneri  : hızlı satış {format_price(sugg['quick'])}, piyasa {format_price(sugg['fair'])}, "
          f"üst {format_price(sugg['high'])}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_ayarlar(app: AutoSell, args: argparse.Namespace) -> int:
    print(f"Ayar dosyası: {app.paths.settings_file}")
    print(json.dumps(app.settings_store.public_dict(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autosell", description="Sahibinden & Letgo ilan asistanı ve fırsat avcısı")
    parser.add_argument("--veri", help="Veri klasörü (varsayılan: ./veri veya AUTOSELL_DATA_DIR)")
    parser.add_argument("-v", "--ayrintili", action="store_true", help="Ayrıntılı günlük")
    parser.add_argument("--demo", dest="demo_global", action="store_true",
                        help="Gerçek yapay zekâ yerine örnek yanıtlar kullan (API anahtarı gerekmez)")
    parser.add_argument("--version", action="version", version=f"autosell {__version__}")
    sub = parser.add_subparsers(dest="komut", required=True)

    p = sub.add_parser("panel", help="Web panelini başlat")
    p.add_argument("--host", default="127.0.0.1", help="Telefon/ağ erişimi için 0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--demo", action="store_true", help="Örnek verilerle, API anahtarı olmadan dene")
    p.add_argument("--sifresiz", action="store_true", help="Ağa şifresiz açmaya izin ver (önerilmez)")
    p.set_defaults(func=cmd_panel)

    p = sub.add_parser("giris", help="Platforma tarayıcıda giriş yap (oturum saklanır)")
    p.add_argument("platform", choices=PLATFORMS)
    p.set_defaults(func=cmd_giris)

    p = sub.add_parser("olustur", help="Fotoğraf/notlardan yapay zekâ ile ilan taslağı oluştur")
    p.add_argument("fotograflar", nargs="*", help="Fotoğraf dosyaları ya da klasör")
    p.add_argument("--not", dest="not_", help="Ürün hakkında notlar")
    p.add_argument("--fiyat", type=float)
    p.add_argument("--platform", type=_platforms, default=None)
    p.set_defaults(func=cmd_olustur)

    p = sub.add_parser("yayinla", help="Taslağı platform(lar)da yayınla")
    p.add_argument("taslak", help="Taslak kimliği")
    p.add_argument("--platform", type=_platforms, default=None)
    p.add_argument("--otomatik", action="store_true", help="Son onayı sormadan yayınla")
    p.set_defaults(func=cmd_yayinla)

    p = sub.add_parser("toplu", help="Klasördeki her ürün alt klasörünü oluşturup yayınla")
    p.add_argument("klasor")
    p.add_argument("--platform", type=_platforms, default=None)
    p.add_argument("--otomatik", action="store_true")
    p.add_argument("--sadece-olustur", action="store_true", help="Yalnızca taslak oluştur, yayınlama")
    p.set_defaults(func=cmd_toplu)

    p = sub.add_parser("tara", help="Takip listelerini tara (fırsat avcısı)")
    p.add_argument("--izle", action="store_true", help="Sürekli, ayarlanan aralıklarla tara")
    p.set_defaults(func=cmd_tara)

    p = sub.add_parser("arastir", help="Bir ürün için piyasa fiyat araştırması yap")
    p.add_argument("kelime", nargs="?", default="")
    p.add_argument("--url", default="")
    p.add_argument("--platform", choices=PLATFORMS, default="sahibinden")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_arastir)

    p = sub.add_parser("ayarlar", help="Ayar dosyasının yerini ve içeriğini göster")
    p.set_defaults(func=cmd_ayarlar)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:  # çalışma klasöründeki .env dosyasını oku (API anahtarları vb.; git'e eklenmez)
        from dotenv import load_dotenv

        load_dotenv(Path.cwd() / ".env")
    except ImportError:  # pragma: no cover
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.ayrintili else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = AutoSell(args.veri)
    if args.demo_global or getattr(args, "demo", False):
        from .demo import DemoProvider

        app.provider_override = DemoProvider()
    try:
        return int(args.func(app, args) or 0)
    except KeyError as exc:
        print(f"✖ {str(exc).strip(chr(39))}")
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - kullanıcıya anlaşılır mesaj
        print(f"✖ {exc}")
        if args.ayrintili:
            raise
        return 1
    finally:
        app.shutdown()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
