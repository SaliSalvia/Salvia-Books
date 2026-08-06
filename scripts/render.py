# -*- coding: utf-8 -*-
"""
render.py
---------
ساخت HTML (صفحات عمودی A4، فونت بزرگ، جلد + پشت‌جلد + فوتر استاندارد در
همه‌ی صفحات میانی) و تبدیل آن به PDF با Playwright (کرومیوم headless).
"""

from pathlib import Path

FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Vazirmatn:wght@400;500;600;700;800&"
    "family=EB+Garamond:ital,wght@0,400;0,600;1,400&display=swap');"
)

CSS = """
@page { size: 794px 1123px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; }
.page {
  width: 794px; height: 1123px;
  page-break-after: always;
  position: relative;
  overflow: hidden;
  font-family: var(--font);
}
[dir="rtl"] .page { direction: rtl; }
[dir="ltr"] .page { direction: ltr; }

.cover, .backcover {
  background: radial-gradient(ellipse at center, #2a2359 0%, #14122e 70%);
  color: #e9dcb8;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; padding: 70px;
}
.cover .kicker, .backcover .kicker { letter-spacing: 4px; font-size: 15px; color: #b79a55; margin-bottom: 18px; }
.cover h1 { font-size: 50px; margin: 10px 0 14px; }
.cover .blurb { font-size: 22px; font-style: italic; color: #d8c99a; max-width: 560px; line-height: 1.8; margin-top: 10px; }
.cover .credit, .backcover .credit { margin-top: 60px; font-size: 16px; color: #c8ae6a; display:flex; flex-direction:column; align-items:center; gap:10px;}
.cover .credit img, .backcover .credit img { width: 64px; height: 64px; object-fit: contain; }
.backcover .note { font-size: 18px; line-height: 1.9; max-width: 560px; color: #d8c99a; margin-bottom: 40px; }
.backcover .github { font-size: 15px; color: #9fb3d9; margin-top: 6px; }

.text-page {
  background: #f4ecd8; color: #2b2410;
  padding: 90px 70px 110px;
  display: flex; flex-direction: column; justify-content: center;
}
.text-page .title-wrap { text-align: center; margin-bottom: 36px; }
.text-page .kicker { letter-spacing: 3px; font-size: 14px; color: #a5843a; margin-bottom: 16px; }
.text-page h2 { font-size: 36px; border-bottom: 2px solid #c8a24a; display: inline-block; padding-bottom: 12px; margin: 0; }
.text-page p { font-size: 23px; line-height: 2.05; text-align: justify; margin: 0 0 24px; }

.image-page { background: #f4ecd8; display: flex; flex-direction: column; }
.image-page .img-half { width: 100%; height: 561px; object-fit: cover; }
.image-page .caption-half {
  height: 512px; padding: 46px 60px; display: flex; flex-direction: column;
  justify-content: center; text-align: center;
}
.image-page .caption-half .kicker { letter-spacing: 3px; font-size: 13px; color: #a5843a; margin-bottom: 14px; }
.image-page .caption-half h3 { font-size: 28px; margin: 0 0 18px; color: #2b2410; }
.image-page .caption-half p { font-size: 21px; line-height: 1.9; color: #3a3018; }

.footer {
  position: absolute; bottom: 26px; left: 0; right: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: #8a7a4f;
}
.footer .page-num { position: absolute; left: 50%; transform: translateX(-50%); }
.footer .brand { position: absolute; left: 46px; display: flex; align-items: center; gap: 10px; }
.footer .brand img { width: 30px; height: 30px; object-fit: contain; }
.footer .brand span { font-size: 12px; color: #9a875a; }
"""


def _footer_html(page_num, logo_uri):
    return f"""
    <div class="footer">
      <div class="brand"><img src="{logo_uri}"><span>Design by: @SaliSalvia</span></div>
      <div class="page-num">{page_num}</div>
    </div>
    """


def render_book_html(*, lang: str, title: str, author: str, blurb: str,
                      sections: list, logo_uri: str, github_url: str,
                      out_html_path: Path):
    font_var = "'Vazirmatn', 'EB Garamond', serif" if lang == "fa" else "'EB Garamond', 'Vazirmatn', serif"
    dir_attr = "rtl" if lang == "fa" else "ltr"
    kicker_top = "A CURATORIAL VISUAL EDITION" if lang == "en" else "یک نسخه‌ی کیوریتوریِ تصویری"
    label_by = "طراحی و ساخت" if lang == "fa" else "Designed & built by"
    colophon_title = "About this edition" if lang == "en" else "درباره‌ی این نسخه"
    colophon_body_fa = (
        "این نسخه با کمک هوش مصنوعی (تحلیل متن، تصویرسازی و صفحه‌آرایی خودکار) "
        "به‌صورت غیرانتفاعی و صرفاً برای بازخوانیِ بصریِ اثر ساخته شده است."
    )
    colophon_body_en = (
        "This edition was generated with the help of AI (automated text analysis, "
        "illustration, and layout) as a non-commercial visual companion to the original work."
    )
    colophon_body = colophon_body_fa if lang == "fa" else colophon_body_en

    parts = [f"""<!DOCTYPE html>
<html lang="{lang}" dir="{dir_attr}">
<head><meta charset="UTF-8"><style>
{FONT_IMPORT}
:root {{ --font: {font_var}; }}
{CSS}
</style></head><body>
"""]

    # جلد
    parts.append(f"""
    <div class="page cover" dir="{dir_attr}">
      <div class="kicker">{kicker_top}</div>
      <h1>{title}</h1>
      <div class="blurb">{blurb}</div>
      <div class="credit">
        <img src="{logo_uri}">
        <div>{label_by}: <b>@SaliSalvia</b></div>
      </div>
    </div>
    """)

    page_num = 2
    total = len(sections)
    for idx, sec in enumerate(sections, start=1):
        text_html = "".join(f"<p>{p}</p>" for p in sec["paragraphs"])
        parts.append(f"""
        <div class="page text-page" dir="{dir_attr}">
          <div class="title-wrap">
            <div class="kicker">{sec.get('chapter_kicker','')}</div>
            <h2>{sec.get('chapter_title','')}</h2>
          </div>
          {text_html}
          {_footer_html(page_num, logo_uri)}
        </div>
        """)
        page_num += 1

        if sec.get("image_path"):
            img_uri = Path(sec["image_path"]).resolve().as_uri()
            parts.append(f"""
            <div class="page image-page" dir="{dir_attr}">
              <img class="img-half" src="{img_uri}">
              <div class="caption-half">
                <div class="kicker">{sec.get('chapter_kicker','')}</div>
                <h3>{sec.get('chapter_title','')}</h3>
                <p>{sec.get('caption','')}</p>
              </div>
              {_footer_html(page_num, logo_uri)}
            </div>
            """)
            page_num += 1

    # پشت‌جلد / کولوفون
    parts.append(f"""
    <div class="page backcover" dir="{dir_attr}">
      <div class="kicker">{colophon_title}</div>
      <div class="note">{colophon_body}</div>
      <div class="credit">
        <img src="{logo_uri}">
        <div>{label_by}: <b>@SaliSalvia</b></div>
        <div class="github">{github_url}</div>
      </div>
    </div>
    """)

    parts.append("</body></html>")
    out_html_path.write_text("".join(parts), encoding="utf-8")


def html_to_pdf(html_path: Path, pdf_path: Path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri())
        page.wait_for_timeout(500)
        page.pdf(
            path=str(pdf_path),
            width="794px", height="1123px",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
