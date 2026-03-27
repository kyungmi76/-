"""
대학 입학설명회 자동신청 봇
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
지원 대학:
  - 연세대학교  2026-04-18 10:00
  - 고려대학교  2026-04-25 10:00
  - 경희대학교  2026-05-30 13:00

사용법:
  1. pip install -r requirements.txt
  2. playwright install chromium
  3. config.yaml 에 로그인 정보·신청자 정보 입력
  4. python bot.py           ← 자동 스케줄 실행
     python bot.py --setup   ← 셀렉터 확인용 (브라우저만 열기)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import logging
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PwTimeout,
)

# ─────────────────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────────────────
CFG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    if not CFG_PATH.exists():
        print("[오류] config.yaml 파일이 없습니다.")
        sys.exit(1)
    with open(CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────
# 로거
# ─────────────────────────────────────────────────────────
def make_logger(name: str) -> logging.Logger:
    fmt = f"%(asctime)s [{name}] %(message)s"
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        fh = logging.FileHandler("bot.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(sh)
        logger.addHandler(fh)
    return logger


root_log = make_logger("BOT")


# ─────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────
async def find_and_fill(page: Page, name_candidates: str, value: str):
    """콤마로 구분된 name 후보 중 존재하는 필드에 value 입력."""
    if not value:
        return
    for name in name_candidates.split(","):
        name = name.strip()
        sel = (
            f'input[name="{name}"], select[name="{name}"], textarea[name="{name}"],'
            f'input[id="{name}"], select[id="{name}"]'
        )
        loc = page.locator(sel)
        if await loc.count() > 0:
            tag = await loc.first.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                try:
                    await loc.first.select_option(label=value)
                except Exception:
                    await loc.first.select_option(value=value)
            else:
                await loc.first.fill(value)
            return


async def click_first(page: Page, selector: str) -> bool:
    """셀렉터 중 첫 번째 존재하는 요소 클릭. 성공 시 True."""
    loc = page.locator(selector)
    if await loc.count() > 0:
        await loc.first.click()
        return True
    return False


async def wait_for_selector_any(page: Page, selector: str, timeout: int = 5000) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return True
    except PwTimeout:
        return False


# ─────────────────────────────────────────────────────────
# 대학별 신청 클래스
# ─────────────────────────────────────────────────────────
class UniversityBot:
    def __init__(self, key: str, ucfg: dict, cfg: dict):
        self.key = key
        self.ucfg = ucfg          # 대학별 설정
        self.cfg = cfg            # 전체 설정
        self.applicant = cfg["applicant"]
        self.bot_cfg = cfg["bot"]
        self.log = make_logger(ucfg["name"])
        self.target_dt: datetime = datetime.strptime(
            ucfg["target_datetime"], "%Y-%m-%d %H:%M:%S"
        )

    # ── 로그인 ──────────────────────────────────────────
    async def login(self, page: Page) -> bool:
        lcfg = self.ucfg["login"]
        login_id = lcfg["id"]
        login_pw = lcfg["password"]
        login_url = lcfg.get("url", "")

        if not login_url or login_id in ("YONSEI_ID", "KOREA_ID", "KHU_ID"):
            self.log.warning(f"config.yaml에 로그인 정보를 입력하세요 (login.id / login.password)")
            return False

        self.log.info(f"로그인 페이지: {login_url}")
        await page.goto(login_url, wait_until="domcontentloaded",
                        timeout=self.bot_cfg["timeout"])

        # ID 입력
        id_loc = page.locator(lcfg["id_selector"])
        if await id_loc.count() == 0:
            self.log.error("ID 입력 필드를 찾지 못했습니다. config.yaml > id_selector 확인")
            return False
        await id_loc.first.fill(login_id)

        # PW 입력
        pw_loc = page.locator(lcfg["pw_selector"])
        if await pw_loc.count() == 0:
            self.log.error("PW 입력 필드를 찾지 못했습니다. config.yaml > pw_selector 확인")
            return False
        await pw_loc.first.fill(login_pw)

        # 로그인 버튼 클릭
        if not await click_first(page, lcfg["submit_selector"]):
            self.log.error("로그인 버튼을 찾지 못했습니다.")
            return False

        await page.wait_for_load_state("domcontentloaded",
                                       timeout=self.bot_cfg["timeout"])

        # 성공 여부 확인
        success = await wait_for_selector_any(page, lcfg["success_check"], 5000)
        if success:
            self.log.info("로그인 성공")
        else:
            self.log.warning("로그인 성공 확인 불가 (계속 진행)")
        return True

    # ── 설명회 신청 ─────────────────────────────────────
    async def apply(self, page: Page) -> bool:
        scfg = self.ucfg["seminar"]
        seminar_url = scfg["url"]

        self.log.info(f"설명회 페이지 이동: {seminar_url}")
        await page.goto(seminar_url, wait_until="domcontentloaded",
                        timeout=self.bot_cfg["timeout"])

        # 신청 버튼 탐색
        apply_btn = page.locator(scfg["apply_btn_selector"])
        count = await apply_btn.count()

        if count == 0:
            self.log.info("신청 버튼 없음 (아직 신청 기간 아님)")
            return False

        # 마감/종료 상태인 버튼 제외 후 첫 번째 클릭
        clicked = False
        for i in range(count):
            btn = apply_btn.nth(i)
            text = (await btn.text_content() or "").strip()
            if any(kw in text for kw in ["마감", "종료", "마감됨", "접수종료"]):
                continue
            self.log.info(f"신청 버튼 클릭: '{text}'")
            await btn.click()
            await page.wait_for_load_state("domcontentloaded",
                                           timeout=self.bot_cfg["timeout"])
            clicked = True
            break

        if not clicked:
            self.log.info("신청 가능한 버튼 없음 (모두 마감)")
            return False

        # 폼 작성
        fields = scfg.get("form_fields", {})
        await find_and_fill(page, fields.get("name", "name"),   self.applicant.get("name", ""))
        await find_and_fill(page, fields.get("phone", "phone"), self.applicant.get("phone", ""))
        await find_and_fill(page, fields.get("email", "email"), self.applicant.get("email", ""))
        await find_and_fill(page, fields.get("school", "school"), self.applicant.get("school", ""))
        await find_and_fill(page, fields.get("grade", "grade"), self.applicant.get("grade", ""))
        self.log.info("신청 폼 작성 완료")

        # 개인정보 동의 체크
        agree = page.locator(
            'input[type="checkbox"][name*="agree"],'
            'input[type="checkbox"][id*="agree"],'
            'input[type="checkbox"][name*="privacy"],'
            'input[type="checkbox"][name*="personal"]'
        )
        for i in range(await agree.count()):
            if not await agree.nth(i).is_checked():
                await agree.nth(i).check()

        # 제출
        submitted = await click_first(
            page,
            'button[type="submit"], input[type="submit"],'
            'button:has-text("신청"), button:has-text("접수"),'
            'a:has-text("신청하기"), a:has-text("신청완료")',
        )
        if not submitted:
            self.log.error("제출 버튼을 찾지 못했습니다.")
            return False

        await page.wait_for_load_state("networkidle",
                                       timeout=self.bot_cfg["timeout"])

        # 결과 확인
        body = (await page.inner_text("body")).replace("\n", " ")
        ok_keywords = ["신청이 완료", "접수되었습니다", "완료되었습니다", "감사합니다", "신청완료"]
        if any(kw in body for kw in ok_keywords):
            self.log.info("★ 신청 성공!")
            self._record_success()
            return True
        else:
            self.log.warning("제출 후 결과를 확인할 수 없습니다. 브라우저를 직접 확인하세요.")
            return False

    def _record_success(self):
        with open("applied_sessions.log", "a", encoding="utf-8") as f:
            f.write(
                f"{datetime.now():%Y-%m-%d %H:%M:%S} | 신청완료 | "
                f"{self.ucfg['name']} | {self.target_dt:%Y-%m-%d %H:%M}\n"
            )

    # ── 스케줄 실행 ─────────────────────────────────────
    async def run_scheduled(self, browser: Browser):
        """목표 시각이 될 때까지 대기 후 로그인 → 반복 신청 시도."""
        early = self.bot_cfg["early_start_minutes"]
        wake_dt = self.target_dt - timedelta(minutes=early)
        now = datetime.now()

        # 이미 지난 날짜
        if now > self.target_dt + timedelta(hours=1):
            self.log.info(f"신청 시각({self.target_dt:%m/%d %H:%M})이 이미 지났습니다. 건너뜁니다.")
            return

        # 대기
        if now < wake_dt:
            wait_sec = (wake_dt - now).total_seconds()
            self.log.info(
                f"신청 시작: {self.target_dt:%Y-%m-%d %H:%M} — "
                f"{early}분 전({wake_dt:%H:%M})에 브라우저 시작 예정 "
                f"({wait_sec/3600:.1f}시간 후)"
            )
            await asyncio.sleep(wait_sec)

        # 브라우저 오픈 및 로그인
        ctx: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()

        self.log.info("브라우저 열림 — 로그인 중...")
        logged_in = await self.login(page)
        if not logged_in:
            self.log.error("로그인 실패. config.yaml의 로그인 정보를 확인하세요.")
            await ctx.close()
            return

        # 목표 시각까지 남은 대기
        now = datetime.now()
        if now < self.target_dt:
            remain = (self.target_dt - now).total_seconds()
            self.log.info(f"로그인 완료. 신청 시작까지 {remain:.0f}초 대기...")
            await asyncio.sleep(remain)

        # 신청 루프
        max_retries = self.bot_cfg["max_retries"]
        interval = self.bot_cfg["retry_interval"]
        success = False

        for attempt in range(1, max_retries + 1):
            self.log.info(f"신청 시도 {attempt}/{max_retries}")
            try:
                success = await self.apply(page)
                if success:
                    break
            except PwTimeout:
                self.log.warning("타임아웃 — 재시도")
            except Exception as e:
                self.log.error(f"오류: {e} — 재시도")
                try:
                    await self.login(page)
                except Exception:
                    pass

            if attempt < max_retries:
                await asyncio.sleep(interval)

        if not success:
            self.log.error(f"신청 실패 — {max_retries}회 시도 후 포기")

        # 브라우저는 결과 확인할 수 있도록 유지 (headless=false 시)
        if self.bot_cfg["headless"]:
            await ctx.close()
        else:
            self.log.info("브라우저를 열어둡니다. 결과를 직접 확인하세요. 종료하려면 Ctrl+C")
            await asyncio.sleep(300)  # 5분 유지
            await ctx.close()


# ─────────────────────────────────────────────────────────
# 셀렉터 확인 모드 (--setup)
# ─────────────────────────────────────────────────────────
async def setup_mode(cfg: dict):
    """각 대학 페이지를 순서대로 열어서 사용자가 셀렉터를 직접 확인할 수 있게 함."""
    root_log.info("=== 셀렉터 확인 모드 (--setup) ===")
    root_log.info("각 대학 사이트를 순서대로 열겠습니다. 개발자 도구(F12)로 셀렉터를 확인하세요.")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="ko-KR")
        page = await ctx.new_page()

        for key, ucfg in cfg["universities"].items():
            if not ucfg.get("enabled", True):
                continue
            name = ucfg["name"]
            bot = UniversityBot(key, ucfg, cfg)

            root_log.info(f"\n[{name}] 로그인 페이지 열기...")
            login_url = ucfg["login"].get("url", "")
            if login_url:
                await page.goto(login_url, wait_until="domcontentloaded")
            else:
                seminar_url = ucfg["seminar"]["url"]
                await page.goto(seminar_url, wait_until="domcontentloaded")

            input(f"  [{name}] 셀렉터 확인 후 Enter 키를 누르세요...")

            root_log.info(f"[{name}] 설명회 페이지 열기...")
            await page.goto(ucfg["seminar"]["url"], wait_until="domcontentloaded")
            input(f"  [{name}] 설명회 페이지 확인 후 Enter 키를 누르세요...")

        await browser.close()
    root_log.info("셀렉터 확인 완료. config.yaml을 업데이트 후 python bot.py 를 실행하세요.")


# ─────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────
async def main(setup: bool = False):
    cfg = load_config()

    if setup:
        await setup_mode(cfg)
        return

    # 활성화된 대학만 수집
    tasks = []
    for key, ucfg in cfg["universities"].items():
        if not ucfg.get("enabled", True):
            continue
        bot = UniversityBot(key, ucfg, cfg)
        target_str = bot.target_dt.strftime("%Y-%m-%d %H:%M")
        root_log.info(f"  [{ucfg['name']}] 목표 시각: {target_str}")
        tasks.append(bot)

    if not tasks:
        root_log.error("활성화된 대학이 없습니다. config.yaml > enabled: true 확인")
        return

    root_log.info("=" * 55)
    root_log.info(" 대학 입학설명회 자동신청 봇 시작")
    root_log.info(f" 총 {len(tasks)}개 대학 모니터링")
    root_log.info("=" * 55)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=cfg["bot"]["headless"],
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )

        # 각 대학을 독립적으로 병렬 실행
        await asyncio.gather(
            *(bot.run_scheduled(browser) for bot in tasks)
        )

        await browser.close()

    root_log.info("모든 대학 신청 완료.")


# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="대학 입학설명회 자동신청 봇")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="셀렉터 확인 모드: 각 대학 페이지를 열어 셀렉터를 직접 확인",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(setup=args.setup))
    except KeyboardInterrupt:
        root_log.info("봇 종료 (Ctrl+C)")
