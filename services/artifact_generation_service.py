"""Generate demo sites and interactive tools for the product showcase."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import GeneratedSite, GeneratedTool
from services.audit_service import audit_log
from services.project_service import slugify


class ArtifactGenerationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.sites_root = Path(self.settings.generated_sites_root).resolve()
        self.tools_root = Path(self.settings.generated_tools_root).resolve()
        self.sites_root.mkdir(parents=True, exist_ok=True)
        self.tools_root.mkdir(parents=True, exist_ok=True)

    def create_site(
        self,
        *,
        prompt: str,
        user_external_id: str = "telegram-user",
        workspace_id: str = "default",
        project_slug: str = "",
    ) -> GeneratedSite:
        site_type = infer_site_type(prompt)
        site_id = self._next_site_id(prompt)
        directory = self.sites_root / site_id
        directory.mkdir(parents=True, exist_ok=True)
        write_text(
            directory / "index.html",
            build_site_html(
                prompt=prompt,
                site_id=site_id,
                site_type=site_type,
                asset_prefix=f"/sites/{site_id}",
            ),
        )
        write_text(directory / "style.css", build_site_css())
        write_text(directory / "script.js", build_site_js())
        metadata = {
            "prompt": prompt,
            "site_type": site_type,
        }
        write_text(directory / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        site = GeneratedSite(
            site_id=site_id,
            workspace_id=workspace_id,
            user_external_id=user_external_id,
            project_slug=project_slug,
            title=human_title(prompt),
            prompt=prompt,
            site_type=site_type,
            directory_path=str(directory),
            public_path=f"/sites/{site_id}",
            metadata_json=metadata,
        )
        self.db.add(site)
        self.db.commit()
        self.db.refresh(site)
        audit_log(
            self.db,
            workspace_id=workspace_id,
            actor_type="agent",
            actor_id="developer",
            action="site.generated",
            object_type="generated_site",
            object_id=site.id,
            metadata={"site_id": site.site_id, "prompt": prompt[:200]},
            commit=True,
        )
        return site

    def create_tool(
        self,
        *,
        prompt: str,
        user_external_id: str = "telegram-user",
        workspace_id: str = "default",
        project_slug: str = "",
    ) -> GeneratedTool:
        tool_type = infer_tool_type(prompt)
        tool_id = self._next_tool_id(prompt)
        directory = self.tools_root / tool_id
        directory.mkdir(parents=True, exist_ok=True)
        write_text(
            directory / "index.html",
            build_tool_html(
                prompt=prompt,
                tool_id=tool_id,
                tool_type=tool_type,
                asset_prefix=f"/tools/{tool_id}",
            ),
        )
        write_text(directory / "style.css", build_tool_css())
        write_text(directory / "script.js", build_tool_js(tool_type))
        metadata = {
            "prompt": prompt,
            "tool_type": tool_type,
        }
        write_text(directory / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        tool = GeneratedTool(
            tool_id=tool_id,
            workspace_id=workspace_id,
            user_external_id=user_external_id,
            project_slug=project_slug,
            title=human_title(prompt),
            prompt=prompt,
            tool_type=tool_type,
            directory_path=str(directory),
            public_path=f"/tools/{tool_id}",
            metadata_json=metadata,
        )
        self.db.add(tool)
        self.db.commit()
        self.db.refresh(tool)
        audit_log(
            self.db,
            workspace_id=workspace_id,
            actor_type="agent",
            actor_id="developer",
            action="tool.generated",
            object_type="generated_tool",
            object_id=tool.id,
            metadata={"tool_id": tool.tool_id, "prompt": prompt[:200]},
            commit=True,
        )
        return tool

    def list_sites(self) -> list[GeneratedSite]:
        return list(self.db.scalars(select(GeneratedSite).order_by(GeneratedSite.created_at.desc())))

    def list_tools(self) -> list[GeneratedTool]:
        return list(self.db.scalars(select(GeneratedTool).order_by(GeneratedTool.created_at.desc())))

    def get_site(self, site_id: str) -> GeneratedSite | None:
        return self.db.scalar(select(GeneratedSite).where(GeneratedSite.site_id == site_id))

    def get_tool(self, tool_id: str) -> GeneratedTool | None:
        return self.db.scalar(select(GeneratedTool).where(GeneratedTool.tool_id == tool_id))

    def _next_site_id(self, prompt: str) -> str:
        return self._next_identifier(
            prompt,
            prefix="site",
            existing=lambda candidate: self.get_site(candidate) is not None,
        )

    def _next_tool_id(self, prompt: str) -> str:
        return self._next_identifier(
            prompt,
            prefix="tool",
            existing=lambda candidate: self.get_tool(candidate) is not None,
        )

    def _next_identifier(
        self,
        prompt: str,
        *,
        prefix: str,
        existing,
    ) -> str:
        base = unique_slug(prompt, prefix=prefix)
        candidate = base
        suffix = 2
        while existing(candidate) or (self.sites_root / candidate).exists() or (self.tools_root / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def unique_slug(text: str, *, prefix: str) -> str:
    compact = slugify(text).strip("-")
    if not compact or compact == "project":
        compact = prefix
    digest = hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:6]
    compact = compact[:64]
    if compact.startswith(prefix):
        return f"{compact}-{digest}"
    return f"{prefix}-{compact}-{digest}"


def human_title(prompt: str) -> str:
    compact = " ".join(prompt.strip().split())
    return compact[:80] or "AI Office Artifact"


def infer_site_type(prompt: str) -> str:
    lowered = prompt.lower()
    if "портфолио" in lowered:
        return "portfolio"
    if "заявк" in lowered or "form" in lowered:
        return "lead_form"
    if "продукт" in lowered:
        return "product"
    if "услуг" in lowered:
        return "service"
    return "landing"


def infer_tool_type(prompt: str) -> str:
    lowered = prompt.lower()
    if "crm" in lowered:
        return "mini_crm"
    if "чеклист" in lowered:
        return "checklist"
    if "бюджет" in lowered:
        return "budget_table"
    if "окупаем" in lowered:
        return "roi_calculator"
    return "cost_calculator"


def build_site_html(*, prompt: str, site_id: str, site_type: str, asset_prefix: str) -> str:
    title = human_title(prompt)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{asset_prefix}/style.css">
</head>
<body class="site-theme">
  <main class="hero">
    <div class="backdrop"></div>
    <section class="hero-copy">
      <p class="eyebrow">AI Office generated site</p>
      <h1>{title}</h1>
      <p class="lead">Тип: {site_type}. Этот сайт создан по запросу: "{prompt}".</p>
      <div class="hero-actions">
        <a href="#offer" class="button primary">Посмотреть оффер</a>
        <a href="#contact" class="button ghost">Оставить заявку</a>
      </div>
    </section>
  </main>
  <section id="offer" class="band">
    <div class="band-inner">
      <h2>Что здесь уже готово</h2>
      <div class="grid">
        <article><h3>Структура</h3><p>Hero, оффер, преимущества, CTA.</p></article>
        <article><h3>Контент</h3><p>Заголовки и блоки можно быстро адаптировать под клиента.</p></article>
        <article><h3>Публикация</h3><p>Артефакт хранится как статический сайт внутри AI Office.</p></article>
      </div>
    </div>
  </section>
  <section id="contact" class="band accent">
    <div class="band-inner">
      <h2>Оставить контакт</h2>
      <form class="lead-form">
        <input placeholder="Имя">
        <input placeholder="Telegram или email">
        <button type="button">Отправить</button>
      </form>
      <p class="note">Demo id: {site_id}</p>
    </div>
  </section>
  <script src="{asset_prefix}/script.js"></script>
</body>
</html>
"""


