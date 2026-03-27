"""
연세대학교 입학설명회 자동신청 봇
- Playwright 기반 실제 브라우저 자동화
- config.yaml에서 로그인 정보 및 신청자 정보를 읽어옴

사용법:
  1. pip install -r requirements.txt
  2. playwright install chromium
  3. config.yaml 파일에 정보 입력
  4. python bot.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PwTimeout

# ─────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("[오류] config.yaml 파일이 없습니다. config.yaml을 먼저 작성해주세요.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ─────────────────────────────────────────────
# 로거 설정
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("admission-bot")

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
BASE_URL = "https://admission.yonsei.ac.kr/seoul/admission/html"
MAIN_URL = f"{BASE_URL}/main/main.asp"

# 설명회 관련 후보 URL (실제 사이트 구조에 따라 자동 탐색)
SEMINAR_URL_CANDIDATES = [
    f"{BASE_URL}/info/seminar.asp",
    f"{BASE_URL}/info/info_s01.asp",
    f"{BASE_URL}/event/seminar.asp",
    f"{BASE_URL}/counsel/seminar.asp",
    f"{BASE_URL}/schedule/seminar.asp",
]

# ─────────────────────────────────────────────
# 로그인
# ─────────────────────────────────────────────
async def login(page: Page, cfg: dict) -> bool:
    """연세대 입학처 로그인. 성공 시 True 반환."""
    login_id = cfg["login"]["id"]
    login_pw = cfg["login"]["password"]

    if login_id == "YOUR_ID":
        log.error("config.yaml에 로그인 정보를 입력해주세요 (login.id, login.password)")
        return False

    log.info("로그인 시도 중...")

    # 메인 페이지에서 로그인 링크 찾기
    await page.goto(MAIN_URL, wait_until="domcontentloaded",
                    timeout=cfg["bot"]["timeout"])

    # 로그인 버튼/링크 클릭
    try:
        login_link = page.locator("a:has-text('로그인'), a:has-text('LOGIN')")
        if await login_link.count() > 0:
            await login_link.first.click()
            await page.wait_for_load_state("domcontentloaded")
    except PwTimeout:
        pass

    # ID/PW 입력 폼 탐색 (여러 가능한 셀렉터 시도)
    id_selectors = [
        'input[name="userId"]', 'input[name="id"]', 'input[name="memId"]',
        'input[id="userId"]', 'input[id="id"]', 'input[type="text"]',
    ]
    pw_selectors = [
        'input[name="userPw"]', 'input[name="pw"]', 'input[name="passwd"]',
        'input[name="password"]', 'input[id="userPw"]', 'input[type="password"]',
    ]

    id_field = await _find_input(page, id_selectors)
    pw_field = await _find_input(page, pw_selectors)

    if not id_field or not pw_field:
        log.warning("로그인 폼을 찾지 못했습니다. headless=false 로 설정 후 직접 확인하세요.")
        return False

    await id_field.fill(login_id)
    await pw_field.fill(login_pw)

    # 제출 버튼 클릭
    submit_selectors = [
        'button[type="submit"]', 'input[type="submit"]',
        'a:has-text("로그인")', 'button:has-text("로그인")',
    ]
    submitted = False
    for sel in submit_selectors:
        loc = page.locator(sel)
        if await loc.count() > 0:
            await loc.first.click()
            submitted = True
            break

    if not submitted:
        log.warning("로그인 제출 버튼을 찾지 못했습니다.")
        return False

    await page.wait_for_load_state("networkidle", timeout=cfg["bot"]["timeout"])

    # 로그인 성공 여부 확인 (로그아웃 링크 존재 여부)
    logout = page.locator("a:has-text('로그아웃'), a:has-text('LOGOUT')")
    if await logout.count() > 0:
        log.info("로그인 성공!")
        return True
    else:
        log.warning("로그인 후 상태를 확인할 수 없습니다. 계속 진행합니다.")
        return True  # 일단 진행

# ─────────────────────────────────────────────
# 설명회 페이지 탐색
# ─────────────────────────────────────────────
async def find_seminar_page(page: Page, cfg: dict) -> str | None:
    """설명회 목록 페이지 URL을 자동으로 탐색. 없으면 None."""
    log.info("설명회 페이지 탐색 중...")

    # 1) 메인 메뉴에서 설명회 링크 탐색
    await page.goto(MAIN_URL, wait_until="domcontentloaded",
                    timeout=cfg["bot"]["timeout"])

    seminar_link = page.locator(
        "a:has-text('설명회'), a:has-text('입학설명회'), a:has-text('대입설명회')"
    )
    if await seminar_link.count() > 0:
        href = await seminar_link.first.get_attribute("href")
        if href:
            url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
            log.info(f"설명회 페이지 발견 (메뉴): {url}")
            return url

    # 2) 후보 URL 직접 접근 시도
    for url in SEMINAR_URL_CANDIDATES:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded",
                                   timeout=cfg["bot"]["timeout"])
            if resp and resp.status == 200:
                # 설명회 관련 키워드가 페이지에 있는지 확인
                content = await page.content()
                if any(kw in content for kw in ["설명회", "입학상담", "접수"]):
                    log.info(f"설명회 페이지 발견 (직접 접근): {url}")
                    return url
        except Exception:
            continue

    log.warning("설명회 페이지를 자동으로 찾지 못했습니다.")
    log.warning("브라우저에서 직접 설명회 페이지를 열고 URL을 config.yaml > seminar_url 에 추가하세요.")
    return None

# ─────────────────────────────────────────────
# 신청 가능한 설명회 목록 조회
# ─────────────────────────────────────────────
async def get_open_sessions(page: Page, seminar_url: str, cfg: dict) -> list[dict]:
    """신청 가능한 설명회 목록 반환. 각 항목은 {title, url, element} 딕셔너리."""
    await page.goto(seminar_url, wait_until="domcontentloaded",
                    timeout=cfg["bot"]["timeout"])

    open_sessions = []

    # '신청', '접수', '참가신청' 텍스트가 있는 링크/버튼 탐색
    candidates = page.locator(
        "a:has-text('신청'), a:has-text('접수'), a:has-text('참가신청'), "
        "button:has-text('신청'), button:has-text('접수')"
    )
    count = await candidates.count()

    for i in range(count):
        elem = candidates.nth(i)
        text = (await elem.text_content() or "").strip()
        href = await elem.get_attribute("href") or ""

        # 마감/종료 상태 제외
        if any(kw in text for kw in ["마감", "종료", "마감됨"]):
            continue

        # 행(row) 또는 상위 컨테이너에서 제목 추출
        title = await _extract_row_title(elem)

        # 키워드 필터 적용
        keywords = [k for k in cfg.get("target_keywords", [""]) if k]
        if keywords and not any(kw in title for kw in keywords):
            continue

        url = href if href.startswith("http") else seminar_url.rsplit("/", 1)[0] + "/" + href.lstrip("/")

        open_sessions.append({"title": title, "url": url, "elem": elem})
        log.info(f"신청 가능 설명회 발견: {title}")

    return open_sessions

# ─────────────────────────────────────────────
# 설명회 신청 실행
# ─────────────────────────────────────────────
async def apply_session(page: Page, session: dict, cfg: dict) -> bool:
    """설명회 신청 폼 제출. 성공 시 True."""
    title = session["title"]
    log.info(f"[신청 시작] {title}")

    # 신청 링크 클릭 또는 URL 이동
    try:
        await session["elem"].click()
        await page.wait_for_load_state("domcontentloaded", timeout=cfg["bot"]["timeout"])
    except Exception:
        if session["url"]:
            await page.goto(session["url"], wait_until="domcontentloaded",
                            timeout=cfg["bot"]["timeout"])

    info = cfg["applicant"]

    # 폼 필드 매핑 (이름/셀렉터 우선순위 순)
    field_map = [
        (["name", "userName", "mem_name", "applicantName"], info.get("name", "")),
        (["phone", "tel", "mobile", "cellphone", "hp"],     info.get("phone", "")),
        (["email", "mail", "userEmail"],                    info.get("email", "")),
        (["school", "highSchool", "schoolName"],            info.get("school", "")),
        (["grade", "schoolGrade"],                          info.get("grade", "")),
        (["region", "area", "sido"],                        info.get("region", "")),
    ]

    for name_candidates, value in field_map:
        if not value:
            continue
        for name in name_candidates:
            sel = f'input[name="{name}"], select[name="{name}"], textarea[name="{name}"]'
            loc = page.locator(sel)
            if await loc.count() > 0:
                tag = await loc.first.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    await loc.first.select_option(label=str(value))
                else:
                    await loc.first.fill(str(value))
                break

    # 개인정보 동의 체크박스 자동 체크
    agree_boxes = page.locator(
        'input[type="checkbox"][name*="agree"], '
        'input[type="checkbox"][id*="agree"], '
        'input[type="checkbox"][name*="privacy"]'
    )
    for i in range(await agree_boxes.count()):
        if not await agree_boxes.nth(i).is_checked():
            await agree_boxes.nth(i).check()

    # 제출 버튼 클릭
    submit = page.locator(
        'button[type="submit"], input[type="submit"], '
        'button:has-text("신청"), button:has-text("접수"), a:has-text("신청하기")'
    )
    if await submit.count() == 0:
        log.error("제출 버튼을 찾지 못했습니다.")
        return False

    await submit.first.click()
    await page.wait_for_load_state("networkidle", timeout=cfg["bot"]["timeout"])

    # 성공 여부 확인 (완료/감사 메시지)
    page_text = await page.inner_text("body")
    success_keywords = ["신청이 완료", "접수되었습니다", "완료되었습니다", "감사합니다"]
    if any(kw in page_text for kw in success_keywords):
        log.info(f"[신청 완료] {title}")
        _write_success_log(title)
        return True
    else:
        log.warning(f"[신청 결과 불명] {title} — 브라우저 화면을 직접 확인하세요.")
        return False

# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────
async def _find_input(page: Page, selectors: list[str]):
    for sel in selectors:
        loc = page.locator(sel)
        if await loc.count() > 0:
            return loc.first
    return None

async def _extract_row_title(elem) -> str:
    """신청 버튼 주변의 행에서 제목 텍스트 추출."""
    try:
        row_text = await elem.evaluate("""el => {
            let node = el;
            for (let i = 0; i < 4; i++) {
                node = node.parentElement;
                if (!node) break;
                if (node.tagName === 'TR' || node.classList.contains('list-item')) {
                    return node.innerText.trim().split('\\n')[0];
                }
            }
            return el.innerText.trim();
        }""")
        return row_text[:60] if row_text else "제목 불명"
    except Exception:
        return "제목 불명"

def _write_success_log(title: str):
    with open("applied_sessions.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 신청완료 | {title}\n")

# ─────────────────────────────────────────────
# 메인 루프
# ─────────────────────────────────────────────
async def main():
    cfg = load_config()
    interval = cfg["bot"]["check_interval"]
    headless = cfg["bot"]["headless"]

    log.info("=" * 50)
    log.info("연세대학교 입학설명회 자동신청 봇 시작")
    log.info(f"확인 주기: {interval}초 | headless: {headless}")
    log.info("=" * 50)

    applied_titles: set[str] = set()  # 이미 신청한 설명회 중복 방지

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()

        # 설명회 페이지 URL (config에 직접 지정 가능)
        seminar_url: str | None = cfg.get("seminar_url")

        # 최초 로그인
        logged_in = await login(page, cfg)
        if not logged_in:
            log.error("로그인 실패. config.yaml을 확인하세요.")
            await browser.close()
            return

        # 설명회 페이지 탐색 (config에 없으면 자동 탐색)
        if not seminar_url:
            seminar_url = await find_seminar_page(page, cfg)

        if not seminar_url:
            log.error("설명회 페이지를 찾지 못했습니다.")
            log.error("config.yaml에 seminar_url: 'https://...' 를 직접 추가하세요.")
            await browser.close()
            return

        log.info(f"모니터링 대상: {seminar_url}")

        # 반복 체크 루프
        while True:
            try:
                log.info(f"설명회 확인 중... ({datetime.now().strftime('%H:%M:%S')})")
                sessions = await get_open_sessions(page, seminar_url, cfg)

                for session in sessions:
                    if session["title"] in applied_titles:
                        continue  # 이미 신청 완료

                    success = await apply_session(page, session, cfg)
                    if success:
                        applied_titles.add(session["title"])

                if not sessions:
                    log.info("현재 신청 가능한 설명회 없음. 다음 확인까지 대기...")

            except PwTimeout:
                log.warning("페이지 로딩 타임아웃. 재시도 예정...")
            except Exception as e:
                log.error(f"오류 발생: {e}")
                # 세션 만료 가능성 → 재로그인
                try:
                    await login(page, cfg)
                except Exception:
                    pass

            await asyncio.sleep(interval)

# ─────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("봇 종료 (Ctrl+C)")
