"""
대학 입학설명회 자동신청 봇
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  연세대  2026-04-18 10:00
  고려대  2026-04-25 10:00
  경희대  2026-05-30 13:00

실행:  python bot.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PwTimeout,
)

# ─────────────────────────────────────
# 설정
# ─────────────────────────────────────
CFG_PATH = Path(__file__).parent / "config.yaml"

def load_config() -> dict:
    with open(CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ─────────────────────────────────────
# 로거
# ─────────────────────────────────────
def make_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter(f"%(asctime)s [{name}] %(message)s", "%H:%M:%S")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        fh = logging.FileHandler("bot.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(sh)
        logger.addHandler(fh)
    return logger

root_log = make_logger("봇")

# ─────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────
LOGIN_PAGE_KEYWORDS = ["로그인", "login", "로그인이 필요", "회원가입"]

async def is_redirected_to_login(page: Page) -> bool:
    """현재 페이지가 로그인 페이지인지 확인."""
    url = page.url.lower()
    if any(kw in url for kw in ["login", "member", "signin"]):
        return True
    try:
        body = await page.inner_text("body")
        pw_fields = page.locator('input[type="password"]')
        if await pw_fields.count() > 0:
            return True
    except Exception:
        pass
    return False

async def fill_field(page: Page, name_candidates: str, value: str):
    """이름 후보(콤마 구분) 중 존재하는 입력 필드에 값 입력."""
    if not value:
        return
    for name in name_candidates.split(","):
        name = name.strip()
        for attr in ["name", "id"]:
            sel = (
                f'input[{attr}="{name}"], '
                f'select[{attr}="{name}"], '
                f'textarea[{attr}="{name}"]'
            )
            loc = page.locator(sel)
            if await loc.count() > 0:
                tag = await loc.first.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    try:
                        await loc.first.select_option(label=value)
                    except Exception:
                        try:
                            await loc.first.select_option(value=value)
                        except Exception:
                            pass
                else:
                    await loc.first.fill(value)
                return

async def click_first(page: Page, selector: str) -> bool:
    loc = page.locator(selector)
    if await loc.count() > 0:
        await loc.first.click()
        return True
    return False

# ─────────────────────────────────────
# 대학별 봇
# ─────────────────────────────────────
class UniversityBot:
    def __init__(self, key: str, ucfg: dict, cfg: dict):
        self.key = key
        self.name = ucfg["name"]
        self.ucfg = ucfg
        self.cfg = cfg
        self.applicant = cfg["applicant"]
        self.bot_cfg = cfg["bot"]
        self.log = make_logger(self.name)
        # 신청 접수 시작 시각 (선착순 클릭 타이밍)
        self.target_dt = datetime.strptime(ucfg["apply_open_datetime"], "%Y-%m-%d %H:%M:%S")
        # 원하는 설명회 날짜 (폼에서 선택)
        self.session_date = ucfg.get("session_date", "")
        self.session_date_text = ucfg.get("session_date_text", "")

    async def try_apply(self, page: Page) -> bool:
        """설명회 신청 시도. 성공 True / 신청버튼없음 False / 로그인필요 None 반환."""
        scfg = self.ucfg["seminar"]
        url = scfg["url"]

        self.log.info(f"페이지 이동: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=self.bot_cfg["timeout"])
        await asyncio.sleep(1)

        # 로그인 페이지로 이동됐는지 확인
        if await is_redirected_to_login(page):
            self.log.warning("⚠️  로그인이 필요한 사이트입니다!")
            return None  # 로그인 필요 신호

        # 신청 버튼 찾기
        apply_sel = scfg["apply_btn_selector"]
        btns = page.locator(apply_sel)
        count = await btns.count()

        if count == 0:
            self.log.info("신청 버튼 없음 — 아직 접수 전이거나 페이지 구조가 다릅니다.")
            return False

        # 마감되지 않은 버튼 클릭
        clicked = False
        for i in range(count):
            btn = btns.nth(i)
            text = (await btn.text_content() or "").strip()
            if any(kw in text for kw in ["마감", "종료", "접수종료", "마감됨"]):
                continue
            self.log.info(f"신청 버튼 클릭: '{text}'")
            await btn.click()
            await page.wait_for_load_state("domcontentloaded", timeout=self.bot_cfg["timeout"])
            clicked = True
            break

        if not clicked:
            self.log.info("모든 버튼이 마감 상태입니다.")
            return False

        # 로그인 페이지로 넘어갔는지 다시 확인
        if await is_redirected_to_login(page):
            self.log.warning("⚠️  신청 버튼 클릭 후 로그인 페이지로 이동했습니다.")
            return None

        # 폼 작성
        self.log.info("신청 폼 작성 중...")
        fields = scfg.get("form_fields", {})
        await fill_field(page, fields.get("name",   "name,userName,applicantName,memName"), self.applicant.get("name", ""))
        await fill_field(page, fields.get("phone",  "phone,tel,mobile,hp,cellphone,handphone"), self.applicant.get("phone", ""))
        await fill_field(page, fields.get("email",  "email,mail,userEmail,eMail"), self.applicant.get("email", ""))
        await fill_field(page, fields.get("school", "school,highSchool,schoolName,scNm"), self.applicant.get("school", ""))
        await fill_field(page, fields.get("grade",  "grade,schoolGrade,hakNyun"), self.applicant.get("grade", ""))
        await fill_field(page, fields.get("region", "region,area,sido,siDo"), self.applicant.get("region", ""))

        # 원하는 설명회 날짜 선택
        await self._select_session_date(page)

        # 개인정보 동의 체크박스 모두 체크
        agree = page.locator(
            'input[type="checkbox"][name*="agree"],'
            'input[type="checkbox"][id*="agree"],'
            'input[type="checkbox"][name*="privacy"],'
            'input[type="checkbox"][name*="personal"],'
            'input[type="checkbox"][name*="chk"]'
        )
        for i in range(await agree.count()):
            if not await agree.nth(i).is_checked():
                await agree.nth(i).check()

        # 제출
        submitted = await click_first(
            page,
            'button[type="submit"], input[type="submit"],'
            'button:has-text("신청"), button:has-text("접수"),'
            'a:has-text("신청하기"), a:has-text("신청완료"), a:has-text("확인")',
        )
        if not submitted:
            self.log.warning("제출 버튼을 찾지 못했습니다. 브라우저를 직접 확인하세요.")
            return False

        await page.wait_for_load_state("networkidle", timeout=self.bot_cfg["timeout"])

        body = (await page.inner_text("body")).replace("\n", " ")
        if any(kw in body for kw in ["신청이 완료", "접수되었습니다", "완료되었습니다", "신청완료", "감사합니다"]):
            self.log.info("★★★ 신청 성공! ★★★")
            self._record()
            return True

        self.log.warning("제출했지만 성공 메시지를 찾지 못했습니다. 브라우저를 확인하세요.")
        return False

    async def try_login(self, page: Page) -> bool:
        """설정에 로그인 정보가 있으면 로그인 시도."""
        lcfg = self.ucfg.get("login", {})
        login_id = lcfg.get("id", "")
        login_pw = lcfg.get("password", "")
        login_url = lcfg.get("url", "")

        if not login_url or not login_id or login_id in ("YONSEI_ID", "KOREA_ID", "KHU_ID"):
            return False

        self.log.info(f"로그인 시도: {login_url}")
        await page.goto(login_url, wait_until="domcontentloaded", timeout=self.bot_cfg["timeout"])

        id_loc = page.locator(lcfg.get("id_selector", 'input[type="text"]'))
        pw_loc = page.locator(lcfg.get("pw_selector", 'input[type="password"]'))

        if await id_loc.count() == 0 or await pw_loc.count() == 0:
            self.log.error("로그인 폼을 찾지 못했습니다.")
            return False

        await id_loc.first.fill(login_id)
        await pw_loc.first.fill(login_pw)
        await click_first(page, lcfg.get("submit_selector", 'button[type="submit"]'))
        await page.wait_for_load_state("domcontentloaded", timeout=self.bot_cfg["timeout"])
        self.log.info("로그인 완료")
        return True

    async def _select_session_date(self, page: Page):
        """설명회 날짜 선택 (라디오버튼 / 드롭다운 / 링크 모두 지원)."""
        if not self.session_date:
            return

        date_obj = datetime.strptime(self.session_date, "%Y-%m-%d")
        # 폼에서 나타날 수 있는 다양한 날짜 표현
        candidates = [
            self.session_date,                          # 2026-04-18
            date_obj.strftime("%Y.%m.%d"),              # 2026.04.18
            date_obj.strftime("%-m월 %-d일"),            # 4월 18일
            date_obj.strftime("%m/%d"),                  # 04/18
            date_obj.strftime("%-m/%-d"),                # 4/18
        ]
        if self.session_date_text:
            candidates += [t.strip() for t in self.session_date_text.split(",")]

        # 1) 라디오/체크박스에서 날짜 값 탐색
        for cand in candidates:
            radio = page.locator(
                f'input[type="radio"][value*="{cand}"],'
                f'input[type="checkbox"][value*="{cand}"]'
            )
            if await radio.count() > 0:
                await radio.first.check()
                self.log.info(f"설명회 날짜 선택 (라디오): {cand}")
                return

        # 2) select 드롭다운에서 날짜 옵션 탐색
        selects = page.locator("select")
        for i in range(await selects.count()):
            sel = selects.nth(i)
            opts = await sel.evaluate("el => Array.from(el.options).map(o => ({v:o.value, t:o.text}))")
            for opt in opts:
                if any(c in opt["v"] or c in opt["t"] for c in candidates):
                    try:
                        await sel.select_option(value=opt["v"])
                    except Exception:
                        await sel.select_option(label=opt["t"])
                    self.log.info(f"설명회 날짜 선택 (드롭다운): {opt['t']}")
                    return

        # 3) 날짜 텍스트가 포함된 링크/버튼 클릭
        for cand in candidates:
            loc = page.locator(f"a:has-text('{cand}'), button:has-text('{cand}'), label:has-text('{cand}')")
            if await loc.count() > 0:
                await loc.first.click()
                self.log.info(f"설명회 날짜 선택 (클릭): {cand}")
                return

        self.log.warning(f"설명회 날짜({self.session_date}) 선택 항목을 찾지 못했습니다. 브라우저에서 직접 선택하세요.")

    def _record(self):
        with open("applied_sessions.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | 신청완료 | {self.name} | {self.target_dt:%Y-%m-%d %H:%M}\n")

    # ── 스케줄 실행 ──────────────────────────────
    async def run_scheduled(self, browser: Browser):
        early = self.bot_cfg["early_start_minutes"]
        wake_dt = self.target_dt - timedelta(minutes=early)
        now = datetime.now()

        if now > self.target_dt + timedelta(hours=2):
            self.log.info(f"신청 접수 시각({self.target_dt:%m/%d %H:%M})이 이미 지났습니다.")
            return

        if now < wake_dt:
            wait_sec = (wake_dt - now).total_seconds()
            h, m = divmod(int(wait_sec), 3600)
            m = m // 60
            self.log.info(
                f"대기 중... 목표: {self.target_dt:%Y-%m-%d %H:%M} "
                f"/ 브라우저 오픈 예정: {wake_dt:%H:%M} ({h}시간 {m}분 후)"
            )
            await asyncio.sleep(wait_sec)

        # 브라우저 컨텍스트 생성
        ctx: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()
        self.log.info(f"브라우저 열림 ({self.name})")

        # 목표 시각까지 대기
        now = datetime.now()
        if now < self.target_dt:
            remain = (self.target_dt - now).total_seconds()
            self.log.info(f"신청 시작까지 {remain:.0f}초 대기...")
            await asyncio.sleep(remain)

        # 신청 루프
        max_retries = self.bot_cfg["max_retries"]
        interval = self.bot_cfg["retry_interval"]
        login_attempted = False
        success = False

        for attempt in range(1, max_retries + 1):
            self.log.info(f"신청 시도 {attempt}/{max_retries}")
            try:
                result = await self.try_apply(page)

                if result is True:
                    success = True
                    break

                elif result is None:
                    # 로그인 필요 → 한 번만 시도
                    if not login_attempted:
                        login_attempted = True
                        logged = await self.try_login(page)
                        if not logged:
                            self.log.error(
                                f"\n{'='*50}\n"
                                f"  [{self.name}] 로그인이 필요합니다!\n"
                                f"  config.yaml 에 로그인 정보를 입력하거나\n"
                                f"  열린 브라우저에서 직접 로그인해 주세요.\n"
                                f"{'='*50}"
                            )
                            # 브라우저는 열어두고 사용자가 직접 진행할 수 있게 대기
                            await asyncio.sleep(interval)
                    else:
                        await asyncio.sleep(interval)

                else:
                    # False: 신청 버튼 없음 → 대기 후 재시도
                    await asyncio.sleep(interval)

            except PwTimeout:
                self.log.warning("타임아웃 — 재시도")
                await asyncio.sleep(interval)
            except Exception as e:
                self.log.error(f"오류: {e}")
                await asyncio.sleep(interval)

        if not success:
            self.log.error(f"신청 실패 — {max_retries}회 시도 완료")

        # 브라우저 5분 유지 (결과 확인용)
        self.log.info("브라우저를 5분간 열어둡니다. 결과를 직접 확인하세요.")
        await asyncio.sleep(300)
        await ctx.close()


# ─────────────────────────────────────
# 메인
# ─────────────────────────────────────
async def main():
    cfg = load_config()

    bots = [
        UniversityBot(k, v, cfg)
        for k, v in cfg["universities"].items()
        if v.get("enabled", True)
    ]

    root_log.info("=" * 55)
    root_log.info(" 대학 입학설명회 자동신청 봇 시작")
    for b in bots:
        root_log.info(f"  [{b.name}] 접수 시작: {b.target_dt:%Y-%m-%d %H:%M} → 신청 설명회: {b.session_date}")
    root_log.info("=" * 55)
    root_log.info("종료하려면 Ctrl+C")
    root_log.info("")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=cfg["bot"]["headless"],
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        await asyncio.gather(*(b.run_scheduled(browser) for b in bots))
        await browser.close()

    root_log.info("모든 대학 처리 완료.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        root_log.info("봇 종료 (Ctrl+C)")