def build_site_css() -> str:
    return """:root {
  --bg: #f3ecdf;
  --ink: #1d241f;
  --panel: rgba(255,255,255,0.72);
  --accent: #b94d27;
  --accent-2: #2b6f67;
  --line: rgba(29,36,31,0.12);
}
* { box-sizing: border-box; }
body { margin: 0; font-family: Georgia, "Times New Roman", serif; color: var(--ink); background:
radial-gradient(circle at top left, rgba(185,77,39,0.18), transparent 28%),
linear-gradient(135deg, #f7f0e8, #e4eadf); }
.hero { min-height: 80vh; display: grid; align-items: center; padding: 5rem 6vw; position: relative; overflow: hidden; }
.backdrop { position: absolute; inset: 0; background:
linear-gradient(120deg, rgba(43,111,103,0.18), transparent 40%),
radial-gradient(circle at right, rgba(185,77,39,0.22), transparent 28%); }
.hero-copy { position: relative; max-width: 760px; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; }
h1 { font-size: clamp(3rem, 7vw, 5.75rem); line-height: 0.95; margin: 0.25rem 0 1rem; }
.lead { font: 1.1rem/1.6 "Trebuchet MS", "Avenir Next", sans-serif; max-width: 42rem; }
.hero-actions, .grid, .lead-form { display: flex; gap: 1rem; flex-wrap: wrap; }
.button, button { display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 0.9rem 1.4rem; text-decoration: none; border: 1px solid var(--line); background: var(--panel); color: var(--ink); }
.primary { background: var(--accent); color: #fff; border-color: transparent; }
.ghost { backdrop-filter: blur(12px); }
.band { padding: 4rem 6vw; }
.band-inner { max-width: 1100px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
article { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1rem; backdrop-filter: blur(14px); }
.accent { background: rgba(255,255,255,0.45); }
.lead-form input { min-width: 220px; padding: 0.8rem 1rem; border-radius: 999px; border: 1px solid var(--line); }
.note { font-family: "Trebuchet MS", sans-serif; color: rgba(29,36,31,0.62); }
@media (max-width: 640px) { .hero { padding-top: 4rem; } h1 { font-size: 2.8rem; } }
"""


def build_site_js() -> str:
    return """document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const target = document.querySelector(link.getAttribute("href"));
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});
"""


def build_tool_html(*, prompt: str, tool_id: str, tool_type: str, asset_prefix: str) -> str:
    title = human_title(prompt)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{asset_prefix}/style.css">
</head>
<body>
  <main class="tool-shell">
    <header>
      <p class="eyebrow">AI Office interactive tool</p>
      <h1>{title}</h1>
      <p>Тип: {tool_type}. Запрос: "{prompt}".</p>
    </header>
    <section class="panel">
      <div class="row">
        <label>Пользователи<input id="users" type="number" value="10" min="0"></label>
        <label>Часы в неделю<input id="hours" type="number" value="40" min="0"></label>
        <label>Ставка<input id="rate" type="number" value="25" min="0"></label>
      </div>
      <div id="result" class="result">0</div>
    </section>
    <section class="panel">
      <h2>Checklist</h2>
      <ul id="checklist">
        <li><input type="checkbox"> Telegram flow</li>
        <li><input type="checkbox"> Goal setup</li>
        <li><input type="checkbox"> Demo review</li>
      </ul>
      <p class="note">Tool id: {tool_id}</p>
    </section>
  </main>
  <script src="{asset_prefix}/script.js"></script>
</body>
</html>
"""


def build_tool_css() -> str:
    return """:root {
  --bg: #f6f8fb;
  --panel: #ffffff;
  --ink: #132034;
  --accent: #0e8d7a;
  --line: #d6deea;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: "Trebuchet MS", "Avenir Next", sans-serif; background:
linear-gradient(180deg, #eaf3ff, #f7fafc); color: var(--ink); }
.tool-shell { max-width: 980px; margin: 0 auto; padding: 3rem 1.25rem 4rem; }
header h1 { font: 700 clamp(2rem, 5vw, 4rem)/0.95 Georgia, serif; margin: 0.2rem 0 0.8rem; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; color: var(--accent); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1rem; margin-top: 1rem; box-shadow: 0 18px 40px rgba(20,32,52,0.06); }
.row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.8rem; }
label { display: grid; gap: 0.35rem; font-size: 0.9rem; }
input { width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 0.75rem 0.85rem; }
.result { margin-top: 1rem; font-size: 2rem; font-weight: 700; color: var(--accent); }
.note { color: #516173; font-size: 0.9rem; }
"""


def build_tool_js(tool_type: str) -> str:
    if tool_type == "checklist":
        return """document.querySelectorAll('#checklist input').forEach((box) => {
  box.addEventListener('change', () => {
    document.getElementById('result').textContent =
      `${document.querySelectorAll('#checklist input:checked').length} задач выполнено`;
  });
});
"""
    return """const users = document.getElementById('users');
const hours = document.getElementById('hours');
const rate = document.getElementById('rate');
const result = document.getElementById('result');
function update() {
  const total = Number(users.value || 0) * Number(hours.value || 0) * Number(rate.value || 0);
  result.textContent = `${total.toLocaleString('ru-RU')} у.е.`;
}
[users, hours, rate].forEach((input) => input.addEventListener('input', update));
update();
"""
